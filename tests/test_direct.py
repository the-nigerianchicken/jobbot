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

# --- every board is reachable through the registry ---------------------------
for name in ("google", "microsoft", "apple", "uber", "shopify"):
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
for name in ("google", "microsoft", "apple", "uber", "shopify"):
    check(f"{name} registers itself", (name, name) in listed)
check("snap registers itself, on Workday",
      ("workday", "snapchat|wd1.myworkdaysite.com/recruiting|snap") in listed)
check("every built-in board has something to read it with",
      all(b["source"] in sources.FETCHERS for b in direct.BUILTIN))

print()
sys.exit(1 if fails else 0)
