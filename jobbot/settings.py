"""His settings from the app, laid over the files they start from.

The files stay the defaults: criteria.yaml (what to look for), answers.yaml
(form answers), pipeline/profile.yaml (his facts, synced from OneDrive) and
pipeline/PIPELINE.md (his resume rules). What he changes in the app's Settings
is kept in the app, fetched at the start of every run into data/settings.json,
and applied here on top of those files.

A change is kept together with the default it was made against. Anything he
did not touch keeps following the file, so editing profile.yaml on OneDrive
still reaches every field he has not overridden in the app.

    python -m jobbot.settings pull     # fetch from the app into data/settings.json
    python -m jobbot.settings show     # print what is in effect
"""
import copy, json, re, sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# Under data/, so JOBBOT_DATA points the tests at a copy of their own rather
# than at what he has saved in the app.
from . import paths, store
FILE = Path(store.DATA) / "settings.json"
SECTIONS = ("search", "profile", "resume", "answers")

# Terms he can pick. Any he does not want are dropped when a posting names them.
SEASONS = ["Fall 2026", "Winter 2027", "Spring 2027", "Summer 2027", "Fall 2027",
           "Winter 2028", "Spring 2028", "Summer 2028"]
# The words that put a title at a level; each level is on or off.
LEVELS = {
    "internship": ["intern", "interns", "internship", "internships", "co-op", "coop", "co op",
                   "student", "work term"],
    "new_grad": ["new grad", "new graduate", "early career", "entry level", "graduate program",
                 "emerging talent", "university grad"],
}
US_MARKER = re.compile(r"\b(united states|usa|u\.s\.|us|nyc|sf|ny|ca|wa|tx|ma|il|co|ga|nc|va|pa|nj|"
                       r"new york|san francisco|seattle|boston|austin|chicago)\b", re.I)

ANSWER_INSTRUCTIONS = """- First person, and it should sound like him: direct, specific, a bit warm, no
  corporate throat-clearing ("I am writing to express my interest..."). Two to
  four sentences unless the question asks for more.
- Lead with something concrete he built, then why this team. Name something real
  from the posting - the product, the stack, the problem - so it could not be sent
  to any other company.
- Opinions, motivation and enthusiasm are his to state: say what he finds
  interesting and why, and commit to it rather than hedging.
- He reads every answer before it is submitted, so write the confident version.
  You may put plausible detail around his real work (what a project did, why he
  built it, what he would try next). Do not invent an employer, a job title, a
  degree, a GPA or a certification.
- Select: exactly one of the listed options. Multiselect: options joined with "; ".
- Years of experience: count from his dated roles.
- Where the honest answer is small, say it plainly and move on - never apologise
  for it and never pad it."""


# --------------------------------------------------------------------------- #
# stored edits
# --------------------------------------------------------------------------- #

def merge3(now, then, mine):
    """His value where he changed it from the default he saw; the current
    default everywhere else. Lists of records merge by id; other lists are one
    value."""
    if mine is None:
        return now
    if then is not None and mine == then:
        return now
    if isinstance(mine, dict) and isinstance(now, dict):
        then = then if isinstance(then, dict) else {}
        out = {k: merge3(now.get(k), then.get(k), v) for k, v in mine.items()}
        for k, v in now.items():
            if k not in mine:
                out[k] = v
        return out
    if (isinstance(mine, list) and isinstance(now, list) and mine and now
            and all(isinstance(x, dict) and "id" in x for x in mine + now)):
        before = {x["id"]: x for x in (then or []) if isinstance(x, dict) and "id" in x}
        current = {x["id"]: x for x in now}
        out = [merge3(current.get(x["id"]), before.get(x["id"]), x) for x in mine]
        # A record added to the file since he last saved still arrives.
        seen = {x["id"] for x in mine}
        out += [x for x in now if x["id"] not in seen and x["id"] not in before]
        return out
    return mine


def stored():
    """{section: {"value": ..., "value_base": ...}} as last fetched from the app."""
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def effective(section, base):
    s = stored().get(section) or {}
    return merge3(base, s.get("value_base"), s.get("value")) if s.get("value") is not None else base


