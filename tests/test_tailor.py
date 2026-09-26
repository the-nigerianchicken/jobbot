"""Offline tests for jobbot.tailor: queueing, dedup, rendering, issue text.

Rendering is checked against samples/resume_tailor_duolingo.json, a resume the user
actually sent (Duolingo, 2026-09-16) re-expressed as resume.json. The full
compile + verify_resume.py path needs tectonic and runs in the resume workflow.
"""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["JOBBOT_DATA"] = tempfile.mkdtemp()
os.environ["JOBBOT_OUT"] = tempfile.mkdtemp()

from jobbot import tailor, verify
# Outside a run there is no repo to take the owner's handle from.
tailor.REPO = tailor.REPO or "someone/jobbot"
tailor.GH_USER = tailor.OWNER = tailor.GH_USER or tailor.REPO.split("/")[0]

fails = []
def check(name, ok, detail=""):
    print(f"{'ok ' if ok else 'BAD'} {name}" + (f": {detail}" if not ok and detail else ""))
    if not ok:
        fails.append(name)

# --- escaping ---------------------------------------------------------------
check("bold + escapes", tailor.tex_inline("cut **~90%** & shipped C#_x") ==
      r"cut \textbf{$\sim$90\%} \& shipped C\#\_x", tailor.tex_inline("cut **~90%** & shipped C#_x"))
check("plain strips bold", tailor.plain("a **b** c") == "a b c")

# --- dedup against manual applications --------------------------------------
prior = [{"company": "Duolingo", "role": "Software Engineer Intern", "ids": ["8805925002"]},
         {"company": "Shopify", "role": "Dev Degree", "ids": []}]
t = lambda **k: {"company": "X", "org": "x", "title": "T", "raw_id": "", **k}
check("dedup by job id", tailor.already_applied(t(raw_id="8805925002"), prior))
check("dedup by company+role", tailor.already_applied(
    t(company="Duolingo University Recruiting", org="duolingounirecruitment",
      title="Software Engineer, Intern"), prior))
check("different role not deduped", not tailor.already_applied(
    t(company="Duolingo", org="duolingo", title="Machine Learning Engineer Intern"), prior))
# Real cases from the 2026-09-16 tier-1 backlog vs his OneDrive folders.
real_prior = [{"company": "RobinHood", "role": "Software Developer Intern Backend - Toronto Summer 2027", "ids": []},
              {"company": "RobinHood", "role": "Software Developer Intern Web - Toronto Summer 2027", "ids": []},
              {"company": "Notion", "role": "Software Engineer Intern - Summer 2027", "ids": []},
              {"company": "Sierra", "role": "Intern Agent Development - Summer 2027", "ids": []},
              {"company": "Cohere", "role": "Software Engineer Intern - Winter 2027", "ids": []},
              {"company": "DoorDash", "role": "Software Engineer Intern Summer 2027 - Toronto", "ids": []}]
rp = lambda company, title, loc: tailor.already_applied(t(company=company, org=_k(company), title=title, location=loc), real_prior)
_k = lambda c: c.lower().replace(" ", "")
check("robinhood backend toronto = done", rp("Robinhood", "Software Developer Intern, Backend (Summer 2027)", "Toronto, Canada"))
check("robinhood web toronto = done", rp("Robinhood", "Software Developer Intern, Web (Summer 2027)", "Toronto, Canada"))
check("robinhood backend WINTER != summer folder", not rp("Robinhood", "Software Developer Intern/Co-op, Backend (Winter 2027)", "Toronto, Canada"))
check("robinhood backend US seat != toronto folder", not rp("Robinhood", "Software Engineering Intern, Backend (Summer 2027)", "Bellevue, WA; Menlo Park, CA"))
check("notion winter != summer folder", not rp("Notion", "Software Engineer Intern (Winter 2027)", "San Francisco, California"))
check("robinhood iOS toronto != web folder", not rp("Robinhood", "Software Developer Intern, iOS (Summer 2027)", "Toronto, Canada"))
check("doordash US seat != toronto folder", not rp("DoorDash USA", "Software Engineer, Intern (Summer 2027) - US", "New York, NY; San Francisco, CA"))
check("doordash toronto = done", rp("DoorDash Canada", "Software Engineer, Intern (Summer 2027) - TOR", "Toronto, ON"))
# Wrong matches seen in the app's Applied list, 2026-09-18.
check("substring company is not the same company (Ada vs DoorDash Canada)",
      not tailor.already_applied(t(company="Doordash Canada", org="doordashcanada",
                                   title="Software Engineer, Intern (Summer 2027) - TOR", location="Toronto, ON"),
                                 [{"company": "Ada", "role": "Software Engineering Intern", "ids": []}]))
