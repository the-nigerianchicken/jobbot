"""Seed the app's database from what already exists, once.

The app is the tracker from here on, so everything he has must be in it before
the switch:

  Tracker.xlsx        299 applications, back to January - his real record
  data/tailored.json  resumes built, issue numbers, labels
  data/pending.json   found, resume on the way
  data/approvals.jsonl / applications.jsonl   what he approved and what happened

Writes app/seed.sql, applied with:
    cd app && npx wrangler d1 execute jobbot --remote --file=seed.sql

Safe to run twice: jobs are replaced by uid, and an application is only
inserted if no row has the same company, title and date.
"""
import json, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import tailor

ROOT = tailor.ROOT
OUT = tailor.CODE_ROOT / "app" / "seed.sql"
TRACKER = Path(r"C:\Users\thema\OneDrive\Desktop\Resumes\Applications 2026\Tracker.xlsx")
SHEET = "Internships Applied"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

# What an apply run ends in. Anything else stopped for him.
SUBMITTED = {"submitted"}
NEEDS_HIM = {"verification", "captcha", "needs_you", "blocked", "unconfirmed", "fill_failed", "error"}
RUN_NOTE = {
    "verification": "The site emailed you a code - finish it yourself",
    "captcha": "A CAPTCHA appeared - finish it yourself",
    "blocked": "The site refused an automated submit - apply by hand",
    "unconfirmed": "Submitted but unconfirmed - check your email",
    "fill_failed": "Some fields could not be filled",
    "needs_you": "A question needs your answer",
    "error": "The apply run hit an error",
}
# His words, kept as he writes them in the spreadsheet.
OUTCOMES = {"no response": "no response", "rejected": "rejected", "oa": "OA",
            "interview": "interview", "offer": "offer", "accepted": "accepted",
            "withdrawn": "withdrawn", "ghosted": "no response"}

TERM = re.compile(r"\b(summer|winter|fall|autumn|spring)\s*'?\s*(20\d\d|\d\d)\b", re.I)


def q(value):
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def blank(value):
    """An empty cell in his spreadsheet is sometimes the word None."""
    text = str(value or "").strip()
    return None if not text or text.lower() in {"none", "n/a", "-", "null"} else text


SEASON_OF_MONTH = {1: "Winter", 2: "Winter", 3: "Winter", 4: "Winter", 5: "Summer", 6: "Summer",
                   7: "Summer", 8: "Summer", 9: "Fall", 10: "Fall", 11: "Fall", 12: "Fall"}
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}
TERM_ANY = re.compile(
    r"\b(?:(summer|winter|fall|autumn|spring)\s*'?\s*(20\d\d|\d\d)\b"
    r"|(20\d\d)\s+(summer|winter|fall|autumn|spring)\b"
    r"|(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?,?\s+(20\d\d)\b)", re.I)


# A date after these words is when the student graduates, not the term:
# "graduating between Fall 2028 and Summer 2029".
NOT_TERM = re.compile(r"graduat|degree|class of|complet|enrolled|pursuing|expected|returning to|remaining", re.I)


def term_of(*texts):
    """The terms a posting is for, from the first text that names any:
    "Summer 2027", "2027 Summer", or a start month ("January 2027" is Winter)."""
    for t in texts:
        found = []
        text = (t or "")[:6000]
        for m in TERM_ANY.finditer(text):
            if NOT_TERM.search(text[max(0, m.start() - 90):m.start()]):
                continue
            if m.group(1):
                season, year = m.group(1), m.group(2)
            elif m.group(3):
                season, year = m.group(4), m.group(3)
            else:
                season, year = SEASON_OF_MONTH[MONTHS[m.group(5)[:3].lower()]], m.group(6)
            season = "Fall" if season.lower() == "autumn" else season.title()
            year = year if len(year) == 4 else "20" + year
            if not 2025 <= int(year) <= 2029:
                continue
            name = f"{season} {year}"
            if name not in found:
                found.append(name)
        if found:
            return " / ".join(found[:3])
    return None


def failed(errors, asked):
    """What a failed build should say on a card, in his words rather than jobbot's.

    "never built" is not a failure: the run ended before reaching this posting.
    If he has not asked for it, that is just a job he has not decided about,
    so it belongs with the new ones and needs no explanation.
    """
    errors = errors or []
    if errors == ["never built"]:
        return ("building", "Waiting its turn") if asked else ("new", None)
    said = "; ".join(str(e) for e in errors[:2])[:150]
    if said:
        return "needs", f"The resume could not be built: {said}"
    return "needs", "The resume could not be built - tap Write it again"


