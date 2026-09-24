"""Screening, without a model.

What is checked here is everything around the question: which postings are
worth asking about, how little of each is sent, that nothing is asked twice,
and that a "no" reaches the rules as a drop he can undo. The judgement itself
belongs to the model and is not simulated.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JOBBOT_DATA"] = tempfile.mkdtemp()

from jobbot import match, screen          # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ok ' if ok else 'BAD'} {name}" + ("" if ok else f"   {extra}"))
    fails += 0 if ok else 1


# --- who gets asked about ----------------------------------------------------
rows = [
    {"uid": "plain", "company": "Acme", "title": "Software Engineer Intern",
     "description": "Build backend services in Go. Summer 2027. Toronto."},
    {"uid": "cit", "company": "Astranis", "title": "Backend Software Engineer Intern",
     "location": "San Francisco, CA",
     "description": "x" * 3000 + " U.S. Citizenship, Lawful Permanent Residency, or "
                                 "Refugee/Asylee Status Required to comply with export rules." + "y" * 3000},
    {"uid": "team", "company": "Entrust", "title": "Intern, Software Development",
     "location": "Ottawa, ON",
     "description": "For Entrust's Citizen Remote Identity Verification team, hybrid in Ottawa."},
    {"uid": "phd", "company": "Waymo", "title": "Software Engineer Intern - MS/PhD",
     "location": "Mountain View, CA",
     "description": "Currently enrolled in an MS or PhD program in Computer Science."},
]
ask = screen.candidates(rows, {})
asked = [a["uid"] for a in ask]
check("a posting with nothing to weigh is never sent", "plain" not in asked, str(asked))
check("citizenship, a team name and a degree all get asked about",
      set(asked) == {"cit", "team", "phd"}, str(asked))

# --- how little is sent ------------------------------------------------------
big = next(a for a in ask if a["uid"] == "cit")
check("only the part that matters is sent", len(big["text"]) <= screen.MOST,
      f"{len(big['text'])} characters of a 6,000-character posting")
check("and it is the part that matters", "Refugee/Asylee" in big["text"])
check("where the seat is comes with it, because it decides the answer",
      big["in_canada"] is False and next(a for a in ask if a["uid"] == "team")["in_canada"] is True)

# --- nothing is asked twice --------------------------------------------------
again = screen.candidates(rows, {"cit": {"ok": False}, "team": {"ok": True}})
check("a posting already judged is not asked about again",
      [a["uid"] for a in again] == ["phd"], str([a["uid"] for a in again]))
check("and a run is capped", len(screen.candidates(rows * 40, {}, limit=5)) == 5)

# --- the answer reaches the rules --------------------------------------------
screen._save(screen.ASK, ask)
screen._save(screen.SAY, [
    {"uid": "cit", "ok": False, "why": "needs US citizenship or permanent residency"},
    {"uid": "team", "ok": True},
    {"uid": "nonsense", "ok": False, "why": "not a posting anyone asked about"},
])


class Args:
    pass


screen.cmd_apply(Args())
kept = screen.verdicts()
check("a no is kept with its reason", kept["cit"]["ok"] is False and "citizenship" in kept["cit"]["why"])
check("a yes is kept too, so it is never asked again", kept["team"]["ok"] is True)
check("an answer about something never asked is ignored", "nonsense" not in kept)
check("one left unanswered stays undecided", "phd" not in kept)

# --- and shows up as a drop he can undo --------------------------------------
crit = json.loads(json.dumps({
    "titles": {"require_any": ["software engineer"], "exclude_any": [], "seniority_exclude": []},
    "terms": {"require_any": ["2027"], "exclude_any": [], "require_in_title_any": ["intern"]},
    "locations": {"preferred": [], "allowed_countries": [], "exclude_any": [], "canada_markers": ["ontario"]},
    "eligibility": {"drop_outside_canada_if_description_contains": [], "flag_if_description_contains": []},
    "freshness": {},
}))


class P:
    source, org, raw_id, deadline, remote = "greenhouse", "x", "", None, False
    posted_at = None
    age_hours = None

    def __init__(self, uid, title, location, description):
        self._uid, self.title, self.location, self.description = uid, title, location, description
        self.company, self.url, self.apply_url = "Astranis", "", ""

    @property
    def uid(self):
        return self._uid


match.screened(refresh=True)
m, why = match.classify(P("cit", "Software Engineer Intern 2027", "San Francisco, CA", "x"), crit)
check("a posting he cannot take is dropped", m is None, str(why))
check("with the model's own words as the reason",
      why and "citizenship" in why and why.startswith("not eligible"), str(why))
m2, _ = match.classify(P("team", "Software Engineer Intern 2027", "Ottawa, Ontario", "x"), crit)
check("one it cleared is kept", m2 is not None)
m3, _ = match.classify(P("never-asked", "Software Engineer Intern 2027", "Ottawa, Ontario", "x"), crit)
check("one it never saw is kept", m3 is not None)

print()
sys.exit(1 if fails else 0)