check("a season alone does not identify a role (Motorola)",
      not tailor.already_applied(t(company="motorolasolutions", org="motorolasolutions",
                                   title="DSP Software Engineering Intern - Summer 2027", location="Toronto"),
                                 [{"company": "Motorola", "role": "Summer Software Engineer Co-Op", "ids": []}]))
check("corporate suffix still matches (Motorola Solutions = Motorola)",
      tailor.already_applied(t(company="motorolasolutions", org="motorolasolutions",
                               title="Summer Software Engineer Co-Op", location="Toronto"),
                             [{"company": "Motorola", "role": "Summer Software Engineer Co-Op", "ids": []}]))
check("sierra agent intern = done", rp("Sierra", "Software Engineer Intern, Agent (Summer 2027)", "San Francisco, CA"))
check("cohere ML intern != SWE intern", not rp("Cohere", "Machine Learning Intern/Co-op  (Winter 2027)", "Canada"))
check("slug company prettified", tailor.display_company("gecko-robotics", "gecko-robotics") == "Gecko Robotics")

# --- queue: pending -> next -> ledger ---------------------------------------
posting = lambda uid, tier, posted: {
    "uid": uid, "tier": tier, "reasons": [], "source": "greenhouse", "org": "acme",
    "company": "Acme", "title": f"Software Engineer Intern {uid}", "location": "Toronto, ON",
    "url": "u", "apply_url": "a", "posted_at": posted, "deadline": None, "raw_id": uid,
    "description": "Summer 2027 internship. " + "You will build backend services in Python "
                   "and Go with the platform team, write tests, and ship to production. " * 6}
