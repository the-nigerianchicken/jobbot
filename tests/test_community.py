"""The community lists as a source: offline, with rows shaped like the real file."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobbot import community, match, watch
from jobbot.model import Posting

fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ok ' if ok else 'BAD'} {name}" + ("" if ok else f"   {extra}"))
    fails += 0 if ok else 1


now = int(time.time())
row = lambda **kw: {"active": True, "is_visible": True, "category": "Software", "sponsorship": "Other",
                    "company_name": "Tesla", "title": "Software Engineer Intern",
                    "locations": ["Palo Alto, CA"], "url": "https://www.tesla.com/careers/job/1",
                    "date_posted": now - 3600, "id": "x1", **kw}
rows = [
    row(),
    row(id="gh", company_name="Robinhood", url="https://boards.greenhouse.io/robinhood/jobs/8123225"),
    row(id="hw", category="Hardware", url="https://hw"),
    row(id="off", active=False, url="https://off"),
    row(id="cit", company_name="Lockheed", sponsorship="U.S. Citizenship is Required", url="https://lm/1"),
    row(id="ok", company_name="Stripe", sponsorship="Offers Sponsorship", url="https://stripe/1"),
    row(id="dup", url="https://www.tesla.com/careers/job/1"),
]
got = community.fetch("simplify", get=lambda url, **kw: rows)
by = {p.raw_id: p for p in got}

check("active software postings come through", "x1" in by and "gh" in by)
check("hardware and closed postings do not", "hw" not in by and "off" not in by)
check("the same link listed twice is one posting", "dup" not in by)
check("the list's own date is the posted time", by["x1"].posted_at and by["x1"].age_hours < 2)
check("a greenhouse link knows its native uid",
      by["gh"].alias == community._uid("greenhouse", "robinhood", "8123225"))
check("citizenship required is carried into the text", "Citizenship" in by["cit"].description)
check("offering sponsorship is not", by["ok"].description == "")

# Native copies win: they have the full job description.
native = Posting(source="greenhouse", org="robinhood", company="Robinhood", title="Backend intern",
                 location="Toronto", url="u", apply_url="u", posted_at=None, raw_id="8123225")
kept = community.dedupe(got + [native], seen={})
check("a posting jobbot reads itself is not repeated from the list",
      not any(p.source == "community" and p.raw_id == "gh" for p in kept))
kept = community.dedupe(got, seen={community._uid("greenhouse", "robinhood", "8123225"): {}})
check("nor one it has already seen on an earlier run",
      not any(p.source == "community" and p.raw_id == "gh" for p in kept))
wd = Posting(source="workday", org="t|wd1.myworkdayjobs.com|s", company="Tesla",
             title="Software Engineer Intern", location="", url="w", apply_url="w", posted_at=None, raw_id="JR1")
check("workday copies are matched on company and title",
      not any(p.source == "community" and p.raw_id == "x1" for p in community.dedupe(got + [wd], seen={})))

# Through his real criteria: a US seat that needs citizenship is dropped.
crit, targets = watch.load_criteria(), watch.load_targets()
m_cit, why = match.classify(by["cit"], crit, targets)
check("a US internship requiring citizenship is dropped by his rules", m_cit is None, why)
m_ok, why = match.classify(by["x1"], crit, targets)
check("a fresh US software internship at a company he follows passes", m_ok is not None, why)

check("the ATS ids come out of the usual link shapes",
      community.native("https://job-boards.greenhouse.io/figma/jobs/5555") ==
      community._uid("greenhouse", "figma", "5555") and
      community.native("https://jobs.lever.co/sep/abc-123") == community._uid("lever", "sep", "abc-123") and
      community.native("https://jobs.ashbyhq.com/base/xyz") == community._uid("ashby", "base", "xyz") and
      community.native("https://www.tesla.com/careers/job/1") is None)

board = {"jobs": [{"id": "other", "descriptionPlain": "not this one"},
                  {"id": "abc-123", "descriptionPlain": "Build agents with Python."}]}
check("an Ashby posting's text comes from Ashby's board API",
      community.describe("https://jobs.ashbyhq.com/withpace/abc-123",
                         get=lambda u: board if "posting-api/job-board/withpace" in u else None)
      == "Build agents with Python.")

# A careers page read whole gives its menus as bullets with nothing in them.
filler = "You will build services with Python and Go on the platform team, write tests and ship. " * 12
page = ("<html><nav><ul><li><a>Jobs</a></li><li><a>About</a></li><li><a>About</a></li></ul></nav>"
        "<main><h1>Software Engineer Intern</h1><p>" + filler + "</p>"
        "<ul><li>Qualifications: pursuing a degree</li><li>Responsibilities: ship code</li></ul></main>"
        "<footer>Cookie policy</footer></html>")
text = community.page_text(page)
check("the posting is kept", "Qualifications: pursuing a degree" in text and "Software Engineer Intern" in text)
check("the furniture is not", "Jobs" not in text and "Cookie" not in text)
check("no bullet arrives empty", not any(l.strip() in ("-", "•") for l in text.splitlines()))
check("a page that is not a posting is refused", community.page_text("<main><p>Hello.</p></main>") == "")

print()
sys.exit(1 if fails else 0)
