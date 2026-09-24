"""The community internship lists, read as a source of postings.

jobbot reads five kinds of career site itself: Greenhouse, Lever, Ashby,
Amazon, and the Workday tenants it has learned are worth watching. Most
internships are posted somewhere else - Oracle, iCIMS, SmartRecruiters, a
Workday tenant it does not poll, a company's own site. Measured on 2026-09-21:
of the 725 US/Canada internships the lists carried that week, 27 had reached
him.

SimplifyJobs and vanshb03 keep those lists by hand, across every site, usually
within hours. They used to be read only to discover which boards to poll; now
every posting on them is a posting. Where the same job is on a board jobbot
reads itself, the native copy wins, because it carries the full description.
"""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .model import Posting

LISTS = {
    "simplify": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/"
                ".github/scripts/listings.json",
    "vansh": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/"
             ".github/scripts/listings.json",
}

# Roles a CS student is not applying for. Everything else goes through the same
# title, term and location rules as any other posting.
NOT_HIS = {"Hardware", "Hardware Engineering", "Product"}

# What the lists record about sponsorship, and which of those rule a US seat
# out for him. Only these reach the description, because the location rule
# drops a non-Canada posting whose text mentions sponsorship at all - and
# "Offers Sponsorship" must not be caught by that.
BLOCKS = {"Does Not Offer Sponsorship", "U.S. Citizenship is Required"}


def _uid(source, org, raw_id):
    return hashlib.sha1(f"{source}:{org}:{raw_id}".encode()).hexdigest()[:16]


def native(url):
    """The uid jobbot gives this posting when it reads the board itself, if it does."""
    u = urlparse(url or "")
    host = u.netloc.lower()
    parts = [p for p in u.path.split("/") if p]
    if "greenhouse.io" in host:
        if "jobs" in parts:
            i = parts.index("jobs")
            if i >= 1 and i + 1 < len(parts) and parts[i + 1].isdigit():
                return _uid("greenhouse", parts[i - 1].lower(), parts[i + 1])
        query = dict(q.split("=", 1) for q in u.query.split("&") if "=" in q)
        if query.get("for") and query.get("token"):
            return _uid("greenhouse", query["for"].lower(), query["token"])
        return None
    if host.endswith("lever.co") and len(parts) >= 2:
        return _uid("lever", parts[0].lower(), parts[1])
    if "ashbyhq.com" in host and len(parts) >= 2:
        return _uid("ashby", parts[0].lower(), parts[1])
    if "amazon.jobs" in host and "jobs" in parts:
        i = parts.index("jobs")
        if i + 1 < len(parts):
            return _uid("amazon", "amazon", parts[i + 1])
    return None


def _when(value):
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def fetch(org, get=None):
    """Every active posting on one community list."""
    if get is None:
        from .sources import _get as get
    rows = get(LISTS[org]) or []
    out, urls = [], set()
    for r in rows:
        if r.get("active") is False or r.get("is_visible") is False:
            continue
        if r.get("category") in NOT_HIS:
            continue
        url = (r.get("url") or "").strip()
        if not url or url in urls:
            continue
        urls.add(url)
        sponsor = r.get("sponsorship") or ""
        p = Posting(
            source="community", org=org,
            company=(r.get("company_name") or "").strip(),
            title=(r.get("title") or "").strip(),
            location="; ".join(r.get("locations") or []),
            url=url, apply_url=url,
            posted_at=_when(r.get("date_posted")),
            description=f"Sponsorship: {sponsor}" if sponsor in BLOCKS else "",
            raw_id=str(r.get("id") or url))
        p.alias = native(url)
        # The list says which terms it is for; the title often does not.
        p.terms = [str(t) for t in r.get("terms") or []]
        out.append(p)
    return out


def dedupe(postings, seen):
    """Drop list postings jobbot already has from the employer's own board.

    Native copies carry the full description, so they win. Workday uids cannot
    be worked out from a URL, so those are matched on company and title.
    """
    key = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    mine = [p for p in postings if p.source != "community"]
    have = {p.uid for p in mine} | set(seen)
    pairs = {(key(p.company), key(p.title)) for p in mine}
    kept = []
    for p in postings:
        if p.source == "community":
            if getattr(p, "alias", None) and p.alias in have:
                continue
            if (key(p.company), key(p.title)) in pairs:
                continue
        kept.append(p)
    return kept