from datetime import datetime, timedelta, timezone
ago = lambda h: (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()
tailor._save("pending.json", {"a": posting("a", 3, ago(1)), "b": posting("b", 1, ago(20)),
                              "c": posting("c", 1, ago(5)), "old": posting("old", 3, ago(30))})

# Resumes are written on request now: nothing he has not asked for is open.
asking = tailor.on_request
tailor.on_request = lambda: True
check("nothing is written that he has not asked for", tailor.open_postings(record=False) == [])
tailor._save("requested.json", {"old": {"apply": False}})
check("a posting he asked for is written even past the age limit",
      [p["uid"] for p in tailor.open_postings(record=False)] == ["old"])
tailor._save("requested.json", {})

# The original automatic mode, one switch away in criteria.yaml.
tailor.on_request = lambda: False
order = [p["uid"] for p in tailor.open_postings()]
check("tier first, then newest; over-age dropped", order == ["c", "b", "a"], order)

class A: limit = 2
tailor.cmd_next(A)
ledger = tailor._load("tailored.json", {})
check("next prepares limit", sorted(u for u, v in ledger.items() if v["status"] == "in_progress") == ["b", "c"])
check("over-age posting recorded as dropped", ledger.get("old", {}).get("status") == "dropped")
folder = tailor.resolve_folder(ledger["c"]["folder"])
check("JD.md + skeleton written", (folder / "JD.md").exists() and (folder / "resume.json").exists())
check("prepared are no longer open", [p["uid"] for p in tailor.open_postings()] == ["a"])

# --- rendering + shape (needs the real profile) -----------------------------
prof_path = os.path.join(ROOT, "data", "profile.json")
if os.path.exists(prof_path):
    prof = json.load(open(prof_path, encoding="utf-8"))
    r = json.load(open(os.path.join(ROOT, "samples", "resume_tailor_duolingo.json"), encoding="utf-8"))
    check("sample shape ok", tailor.check_shape(r, prof) == [], tailor.check_shape(r, prof))
    tex = tailor.render_tex(r, prof)
    for needle in [r"\rEntry{AI Engineer Intern}{Sep 2026 -- Present}{Northwind Insurance}{Toronto, ON}",
                   r"{Expected Dec 2027}", r"\textbf{35\% to 80\%}", r"\textbf{Data \& AI:}",
                   r"\rProject{Document Question-Answering Platform}{Go, Python, PostgreSQL, Redis, Docker}"]:
        check(f"tex contains {needle[:40]}", needle in tex)
    bad = dict(r, term="spring_2030", sections=list(reversed(r["sections"])), skills={"a": "b"})
    errs = " ".join(tailor.check_shape(bad, prof))
    check("shape catches term/order/skills",
          "term" in errs and "reverse-chronological" in errs and "skills" in errs, errs)
    plain = {"sections": [{**s, "bullets": [{**b, "text": tailor.plain(b["text"])} for b in s["bullets"]]}
                          for s in r["sections"]]}
    fl = [f for f in verify.verify(prof, plain) if f["severity"] == "FAIL"]
    check("a resume he actually sent passes the verifier", not fl, fl)

# --- issue text ---------------------------------------------------------------
body = tailor.issue_body({"company": "Acme", "title": "SWE Intern", "tier": 1, "location": "Toronto",
                          "posted_at": "2026-09-16T00:00:00", "deadline": None, "pdf": "resumes/A/B/x.pdf",
                          "folder": "resumes/A/B", "url": "https://p", "apply_url": "https://a",
                          "reasons": [], "labels": ["INFO COINED_METRIC: '94%' ..."]})
check("silent issue has no mention", not tailor.GH_USER or "@" + tailor.GH_USER not in body)
alert = tailor.issue_body({"company": "Acme", "title": "SWE Intern", "tier": 1, "location": "Toronto",
                           "posted_at": None, "deadline": None, "pdf": "resumes/A/B/x.pdf",
                           "folder": "resumes/A/B", "url": "u", "apply_url": "a", "reasons": []}, mention=True)
check("alert issue mentions owner", alert.startswith("@" + tailor.GH_USER))

# --- once-only notification + applied exclusion ------------------------------
tailor.mark_notified(["j1"], "alert", issue="7")
tailor.mark_notified(["j1", "j2"], "digest")
n = tailor.notified()
check("first notification wins", n["j1"]["via"] == "alert" and n["j2"]["via"] == "digest")
with open(tailor.DATA / "approvals.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"uid": "a"}) + "\n")
check("approved counts as applied", "a" in tailor.approved_uids())
check("issue links pdf and apply", "resumes/A/B/x.pdf" in body and "https://a" in body)
check("issue lists labels", "COINED_METRIC" in body and "/approve" in body)

# --- taking a request back ---------------------------------------------------
# Stopping a resume has to stop the next plan from picking the posting straight
# back up, or the card he cancelled starts building again a minute later.
tailor._save("requested.json", {"w1": {"apply": True, "at": "2026-09-24T00:00:00+00:00"}})
tailor._save("tailored.json", {"w1": {"status": "in_progress", "company": "Writing"},
                               "w2": {"status": "resume_ready", "folder": "resumes/W/2"}})
check("a request he takes back is gone", tailor.withdraw("w1") and "w1" not in tailor.requested())
check("and so is the half-written ledger row", "w1" not in tailor._load("tailored.json", {}))
check("a resume that exists is left alone", not tailor.withdraw("w2")
      and tailor._load("tailored.json", {}).get("w2", {}).get("folder") == "resumes/W/2")
check("withdrawing something nobody asked for changes nothing", not tailor.withdraw("w3"))

print()
if fails:
    print(f"{len(fails)} failure(s)"); sys.exit(1)
print("tailor suite OK")


# 2026-09-25: a resume was written, the app said it was ready, and the file was
# thrown away with the runner. tailor wrote resumes next to its own source in
# the code checkout; gitsync commits his private one, so nothing ever kept them.
# Every path a ledger entry names has to resolve against the tree that is kept.
def test_resumes_are_written_where_they_are_kept():
    import importlib, os
    from jobbot import paths as _paths
    # The suite points the individual paths at fixtures; this asks the question
    # the runners ask, where only JOBBOT_PRIVATE is set.
    overrides = ("JOBBOT_PRIVATE", "JOBBOT_OUT", "JOBBOT_DATA", "JOBBOT_PIPELINE",
                 "JOBBOT_CRITERIA", "JOBBOT_ANSWERS", "JOBBOT_TARGETS")
    was = {k: os.environ.pop(k, None) for k in overrides}
    os.environ["JOBBOT_PRIVATE"] = os.path.join(os.path.dirname(__file__), "_elsewhere")
    try:
        importlib.reload(_paths)
        t = importlib.reload(importlib.import_module("jobbot.tailor"))
        g = importlib.reload(importlib.import_module("jobbot.gitsync"))
        assert str(t.OUT).startswith(str(g.ROOT)), f"{t.OUT} is not inside {g.ROOT}"
        assert str(t.ROOT) == str(g.ROOT), f"{t.ROOT} != {g.ROOT}"
        # jobbot's own files stay with jobbot's own source.
        assert "_elsewhere" not in str(t.SAMPLE), t.SAMPLE
    finally:
        os.environ.pop("JOBBOT_PRIVATE", None)
        for k, v in was.items():
            if v is not None:
                os.environ[k] = v
        importlib.reload(_paths)
        importlib.reload(importlib.import_module("jobbot.tailor"))
        importlib.reload(importlib.import_module("jobbot.gitsync"))


test_resumes_are_written_where_they_are_kept()
print("resumes are written into the tree that is committed")


# 2026-09-25: the ledger said Snowflake's resume was ready, with a pdf, and
# resumes/Snowflake did not exist - the file had been written into the wrong
# checkout and thrown away. A card promising a resume he cannot open is worse
# than no card.
def test_ready_means_the_resume_is_there():
    import importlib, json, os, tempfile
    from pathlib import Path
    from jobbot import paths as _paths
    overrides = ("JOBBOT_PRIVATE", "JOBBOT_OUT", "JOBBOT_DATA", "JOBBOT_PIPELINE",
                 "JOBBOT_CRITERIA", "JOBBOT_ANSWERS", "JOBBOT_TARGETS")
    was = {k: os.environ.pop(k, None) for k in overrides}
    home = Path(tempfile.mkdtemp())
    os.environ["JOBBOT_PRIVATE"] = str(home)
    try:
        importlib.reload(_paths)
        importlib.reload(importlib.import_module("jobbot.tailor"))
        ss = importlib.reload(importlib.import_module("jobbot.seed_store"))
        built = home / "resumes" / "Mercury" / "Intern"
        built.mkdir(parents=True)
        (built / "resume.json").write_text("{}")
        assert ss.written({"folder": "resumes/Mercury/Intern"}) is True
        assert ss.written({"folder": "resumes/Snowflake/Intern"}) is False
        assert ss.written({}) is False
        # A folder prepared but never written is not a resume.
        empty = home / "resumes" / "Notion" / "Intern"
        empty.mkdir(parents=True)
        (empty / "brief.md").write_text("x")
        assert ss.written({"folder": "resumes/Notion/Intern"}) is False
        # And a checkout with no resumes at all is not an answer about any of them.
        bare = Path(tempfile.mkdtemp())
        os.environ["JOBBOT_PRIVATE"] = str(bare)
        importlib.reload(_paths)
        importlib.reload(importlib.import_module("jobbot.tailor"))
        ss = importlib.reload(importlib.import_module("jobbot.seed_store"))
        assert ss.written({"folder": "resumes/Mercury/Intern"}) is True
    finally:
        os.environ.pop("JOBBOT_PRIVATE", None)
        for k, v in was.items():
            if v is not None:
                os.environ[k] = v
        importlib.reload(_paths)
        importlib.reload(importlib.import_module("jobbot.tailor"))
        importlib.reload(importlib.import_module("jobbot.seed_store"))


test_ready_means_the_resume_is_there()
print("a card says Ready only when the resume is there")