def pull():
    """Fetch his settings from the app. Returns True when they changed."""
    from . import appsync
    if not appsync.BASE or not appsync.TOKEN:
        return False
    try:
        got = appsync.call("/api/settings?raw=1").get("raw") or {}
    except Exception as e:                      # the app being down must not stop a run
        print(f"settings: could not fetch ({e}); using the last copy")
        return False
    new = {k: {"value": v.get("value"), "value_base": v.get("value_base")}
           for k, v in got.items() if k in SECTIONS and v.get("value") is not None}
    if new == stored():
        return False
    FILE.write_text(json.dumps(new, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"settings: {len(new)} section(s) changed in the app: {', '.join(sorted(new)) or 'all reset'}")
    return True


# --------------------------------------------------------------------------- #
# the files, as the app shows them
# --------------------------------------------------------------------------- #

def _raw_criteria():
    return yaml.safe_load(paths.CRITERIA.read_text(encoding="utf-8"))


def _raw_bank():
    return yaml.safe_load(paths.ANSWERS.read_text(encoding="utf-8"))


def search_base(crit=None):
    crit = crit or _raw_criteria()
    t, ti, loc = crit["terms"], crit["titles"], crit["locations"]
    fresh = crit.get("freshness") or {}
    excluded = {x.lower() for x in t.get("exclude_any", [])}
    return {
        "seasons": {s: s.lower() not in excluded for s in SEASONS},
        "levels": {"internship": True,
                   "new_grad": not any(w in [x.lower() for x in ti["exclude_any"]] for w in LEVELS["new_grad"])},
        "roles_wanted": list(ti["require_any"]),
        "roles_excluded": [x for x in ti["exclude_any"] if x.lower() not in LEVELS["new_grad"]],
        "window_hours": fresh.get("max_age_hours", 24),
        "window_following_hours": (fresh.get("max_age_hours_by_tier") or {}).get(1, 72),
        "places": {"canada": True, "us": True, "remote": True},
        "places_excluded": [],
        "hide_no_sponsor": bool(crit["eligibility"].get("drop_outside_canada_if_description_contains")),
    }


def profile_base(profile=None):
    from . import tailor
    p = profile or _raw_profile()
    ident, edu = p["identity"], p["education"][0]
    bank = _raw_bank()["identity"]

    def facts(entry):
        return [{"id": f["id"], "text": f.get("text", ""), "metrics": list(f.get("metrics") or []),
                 "tech": list(f.get("tech") or [])} for f in entry.get("facts") or []]

    entries = [{"id": e["id"], "kind": "experience", "name": e.get("employer", ""), "role": e.get("title", ""),
                "dates": " - ".join(filter(None, [e.get("start"), e.get("end")])), "use": True,
                "facts": facts(e)} for e in p["experience"]]
    entries += [{"id": e["id"], "kind": "project", "name": e.get("name", ""), "role": "", "dates": "",
                 "use": True, "facts": facts(e)} for e in p["projects"]]
    return {
        "contact": {k: ident.get(k, "") for k in ("name", "email", "phone", "location", "linkedin", "github")}
                   | {"website": ""},
        "education": {"school": edu.get("institution", ""), "degree": edu.get("degree", ""),
                      "degree_level": bank.get("degree", ""), "major": bank.get("major", ""),
                      "gpa": str(bank.get("gpa", "")), "start_month": bank.get("school_start_month", ""),
                      "start_year": str(bank.get("school_start_year", "")),
                      "coursework": edu.get("coursework", ""),
                      "grad_by_term": dict(edu.get("grad_by_term") or {})},
        "notes": "",
        "entries": entries,
        "skills": {k: list(v) for k, v in (p.get("skills") or {}).items()},
    }


# Which Claude writes the resumes. Empty means whatever the action ships with.
MODELS = [["", "Default"], ["claude-opus-5", "Opus 5 - the most careful"],
          ["claude-sonnet-5", "Sonnet 5 - balanced"], ["claude-haiku-4-5-20251001", "Haiku 4.5 - the fastest"]]


def resume_base():
    """PIPELINE.md is the laptop's flow: saving JD.md, the JD index, .tex files,
    the tracker, a summary written back to him. None of that exists in a cloud
    run, and handing it over sent the writer after tools it does not have
    (2026-09-22). WRITING_RULES.md is the same judgment, without the mechanics."""
    for name in ("WRITING_RULES.md", "PIPELINE.md"):
        rules = paths.PIPELINE / name
        if rules.exists():
            return {"model": "", "instructions": "", "rules": rules.read_text(encoding="utf-8")}
    return {"model": "", "instructions": "", "rules": ""}


def answers_base(bank=None, profile=None):
    bank = bank or _raw_bank()
    jobs = (profile or {}).get("experience") or []
    employer = (jobs[0].get("employer") if jobs else "") or ""
    return {
        "form_location": bank["identity"].get("location", ""),
        "current_employer": employer,
        "sponsorship_us": bank["sponsorship_text"]["us"],
        "sponsorship_canada": bank["sponsorship_text"]["canada"],
        "relocate": "Yes", "onsite": "Yes",
        "demographics": "decline",
        "how_heard": "Company careers page",
        "instructions": ANSWER_INSTRUCTIONS,
    }


def bases():
    """What the app shows as the default for each section."""
    profile = _raw_profile()
    return {"search": search_base(), "profile": profile_base(profile), "resume": resume_base(),
            "answers": answers_base(profile=profile)}


def _raw_profile():
    from . import tailor
    return tailor.load_profile(raw=True)


# --------------------------------------------------------------------------- #
# applying them
# --------------------------------------------------------------------------- #

def apply_search(crit):
    s = effective("search", search_base(crit))
    if s == search_base(crit):
        return crit
    crit = copy.deepcopy(crit)
    t, ti = crit["terms"], crit["titles"]
    seasons = {x.lower() for x in SEASONS}
    t["exclude_any"] = ([x for x in t["exclude_any"] if x.lower() not in seasons]
                        + [k.lower() for k, on in s["seasons"].items() if not on])
    t["require_any"] = list(dict.fromkeys(t["require_any"] + [k.lower() for k, on in s["seasons"].items() if on]))
    levels = s.get("levels") or {}
    t["require_in_title_any"] = [w for lvl, on in levels.items() if on for w in LEVELS.get(lvl, [])] \
        or t["require_in_title_any"]
    ti["require_any"] = list(s["roles_wanted"])
    ti["exclude_any"] = list(s["roles_excluded"]) + ([] if levels.get("new_grad") else LEVELS["new_grad"])
    fresh = crit.setdefault("freshness", {})
    fresh["max_age_hours"] = int(s["window_hours"])
    fresh["max_age_hours_by_tier"] = {1: int(s["window_following_hours"])}
    crit["locations"]["allow"] = dict(s["places"])
    crit["locations"]["exclude_any"] = list(crit["locations"]["exclude_any"]) + list(s.get("places_excluded") or [])
    if not s.get("hide_no_sponsor", True):
        crit["eligibility"]["drop_outside_canada_if_description_contains"] = []
    return crit


def seat_kinds(loc, in_canada):
    """Which of canada / us / remote a posting's locations offer."""
    kinds = set()
    if in_canada:
        kinds.add("canada")
    if "remote" in (loc or "").lower():
        kinds.add("remote")
    if not in_canada or US_MARKER.search(loc or ""):
        if not (kinds == {"remote"} and not US_MARKER.search(loc or "")):
            kinds.add("us")
    return kinds


def _swap(text, old, new):
    return text.replace(old, new) if old and new and old != new and isinstance(text, str) else text


def apply_profile(profile):
    base = profile_base(profile)
    p = effective("profile", base)
    if p == base:
        return profile
    out = copy.deepcopy(profile)
    lx, edu = out.get("latex") or {}, out["education"][0]
    for k, v in p["contact"].items():
        old = base["contact"].get(k)
        if k in out["identity"]:
            out["identity"][k] = v
        if "header" in lx:
            lx["header"] = _swap(lx["header"], old, v)
    e = p["education"]
    for key, field in (("school", "institution"), ("degree", "degree"), ("coursework", "coursework")):
        edu["latex"] = _swap(edu.get("latex", ""), base["education"][key], e[key])
        edu[field] = e[key]
    edu["latex"] = _swap(edu.get("latex", ""), base["education"]["gpa"], e["gpa"])
    edu["gpa"] = _swap(edu.get("gpa", ""), base["education"]["gpa"], e["gpa"])
    edu["grad_by_term"] = dict(e["grad_by_term"])
    mine = {x["id"]: x for x in p["entries"]}
    for group in ("experience", "projects"):
        kept = []
        for entry in out[group]:
            m = mine.get(entry["id"])
            if m and m.get("use") is False:
                continue
            if m:
                was = {f["id"]: f for f in entry.get("facts") or []}
                facts = []
                for f in m["facts"]:
                    old = was.get(f["id"], {"id": f["id"] or f"{entry['id']}.app{len(facts) + 1}",
                                             "frames": [], "provenance": "his own words, from the app"})
                    facts.append({**old, "id": old["id"], "text": f["text"],
                                  "metrics": list(f.get("metrics") or []), "tech": list(f.get("tech") or [])})
                entry["facts"] = facts
            kept.append(entry)
        out[group] = kept
    out["skills"] = p["skills"]
    if p.get("notes"):
        out["notes_from_him"] = p["notes"]
    return out


def apply_bank(bank, profile=None):
    """answers.yaml, with his contact, education and standard answers."""
    pb = effective("profile", profile_base(profile)) if profile is not None else None
    a = effective("answers", answers_base(bank, profile))
    bank = copy.deepcopy(bank)
    ident = bank["identity"]
    if pb:
        c, e = pb["contact"], pb["education"]
        name = c.get("name", "").split()
        if name:
            ident["first_name"], ident["last_name"], ident["full_name"] = name[0], " ".join(name[1:]), c["name"]
        ident.update({"email": c["email"], "phone": c["phone"], "linkedin": c["linkedin"], "github": c["github"],
                      "school": e["school"], "degree": e["degree_level"], "major": e["major"], "gpa": e["gpa"],
                      "school_start_month": e["start_month"], "school_start_year": e["start_year"]})
    ident["location"] = a["form_location"]
    bank["sponsorship_text"] = {"us": a["sponsorship_us"], "canada": a["sponsorship_canada"]}
    yes_no = lambda v: {"option": "^yes" if v == "Yes" else "^no", "value": v}
    first = [
        {"match": "relocat", **yes_no(a["relocate"])},
        {"match": "on-?site|in[- ]office|hybrid|commut|in person|anchor day", **yes_no(a["onsite"])},
        {"match": "how did you (hear|find|learn)|where did you (hear|find)",
         "option": ["career", "company (web)?site|website", "job (board|site)", "^other"], "value": a["how_heard"]},
        {"match": "current (company|employer)|^org(anization)?$", "value": a["current_employer"]},
    ]
    if a["demographics"] != "decline":
        first.insert(0, {"match": "gender|pronoun|race|ethnic|hispanic|latino|veteran|disabilit|sexual orientation|"
                                  "transgender|lgbt", "needs_you": True})
    if pb and pb["contact"].get("website"):
        first.append({"match": "portfolio|personal (web)?site|website", "value": pb["contact"]["website"]})
    bank["rules"] = first + bank["rules"]
    return bank


def brief_sections():
    """What the resume writer reads from his settings, after the defaults."""
    r = effective("resume", resume_base())
    a = effective("answers", answers_base())
    return r, a


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    what = argv[0] if argv else "show"
    if what == "pull":
        changed = pull()
        if changed and "--push" in argv:
            from . import gitsync
            gitsync.push("settings changed in the app", ["data/settings.json"])
        return 0
    for k in SECTIONS:
        print(f"{k}: {'edited in the app' if (stored().get(k) or {}).get('value') is not None else 'defaults'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
