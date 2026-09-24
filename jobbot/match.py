"""Filtering and ranking against criteria.yaml.

Everything here is data-driven. Retargeting from 2027 internships to 2028 new
grad is a criteria.yaml edit, not a code change.
"""
import re

from .model import Match

TARGETS_DEFAULT = set()


def _any_in(needles, haystack):
    """Whole-word containment.

    Plain substring matching let "intern" match "internal" and
    "international", which pulled a pile of senior full-time roles into the
    results. Multi-word needles are matched as phrases; trailing-fragment
    needles ending in a letter still get a boundary on both sides.
    """
    h = (haystack or "").lower()
    hits = []
    for n in needles:
        nl = n.lower().strip()
        if not nl:
            continue
        pat = r"(?<![a-z0-9])" + re.escape(nl).replace(r"\ ", r"[\s\-/]+") + r"(?![a-z0-9])"
        if re.search(pat, h):
            hits.append(n)
    return hits


def _any_in_loose(needles, haystack):
    """Substring containment, for prefix-style needles like "data scien"."""
    h = (haystack or "").lower()
    return [n for n in needles if n.lower() in h]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _is_target(posting, targets):
    """Token-level match, not substring.

    Substring matching made "Ada" fire inside "BDO Canada" and "RBC" inside
    unrelated slugs, promoting non-target companies into tier 1. Targets must
    match a whole token, or the whole normalized company name.
    """
    if not targets:
        return False
    for field in (posting.company, posting.org):
        n = _norm(field)
        if not n:
            continue
        toks = set(n.split())
        joined = n.replace(" ", "")
        for t in targets:
            tn = _norm(t)
            if not tn:
                continue
            if tn in toks or joined == tn.replace(" ", ""):
                return True
    return False


def near_miss(posting, why, crit, days=7):
    """A dropped posting he might still want to see: an internship or new-grad
    role from the last week, turned away by a rule rather than by what it is.

    Everything else (full-time and senior roles, old postings) is the bulk of
    every board and would bury the few worth a second look.
    """
    if not why or why.startswith(("seniority", "title carries no")):
        return False
    age = posting.age_hours
    if age is None or age > days * 24:
        return False
    return posting.source == "community" or bool(
        _any_in(crit["terms"].get("require_in_title_any") or [], posting.title.lower()))