def shots(folder):
    """Screenshots the apply run left behind, so he can see where it stopped."""
    if not folder:
        return None
    shots_dir = ROOT / folder / "apply"
    if not shots_dir.is_dir():
        return None
    found = sorted(p for p in shots_dir.glob("*.png"))
    return json.dumps([str(p.relative_to(ROOT)).replace("\\", "/") for p in found[:6]]) or None


def saved_jd(folder):
    """The description a resume was written from, for jobs that have left the queue.

    JD.md is a header, a blank line, an optional note from him, then the
    posting itself.
    """
    if not folder:
        return None
    path = ROOT / folder / "JD.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    body = text.split("\n\n", 1)[1] if "\n\n" in text else ""
    marker = "Follow it unless it would mean claiming something he has not done."
    if body.lstrip().startswith("## What the user asked for") and marker in body:
        body = body.split(marker, 1)[1]
    return body.strip()[:12000] or None


def runs():
    out = {}
    p = tailor.DATA / "applications.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["uid"]] = r                        # later lines win
    return out


def job_rows():
    ledger, pending = tailor._load("tailored.json", {}), tailor._load("pending.json", {})
    approved, last, want = tailor.approved_uids(), runs(), tailor.requested()
    # Postings a model read and found he cannot take. The rules stop matching
    # them, but they were already on the board from an earlier sweep, and this
    # list is what tells the app what jobbot still knows about - so without
    # this they simply stayed there (2026-09-24). Anything he has since acted on
    # is his: only jobbot's own untouched states are withdrawn.
    from .screen import verdicts
    turned = {uid for uid, v in verdicts().items() if not v.get("ok")}
    rows = []
    for uid, v in ledger.items():
        run, status = last.get(uid), v.get("status")
        if status in ("resume_ready", "build_failed"):
            if run and run["status"] in SUBMITTED:
                state, note = "done", "Submitted"
            elif run and run["status"] in NEEDS_HIM:
                state, note = "needs", RUN_NOTE.get(run["status"], run["status"])
            elif uid in approved:
                state, note = "working", "Applying"
            elif status == "build_failed":
                state, note = failed(v.get("errors"), uid in want)
            else:
                state, note = "ready", None
        elif status == "in_progress":
            state, note = "building", "Writing your resume"
        elif status == "retry":
            # Queued to be written again. Until he asks, it is simply a posting.
            state, note = ("building", "Writing it again") if uid in want else ("new", None)
        elif status == "cannot_build":
            # A resume already on disk outranks a later "cannot be written":
            # the card was showing both at once (2026-09-22).
            if v.get("pdf"):
                state, note = "ready", None
            else:
                state, note = "needs", v.get("reason") or "This one cannot be written"
        elif status == "skipped":
            state, note = "skipped", v.get("reason")
        else:
            continue                 # dropped (no longer matches) and already_applied (a tracker row)
        t = pending.get(uid, {})
        pick = lambda k: v.get(k) or t.get(k)
        rows.append({
            "uid": uid, "company": pick("company") or "", "title": pick("title") or "",
            "tier": pick("tier"),
            "term": term_of(" / ".join(t.get("terms") or []), v.get("title"), t.get("title"), t.get("description")),
            "location": pick("location"), "source": t.get("source"), "org": t.get("org"),
            "raw_id": t.get("raw_id"), "url": pick("url"), "apply_url": pick("apply_url"),
            "posted_at": pick("posted_at"), "deadline": pick("deadline"), "state": state, "note": note,
            "says": v.get("says"),
            "knockout": 1 if any(re.search("knockout", str(l), re.I) for l in (v.get("labels") or [])) else 0,
            "folder": v.get("folder"), "pdf": v.get("pdf"), "preview": v.get("preview"),
            "issue": v.get("issue"), "seen_at": v.get("at") or NOW, "updated_at": NOW,
            "jd": (t.get("description") or "")[:12000] or saved_jd(v.get("folder")),
            "shots": shots(v.get("folder")),
        })
    stale = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    # Shown, not hidden: the duplicate check guesses (it once took a new TD role
    # for an old one), and hiding a real posting is the failure he cares about.
    prior = tailor.prior_applications()
    for uid, t in pending.items():
        if uid in ledger:
            continue
        # One the screening turned away, and which he has not touched: it stops
        # being something jobbot knows about, so the app drops it and shows it
        # in Filtered out with the reason instead.
        if uid in turned and uid not in want and uid not in approved:
            continue
        # A posting he never asked about is not written for, and after a week
        # it stops taking up room in the feed.
        if (t.get("posted_at") or t.get("queued_at") or "") < stale and uid not in want:
            continue
        # Nothing is written until he asks: a posting he has not tapped is
        # simply a job he has not decided about yet.
        asked = uid in want
        # Applied by hand before any resume was written: it is done.
        if uid in approved or (last.get(uid) or {}).get("status") in SUBMITTED:
            rows.append({"uid": uid, "company": t.get("company", ""), "title": t.get("title", ""),
                         "tier": t.get("tier"), "location": t.get("location"), "url": t.get("url"),
                         "apply_url": t.get("apply_url"), "posted_at": t.get("posted_at"),
                         "state": "done", "note": "Submitted", "knockout": 0,
                         "seen_at": t.get("queued_at") or NOW, "updated_at": NOW})
            continue
        rows.append({"uid": uid, "company": t.get("company", ""), "title": t.get("title", ""),
                     "tier": t.get("tier"), "location": t.get("location"),
                     "term": term_of(" / ".join(t.get("terms") or []), t.get("title"), t.get("description")),
                     "source": t.get("source"), "org": t.get("org"), "raw_id": t.get("raw_id"),
                     "url": t.get("url"), "apply_url": t.get("apply_url"), "posted_at": t.get("posted_at"),
                     "deadline": t.get("deadline"),
                     "state": "building" if asked else "new",
                     "note": "Writing your resume" if asked else (
                         "Looks like one you have applied to before"
                         if tailor.already_applied(t, prior) else None),
                     "knockout": 0, "folder": None, "pdf": None, "preview": None, "issue": None,
                     "seen_at": t.get("queued_at") or NOW, "updated_at": NOW,
                     "jd": (t.get("description") or "")[:12000] or None})
    return rows


