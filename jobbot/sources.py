"""ATS board clients.

Every client returns Postings carrying the employer's own published timestamp.
No aggregator relative dates ever enter the system - that was the original
failure mode (a June posting showing as "16 hours ago") and the schema makes it
unrepresentable: posted_at is either an employer timestamp or None.
"""
import concurrent.futures as cf
import logging
import time
from datetime import datetime, timezone

import requests
from dateutil import parser as dateparse

from .model import Posting

log = logging.getLogger(__name__)

TIMEOUT = 20
UA = "jobbot/1.0 (personal job search agent; contact: you@example.com)"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA


class SourceError(Exception):
    pass


def _request(method, url, **kw):
    """One retry with a pause: polling 2,000+ boards draws throttling and
    dropped connections, and a transient failure must not look like a dead
    board (it disabled 46 of them on 2026-09-18)."""
    last = None
    for attempt in range(2):
        try:
            r = SESSION.request(method, url, timeout=TIMEOUT, **kw)
            if r.status_code == 404:
                raise SourceError(f"404 board not found: {url}")
            if r.status_code in (429, 503) and attempt == 0:
                time.sleep(2)
                continue
            r.raise_for_status()
            return r.json()
        except SourceError:
            raise
        except (requests.RequestException, ValueError) as e:
            last = e
            if attempt == 0:
                time.sleep(1.5)
    raise last


def _get(url, **kw):
    return _request("GET", url, **kw)


def _post(url, payload, **kw):
    return _request("POST", url, json=payload,
                    headers={"Accept": "application/json", "Content-Type": "application/json"}, **kw)