def classify(posting, crit, targets=None):
    """Return (Match | None, drop_reason)."""
    targets = {t.lower() for t in (targets or TARGETS_DEFAULT)}
    title = posting.title.lower()
    loc = (posting.location or "").lower()
    desc = (posting.description or "").lower()
    blob = f"{title} {desc}"

    excl = _any_in_loose(crit["titles"]["exclude_any"], title)
    if excl:
        return None, f"title excluded ({excl[0]})"
    if not _any_in_loose(crit["titles"]["require_any"], title):
        return None, "title not a wanted role"

    # Seniority gate. A student is not eligible for Staff/Senior/Principal
    # roles, and those were dominating tier 1 because they are posted in
    # Toronto by target companies.
    # "Member of Technical Staff" is a job title, not a Staff level.
    sen = _any_in(crit["titles"].get("seniority_exclude", []), title.replace("technical staff", "technical"))
    if sen:
        return None, f"seniority excluded ({sen[0]})"

    # The level signal must be in the TITLE. Descriptions mention "co-op" or a
    # year in boilerplate constantly, so trusting the description here let
    # full-time roles through.
    lvl = crit["terms"].get("require_in_title_any")
    # Whole-word: loose matching let "intern" fire inside "Internal", which put
    # "SpaceX Software Engineer, Internal Applications" through on 2026-09-16.
    if lvl and not _any_in(lvl, title):
        return None, "title carries no internship/new-grad signal"

    if _any_in_loose(crit["terms"]["exclude_any"], blob):
        return None, f"wrong term ({_any_in_loose(crit['terms']['exclude_any'], blob)[0]})"
    if not _any_in_loose(crit["terms"]["require_any"], blob):
        return None, "no matching term"

    canadian = bool(_any_in(crit["locations"].get("canada_markers", []), loc))
    # "London, ON" is Canadian; "London" alone is not.
    if not canadian and _any_in(crit["locations"]["exclude_any"], loc):
        return None, f"location excluded ({loc})"

    # Positive geography gate. criteria.yaml declared allowed_countries but
    # nothing enforced it, so "Doha, Qatar" passed on the blocklist's silence.
    # Not for the curated lists: they only carry US and Canadian internships,
    # and write places however they like ("NYC", "SF") - keeping only the
    # spellings listed here lost 70 US postings in a month (2026-09-21). Those
    # are dropped only when they name another country.
    allowed = crit["locations"].get("allowed_countries") or []
    if allowed and loc and posting.source != "community":
        ok = (_any_in(allowed, loc)
              or _any_in(crit["locations"]["preferred"], loc)
              or _any_in(crit["locations"].get("allowed_regions", []), loc))
        if not ok:
            return None, f"location not in allowed geography ({loc[:40]})"

    reasons = []
    borderline = _any_in_loose(crit["titles"].get("borderline_any", []), title)
    if borderline:
        reasons.append(f"borderline role type: {borderline[0]} - confirm from JD")

    in_canada = bool(_any_in(crit["locations"].get("canada_markers", []), loc))

    # Places he turned off in Settings. A posting stays if any seat it offers
    # is one he wants.
    allow = crit["locations"].get("allow")
    if allow and loc:
        from .settings import seat_kinds
        kinds = seat_kinds(loc, in_canada)
        if kinds and not any(allow.get(k, True) for k in kinds):
            return None, f"place turned off in settings ({', '.join(sorted(kinds))})"

    # He is a Canadian citizen: a no-sponsorship clause only disqualifies him
    # from a role he would have to take outside Canada. A posting listing a
    # Canadian location alongside US ones stays, since he can take that seat.
    elig = crit["eligibility"]
    if not in_canada:
        blocker = _any_in_loose(elig.get("drop_outside_canada_if_description_contains", []), desc)
        if blocker:
            return None, f"needs US work authorization ({blocker[0]})"

    flags = _any_in_loose(elig["flag_if_description_contains"], desc)
    for f in flags:
        reasons.append(f"eligibility flag: {f!r}")

    preferred = bool(_any_in(crit["locations"]["preferred"], loc))
    is_target = _is_target(posting, targets)

    # the user, 2026-09-16: every tier gets a resume; tier only orders the work.
    # Canada is not split by province.
    tier = 1 if is_target else 2 if in_canada else 3

    age = posting.age_hours
    fresh = crit.get("freshness") or {}
    limit = (fresh.get("max_age_hours_by_tier") or {}).get(tier, fresh.get("max_age_hours"))
    if limit is not None and age is not None and age > limit:
        return None, f"posted too long ago (over {limit}h)"

    if age is not None:
        if age <= crit["freshness"]["hot_hours"]:
            reasons.append(f"HOT - posted {age:.1f}h ago")
        elif age <= crit["freshness"]["warm_hours"]:
            reasons.append(f"posted {age:.0f}h ago")
    else:
        reasons.append("no employer timestamp - treat date as unknown")

    if posting.deadline:
        reasons.append(f"deadline {posting.deadline.date()}")

    return Match(posting=posting, tier=tier, reasons=reasons), None


def run(postings, crit, targets=None, dropped=None):
    """Matches, and a count per drop reason. Pass a list as `dropped` to get
    each dropped posting with its reason too."""
    matches, drops = [], {}
    for p in postings:
        m, why = classify(p, crit, targets)
        if m:
            matches.append(m)
        else:
            drops[why] = drops.get(why, 0) + 1
            if dropped is not None:
                dropped.append((p, why))
    matches.sort(key=lambda m: (m.tier, -(m.posting.age_hours is None),
                                m.posting.age_hours if m.posting.age_hours is not None else 1e9))
    return matches, drops
