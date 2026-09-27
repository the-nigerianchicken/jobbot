"""The boards the big companies run themselves, read from saved pages.

Nothing here touches the network. What it guards is the reading: the shapes
these pages ship their postings in, and the two ways a Workday tenant can be
addressed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobbot import direct, sources

fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ok ' if ok else 'BAD'} {name}" + ("" if ok else f"   {extra}"))
    fails += 0 if ok else 1


# --- a page that keeps its postings in a JavaScript string -------------------
job = {"positionId": "200685016", "postingTitle": 'Tooling "Engineering" Intern - iPhone',
       "postDateInGMT": "2026-09-24T10:59:42.524Z", "transformedPostingTitle": "tooling-intern",
       "locations": [{"name": "Cupertino", "city": "Cupertino", "stateProvince": "California"}],
       "team": {"teamCode": "STDNT"}, "jobSummary": "Work on <b>tools</b> for iPhone. " + "x" * 400}
page = ('<html><script>window.__staticRouterHydrationData = JSON.parse(' +
        json.dumps(json.dumps({"loaderData": {"root": {"searchResults": [job]}}})) +
        ');</script></html>')

found = direct.objects_with(direct.payload(page), "postDateInGMT")
check("a posting inside a JavaScript string is read", len(found) == 1, f"got {len(found)}")
check("a quote in the title survives",
      bool(found) and found[0]["postingTitle"] == 'Tooling "Engineering" Intern - iPhone')
check("unescaping by hand would not have worked",
      len(direct.objects_with(page, "postDateInGMT")) == 0)

# --- Google's cards ----------------------------------------------------------
card = ('<li class="lLd3Je"><p class="l103df">Google | <span class="pwO9Dc">'
        '<span class="r0wTof ">Waterloo, ON, Canada</span>'
        '<span class="r0wTof p3oCrc">; Toronto, ON, Canada</span>'
        '<span class="r0wTof p3oCrc">; Waterloo, ON, Canada</span>'
        '<span class="BVHzed">; +7 more</span></span></p>'
        '<div class="Xsxa1e"><h4>Minimum qualifications</h4><ul><li>Pursuing a BS</li></ul></div>'
        '<a class="WpHeLc" href="jobs/results/123-software-engineering-intern-summer-2027?x=1" '
        'aria-label="Learn more about Software Engineering Intern, BS/MS, Summer 2027"></a></li>')
where = direct._google_where(card, "123")
check("each city is listed once", where == "Waterloo, ON, Canada; Toronto, ON, Canada; and 7 more", where)
check("the qualifications come through as the description",
      "Pursuing a BS" in direct._google_about(card, "123"))
hit = direct.G_CARD.findall(card)
check("the card gives id and real title",
      hit and hit[0][1] == "123" and hit[0][2].startswith("Software Engineering Intern"), str(hit))

# --- a title carried only by a slug ------------------------------------------
check("a slug reads as a title",
      direct._title_from_slug("senior-ml-engineer-for-ios") == "Senior ML Engineer for iOS",
      direct._title_from_slug("senior-ml-engineer-for-ios"))

# --- the two shapes of a Workday address -------------------------------------
own = sources._workday_parts("nvidia|wd5.myworkdayjobs.com|NVIDIAExternalCareerSite")
check("a tenant with its own subdomain", own[3] == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", own[3])
shared = sources._workday_parts("snapchat|wd1.myworkdaysite.com/recruiting|snap")
check("a tenant sharing a host", shared[3] == "https://wd1.myworkdaysite.com/recruiting/snapchat/snap", shared[3])

# --- seconds are seconds ------------------------------------------------------
check("epoch seconds read as this year", sources._ts(1790000000).year == 2026, str(sources._ts(1790000000)))
check("epoch milliseconds still read as this year", sources._ts(1790000000000).year == 2026,
      str(sources._ts(1790000000000)))

# --- Netflix: its own site, read through its search API ----------------------
canned = {"count": 2, "positions": [
    {"id": 790317917022, "name": "Machine Learning/AI Infrastructure Engineering Intern (AI Platform)",
     "locations": ["Los Gatos,California,United States of America"], "t_create": 1787097600,
     "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/790317917022",
     "job_description": "<p>Build the platform.</p><ul><li>Python</li><li>Spark</li></ul>"},
    {"id": 790317916733, "name": "Machine Learning/AI Scientist PhD Intern, Winter 2027",
     "location": "Los Gatos,California,United States of America", "t_create": 1787097600,
     "job_description": "<p>Research.</p>"}]}
asked = []
was_page = direct._json_page
direct._json_page = lambda url, params=None: (asked.append(params), canned)[1]
try:
    nf = direct.netflix()
finally:
    direct._json_page = was_page
check("netflix reads its own board", len(nf) == 2 and all(p.company == "Netflix" for p in nf), str(len(nf)))
check("a posting two searches both find is listed once", len({p.raw_id for p in nf}) == len(nf))
check("it stops at the last page instead of asking five times", len(asked) == 2, str(len(asked)))
ml = next((p for p in nf if p.raw_id == "790317917022"), None)
check("the date is the one Netflix published",
      ml is not None and ml.posted_at and (ml.posted_at.year, ml.posted_at.month) == (2026, 8), str(ml and ml.posted_at))
check("the description arrives without its markup",
      ml is not None and "Build the platform" in ml.description and "<p>" not in ml.description)
check("it links to the posting itself", ml is not None and ml.url.endswith("/790317917022"))
phd = next((p for p in nf if p.raw_id == "790317916733"), None)
check("a posting with one location and no link still gets both",
      phd is not None and phd.location.startswith("Los Gatos") and phd.url.endswith("/790317916733"))

# --- never tried is not never worked ------------------------------------------
from jobbot import store as _store                                # noqa: E402
def _stats(ok, fails):
    return {"ok_runs": ok, "fail_runs": fails, "consecutive_failures": 0, "postings_seen": 0,
            "matches_ever": 0, "last_ok": "2026-09-01T00:00:00+00:00" if ok else None,
            "last_error": None, "enabled": True}
gone = {"stats": {"workday:gone": _stats(0, 99), "workday:flaky": _stats(40, 99)}}
miss = {"ok": False, "count": 0, "error": "HTTPError: 422 Client Error: Unprocessable Entity"}
_store.update_health(gone, {"workday:gone": miss, "workday:flaky": miss}, {})
check("a board that never answered in a hundred tries is switched off",
      gone["stats"]["workday:gone"]["enabled"] is False)
check("one that has answered before is only having a bad day",
      gone["stats"]["workday:flaky"]["enabled"] is True)
board = {"source": "workday", "org": "x"}
check("a board not yet tried is tried eagerly", _store.is_hot(board, {"workday:x": _stats(0, 0)}))
check("one that has failed thirty times is not new any more",
      not _store.is_hot(board, {"workday:x": _stats(0, 30)}))

# --- every board is reachable through the registry ---------------------------
for name in ("google", "microsoft", "apple", "uber", "shopify", "netflix"):
    check(f"{name} is a source the watcher knows", name in sources.FETCHERS)
# A board with a fetcher of its own is part of the code, so the registry has it
# even when the registry is empty - which is what a fresh clone, or a registry
# rebuilt from the community lists, would leave behind.
from jobbot import store                                          # noqa: E402
was = store._load
store._load = lambda *a, **k: {"boards": [], "stats": {}}
try:
    listed = {(b["source"], b["org"]) for b in store.load_registry()["boards"]}
finally:
    store._load = was
for name in ("google", "microsoft", "apple", "uber", "shopify", "netflix"):
    check(f"{name} registers itself", (name, name) in listed)
check("snap registers itself, on Workday",
      ("workday", "snapchat|wd1.myworkdaysite.com/recruiting|snap") in listed)
check("every built-in board has something to read it with",
      all(b["source"] in sources.FETCHERS for b in direct.BUILTIN))

print()
sys.exit(1 if fails else 0)
