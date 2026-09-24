"""Tailored resumes for matched postings. Runs on GitHub Actions (resume.yml).

Same split as the rest of jobbot: everything deterministic lives here, and the
model only writes resume.json. The resume workflow drives it:

    python -m jobbot.tailor next --limit 3        # prepare folders for the next postings
      (Claude writes each folder's resume.json from data/profile.json)
    python -m jobbot.tailor build "<folder>"      # verify.py -> .tex -> verify_resume.py
    python -m jobbot.tailor skip <uid> "<reason>"
    python -m jobbot.tailor publish               # one GitHub issue per new resume
    python -m jobbot.tailor enqueue-backlog --tiers 1
    python -m jobbot.tailor status

Where things live:
  data/pending.json    postings waiting for a resume. Written ONLY by watch.py,
                       so the two workflows never edit the same file.
  data/tailored.json   uid -> status (in_progress | resume_ready | skipped |
                       build_failed | already_applied), folder, issue number.
                       Written only by this module.
  resumes/<Company>/<Role>/   JD.md, resume.json, the .tex/.pdf, build.json
  pipeline/            profile.yaml, PIPELINE.md, resume.cls, verify_resume.py,
                       prior_applications.json - synced from OneDrive by
                       jobbot.sync_pipeline.

`build` is the only way a resume reaches PASS. It runs jobbot's fabrication
check on the bullets, then renders the .tex itself and runs verify_resume.py
(compile, one page, layout, Northwind first, ...). The text that was verified
is exactly the text on the page; the model never writes LaTeX.

Nothing here applies, and nothing records an application.

resume.json:
{
  "uid": "...", "company": "...", "role": "...",
  "term": "winter_2027" | "summer_2027" | "fall_2026",     # key of grad_by_term
  "rhythm": 0.85,                                           # optional, 0.6-1.1
  "sections": [
    {"entry_id": "northwind", "bullets": [
        {"text": "Shipped **Python** LLM agents ...", "source_ids": ["northwind.scope"]}]},
    {"entry_id": "rfp_platform", "name": "Document Q&A Platform",   # projects only:
     "stack": "Go, Python, PostgreSQL", "bullets": [...]}           # name/stack optional
  ],
  "skills": {"Languages": "...", "Frameworks": "...", "Cloud/DevOps": "...", "Databases": "..."},
  "note_to_him": "...",          # optional: one or two sentences for him - what you
                                 # were unsure about, what you chose, or a question.
                                 # He reads it on the job and can reply there.
  "coined": [                    # every figure you put on the page that his facts
    {"source_id": "northwind.scope",   # do not already carry. He reads these before
     "number": "40% fewer escalations",  # he sends anything, so declare them all.
     "claim": "what the bullet says it measures",
     "why": "one line: why this is plausible at this scale"}
  ]
}
**double asterisks** mark bold. Write plain text otherwise; escaping is done here.
"""
import argparse, json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from . import match, sources, store, verify, watch

ROOT = Path(__file__).resolve().parent.parent
from . import paths
PIPE = paths.PIPELINE
OUT = Path(os.environ.get("JOBBOT_OUT") or ROOT / "resumes")
DATA = Path(store.DATA)
PROFILE_JSON = paths.DATA / "profile.json"
REPO = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("JOBBOT_REPO", "")
# Workflows live in the repo the run is in; his issues live with his things.
CODE_REPO = os.environ.get("GITHUB_REPOSITORY") or REPO
# Who an alert issue @mentions: the owner of the repo it is opened in.
GH_USER = os.environ.get("JOBBOT_GH_USER") or (REPO.split("/")[0] if REPO else "")
OWNER = GH_USER


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #

def _load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / (name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, DATA / name)


def _mark(uid, status, **extra):
    ledger = _load("tailored.json", {})
    ledger[uid] = {**ledger.get(uid, {}), "status": status,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}
    _save("tailored.json", ledger)


