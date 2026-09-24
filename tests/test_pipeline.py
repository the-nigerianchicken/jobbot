"""Offline end-to-end test of filter + rank + dedup + notify, no network.

Previously read a listings.json from the old cloud sandbox (/tmp/s27), so it
could only run there. The fixtures are now inline.
"""
import json, os, sys, tempfile
from datetime import datetime, timezone, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["JOBBOT_DATA"] = tempfile.mkdtemp()

import yaml
from jobbot.model import Posting
from jobbot import match, notify, store

crit = yaml.safe_load(open(os.path.join(ROOT, "criteria.yaml")))
targets = open(os.path.join(ROOT, "jobbot", "targets.txt")).read().split()
now = datetime.now(timezone.utc)

TITLES = [
    "Software Engineer Intern (Summer 2027)", "Backend Engineering Co-op - Winter 2027",
    "Machine Learning Engineer Intern, Summer 2027", "Data Analyst Intern (Summer 2027)",
    "Product Manager Intern 2027", "Business Operations Intern", "Senior Software Engineer",
    "Data Science Intern, Summer 2027", "Frontend Developer Intern (Winter 2027)",
]
COMPANIES = [("Shopify", "Toronto, ON"), ("Stripe", "San Francisco, CA"),
             ("SmallCo", "Waterloo, ON"), ("OtherCo", "Austin, TX"), ("FarCo", "Berlin, Germany")]

postings = []
for ci, (company, loc) in enumerate(COMPANIES):
    for ti, title in enumerate(TITLES):
        postings.append(Posting(
            source="greenhouse", org=company.lower(), company=company, title=title,
            location=loc, url=f"https://x/{ci}/{ti}", apply_url=f"https://x/{ci}/{ti}",
            posted_at=now - timedelta(hours=ci * 10 + ti), description="Summer 2027 internship",
            raw_id=f"{ci}-{ti}"))
print(f"fixture postings: {len(postings)}")

matches, drops = match.run(postings, crit, targets)
print(f"passing filter: {len(matches)}")
for m in matches:
    print(f"  [T{m.tier}] {m.posting.company:8} | {m.posting.title}")
assert matches, "nothing passed"

tiers = [m.tier for m in matches]
assert tiers == sorted(tiers), "matches not ordered by tier"
assert all(m.posting.company != "FarCo" for m in matches), "geography leak"

bad = [m for m in matches if any(b in m.posting.title.lower() for b in
       ["analyst", "analytics", "data scien", "product manager", "operations", "senior"])]
assert not bad, f"banned titles leaked: {[m.posting.title for m in bad]}"
print("filter OK")

seen = {}
half = len(matches) // 2
for m in matches[:half]:
    store.mark_seen(seen, m.posting)
store.save_seen(seen)
again = [m for m in matches if m.posting.uid not in store.load_seen()]
assert len(again) == len(matches) - half, "dedup broken"
print("dedup OK - uid stable across save/load")

queue = os.path.join(os.environ["JOBBOT_DATA"], "queue.json")
json.dump([{"tier": m.tier, "reasons": m.reasons, **m.posting.to_dict()} for m in again],
          open(queue, "w"))
rc = notify.main([queue])
ncfg = crit.get("notify") or {}
want = 1 if ncfg.get("fail_on_match", True) and any(
    m.tier in ncfg.get("alert_tiers", [1, 2]) for m in again) else 0
assert rc == want, f"notify exit {rc}, wanted {want}"
json.dump([], open(queue, "w"))
assert notify.main([queue]) == 0
assert notify.main([queue, "--test"]) == 1, "--test must always fail the step"
print("notify OK")