def tracker_rows():
    """Every application in the spreadsheet: company, title, date, referral, outcome, notes."""
    if not TRACKER.exists():
        print(f"no tracker at {TRACKER} - skipping his history", file=sys.stderr)
        return []
    import openpyxl
    wb = openpyxl.load_workbook(TRACKER, read_only=True, data_only=True)
    out = []
    for r in wb[SHEET].iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        date = r[2]
        out.append({"uid": None, "company": str(r[0]).strip(), "title": str(r[1] or "").strip(),
                    "applied_at": date.date().isoformat() if hasattr(date, "date") else str(date or "")[:10],
                    "outcome": OUTCOMES.get(str(r[4] or "").strip().lower(), "no response"),
                    "outcome_at": None, "referral": blank(r[3]), "notes": blank(r[5]),
                    "apply_url": None, "pdf": None,
                    "how": "tracker", "updated_at": NOW})
    wb.close()
    return out


def application_rows(jobs):
    rows = tracker_rows()
    by_uid = {j["uid"]: j for j in jobs}
    p = tailor.DATA / "approvals.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            a = json.loads(line)
            j = by_uid.get(a["uid"], {})
            rows.append({"uid": a["uid"], "company": a.get("company") or j.get("company") or "",
                         "title": a.get("title") or j.get("title") or "",
                         "applied_at": (a.get("approved_at") or NOW)[:10], "outcome": "no response",
                         "outcome_at": None, "referral": None, "notes": None,
                         "apply_url": a.get("apply_url"), "pdf": a.get("pdf"),
                         "how": "by hand" if a.get("by_hand") else "jobbot", "updated_at": NOW})
    return rows


JOB_COLS = ["uid", "company", "title", "tier", "term", "location", "source", "org", "raw_id", "url",
            "apply_url", "posted_at", "deadline", "state", "note", "knockout", "folder", "pdf",
            "preview", "issue", "seen_at", "updated_at", "jd", "shots"]
APP_COLS = ["uid", "company", "title", "applied_at", "outcome", "outcome_at", "referral", "notes",
            "apply_url", "pdf", "how", "updated_at"]


def main(argv=None):
    jobs = job_rows()
    apps = application_rows(jobs)
    sql = []
    for j in jobs:
        sql.append(f"INSERT OR REPLACE INTO jobs ({', '.join(JOB_COLS)}) VALUES "
                   f"({', '.join(q(j.get(c)) for c in JOB_COLS)});")
    for a in apps:
        sql.append(f"INSERT INTO applications ({', '.join(APP_COLS)}) "
                   f"SELECT {', '.join(q(a.get(c)) for c in APP_COLS)} WHERE NOT EXISTS "
                   f"(SELECT 1 FROM applications WHERE company = {q(a['company'])} "
                   f"AND title = {q(a['title'])} AND applied_at = {q(a['applied_at'])});")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(sql) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(jobs)} jobs, {len(apps)} applications")
    return 0


if __name__ == "__main__":
    sys.exit(main())