def approved_uids():
    """Jobs approved from the phone (approve.yml). Approved means applied."""
    p = DATA / "approvals.jsonl"
    if not p.exists():
        return set()
    return {json.loads(l)["uid"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}


def notified():
    """uid -> how the user was first told about the job ("alert" or "digest").

    Each job reaches him once: the first notification wins, and every later
    one (a digest after an alert, a resume issue after a digest) is silent.
    """
    return _load("notified.json", {})


def mark_notified(uids, via, **extra):
    n = notified()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for u in uids:
        n.setdefault(u, {"at": now, "via": via, **extra})
    _save("notified.json", n)


def alert_tiers():
    return set((watch.load_criteria().get("notify") or {}).get("alert_tiers", [1, 2]))


def load_profile(raw=False):
    """His facts: data/profile.json (rebuilt when pipeline/profile.yaml is
    newer), with what he changed in the app's Settings on top. `raw` is the
    file alone - the default the app shows."""
    src = PIPE / "profile.yaml"
    if src.exists() and (not PROFILE_JSON.exists() or
                         src.stat().st_mtime > PROFILE_JSON.stat().st_mtime):
        from . import build_profile
        build_profile.main(["--source", str(src), "--out", str(PROFILE_JSON)])
    profile = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
    if raw:
        return profile
    from . import settings
    return settings.apply_profile(profile)


# --------------------------------------------------------------------------- #
# names and prior applications
# --------------------------------------------------------------------------- #

def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _key(s):
    return _norm(s).replace(" ", "")


def safe_segment(s):
    """Same rule as resume_mcp._safe_segment, so folders line up with manual ones."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", (s or "").strip()).strip(". ")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"unusable name: {s!r}")
    return cleaned[:120]


def display_company(company, org):
    """Ashby/Lever often give the board slug as the company ("gecko-robotics")."""
    if company and _key(company) != _key(org):
        return company.strip()
    return " ".join(w.capitalize() for w in re.split(r"[-_\s]+", company or org) if w)


def prior_applications():
    path = PIPE / "prior_applications.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


SYNONYMS = {"swe": ["software", "engineer"], "sde": ["software", "developer"],
            "engineering": ["engineer"], "co": ["coop"], "op": [], "internship": ["intern"],
            "grads": ["grad"], "ml": ["machine", "learning"], "ai": ["ai"]}
NOISE = {"the", "and", "of", "for", "in", "at", "a", "i", "ii", "months", "month", "us", "usa"}
def role_tokens(*texts):
    out = set()
    for w in _norm(" ".join(texts)).split():
        for x in SYNONYMS.get(w, [w]):
            if x not in NOISE:
                out.add(x)
    return out


FILLER = {"software", "engineer", "developer", "development", "intern", "coop", "new", "grad",
          "student", "program", "role", "position"}
# A season or a year alone never identifies a role: "Summer Software Engineer
# Co-Op" must not match a DSP internship just because both say Summer.
WEAK = {"summer", "winter", "fall", "spring", "autumn", "2025", "2026", "2027", "2028", "term", "months"}
# Corporate tails that differ between a tracker row and a board's company name.
SUFFIX = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "group", "holdings",
          "canada", "usa", "us", "america", "solutions", "technologies", "labs", "the"}


def company_tokens(*names):
    out = set()
    for n in names:
        toks = [t for t in _norm(n).split() if t and t not in SUFFIX]
        if toks:
            out.add(" ".join(toks))
            out.add("".join(toks))
    return out


def same_company(a_names, b_name):
    """Token-level, never a bare substring: "Ada" once matched "DoorDash Canada".

    A longer name may extend a shorter one ("Motorola Solutions", "Duolingo
    University Recruiting"), so a prefix counts - but only from 6 characters,
    which is what keeps "Ada" out of "DoorDash" and "Meta" out of "Metabase".
    """
    a, b = company_tokens(*a_names), company_tokens(b_name)
    if a & b:
        return True
    joined = lambda s: sorted((x.replace(" ", "") for x in s), key=len)
    for x in joined(a):
        for y in joined(b):
            short, long = (x, y) if len(x) <= len(y) else (y, x)
            if len(short) >= 6 and long.startswith(short):
                return True
    return False


def already_applied(t, prior):
    """Posting id quoted in a manual JD.md, or the same company and a role whose
    distinguishing words all appear in this posting's title + location.

    Manual folder names are paraphrased ("Software Developer Intern Backend -
    Toronto Summer 2027" for "Software Developer Intern, Backend (Summer 2027)"
    in Toronto), so exact matching missed real duplicates; a loose overlap
    score then hid different seats (Web vs iOS, Toronto vs US). So: every
    non-filler word (team, city, season, year) must be present, and at least
    half of the filler words; a name made only of filler must match entirely.
    """
    have = role_tokens(t["title"], t.get("location") or "")
    for p in prior:
        if t.get("raw_id") and t["raw_id"] in p["ids"]:
            return True
        if not same_company((t["company"], t["org"]), p["company"]):
            continue
        want = role_tokens(p["role"])
        core, filler = want - FILLER, want & FILLER
        if not want:
            continue
        # Nothing but season/year left to tell the roles apart -> demand the
        # whole name, generic words included.
        if not core or not (core - WEAK):
            if want <= have:
                return True
            continue
        if core <= have and len(filler & have) * 2 >= len(filler):
            return True
    return False


def to_posting(t):
    from .model import Posting
    ts = lambda v: datetime.fromisoformat(v) if v else None
    return Posting(source=t["source"], org=t["org"], company=t["company"], title=t["title"],
                   location=t["location"], url=t["url"], apply_url=t["apply_url"],
                   posted_at=ts(t["posted_at"]), description=t["description"],
                   deadline=ts(t["deadline"]), raw_id=t["raw_id"])


def posting_dict(m):
    p = m.posting
    return {"uid": p.uid, "tier": m.tier, "reasons": m.reasons, "source": p.source,
            "org": p.org, "company": display_company(p.company, p.org), "title": p.title,
            "location": p.location, "url": p.url, "apply_url": p.apply_url,
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            "deadline": p.deadline.isoformat() if p.deadline else None,
            "raw_id": p.raw_id, "description": p.description, "terms": getattr(p, "terms", None) or None,
            "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def queue(t):
    """Order: tier, then newest posting first (fresh postings are the race)."""
    return (t["tier"], -(datetime.fromisoformat(t["posted_at"]).timestamp() if t["posted_at"] else 0))


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def requested():
    """Jobs he has asked for a resume for, from the app (data/requested.json).

    Nothing is written for a posting he has not asked about: finding a job is
    cheap, a resume costs a Claude run and a runner minute. `resumes.on_request`
    in criteria.yaml turns this back off.
    """
    return _load("requested.json", {})


def request(uid, apply=True, **extra):
    """Record that he wants this one written (and applied for, if it can be)."""
    want = requested()
    want[uid] = {**want.get(uid, {}), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "apply": bool(apply), **extra}
    _save("requested.json", want)
    return want[uid]


def on_request():
    return bool((watch.load_criteria().get("resumes") or {}).get("on_request", False))


def open_postings(record=True):
    """Postings to write a resume for.

    Two rules decide this. Anything he has not asked for is checked against the
    current criteria and against what he has already applied to, because it is
    jobbot's own idea. Anything he HAS asked for is his decision and is built:
    he tapped Apply on that card, after reading it, so refusing it quietly -
    which is what used to happen when a job was a day old or looked like an
    application he sent months ago - is the worst thing this can do.

    record=False never writes, for callers outside the resume workflow (watch
    must not touch tailored.json).
    """
    ledger, prior, approved = _load("tailored.json", {}), prior_applications(), approved_uids()
    want, ask_first = requested(), on_request()
    crit, targets = watch.load_criteria(), watch.load_targets()
    out = []
    for t in _load("pending.json", {}).values():
        uid, asked = t["uid"], t["uid"] in want
        status = ledger.get(uid, {}).get("status")
        if ask_first and not asked and status != "retry":
            continue                            # he has not asked for this one
        if status and status != "retry" and not asked:
            continue
        if uid in approved:
            continue
        # Re-check against the CURRENT criteria: a posting queued before a
        # criteria edit (e.g. new grad roles turned off) must not get a resume.
        posting = to_posting(t)
        m, why = match.classify(posting, crit, targets)
        if m is not None:
            # Workday/Ashby only give the real date per posting; check it before
            # spending a resume on something posted months ago.
            sources.enrich([m])
            m, why = match.classify(posting, crit, targets)
        expired = False
        if m is not None:
            _, gone = sources.drop_expired([m])
            if gone:
                m, why, expired = None, f"the deadline passed ({posting.deadline:%Y-%m-%d})", True
        if m is None and not asked:
            if record:
                _mark(uid, "dropped", reason=f"no longer matches criteria: {why}",
                      company=t["company"], title=t["title"])
            continue
        if m is None and expired:
            # The one refusal he cannot argue with: the form is closed.
            if record:
                _mark(uid, "cannot_build", reason=f"Not written: {why}.",
                      company=t["company"], title=t["title"])
            continue
        if m is None:
            print(f"{t['company']}: {why} - building it anyway, you asked for it")
        if already_applied(t, prior):
            if not asked:
                if record:
                    _mark(uid, "already_applied", company=t["company"], title=t["title"])
                continue
            print(f"{t['company']}: looks like one you applied to before - building it anyway")
        out.append(t)
    return sorted(out, key=queue)


def stuck_requests(record=True):
    """Requests that cannot turn into a resume, so the app can stop saying "writing".

    A posting he asked for after it had already left the board has no JD to
    write from. That used to sit in the queue forever with nothing running.
    """
    pending, ledger, want = _load("pending.json", {}), _load("tailored.json", {}), requested()
    stuck = []
    for uid in want:
        if uid in pending:
            continue
        v = ledger.get(uid, {})
        if v.get("status") in ("resume_ready", "in_progress", "cannot_build", "skipped") or v.get("folder"):
            continue
        stuck.append(uid)
        if record:
            _mark(uid, "cannot_build",
                  reason="Not written: jobbot lost this posting. Open the posting and ask again.")
    return stuck


def job_text(t):
    """The job description to write from, fetched if the posting came without one.

    A posting that came from a community list has no description; the writer
    cannot tailor a resume to a title alone.
    """
    text = (t.get("description") or "").strip()
    if len(text) >= 300:
        return text
    from . import community
    found = community.describe(t.get("url"))
    return (text + "\n\n" + found).strip() if found else text


def prepare(t):
    t = {**t, "description": job_text(t)}
    folder = OUT / safe_segment(t["company"]) / safe_segment(t["title"])
    folder.mkdir(parents=True, exist_ok=True)
    header = [f"Company: {t['company']}", f"Role: {t['title']}", f"Location: {t['location']}",
              "Term: (read from the JD below)",
              f"Posted: {(t['posted_at'] or 'unknown - no employer timestamp')[:10]} (employer timestamp)",
              f"Deadline: {(t['deadline'] or 'none listed')[:10]}",
              f"Posting: {t['url']}", f"Apply: {t['apply_url']}",
              f"jobbot: uid {t['uid']}, tier {t['tier']}, {t['source']} {t['org']} job {t['raw_id']}"]
    if t["reasons"]:
        header.append("Flags: " + "; ".join(t["reasons"]))
    # What he asked for in the app, in his words. It goes at the top of the JD
    # because the writer reads this file and nothing else about this job.
    note = (_load("hints.json", {}).get(t["uid"]) or "").strip()
    asked = ""
    if note:
        asked = ("\n## What the user asked for on this one\n\n" + note +
                 "\n\nFollow it unless it would mean claiming something he has not done.\n")
    (folder / "JD.md").write_text(
        "\n".join(header) + "\n" + asked + "\n" + t["description"].strip() + "\n", encoding="utf-8")
    rj = folder / "resume.json"
    if not rj.exists():
        rj.write_text(json.dumps({"uid": t["uid"], "company": t["company"], "role": t["title"],
                                  "term": None, "rhythm": 0.85, "sections": [], "skills": {}},
                                 indent=2), encoding="utf-8")
    _mark(t["uid"], "in_progress", company=t["company"], title=t["title"], tier=t["tier"],
          location=t["location"], folder=rel(folder),
          url=t["url"], apply_url=t["apply_url"], posted_at=t["posted_at"],
          deadline=t["deadline"], reasons=t["reasons"])
    return folder


# A resume he wrote and sent, kept with his things rather than with the code.
SAMPLE = next((p for p in (PIPE / "style_sample.json", ROOT / "samples" / "resume_tailor_duolingo.json")
               if p.exists()), PIPE / "style_sample.json")


def write_brief(folder):
    """Everything the writer needs, in one file.

    A resume took 22 turns (2026-09-20), because the model fetched each input
    itself - the posting, his facts, his rules, the style sample, the schema,
    the form - and every turn re-sends the whole conversation. Handing it one
    file makes that one read, the way he pastes a posting into a chat.
    """
    folder = Path(folder)
    parts = [f"# Brief: {folder.parent.name} - {folder.name}", ""]
    parts += ["## The posting (JD.md)", "", (folder / "JD.md").read_text(encoding="utf-8"), ""]
    parts += ["## His facts (data/profile.json)", "", "```json",
              json.dumps({k: v for k, v in load_profile().items() if k not in ("latex", "_generated_from")},
                         indent=1, ensure_ascii=False), "```", ""]
    from . import settings
    mine, answering = settings.brief_sections()
    profile = load_profile()
    if profile.get("notes_from_him"):
        parts += ["## What he wants you to know about him", "", profile["notes_from_him"], ""]
    if mine.get("rules"):
        parts += ["## His resume rules (Settings -> Resume in his app)", "", mine["rules"], ""]
    if (mine.get("instructions") or "").strip():
        parts += ["## His standing instructions - these win over his resume rules above, "
                  "never over the fact rules", "", mine["instructions"].strip(), ""]
    if SAMPLE.exists():
        parts += ["## A resume he wrote and sent - match its voice and density", "", "```json",
                  SAMPLE.read_text(encoding="utf-8"), "```", ""]
    # The page checks, stated up front. The writer used to learn these by
    # failing a build and spending two turns on each fix. A line holds about
    # 108 characters; the longest passing bullet across 347 is 217.
    parts += ["## What the page checks - get these right in the first draft", "",
              "- Every bullet is 150-210 characters of plain text (not counting the ** marks): two full "
              "lines. Over ~215 spills onto a third line and fails. 105-130 leaves one or two words alone "
              "on the second line and fails. A one-line bullet must stay under ~100.",
              "- No em dashes. Use a comma, semicolon or parentheses.",
              "- Two neighbouring bullets never open with the same word.",
              "- Completed, past-tense work only: never open with Building, Adding, Working on, Currently, "
              "Will or Incoming, and never write 'in progress'.",
              "- Never: demonstrated strong, collaborated with stakeholders, team player, cooperative "
              "environment, strong communication skills, effective time management, detail-oriented.",
              "- Experience: Northwind first, at most 4 entries including it; 2-3 bullets per role; "
              "City Hospital gets 3.", ""]
    schema = __doc__.split("resume.json:", 1)[1] if "resume.json:" in (__doc__ or "") else ""
    parts += ["## resume.json schema", "", "```", "resume.json:" + schema.strip(), "```", ""]
    app = folder / "application.json"
    todo = []
    if app.exists():
        for q in json.loads(app.read_text(encoding="utf-8")).get("questions", []):
            if q.get("how") == "draft" and not q.get("answer"):
                line = f'- "{q["label"]}" ({q.get("type") or "text"}{", required" if q.get("required") else ""})'
                if q.get("options"):
                    line += " - options: " + " | ".join(str(o) for o in q["options"])
                todo.append(line)
    parts += ["## Form questions to answer in answers.json", ""]
    parts += todo or ["None - do not write answers.json."]
    if todo:
        parts += ["", "## How he wants form answers written", "", answering.get("instructions") or ""]
    (folder / "brief.md").write_text("\n".join(parts) + "\n", encoding="utf-8")
    return folder / "brief.md"


def take_answers(folder):
    """Fold answers.json, written in one go by the model, into application.json."""
    folder = Path(folder)
    src, app_path = folder / "answers.json", folder / "application.json"
    if not src.exists() or not app_path.exists():
        return 0
    answers = json.loads(src.read_text(encoding="utf-8"))
    app = json.loads(app_path.read_text(encoding="utf-8"))
    took = 0
    for q in app.get("questions", []):
        if q.get("how") == "draft" and not q.get("answer") and answers.get(q.get("label")):
            q["answer"] = answers[q["label"]]
            took += 1
    app_path.write_text(json.dumps(app, indent=2, ensure_ascii=False), encoding="utf-8")
    return took


def cmd_plan(a):
    """The postings waiting for a resume, as a list of uids.

    Each one is then written by its own runner, side by side: five resumes take
    about as long as one (2026-09-22, he asked why they queue).
    """
    stuck_requests()
    from . import settings
    uids = [t["uid"] for t in open_postings()][: a.limit]
    model = (settings.effective("resume", settings.resume_base()) or {}).get("model") or ""
    print(json.dumps(uids))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"uids={json.dumps(uids)}\ncount={len(uids)}\nmodel={model}\n")
    if model:
        print(f"model: {model}")
    return 0


def cmd_next(a):
    from . import questions
    gone = stuck_requests()
    for uid in gone:
        print(f"{uid}: asked for, but the posting has left the board")
    todo = open_postings()
    if getattr(a, "only", None):
        todo = [t for t in todo if t["uid"] == a.only]
    batch = []
    for t in todo[: a.limit]:
        # A resume written from a job title alone would be generic. If the page
        # cannot be read and he has not pasted the posting in, say so on the card.
        if len(job_text(t)) < 300 and not _load("hints.json", {}).get(t["uid"]):
            _mark(t["uid"], "cannot_build", company=t["company"], title=t["title"],
                  reason='jobbot could not read this posting. Paste the job description into '
                         '"Tell Claude what to change" and tap Write it again.')
            print(f"{t['company']}: no readable job description - asked him to paste it")
            continue
        folder = prepare(t)
        batch.append(rel(folder))
        questions.prepare(folder, t["uid"], t["url"], t["apply_url"], t["location"])
        write_brief(folder)
    (DATA / "batch.txt").write_text("\n".join(batch) + ("\n" if batch else ""), encoding="utf-8")
    print(f"{len(todo)} posting(s) need a resume; prepared {len(batch)}:")
    for f in batch:
        print(f"  {f}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"count={len(batch)}\n")
    return 0


def cmd_enqueue_backlog(a):
    """One-off: fetch every board now and queue current matches in the given tiers.

    Writes pending.json, so run it when watch is not mid-run, then push.
    """
    crit, targets = watch.load_criteria(), watch.load_targets()
    postings, _ = sources.fetch_all(store.active_boards(store.load_registry()), max_workers=a.workers)
    matches, _ = match.run(postings, crit, targets)
    pending = _load("pending.json", {})
    added = 0
    for m in matches:
        if m.tier in a.tiers and m.posting.uid not in pending:
            pending[m.posting.uid] = posting_dict(m)
            added += 1
    _save("pending.json", pending)
    print(f"{len(matches)} matches; queued {added} in tiers {a.tiers}; pending now {len(pending)}")
    return 0


BOLD = re.compile(r"\*\*(.+?)\*\*")


def tex_escape(s):
    out = "".join({"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                   "{": r"\{", "}": r"\}", "~": r"$\sim$", "^": r"\^{}",
                   "\\": r"\textbackslash{}"}.get(ch, ch) for ch in s)
    return out.replace("->", r"$\to$")


def tex_inline(s):
    parts, last = [], 0
    for m in BOLD.finditer(s):
        parts += [tex_escape(s[last:m.start()]), r"\textbf{" + tex_escape(m.group(1)) + "}"]
        last = m.end()
    parts.append(tex_escape(s[last:]))
    return "".join(parts)


def plain(s):
    return BOLD.sub(r"\1", s)


def check_shape(resume, profile):
    """Structural errors the fabrication verifier does not cover."""
    errs = []
    grad = profile["education"][0]["grad_by_term"]
    if resume.get("term") not in grad:
        errs.append(f"term must be one of {sorted(grad)}, got {resume.get('term')!r}")
    exp_order = [e["id"] for e in profile["experience"]]
    proj_ids = {p["id"] for p in profile["projects"]}
    secs = resume.get("sections", [])
    exps = [s.get("entry_id") for s in secs if s.get("entry_id") in exp_order]
    projs = [s.get("entry_id") for s in secs if s.get("entry_id") in proj_ids]
    unknown = [s.get("entry_id") for s in secs
               if s.get("entry_id") not in exp_order and s.get("entry_id") not in proj_ids]
    if unknown:
        errs.append(f"unknown entry_id(s): {unknown}")
    if exps != sorted(exps, key=exp_order.index):
        errs.append(f"experience must stay reverse-chronological: {exps} (profile order {exp_order})")
    if not exps:
        errs.append("no experience entries")
    if len(projs) > 2:
        errs.append(f"{len(projs)} projects - max 2")
    if len(resume.get("skills") or {}) != 4:
        errs.append(f"skills must have exactly 4 rows, got {len(resume.get('skills') or {})}")
    r = resume.get("rhythm", 0.85)
    if not isinstance(r, (int, float)) or not 0.6 <= r <= 1.1:
        errs.append(f"rhythm must be 0.6-1.1, got {r!r}")
    return errs


def render_tex(resume, profile):
    lx, edu = profile["latex"], profile["education"][0]
    exp = {e["id"]: e for e in profile["experience"]}
    proj = {p["id"]: p for p in profile["projects"]}
    L = [lx["documentclass"], "", lx["geometry"], lx["header"].rstrip(), "",
         rf"\setrhythm{{{resume.get('rhythm', 0.85)}}}", r"\begin{document}", "",
         r"\begin{rSection}{Education}", "",
         edu["latex"].replace("<GRAD>", edu["grad_by_term"][resume["term"]]).rstrip(), "",
         r"\end{rSection}", "", r"\begin{rSection}{Experience}", ""]

    def items(bullets):
        return ([r"\begin{itemize}"] + [f"  \\item {tex_inline(b['text'])}" for b in bullets]
                + [r"\end{itemize}", ""])

    secs = resume["sections"]
    for s in (s for s in secs if s["entry_id"] in exp):
        e = exp[s["entry_id"]]
        dates = f"{e['start']} -- {e['end']}" if e["end"] else e["start"]
        L.append(rf"\rEntry{{{tex_escape(e['title'])}}}{{{dates}}}"
                 rf"{{{tex_escape(e['employer'])}}}{{{tex_escape(e['location'])}}}")
        L += items(s["bullets"])
    L += [r"\end{rSection}", ""]

    ps = [s for s in secs if s["entry_id"] in proj]
    if ps:
        L += [r"\begin{rSection}{Projects}", ""]
        for s in ps:
            p = proj[s["entry_id"]]
            stack = s.get("stack") or ", ".join(p["facts"][0]["tech"])
            L.append(rf"\rProject{{{tex_escape(s.get('name') or p['name'])}}}{{{tex_escape(stack)}}}")
            L += items(s["bullets"])
        L += [r"\end{rSection}", ""]

    L += [r"\begin{rSection}{Skills}", "", lx["skills_table_open"]]
    for label, row in resume["skills"].items():
        L.append(rf"\textbf{{{tex_escape(label)}:}} & {tex_escape(row)} \\")
    L += [r"\end{tabular}", "", r"\end{rSection}", "", r"\end{document}", ""]
    return "\n".join(L)


def rel(p):
    """Repo-relative posix path (used in links); absolute if outside the repo."""
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).as_posix()


# verify_resume.py reports the space left under the last line. His hand-built
# resumes sit around 25-60pt; the first cloud build left ~250pt and dropped a
# whole role it had room for.
MAX_ROOM_PT = 90


def summarize_labels(findings):
    """One line per kind; '71%' and '71' are the same coined figure."""
    coined, out = [], []
    for f in findings:
        if f["code"] == "COINED_METRIC":
            num = f["detail"].split("'")[1]
            if not any(c.startswith(num) or num.startswith(c) for c in coined):
                coined.append(num)
        else:
            out.append(f"{f['severity']} {f['code']}: {f['detail']}")
    if coined:
        out.insert(0, "INFO COINED_METRIC: ledgered, not measured: " + ", ".join(coined))
    return out


def render_preview(pdf_path):
    """PNG of page 1, shown inline in the GitHub issue so the resume can be read
    on a phone without opening the PDF."""
    try:
        import fitz
        out = pdf_path.with_name("preview.png")
        fitz.open(pdf_path)[0].get_pixmap(dpi=110).save(out)
        return rel(out)
    except Exception as e:                       # noqa: BLE001 - preview is optional
        print(f"preview failed: {e}", file=sys.stderr)
        return None


def resolve_folder(folder):
    p = Path(folder)
    return p if p.is_absolute() else ROOT / p


# What the build can fix without the writer: how much space sits between lines.
# Every other failure is about the words, and goes back to the writer.
SPACING_ONLY = re.compile(r"PDF is \d+ pages|UNDERFILLED|bullet gaps inside jobs are uneven|"
                          r"bullet pair\(s\) inside a job sit only")


def cmd_build(a):
    """Build, and fix the spacing itself before asking the writer to change words.

    A resume a line too long for one page, or a little too empty, used to cost
    two model turns each time. Line spacing (rhythm, 0.6-1.1) is adjusted here
    first, and only what spacing cannot fix is reported back.
    """
    folder = resolve_folder(a.folder)
    took = take_answers(folder)
    if took:
        print(f"{took} drafted answer(s) taken from answers.json")
    path = folder / "resume.json"
    for attempt in range(6):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _build_once(a)
        out = buf.getvalue()
        fails = [l for l in out.splitlines() if l.startswith("FAIL")]
        spacing = fails and all(SPACING_ONLY.search(l) for l in fails)
        if code == 0 or not spacing:
            print(out, end="")
            return code
        resume = json.loads(path.read_text(encoding="utf-8"))
        rhythm = float(resume.get("rhythm", 0.85))
        tighter = any(re.search(r"PDF is \d+ pages", l) for l in fails)
        step = -0.05 if tighter else 0.05
        new = round(min(1.1, max(0.6, rhythm + step)), 2)
        if new == rhythm:
            print(out, end="")
            return code
        resume["rhythm"] = new
        path.write_text(json.dumps(resume, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"spacing: {'too long' if tighter else 'too empty'} at rhythm {rhythm} - trying {new}")
    print(out, end="")
    return code


def _build_once(a):
    folder = resolve_folder(a.folder)
    resume = json.loads((folder / "resume.json").read_text(encoding="utf-8"))
    profile = load_profile()
    report = {"uid": resume.get("uid"), "status": "fail"}

    errs = check_shape(resume, profile)
    for e in errs:
        print(f"FAIL SHAPE {e}")

    # Verify exactly the text that will be rendered. A project's stack line is
    # checked as a claim too, against that project's own facts.
    checked = {"identity": resume.get("identity", {}), "coined": resume.get("coined") or [], "sections": []}
    proj_ids = {p["id"] for p in profile["projects"]}
    for s in resume.get("sections", []):
        bullets = [{**b, "text": plain(b.get("text", ""))} for b in s.get("bullets", [])]
        if s.get("entry_id") in proj_ids and s.get("stack"):
            bullets.append({"text": "Built with " + s["stack"] + ".", "source_ids": [s["entry_id"]]})
        checked["sections"].append({**{k: v for k, v in s.items() if k != "bullets"},
                                    "bullets": bullets})
    findings = verify.verify(profile, checked)
    for f in findings:
        print(f"{f['severity']:4} {f['code']:20} {f['bullet']:28} {f['detail']}")
    fails = [f for f in findings if f["severity"] == "FAIL"]
    report["labels"] = [f for f in findings if f["severity"] in ("INFO", "WARN")]
    if errs or fails:
        report.update(stage="jobbot verify", errors=errs + [f"{f['code']}: {f['detail']}" for f in fails])
        (folder / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nRESULT: FAIL at jobbot verify - {len(errs) + len(fails)} blocking")
        return 1

    tag = re.sub(r"[^A-Za-z0-9]+", "", folder.parent.name) or "Resume"
    who = re.sub(r"[^A-Za-z0-9]+", "_", (profile.get("identity") or {}).get("name", "")).strip("_")
    tex = folder / f"{who + '_' if who else ''}{tag}.tex"
    for old in folder.glob("*.tex"):
        if old != tex:
            old.unlink()
    tex.write_text(render_tex(resume, profile), encoding="utf-8")
    shutil.copy2(PIPE / "resume.cls", folder / "resume.cls")

    proc = subprocess.run([sys.executable, str(PIPE / "scripts" / "verify_resume.py"), str(tex)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300)
    output = (proc.stdout or "") + (proc.stderr or "")
    print("\n--- verify_resume.py ---\n" + output)
    if proc.returncode != 0:
        report.update(stage="verify_resume.py",
                      errors=[l for l in output.splitlines() if l.startswith("FAIL")])
        (folder / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("RESULT: FAIL at verify_resume.py")
        return 1

    room = re.search(r"~(\d+)pt of vertical space remains", output)
    if room and int(room.group(1)) > MAX_ROOM_PT:
        msg = (f"UNDERFILLED: ~{room.group(1)}pt of the page is empty (max {MAX_ROOM_PT}). Add the "
               "next most relevant role or bullets, or raise rhythm - an emptier page reads thin.")
        report.update(stage="page fill", errors=[msg])
        (folder / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"FAIL {msg}\nRESULT: FAIL at page fill")
        return 1

    pdf = rel(tex.with_suffix(".pdf"))
    preview = render_preview(tex.with_suffix(".pdf"))
    from . import questions
    app_problems = questions.refresh(folder)
    for p in app_problems:
        print(f"NOTE application: {p}")
    # Every figure this resume invented, kept with the job so the app can show
     # them and so the same work keeps the same number next time.
    coined = [c for c in (resume.get("coined") or []) if c.get("number")]
    if coined:
        (folder / "coined.json").write_text(json.dumps(coined, indent=2, ensure_ascii=False), encoding="utf-8")
        ledger = _load("coined.json", {})
        ledger[resume.get("uid") or folder.name] = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "company": folder.parent.name, "role": folder.name, "numbers": coined}
        _save("coined.json", ledger)
        print("\ncoined for this resume (he checks these):")
        for c in coined:
            print(f"  {c.get('number')} - {c.get('claim', '')[:70]}")
    report.update(status="pass", pdf=pdf, preview=preview, application_problems=app_problems, coined=coined)
    (folder / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if resume.get("uid"):
        _mark(resume["uid"], "resume_ready", pdf=pdf, preview=preview,
              says=(resume.get("note_to_him") or "").strip()[:600] or None,
              labels=summarize_labels(report["labels"]))
    info = sum(f["severity"] == "INFO" for f in report["labels"])
    warn = sum(f["severity"] == "WARN" for f in report["labels"])
    print(f"RESULT: PASS - {info} swap/coined label(s), {warn} warning(s)")
    return 0


def cmd_skip(a):
    _mark(a.uid, "skipped", reason=a.reason)
    print(f"skipped {a.uid}: {a.reason}")
    return 0


ISSUE_BODY_VERSION = 4      # bump to rewrite the title and body of already-open issues


def issue_title(v):
    """Company and role first: the email subject is "[repo] <title>", so a tier
    tag at the front made every subject look the same."""
    return f"{v['company']} - {' '.join(v['title'].split())} (T{v.get('tier')}){knockout_tag(v)}"[:240]


def knockout_tag(v):
    app_path = ROOT / v["folder"] / "application.json" if v.get("folder") else None
    if app_path and app_path.exists() and json.loads(app_path.read_text(encoding="utf-8")).get("knockouts"):
        return " [knockout?]"
    return ""


def issue_body(v, mention=False):
    blob = f"https://github.com/{REPO}/blob/main"
    link = lambda path: f"{blob}/{quote(path)}"
    if mention:
        head = (f"@{OWNER} new tier {v.get('tier')} job, resume ready." if v.get("pdf") else
                f"@{OWNER} new tier {v.get('tier')} job. The resume could not be built automatically.")
    else:
        head = "Resume ready." if v.get("pdf") else "The resume could not be built automatically."
    lines = [head, "",
             f"**{v['company']}** | {v['title']}",
             f"Tier {v.get('tier')} | {v.get('location') or '?'}",
             f"Posted {(v.get('posted_at') or 'date unknown')[:10]}"
             + (f" | deadline {v['deadline'][:10]}" if v.get("deadline") else ""), "",
             f"**Apply:** {v['apply_url']}", ""]
    if v.get("preview"):
        lines += [f"[![resume preview]({link(v['preview'])}?raw=true)]({link(v['pdf'])})", ""]
    if v.get("pdf"):
        lines += [f"**Resume:** [PDF]({link(v['pdf'])}) | [folder]({link(v['folder'])})"]
    elif v.get("errors"):
        lines += ["**Build errors:**"] + [f"- {e}" for e in v["errors"][:5]]
    lines += [f"**Posting:** {v['url']}", ""]
    app_path = ROOT / v["folder"] / "application.json" if v.get("folder") else None
    if app_path and app_path.exists():
        from . import questions
        lines += questions.summary_markdown(json.loads(app_path.read_text(encoding="utf-8")))
    if v.get("reasons"):
        lines += ["**Flags:** " + "; ".join(v["reasons"]), ""]
    labels = v.get("labels") or []
    if labels:
        lines += ["<details><summary>Swapped tools, coined figures, warnings "
                  f"({len(labels)})</summary>", ""] + [f"- {l}" for l in labels] + ["", "</details>", ""]
    lines += ["---", "Approve: comment `/approve` or add the `approved` label. "
              "Reject: close the issue."]
    return "\n".join(lines)


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")


def cmd_retry(a):
    """Forget build_failed entries (all, or given uids) so they are queued again.

    For failures that were not the posting's fault - a bad token, a runner
    outage. The uid must still be in pending.json to be picked up.
    """
    ledger = _load("tailored.json", {})
    uids = a.uids or [u for u, v in ledger.items() if v["status"] == "build_failed"]
    # A "retry" status (not a deletion) so the entry-by-entry ledger merge in
    # gitsync carries it over a concurrent resume run's copy.
    for u in uids:
        _mark(u, "retry")
    print(f"requeued {len(uids)}")
    return 0


def cmd_approve(a):
    """Record an approval from the issue and reply with the apply link.

    Appends to data/approvals.jsonl (never tailored.json), so the approve and
    resume workflows cannot conflict. The applier will consume this file.
    """
    ledger = _load("tailored.json", {})
    hit = next(((u, v) for u, v in ledger.items() if str(v.get("issue")) == str(a.issue)), None)
    if not hit:
        print(f"ERROR: no resume is linked to issue #{a.issue}", file=sys.stderr)
        return 1
    uid, v = hit
    rec = {"uid": uid, "issue": int(a.issue), "company": v.get("company"), "title": v.get("title"),
           "apply_url": v.get("apply_url"), "pdf": v.get("pdf"),
           "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(DATA / "approvals.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    gh("issue", "edit", str(a.issue), "-R", REPO, "--add-label", "approved")
    auto = (watch.load_criteria().get("apply") or {}).get("submit_sources") or []
    body = ("Approved and recorded as applied - it will not appear in alerts or digests again, and it "
            "is added to Tracker.xlsx the next time `python -m jobbot.sync_pipeline` runs on the "
            "laptop."
            f"\n\nApply here with the answers above: {v.get('apply_url')}"
            f"\n\nOr fill it in a browser window on the laptop: "
            f"`python -m jobbot.apply {a.issue} --handoff`")
    if auto:
        body = ("Approved - applying now. The result (with screenshots) follows in a minute. Recorded "
                "as applied: it will not appear in alerts or digests again, and it is added to "
                "Tracker.xlsx the next time `python -m jobbot.sync_pipeline` runs on the laptop.")
    gh("issue", "comment", str(a.issue), "-R", REPO, "--body", body)
    print(f"approved {uid} (#{a.issue})")
    return 0


def cmd_publish(a):
    ledger = _load("tailored.json", {})
    # Anything Claude left unfinished this run failed to build; don't retry forever.
    batch = set(filter(None, (DATA / "batch.txt").read_text().split("\n"))) if (DATA / "batch.txt").exists() else set()
    for uid, v in ledger.items():
        if getattr(a, "only", None) and uid != a.only:
            continue
        if v["status"] == "in_progress" and v.get("folder") in batch:
            build = ROOT / v["folder"] / "build.json"
            errors = json.loads(build.read_text()).get("errors", []) if build.exists() else ["never built"]
            _mark(uid, "build_failed", errors=errors[:10])
    ledger = _load("tailored.json", {})
    if a.no_issues:
        return 0

    for label, color in (("resume-ready", "0e8a16"), ("approved", "1d76db"), ("needs-resume", "d93f0b"),
                         ("tier-1", "b60205"), ("tier-2", "fbca04"), ("tier-3", "c5def5")):
        gh("label", "create", label, "--color", color, "--force", "-R", REPO)
    published, told, alerts, approved = 0, notified(), alert_tiers(), approved_uids()
    for uid, v in ledger.items():
        if getattr(a, "only", None) and uid != a.only:
            continue
        # A tier 1/2 job whose resume failed still gets its alert.
        failed_alert = (v["status"] == "build_failed" and v.get("tier") in alerts
                        and uid not in told and not v.get("issue"))
        if (v["status"] != "resume_ready" and not failed_alert) or uid in approved:
            continue
        if v.get("issue"):
            if v.get("issue_body_v", 1) < ISSUE_BODY_VERSION:
                if not v.get("preview") and v.get("pdf") and (ROOT / v["pdf"]).exists():
                    v["preview"] = render_preview(ROOT / v["pdf"])
                folder = ROOT / v["folder"]
                if not (folder / "application.json").exists():
                    from . import questions
                    if questions.prepare(folder, uid, v.get("url"), v.get("apply_url"), v.get("location")):
                        questions.refresh(folder)
                was_alert = told.get(uid, {}).get("issue") == str(v["issue"])
                r = gh("issue", "edit", str(v["issue"]), "-R", REPO, "--body", issue_body(v, was_alert),
                       "--title", issue_title(v))
                if r.returncode == 0:
                    _mark(uid, "resume_ready", preview=v.get("preview"), issue_body_v=ISSUE_BODY_VERSION)
                    print(f"refreshed issue #{v['issue']}")
            continue
        # Only an alert-tier job he has not heard about yet @mentions him (email
        # + GitHub app push). Everything else is created silently; the morning
        # digest links to it.
        mention = v.get("tier") in alerts and uid not in told
        title = issue_title(v)
        label = "resume-ready" if v["status"] == "resume_ready" else "needs-resume"
        r = gh("issue", "create", "-R", REPO, "--title", title, "--body", issue_body(v, mention),
               "--label", label, "--label", f"tier-{v.get('tier')}")
        if r.returncode != 0:
            print(f"issue create failed for {uid}: {r.stderr.strip()}", file=sys.stderr)
            continue
        num = r.stdout.strip().rsplit("/", 1)[-1]
        _mark(uid, v["status"], issue=num, issue_body_v=ISSUE_BODY_VERSION)
        if mention:
            mark_notified([uid], "alert", issue=num)
        published += 1
        print(f"published{' (alert)' if mention else ''} {title}: {r.stdout.strip()}")
    print(f"{published} issue(s) opened")

    # Close resume issues that no longer have a live resume behind them: the
    # posting was dropped by a criteria change, or the resume was rebuilt.
    # Read the newest ledger on the remote too, and leave issues under an hour
    # old alone: another job may have opened one this checkout cannot see yet.
    ledgers = [_load("tailored.json", {})]
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, capture_output=True)
    shown = subprocess.run(["git", "show", "origin/main:data/tailored.json"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8")
    if shown.returncode == 0 and shown.stdout.strip():
        ledgers.append(json.loads(shown.stdout))
    live = {str(v.get("issue")) for led in ledgers for u, v in led.items()
            if v["status"] == "resume_ready" and v.get("issue") and u not in approved}
    listed = gh("issue", "list", "-R", REPO, "--label", "resume-ready", "--state", "open",
                "--limit", "200", "--json", "number,createdAt")
    cutoff = datetime.now(timezone.utc).timestamp() - 3600
    for iss in json.loads(listed.stdout or "[]"):
        n = str(iss["number"])
        created = datetime.fromisoformat(iss["createdAt"].replace("Z", "+00:00")).timestamp()
        if n not in live and created < cutoff:
            gh("issue", "close", n, "-R", REPO, "--comment",
               "Closed automatically: applied, no longer matches the criteria, or rebuilt "
               "under a new issue.")
            print(f"closed stale issue #{n}")
    return 0


def cmd_autoapply(a):
    """Carry a resume he asked to apply with straight into the application.

    He tapped Apply, not "write it and wait": once the resume exists and the
    site is one jobbot can submit to, the apply run starts on its own. A site
    it cannot submit to stops here and the app tells him to finish it.
    """
    ledger, want = _load("tailored.json", {}), requested()
    auto = set((watch.load_criteria().get("apply") or {}).get("submit_sources") or [])
    started = []
    for uid, req in want.items():
        v = ledger.get(uid) or {}
        if getattr(a, "only", None) and uid != a.only:
            continue
        if not req.get("apply") or req.get("started") or v.get("status") != "resume_ready":
            continue
        if not v.get("issue"):
            continue                                  # no issue yet: next publish opens one
        source = (v.get("source") or v.get("apply_url") or v.get("url") or "").lower()
        if not any(name in source for name in auto):
            print(f"{v.get('company')}: {source[:40] or 'unknown site'} is his to submit")
            continue
        env = {**os.environ}
        if os.environ.get("GH_CODE_TOKEN"):
            env["GH_TOKEN"] = os.environ["GH_CODE_TOKEN"]      # runs live in the code repo
        r = subprocess.run(["gh", "workflow", "run", "approve.yml", "-R", CODE_REPO,
                            "-f", f"issue={v['issue']}"], capture_output=True, text=True, env=env)
        if r.returncode:
            print(f"could not start the apply run for #{v['issue']}: {r.stderr.strip()[:120]}")
            continue
        request(uid, apply=True, started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        started.append(v.get("company") or uid)
    print(f"apply runs started: {len(started)}" + (f" ({', '.join(started)})" if started else ""))
    return 0


def cmd_status(a):
    if a.open_count:
        n = len(open_postings(record=False))
        print(n)
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as fh:
                fh.write(f"open={n}\n")
        return 0
    ledger = _load("tailored.json", {})
    counts = {}
    for v in ledger.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print(f"open: {len(open_postings(record=False))}  " + "  ".join(f"{k}: {n}" for k, n in sorted(counts.items())))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot.tailor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("next"); s.add_argument("--limit", type=int, default=3)
    s.add_argument("--only", help="one posting's uid, for a runner of its own"); s.set_defaults(func=cmd_next)
    s = sub.add_parser("plan"); s.add_argument("--limit", type=int, default=8); s.set_defaults(func=cmd_plan)
    s = sub.add_parser("enqueue-backlog"); s.add_argument("--tiers", type=int, nargs="+", default=[1])
    s.add_argument("--workers", type=int, default=12); s.set_defaults(func=cmd_enqueue_backlog)
    s = sub.add_parser("build"); s.add_argument("folder"); s.set_defaults(func=cmd_build)
    s = sub.add_parser("skip"); s.add_argument("uid"); s.add_argument("reason"); s.set_defaults(func=cmd_skip)
    s = sub.add_parser("publish"); s.add_argument("--only"); s.add_argument("--no-issues", action="store_true",
                                                  help="only settle unfinished builds")
    s.set_defaults(func=cmd_publish)
    s = sub.add_parser("retry"); s.add_argument("uids", nargs="*"); s.set_defaults(func=cmd_retry)
    s = sub.add_parser("approve"); s.add_argument("issue"); s.set_defaults(func=cmd_approve)
    s = sub.add_parser("autoapply"); s.add_argument("--only"); s.set_defaults(func=cmd_autoapply)
    s = sub.add_parser("status"); s.add_argument("--open-count", action="store_true")
    s.set_defaults(func=cmd_status)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