def describe(url, get=None, get_text=None):
    """The job description for a posting that came from a list without one.

    Used when he asks for a resume: the writer needs the JD. Uses the ATS's
    own API where there is one, and the page's text otherwise.
    """
    from . import sources
    get = get or sources._get
    u = urlparse(url or "")
    host = u.netloc.lower()
    parts = [p for p in u.path.split("/") if p]
    try:
        if "greenhouse.io" in host and "jobs" in parts:
            i = parts.index("jobs")
            data = get(f"https://boards-api.greenhouse.io/v1/boards/{parts[i - 1]}/jobs/{parts[i + 1]}")
            return sources._strip((data or {}).get("content") or "")
        if host.endswith("lever.co") and len(parts) >= 2:
            data = get(f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}") or {}
            lists = " ".join(f"{x.get('text', '')}: {sources._strip(x.get('content', ''))}"
                             for x in data.get("lists") or [])
            return " ".join(filter(None, [data.get("descriptionPlain"), lists,
                                          data.get("additionalPlain")])).strip()
        if "myworkdayjobs.com" in host and "job" in parts:
            tenant, rest = host.split(".", 1)
            before = parts[:parts.index("job")]
            site = before[-1] if before else ""
            stub = Posting(source="workday", org=f"{tenant}|{rest}|{site}", company=tenant,
                           title="", location="", url=f"https://{host}/{site}/" +
                           "/".join(parts[parts.index("job"):]), apply_url=url, posted_at=None)
            return sources.workday_detail(stub).description
        if host == "jobs.ashbyhq.com" and len(parts) >= 2:
            # Ashby's page is drawn in the browser; its public board API has
            # every posting's text (2026-09-21: a whole week of them was blank).
            data = get(f"https://api.ashbyhq.com/posting-api/job-board/{parts[0]}") or {}
            job = next((j for j in data.get("jobs") or [] if j.get("id") == parts[1]), {})
            return job.get("descriptionPlain") or sources._strip(job.get("descriptionHtml") or "")
        if "oraclecloud.com" in host and "sites" in parts and "job" in parts:
            # Oracle's pages are drawn in the browser, but the requisition
            # behind them is public.
            site, job = parts[parts.index("sites") + 1], parts[parts.index("job") + 1]
            data = get(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                       f'?expand=all&onlyData=true&finder=ById;Id="{job}",siteNumber={site}') or {}
            item = (data.get("items") or [{}])[0]
            return sources._strip(" ".join(filter(None, [
                item.get("ExternalDescriptionStr"), item.get("ExternalResponsibilitiesStr"),
                item.get("ExternalQualificationsStr")])))
    except Exception:
        pass
    # Anything else: the page's own text, if the page has any without a browser.
    try:
        import requests
        r = requests.get(url, timeout=20, headers={"user-agent": "Mozilla/5.0 (jobbot)"})
        return page_text(r.text)
    except Exception:
        return ""


# Everything around a posting that is not the posting: menus, cookie banners,
# "related jobs", the footer. Stripped before he ever reads it.
FURNITURE = re.compile(r"(?is)<(script|style|nav|header|footer|aside|form|svg|button|select)[^>]*>.*?</\1>")
CHROME = re.compile(r"(?i)^(cookie|privacy|terms|sign in|log ?in|apply now|share this|follow us|back to|"
                    r"all jobs|similar jobs|related jobs|skip to|menu|search|filter|©|copyright)\b")


def page_text(html):
    """The readable part of a careers page.

    A page scraped whole gives him its menus as bullets with nothing in them -
    one posting arrived with 175 (2026-09-24). Only the lines that read like a
    posting survive.
    """
    from . import sources
    body = re.search(r"(?is)<main[^>]*>(.*?)</main>|<article[^>]*>(.*?)</article>", html or "")
    if body:
        html = next(g for g in body.groups() if g)
    text = sources._strip(FURNITURE.sub(" ", html or ""))
    out, seen = [], None
    for line in text.split("\n"):
        line = line.strip()
        bare = re.sub(r"^[\u2022\-\*\u00b7\u25aa\u25e6]\s*", "", line).strip()
        if not bare or len(bare) < 2 or CHROME.match(bare):
            continue
        if bare == seen:                      # the same link repeated down a menu
            continue
        seen = bare
        out.append(("- " + bare) if line != bare else bare)
    text = "\n".join(out)
    return text[:15000] if reads_like_a_job(text) else ""


# Words any job description uses. A page drawn by JavaScript strips down to ids
# and config instead - Microsoft's gave 15,000 characters of hashes - and that
# must not be handed to the writer as if it were the job.
PLAIN = {"the", "and", "you", "with", "will", "our", "for", "experience", "team", "work",
         "skills", "intern", "students", "ability", "we", "your", "are", "to", "of", "in"}


def reads_like_a_job(text):
    low = (text or "").lower()
    # A page's config survives tag stripping as JSON; a description does not.
    if low.count('":') > 15 or low.count("{") > 15:
        return False
    if not any(w in low for w in ("qualification", "responsibilit", "requirement", "what you", "you will")):
        return False
    words = re.findall(r"[a-z]+", low)
    if len(words) < 120:
        return False
    return sum(w in PLAIN for w in words) / len(words) > 0.12