def _ts(value):
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            # Lever uses epoch milliseconds
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = dateparse.parse(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


# --------------------------------------------------------------------------
# Greenhouse - first_published is the authoritative post date, and the board
# also exposes application_deadline, which nothing else gives us.
# --------------------------------------------------------------------------
def greenhouse(org: str, with_content=True) -> list[Posting]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{org}/jobs"
    data = _get(url, params={"content": "true"} if with_content else None)
    out = []
    for j in data.get("jobs", []):
        posted = _ts(j.get("first_published")) or _ts(j.get("updated_at"))
        out.append(Posting(
            source="greenhouse", org=org,
            company=j.get("company_name") or org,
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            apply_url=j.get("absolute_url", ""),
            posted_at=posted,
            deadline=_ts(j.get("application_deadline")),
            description=_strip(j.get("content", "")),
            raw_id=str(j.get("id", "")),
        ))
    return out


def lever(org: str) -> list[Posting]:
    url = f"https://api.lever.co/v0/postings/{org}"
    data = _get(url, params={"mode": "json"})
    out = []
    for j in data:
        cat = j.get("categories") or {}
        out.append(Posting(
            source="lever", org=org, company=org,
            title=j.get("text", ""),
            location=cat.get("location", "") or j.get("country", "") or "",
            url=j.get("hostedUrl", ""),
            apply_url=j.get("applyUrl", j.get("hostedUrl", "")),
            posted_at=_ts(j.get("createdAt")),
            description=j.get("descriptionPlain", "") or j.get("description", ""),
            remote=(j.get("workplaceType", "") == "remote"),
            raw_id=str(j.get("id", "")),
        ))
    return out


def ashby(org: str) -> list[Posting]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    data = _get(url)
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append(Posting(
            source="ashby", org=org, company=org,
            title=j.get("title", ""),
            location=j.get("location", "") or "",
            url=j.get("jobUrl", ""),
            apply_url=j.get("applyUrl", j.get("jobUrl", "")),
            posted_at=_ts(j.get("publishedAt")),
            description=j.get("descriptionPlain", ""),
            remote=bool(j.get("isRemote")),
            raw_id=str(j.get("id", "")),
        ))
    return out


# Workday: about half of all listings, and the reason an Amazon-sized employer
# can be invisible. The board list only gives relative dates ("Posted 30+ Days
# Ago"), but each job's own endpoint carries the employer's startDate, so the
# list is filtered on title first and only candidates cost a second request.
# org is "tenant|host|site", e.g. "nvidia|wd5.myworkdayjobs.com|NVIDIAExternalCareerSite".
WORKDAY_QUERIES = ("intern", "co-op")


def _workday_parts(org):
    parts = org.split("|")
    if len(parts) != 3:
        raise ValueError(f"workday org must be tenant|host|site, got {org!r}")
    return parts


def workday(org: str, pages=2, per_page=20) -> list[Posting]:
    tenant, host, site = _workday_parts(org)
    base = f"https://{tenant}.{host}/wday/cxs/{tenant}/{site}"
    out, seen = [], set()
    for query in WORKDAY_QUERIES:
        for page in range(pages):
            data = _post(f"{base}/jobs", {"appliedFacets": {}, "limit": per_page,
                                          "offset": page * per_page, "searchText": query})
            posts = data.get("jobPostings") or []
            for j in posts:
                path = j.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                out.append(Posting(
                    source="workday", org=org, company=tenant,
                    title=j.get("title", ""),
                    location=j.get("locationsText", "") or "",
                    url=f"https://{tenant}.{host}/{site}{path}",
                    apply_url=f"https://{tenant}.{host}/{site}{path}/apply",
                    posted_at=None,                  # filled by workday_detail
                    description=j.get("title", ""),
                    raw_id=(j.get("bulletFields") or [path])[0]))
            if len(posts) < per_page:
                break
    return out


def workday_detail(posting):
    """Fill in the employer's own date and the description. One request."""
    tenant, host, site = _workday_parts(posting.org)
    # Split on "/job/", not on the site name: the site name is often the tenant
    # name too, which also appears in the host (copart.wd12.../copart/job/...).
    if "/job/" not in posting.url:
        return posting
    path = "/job/" + posting.url.split("/job/", 1)[1]
    info = (_get(f"https://{tenant}.{host}/wday/cxs/{tenant}/{site}{path}") or {}).get("jobPostingInfo") or {}
    posting.posted_at = _ts(info.get("startDate")) or posting.posted_at
    posting.description = _strip(info.get("jobDescription") or "") or posting.description
    posting.location = info.get("location") or posting.location
    if info.get("externalUrl"):
        posting.apply_url = info["externalUrl"]
    return posting


def amazon(org="amazon", pages=3, per_page=100) -> list[Posting]:
    """Amazon runs its own board, so nothing reached him from it (he spotted an
    SDE Internship Summer 2027 himself on 2026-09-18). amazon.jobs has a public
    search endpoint with the employer's own posted_date; `sort=recent` means a
    few pages cover everything posted in the last week or so.

    Applying still needs an Amazon account, so these are prepare-only.
    """
    out, seen = [], set()
    for page in range(pages):
        data = _get("https://www.amazon.jobs/en/search.json",
                    params={"category[]": "software-development", "sort": "recent",
                            "result_limit": per_page, "offset": page * per_page})
        jobs = data.get("jobs") or []
        for j in jobs:
            jid = str(j.get("id_icims") or j.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            text = " ".join(filter(None, [j.get("description_short"), j.get("description"),
                                          j.get("basic_qualifications"), j.get("preferred_qualifications")]))
            out.append(Posting(
                source="amazon", org="amazon", company=j.get("company_name") or "Amazon",
                title=j.get("title", ""),
                location=j.get("location") or ", ".join(filter(None, [j.get("city"), j.get("state"),
                                                                     j.get("country_code")])),
                url="https://www.amazon.jobs" + (j.get("job_path") or ""),
                apply_url=j.get("url_next_step") or "https://www.amazon.jobs" + (j.get("job_path") or ""),
                posted_at=_ts(j.get("posted_date")),
                description=_strip(text),
                raw_id=jid))
        if len(jobs) < per_page:
            break
    return out


def _community(org):
    from . import community
    return community.fetch(org)


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "amazon": amazon,
            "workday": workday, "community": _community}

# Ashby's public board feed omits application deadlines, so a posting whose
# deadline passed in May can be re-published today and look brand new (NPX,
# 2026-09-17). The page's own GraphQL has the field; asked only for postings
# that already matched, which is a handful per run.
ASHBY_DEADLINE_Q = ("query ApiJobPosting($o: String!, $j: String!) { jobPosting("
                    "organizationHostedJobsPageName: $o, jobPostingId: $j) { applicationDeadline } }")


def ashby_deadline(org: str, job_id: str):
    r = requests.post("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting", timeout=30,
                      headers={"User-Agent": UA},
                      json={"operationName": "ApiJobPosting", "query": ASHBY_DEADLINE_Q,
                            "variables": {"o": org, "j": job_id}})
    d = ((r.json().get("data") or {}).get("jobPosting") or {}).get("applicationDeadline")
    return _ts(d)


def enrich(matches, max_workers=8):
    """Fill in what the cheap board listing could not give: Workday's real
    posted date and description, Ashby's application deadline. Only for
    postings that already matched, so it stays a handful of requests."""
    def one(m):
        try:
            if m.posting.source == "workday" and m.posting.posted_at is None:
                workday_detail(m.posting)
            elif m.posting.source == "ashby" and m.posting.deadline is None:
                m.posting.deadline = ashby_deadline(m.posting.org, m.posting.raw_id)
        except Exception:                        # noqa: BLE001 - enrichment is best effort
            pass
    todo = [m for m in matches
            if (m.posting.source == "workday" and m.posting.posted_at is None)
            or (m.posting.source == "ashby" and m.posting.deadline is None)]
    if todo:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
            list(pool.map(one, todo))
    return matches


def drop_expired(matches, max_workers=8):
    """(kept, expired) - fills in missing Ashby deadlines first."""
    enrich(matches, max_workers)
    now = datetime.now(timezone.utc)
    kept = [m for m in matches if not (m.posting.deadline and m.posting.deadline < now)]
    return kept, [m for m in matches if m not in kept]


def _strip(html: str) -> str:
    """Tags out, structure kept: paragraphs and list items stay on their own
    lines, because he reads these descriptions in the app and the writer reads
    them in JD.md - and a posting flattened to one line is unreadable to both."""
    import html as htmlmod
    import re
    text = htmlmod.unescape(html or "")
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/ul|/ol|/h[1-6]|/tr|/section)\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_all(entries, max_workers=12):
    """entries: iterable of (source, org). Returns (postings, health).

    Failures are captured per-board rather than aborting the run - one dead
    board must never cost us the other 900.
    """
    postings, health = [], {}

    def one(entry):
        source, org = entry
        key = f"{source}:{org}"
        try:
            got = FETCHERS[source](org)
            return key, got, None
        except Exception as e:                      # noqa: BLE001 - reported, not raised
            return key, [], f"{type(e).__name__}: {e}"

    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        for key, got, err in pool.map(one, entries):
            health[key] = {"ok": err is None, "error": err, "count": len(got)}
            postings.extend(got)
    return postings, health
