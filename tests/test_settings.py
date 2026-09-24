"""His Settings from the app, applied on top of the files."""
import copy, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobbot import match, questions, settings, tailor, watch
from jobbot.model import Posting

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("ok   " if ok else "BAD  ") + name + ("" if ok else "   " + str(extra)))
    fails += 0 if ok else 1


tmp = Path(tempfile.mkdtemp()) / "settings.json"
settings.FILE = tmp


def save(section, value, base):
    data = json.loads(tmp.read_text()) if tmp.exists() else {}
    data[section] = {"value": value, "value_base": base}
    tmp.write_text(json.dumps(data))


def posting(title, loc, hours=1, desc="Summer 2027 internship"):
    return Posting(source="greenhouse", org="smallco", company="SmallCo", title=title, location=loc,
                   url="u", apply_url="u", posted_at=datetime.now(timezone.utc) - timedelta(hours=hours),
                   description=desc, raw_id=title)


# ---------------------------------------------------------------- merging ---
check("an untouched field follows the file",
      settings.merge3({"a": 2, "b": 1}, {"a": 1, "b": 1}, {"a": 1, "b": 5}) == {"a": 2, "b": 5})
check("a field he changed stays his even when the file changes",
      settings.merge3({"a": 2}, {"a": 1}, {"a": 9}) == {"a": 9})
check("a record added to the file later still arrives",
      [x["id"] for x in settings.merge3([{"id": "x"}, {"id": "new"}], [{"id": "x"}], [{"id": "x", "v": 1}])]
      == ["x", "new"])
check("a record he removed stays removed",
      settings.merge3([{"id": "x"}, {"id": "y"}], [{"id": "x"}, {"id": "y"}], [{"id": "x", "v": 1}])
      == [{"id": "x", "v": 1}])

# ----------------------------------------------------------------- search ---
raw = watch.load_criteria(os.path.join(settings.ROOT, "criteria.yaml"))
base = settings.search_base(raw)
check("with nothing saved, the search is criteria.yaml", watch.load_criteria() == raw)
mine = copy.deepcopy(base)
mine["seasons"]["Summer 2027"] = False
mine["roles_wanted"].append("robotics")
mine["roles_excluded"].remove("quant")
mine["window_hours"] = 72
mine["places"]["us"] = False
save("search", mine, base)
crit = watch.load_criteria()
drop = lambda p: match.classify(p, crit, [])[1]
check("a term he turned off is dropped", (drop(posting("Software Engineer Intern", "Toronto, ON",
                                                       desc="Summer 2027 internship")) or "").startswith("wrong term"))
check("a role he added is wanted", drop(posting("Robotics Intern (Winter 2027)", "Toronto, ON",
                                                desc="Winter 2027")) is None)
check("a role he stopped excluding comes through",
      drop(posting("Quant Developer Intern (Winter 2027)", "Toronto, ON", desc="Winter 2027")) is None)
check("his posting window is used",
      drop(posting("Software Engineer Intern (Winter 2027)", "Toronto, ON", hours=60, desc="Winter 2027")) is None)
check("a place he turned off is dropped",
      (drop(posting("Software Engineer Intern (Winter 2027)", "Austin, TX", desc="Winter 2027")) or "")
      .startswith("place turned off"))
check("a posting with a seat he wants stays",
      drop(posting("Software Engineer Intern (Winter 2027)", "Toronto, ON; New York, NY", desc="Winter 2027")) is None)
new_grad = copy.deepcopy(base)
new_grad["levels"]["new_grad"] = True
save("search", new_grad, base)
crit = watch.load_criteria()
check("turning on new grad lets new-grad titles through",
      match.classify(posting("Software Engineer, New Grad 2027", "Toronto, ON", desc="2027"), crit, [])[0] is not None)
tmp.unlink()

# ---------------------------------------------------------------- profile ---
rawp = tailor.load_profile(raw=True)
pbase = settings.profile_base(rawp)
mine = copy.deepcopy(pbase)
mine["contact"]["phone"] = "+1 (416) 555-0100"
mine["education"]["gpa"] = "3.61"
first = mine["entries"][0]
first["facts"][0]["text"] = "Shipped an agent that answers benefits questions."
first["facts"][0]["metrics"] = ["40% fewer escalations"]
first["facts"].append({"id": "", "text": "Wrote the eval harness.", "metrics": [], "tech": ["Python"]})
off = next(e for e in mine["entries"] if e["kind"] == "project")
off["use"] = False
mine["notes"] = "I prefer backend roles."
save("profile", mine, pbase)
p = tailor.load_profile()
check("his phone reaches the resume header",
      "+1 (416) 555-0100" in p["latex"]["header"] and rawp["identity"]["phone"] not in p["latex"]["header"])
check("his GPA reaches the education line", "3.61" in p["education"][0]["latex"])
f0 = p["experience"][0]["facts"][0]
check("an edited fact is used, with its new number",
      f0["text"].startswith("Shipped an agent") and f0["metrics"] == ["40% fewer escalations"])
check("an added fact gets an id the verifier can cite",
      any(f["id"].endswith(".app2") and f["tech"] == ["Python"] for f in p["experience"][0]["facts"]))
check("an entry he turned off is not offered", off["id"] not in [x["id"] for x in p["projects"]])
check("his notes reach the writer", p.get("notes_from_him") == "I prefer backend roles.")
bank = questions.load_bank()
check("forms get the same phone", bank["identity"]["phone"] == "+1 (416) 555-0100")

# ---------------------------------------------------------------- answers ---
abase = settings.answers_base()
mine = dict(abase, relocate="No", demographics="ask", how_heard="LinkedIn")
save("answers", mine, abase)
bank = questions.load_bank()
first_rule = lambda text: next(r for r in bank["rules"] if __import__("re").search(r["match"], text))
check("relocation answer is his", first_rule("are you willing to relocate?")["value"] == "No")
check("demographics come to him instead of declining", first_rule("what is your gender?").get("needs_you"))
check("how he heard is his", first_rule("how did you hear about us?")["value"] == "LinkedIn")

# ------------------------------------------------------------ nothing set ---
tmp.unlink()
check("with nothing saved, the profile is the file", tailor.load_profile() == rawp)

print()
sys.exit(1 if fails else 0)
