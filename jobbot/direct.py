"""The boards a company runs itself.

Most employers rent an ATS, and we read the ATS feed: one client covers eight
hundred companies. The largest employers do not. Google, Microsoft, Apple and
Uber each built their own careers site, so none of them has ever reached him
from the two thousand boards in the registry - he has been finding them by
hand, which is the thing this was built to stop (2026-09-24).

Each fetcher here reads the same public page a person would, and takes the
employer's own timestamp where the page publishes one. Where a board does not
publish a date, posted_at stays None rather than being guessed: an invented
date is what made an old posting read as "16 hours ago", and the schema makes
that unrepresentable.

Two of the eight he asked for are not here:

  Meta   - metacareers.com answers its own page only, through a signed GraphQL
           call the site rebuilds for each deploy.
  Tesla  - tesla.com sits behind Akamai, which refuses anything that is not a
           browser it recognises, whatever headers it is given.

Neither will answer a server, and working around that is not something jobbot
does. Both still reach him through the curated lists, and the browser
extension can hand a posting straight to jobbot from a page he is reading.
"""
import json
import re
from urllib.parse import urljoin

import requests

from .model import Posting
from .sources import TIMEOUT, SourceError, _strip, _ts

# These are careers pages, not APIs, and several serve a different page to a
# client that does not look like a browser. Nothing here hides what it is doing
# beyond the name it gives: no cookies, no tokens, one request at a time.
BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
WEB = requests.Session()
WEB.headers.update({"User-Agent": BROWSER, "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})


def _page(url, params=None, tries=2):
    """One retry, then give up and let fetch_all record the board as sick."""
    last = None
    for attempt in range(tries):
        try:
            r = WEB.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 403:
                raise SourceError(f"403 refused: {url}")
            r.raise_for_status()
            return r.text
        except SourceError:
            raise
        except requests.RequestException as e:
            last = e
    raise last


def _json_page(url, params=None):
    text = _page(url, params)
    try:
        return json.loads(text)
    except ValueError as e:
        raise SourceError(f"{url} answered with a page, not JSON") from e


def _tags(html):
    return re.sub(r"<[^>]+>", " ", html)


def _words(html):
    return re.sub(r"\s+", " ", _tags(html)).strip()


# A page built with a JavaScript framework ships its data as a string inside a
# script tag - Apple's whole board arrives as JSON.parse("..."). Decoding that
# string is the only way to read it: unescaping it by hand loses every posting
# whose description contains a quote, which was 17 of Apple's 20 (2026-09-24).
LONG_STRING = re.compile(r'"((?:[^"\\]|\\.){400,}?)"', re.S)


def payload(html):
    """The page, plus every long JavaScript string in it, decoded."""
    parts = [html]
    for m in LONG_STRING.finditer(html):
        try:
            parts.append(json.loads('"' + m.group(1) + '"'))
        except ValueError:
            continue
    return "\n".join(parts)


def objects_with(text, key, limit=400):
    """Every JSON object in `text` that carries `key`.

    The blob is nested and far too large to parse whole, so this walks out from
    each mention of a field we want to the braces around it.
    """
    flat = text
    out = []
    for hit in re.finditer('"' + re.escape(key) + '"\\s*:', flat):
        start, depth = None, 0
        for i in range(hit.start(), max(-1, hit.start() - 60000), -1):
            if flat[i] == "}":
                depth += 1
            elif flat[i] == "{":
                if depth == 0:
                    start = i
                    break
                depth -= 1
        if start is None:
            continue
        depth = 0
        for j in range(start, min(len(flat), start + 60000)):
            if flat[j] == "{":
                depth += 1
            elif flat[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out.append(json.loads(flat[start:j + 1]))
                    except ValueError:
                        pass
                    break
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Google - the results page is rendered on the server, and its own filter for
# student roles (target_level) is exactly the set he wants. No posted date is
# published anywhere on it, so these arrive dateless and are ranked by when
# jobbot first saw them.
# ---------------------------------------------------------------------------
GOOGLE_ROOT = "https://www.google.com/about/careers/applications/"
G_CARD = re.compile(
    r'<a class="[^"]*"\s+href="(jobs/results/(\d+)-[^"?]*)[^"]*"\s+aria-label="Learn more about ([^"]*)"',
    re.S)


def google(org="google", pages=2) -> list[Posting]:
    out, seen = [], set()
    for page in range(1, pages + 1):
        html = _page(GOOGLE_ROOT + "jobs/results/",
                     {"target_level": "INTERN_AND_APPRENTICE", "sort_by": "date", "page": page})
        cards = G_CARD.findall(html)
        if not cards:
            break
        for href, jid, title in cards:
            if jid in seen:
                continue
            seen.add(jid)
            url = urljoin(GOOGLE_ROOT, href.replace("&amp;", "&"))
            out.append(Posting(
                source="google", org="google", company="Google",
                title=_words(title), location=_google_where(html, jid),
                url=url, apply_url=url, posted_at=None,
                description=_google_about(html, jid), raw_id=jid))
        if len(cards) < 20:
            break
    return out


def _slice(html, jid):
    """The card a job id sits in: from the previous card boundary to the next."""
    at = html.find("-" + jid + "-")
    at = html.find(jid) if at < 0 else at
    if at < 0:
        return ""
    start = html.rfind('<li class="lLd3Je"', 0, at)
    if start < 0:
        start = max(0, at - 6000)
    end = html.find('<li class="lLd3Je"', at)
    return html[start:end if end > 0 else at + 2000]


def _google_where(html, jid):
    card = _slice(html, jid)
    places, seen = [], set()
    for raw in re.findall(r'<span class="r0wTof[^"]*">([^<]+)</span>', card):
        place = raw.strip().lstrip(";").strip()
        if place and place.lower() not in seen:
            seen.add(place.lower())
            places.append(place)
    more = re.search(r'<span class="BVHzed">;\s*\+(\d+) more</span>', card)
    where = "; ".join(places[:3])
    if more and where:
        where += f"; and {more.group(1)} more"
    return where


def _google_about(html, jid):
    card = _slice(html, jid)
    about = re.search(r'<div class="Xsxa1e">(.*?)</div>', card, re.S)
    return _strip(about.group(1)) if about else ""


# ---------------------------------------------------------------------------
# Microsoft - moved onto Phenom, whose search endpoint is public JSON and gives
# the employer's own postedTs. One query per term he cares about; asking for
# everything would be 9,000 postings a run.
# ---------------------------------------------------------------------------
MS_API = "https://apply.careers.microsoft.com/api/pcsx/search"
MS_QUERIES = ("software engineer intern", "software engineering internship",
              "research intern", "data scientist intern", "explore intern")


def microsoft(org="microsoft", per_query=40) -> list[Posting]:
    out, seen = [], set()
    for q in MS_QUERIES:
        data = _json_page(MS_API, {"domain": "microsoft.com", "query": q, "location": "",
                                   "start": 0, "num": per_query, "sort_by": "date"})
        for p in ((data.get("data") or {}).get("positions") or []):
            jid = str(p.get("atsJobId") or p.get("displayJobId") or p.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            url = urljoin("https://apply.careers.microsoft.com/",
                          p.get("positionUrl") or f"careers/job/{jid}")
            out.append(Posting(
                source="microsoft", org="microsoft", company="Microsoft",
                title=p.get("name", ""),
                location="; ".join(p.get("locations") or [])[:200],
                url=url, apply_url=url,
                posted_at=_ts(p.get("postedTs")) or _ts(p.get("creationTs")),
                description=" ".join(filter(None, [p.get("name"), p.get("department"),
                                                   p.get("workLocationOption")])),
                raw_id=jid))
    return out


# ---------------------------------------------------------------------------
# Apple - the search page carries every posting on it as JSON, summary and all,
# with postDateInGMT to the second. The richest of the four.
# ---------------------------------------------------------------------------
APPLE_SEARCH = "https://jobs.apple.com/en-us/search"
# Apple files every student role under one team, which is a better filter than
# any words we could search for.
APPLE_FILTERS = ({"team": "internships-STDNT-INTRN"},
                 {"key": "software engineering internship"})


def apple(org="apple", pages=2) -> list[Posting]:
    out, seen = [], set()
    for q in APPLE_FILTERS:
        for page in range(1, pages + 1):
            html = _page(APPLE_SEARCH, dict(q, sort="newest", page=page))
            found = objects_with(payload(html), "postDateInGMT")
            if not found:
                break
            for j in found:
                jid = str(j.get("positionId") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                slug = j.get("transformedPostingTitle") or "role"
                team = (j.get("team") or {}).get("teamCode") or ""
                url = f"https://jobs.apple.com/en-us/details/{jid}/{slug}" + (f"?team={team}" if team else "")
                out.append(Posting(
                    source="apple", org="apple", company="Apple",
                    title=j.get("postingTitle", ""),
                    location="; ".join(filter(None, (
                        loc.get("name") or ", ".join(filter(None, (loc.get("city"), loc.get("stateProvince"))))
                        for loc in (j.get("locations") or []))))[:200],
                    url=url, apply_url=url,
                    posted_at=_ts(j.get("postDateInGMT")) or _ts(j.get("postingDate")),
                    description=_strip(j.get("jobSummary") or j.get("description") or ""),
                    raw_id=jid))
    return out


# ---------------------------------------------------------------------------
# Uber - its careers site searches in the browser, so the list page serves the
# same ten roles whatever is asked of it. Its sitemap, though, is the whole
# board: 540 postings, each with the time it last changed. Read that, take the
# ones that changed recently, and get the date and the text from each posting's
# own schema.org block. A posting's page is half a megabyte, so this is a board
# to sweep hourly, not every five minutes.
# ---------------------------------------------------------------------------
UBER_SITEMAP = "https://jobs.uber.com/en/jobs/sitemap.xml"
UBER_ENTRY = re.compile(r"<loc>(https://jobs\.uber\.com/en/jobs/(\d+)/)</loc>\s*<lastmod>([^<]+)</lastmod>")


def uber(org="uber", limit=25, days=4) -> list[Posting]:
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fresh = []
    for url, jid, changed in UBER_ENTRY.findall(_page(UBER_SITEMAP)):
        when = _ts(changed)
        if when and when >= since:
            fresh.append((when, url, jid))
    fresh.sort(reverse=True)
    out = []
    for _, url, jid in fresh[:limit]:
        try:
            page = _page(url)
        except (SourceError, requests.RequestException):
            continue
        for j in objects_with(payload(page), "datePosted"):
            if j.get("@type") != "JobPosting":
                continue
            where = j.get("jobLocation") or {}
            if isinstance(where, list):
                where = where[0] if where else {}
            addr = (where.get("address") or {}) if isinstance(where, dict) else {}
            out.append(Posting(
                source="uber", org="uber", company="Uber",
                title=j.get("title", ""),
                location=", ".join(filter(None, (addr.get("addressLocality"), addr.get("addressRegion"),
                                                 addr.get("addressCountry")))),
                url=url, apply_url=url,
                posted_at=_ts(j.get("datePosted")),
                description=_strip(str(j.get("description") or "")),
                raw_id=jid))
            break
    return out


# ---------------------------------------------------------------------------
# Shopify - its board runs on a rented Ashby that is not published under the
# public board name, so the careers page itself is the feed. Title and link
# only: the page publishes no date, and the posting's own page keeps its text
# in an encoding that changes with every deploy.
# ---------------------------------------------------------------------------
SHOPIFY_SEARCH = "https://www.shopify.com/careers/search"
SHOP_LINK = re.compile(r'/careers/([a-z0-9-]+)_([0-9a-f-]{36})')


def shopify(org="shopify") -> list[Posting]:
    out, seen = [], set()
    # The page ignores a keyword and serves the whole board either way, so ask
    # once and let his own rules do the filtering.
    for html in (_page(SHOPIFY_SEARCH),):
        for slug, uid in SHOP_LINK.findall(html):
            if uid in seen:
                continue
            seen.add(uid)
            url = f"https://www.shopify.com/careers/{slug}_{uid}"
            out.append(Posting(
                source="shopify", org="shopify", company="Shopify",
                title=_title_from_slug(slug), location="",
                url=url, apply_url=url, posted_at=None,
                description="", raw_id=uid))
    return out


SMALL = {"and", "or", "of", "for", "the", "to", "in", "at", "on", "a", "an", "with"}
CAPS = {"ai": "AI", "ml": "ML", "ios": "iOS", "ux": "UX", "ui": "UI", "api": "API", "sre": "SRE",
        "qa": "QA", "us": "US", "uk": "UK", "emea": "EMEA", "apac": "APAC", "nlp": "NLP",
        "llm": "LLM", "sde": "SDE", "it": "IT", "hr": "HR"}


def _title_from_slug(slug):
    words = []
    for i, w in enumerate(slug.split("-")):
        if w in CAPS:
            words.append(CAPS[w])
        elif i and w in SMALL:
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


FETCHERS = {"google": google, "microsoft": microsoft, "apple": apple,
            "uber": uber, "shopify": shopify}

# Boards that exist because there is code here to read them, rather than
# because a list mentioned them. The registry gets them whether or not anyone
# remembers to add them: the fetcher is the definition, and a registry rebuilt
# from the lists would otherwise drop them.
#
# target=True means the five-minute sweep. Uber is not one: reading its board
# means a request per posting, which belongs on the hourly pass. Snap is on
# Workday, under a host it shares, which sources.workday now understands.
BUILTIN = [
    {"source": "google", "org": "google", "target": True},
    {"source": "microsoft", "org": "microsoft", "target": True},
    {"source": "apple", "org": "apple", "target": True},
    {"source": "shopify", "org": "shopify", "target": True},
    {"source": "uber", "org": "uber", "target": False},
    {"source": "workday", "org": "snapchat|wd1.myworkdaysite.com/recruiting|snap", "target": True},
]
