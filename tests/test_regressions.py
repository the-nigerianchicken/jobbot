"""Regressions from the first live run (2026-09-15, 1020 boards / 50,082 postings).

Each case is a real posting that was classified wrongly.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
import yaml
from jobbot.model import Posting
from jobbot import match

crit = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), '..', 'criteria.yaml')))
targets = open(os.path.join(os.path.dirname(__file__), '..', 'jobbot', 'targets.txt')).read().split()
now = datetime.now(timezone.utc)


def p(company, title, loc, desc="Summer 2027 internship program", hours_ago=0):
    return Posting(source="greenhouse", org=company.lower(), company=company, title=title,
                   location=loc, url="u", apply_url="u", posted_at=now - timedelta(hours=hours_ago),
                   description=desc, raw_id=title)


def listed(company, title, loc):
    """From a curated community list: US and Canadian internships only."""
    q = p(company, title, loc)
    q.source = "community"
    return q


MILITARY = ("Summer 2027 internship. Prior leadership through academic achievement, "
            "internships, campus involvement, athletics, or military service.")
SPONSOR = "Summer 2027 internship. Sponsorship is not available for this role."

SHOULD_DROP = [
    (p("Faire", "Staff Software Engineer - Code Authoring", "Toronto, ON"), "staff role"),
    (p("Robinhood", "Senior Staff Software Developer, Core Infrastructure", "Toronto, Canada"), "senior/staff"),
    (p("Anthropic", "Staff + Senior Software Engineer, Inference", "Ontario, CAN"), "staff+senior"),
    (p("Robinhood", "Staff Offensive Security Engineer", "Toronto, Canada"), "staff"),
    (p("cohere", "Site Reliability Engineer, Inference Infrastructure", "Toronto"), "full-time, no level signal"),
    (p("Robinhood", "Web Developer", "Toronto, Canada"), "full-time, no level signal"),
    (p("Robinhood", "Software Developer, Ops Platform and Fraud Investigations", "Toronto, Canada"), "full-time"),
    (p("Cloudflare", "Senior Software Engineer, Internal Fraud Platform", "Hybrid"), "'intern' inside 'Internal'"),
    # Live run 2026-09-16: no seniority word, so only the title level gate can stop it.
    (p("SpaceX", "Software Engineer, Internal Applications", "Hawthorne, CA"), "'intern' inside 'Internal', no seniority word"),
    (p("Scale AI", "Software Engineering Intern (Summer 2027)", "Doha, Qatar"), "geography"),
    (p("Snowflake", "Senior Software Engineer, Notebooks", "CA-Ontario-Toronto"), "senior"),
    (p("SomeCo", "Data Analyst Intern", "Toronto, ON"), "banned role type"),
    (p("SomeCo", "Software Engineer Intern", "London, United Kingdom"), "geography"),
    # The same rule still has to work when the posting really does say it.
    (p("GDIT", "Software Development Intern", "Bossier City, LA", desc=SPONSOR), "will not sponsor"),
    # Age caps (2026-09-17): 24h, tier 1 up to 72h. The Cohere posting from May.
    (p("cohere", "Machine Learning Intern/Co-op  (Winter 2027)", "Canada", hours_ago=24*127), "posted 2026-05-13"),
    (p("Cohere", "Software Engineering Intern (Winter 2027)", "Toronto, ON", hours_ago=80), "tier 1 over 72h"),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Toronto, ON", hours_ago=30), "tier 2 over 24h"),
    # No new grad roles (2026-09-17).
    (p("openai", "Software Engineer, Applied Emerging Talent (2027)", "San Francisco"), "new grad program"),
    (p("Sierra", "Software Engineer, Agent (New Grad 2027)", "San Francisco, CA"), "new grad"),
    (p("Notion", "Software Engineer, Early Career (AI)", "San Francisco, California"), "early career"),
    (p("SomeCo", "Software Engineer Intern (Summer 2027)", "Austin, TX",
       "Summer 2027 internship. We are unable to sponsor visas for this role."), "US seat, no sponsorship"),
    (p("SomeCo", "Software Engineer Intern (Summer 2027)", "Remote",
       "Summer 2027 intern. Must be a U.S. citizen due to ITAR."), "US citizenship required"),
    (p("SomeCo", "Software Engineer Intern (Summer 2027)", "Glasgow, UK"), "UK"),
    (p("SomeCo", "Software Engineer Intern (Summer 2027)", "Berlin, DE"), "Germany, not Delaware"),
    (listed("SomeCo", "Software Engineer Intern (Summer 2027)", "Glasgow, UK"), "listed, but abroad"),
    (listed("SomeCo", "Software Engineer Intern (Summer 2027)", "Bengaluru"), "listed, but abroad"),
]

SHOULD_KEEP = [
    # 2026-09-26: "itar" sits inside "military", and the sponsorship phrases were
    # matched as substrings. 42 of the 74 postings this rule had turned away were
    # US roles whose only offence was the word "military" in their boilerplate.
    (p("Booz Allen", "Software Developer Intern", "San Diego, CA", desc=MILITARY), 3),
    (p("Upbound Group", "Software Engineer Intern", "Draper, UT", desc=MILITARY), 3),
    # Tiers (2026-09-16): 1 target company, 2 any other in Canada, 3 any other US/remote.
    (p("DoorDash Canada", "Software Engineer, Intern (Summer 2027) - TOR", "Toronto, ON"), 1),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Waterloo, ON"), 2),
    (p("Cohere", "Software Engineering Intern (Winter 2027)", "Toronto, ON", hours_ago=60), 1),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Austin, TX", hours_ago=20), 3),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Vancouver, BC"), 2),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Austin, TX"), 3),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "On Site, Palo Alto, California"), 3),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "CA-ON-Toronto"), 2),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Remote - Canada"), 2),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Toronto, ON; New York, NY",
       "Summer 2027 internship. Candidates must be authorized to work without sponsorship."), 2),
    (p("Robinhood", "Software Developer Intern/Co-op, Backend (Winter 2027)", "Toronto, Canada"), 1),
    (p("kepler", "Embedded Software Engineering Intern (January 2027) (4 months)", "Toronto, Ontario"), 1),
    (p("Figma", "Software Engineer Intern (Summer 2027)", "San Francisco, CA"), 1),

    (p("DoorDash USA", "Software Engineer, Intern (Summer 2027) - US", "New York, NY"), 1),
    # 2026-09-21: the community lists shorten cities; Lazard's NYC role was dropped as foreign.
    (p("Lazard", "AI Engineer Intern (Summer 2027)", "NYC"), 3),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "SF"), 3),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "Cedar Rapids, IA"), 3),
    # The curated lists are trusted on place: any spelling they use stays.
    (listed("SmallCo", "Software Engineer Intern (Summer 2027)", "Hoboken"), 3),
    (listed("Pace", "Member of Technical Staff Intern (Summer 2027)", "NYC"), 3),
    (listed("Charta", "Front-End Engineer Intern (Summer 2027)", "SF"), 3),
    (listed("SmallCo", "Software Engineer Intern (Summer 2027)", "Dublin, OH"), 3),
    (p("SmallCo", "Software Engineer Intern (Summer 2027)", "London, ON"), 2),
]

fails = 0
for posting, why in SHOULD_DROP:
    m, drop = match.classify(posting, crit, targets)
    if m is not None:
        print(f"LEAK  {posting.company} | {posting.title}  ({why})")
        fails += 1
for posting, want_tier in SHOULD_KEEP:
    m, drop = match.classify(posting, crit, targets)
    if m is None:
        print(f"LOST  {posting.company} | {posting.title}  -> dropped: {drop}")
        fails += 1
    elif m.tier != want_tier:
        print(f"TIER  {posting.company} | {posting.title}  -> T{m.tier}, wanted T{want_tier}")
        fails += 1

# --- expired postings ---------------------------------------------------------
# NPX re-published a posting on 2026-09-17 whose deadline was 2026-05-19; Ashby's
# public feed omits deadlines, so it looked brand new.
from jobbot import sources
from jobbot.model import Match

def _m(deadline, source="ashby"):
    post = p("NPX", "Software Developer Intern", "Ontario")
    post.source, post.deadline = source, deadline
    return Match(posting=post, tier=2, reasons=[])

kept, expired = sources.drop_expired([_m(now - timedelta(days=120)), _m(now + timedelta(days=30)),
                                      _m(None, source="lever")])
if len(kept) != 2 or len(expired) != 1:
    print(f"LEAK expired postings: kept {len(kept)}, expired {len(expired)}")
    sys.exit(1)
print("expired postings dropped, future deadlines kept")

# Amazon runs its own board; nothing from it reached him until 2026-09-18, when
# he spotted "Software Development Engineer Internship - Summer -2027 (USA)".
amazon_post = Posting(source="amazon", org="amazon", company="Amazon",
                      title="Software Development Engineer Internship - Summer -2027 (USA)",
                      location="US, WA, Seattle", url="u", apply_url="u", posted_at=now,
                      description="Summer 2027 internship for students graduating 2027-2028", raw_id="10552937")
m, why = match.classify(amazon_post, crit, targets)
if m is None or m.tier != 1:
    print(f"LOST Amazon SDE internship -> {why or ('T%d' % m.tier)}")
    sys.exit(1)
print("amazon source: SDE internship kept at tier 1")

# A term he cannot take, spelled out only as a date (2026-09-26). 26 postings
# for Winter 2026 - a term that ended in April - sat in New because the words
# "winter 2026" appeared nowhere; only "start date: January 2026" did, which is
# what the card was already showing as the term.
from datetime import date
TERMS = [
    ("Start date: January 2026", "Winter 2026 is over"),
    ("Summer 2026 internship", "Summer 2026 is over"),
    ("starts May 2028", "Summer 2028 starts after he graduates"),
    ("Summer 2027 internship", None),
    ("Winter 2027 co-op", None),
    ("Fall 2027 term", None),                       # he graduates that December
    ("Fall 2026 start", None),                      # not over yet, so his to judge
    ("Winter 2026 or Summer 2027", None),           # one he can take is enough
    ("no dates here at all", None),                 # unknown is never a drop
]
for desc, want in TERMS:
    got = match.dead_terms("Software Engineer Intern", desc, crit, today=date(2026, 9, 26))
    if got != want:
        print(f"TERM {desc!r}: wanted {want!r}, got {got!r}")
        fails += 1
print(f"dead terms: {len(TERMS)} cases")

print()
print(f"{len(SHOULD_DROP)} should-drop, {len(SHOULD_KEEP)} should-keep, {fails} failure(s)")
sys.exit(1 if fails else 0)
