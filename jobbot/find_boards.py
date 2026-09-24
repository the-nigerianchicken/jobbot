"""Find the career boards of the companies he follows.

The registry is built from links the community lists happen to carry, so a
company he follows can be missing from it entirely: on 2026-09-24, 39 of his 81
followed companies were - Google, Microsoft, Shopify, Stripe, Databricks, Waymo
among them. Those reached him only if a list mentioned them, hours late.

This asks each ATS directly whether it hosts a board under the company's name,
and registers the ones that answer with real postings.

    python -m jobbot.find_boards            # every followed company with no board
    python -m jobbot.find_boards --all      # every followed company, even known ones
    python -m jobbot.find_boards --add      # and write what it finds into the registry
"""
import argparse, itertools, json, re, sys
from concurrent.futures import ThreadPoolExecutor

from . import store, watch

KEY = lambda s: re.sub(r"[^a-z0-9]+", "", str(s or "").lower())

# The shapes a company's slug usually takes on each board.
def slugs(name):
    plain = KEY(name)
    spaced = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return list(dict.fromkeys([plain, spaced, spaced.replace("-", "")]))


def greenhouse(slug, get):
    data = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    n = len((data or {}).get("jobs") or [])
    return ("greenhouse", slug, n) if n else None


def lever(slug, get):
    data = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    n = len(data or []) if isinstance(data, list) else 0
    return ("lever", slug, n) if n else None


def ashby(slug, get):
    data = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    n = len((data or {}).get("jobs") or [])
    return ("ashby", slug, n) if n else None


BOARDS = (greenhouse, lever, ashby)


def look(name, get):
    """The first board that answers for this company, with how many jobs it has."""
    for slug, board in itertools.product(slugs(name), BOARDS):
        try:
            found = board(slug, get)
        except Exception:
            found = None
        if found:
            return found
    return None


def missing(targets, reg):
    known = set()
    for b in reg.get("boards", []):
        known.add(KEY(b.get("org")))
    out = []
    for t in targets:
        k = KEY(t)
        if k in known or any(k == o or (len(k) > 4 and k in o) for o in known):
            continue
        out.append(t)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="look up every followed company")
    ap.add_argument("--add", action="store_true", help="write what is found into the registry")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    from .sources import _get as get
    targets, reg = watch.load_targets(), store.load_registry()
    want = targets if a.all else missing(targets, reg)
    print(f"{len(want)} followed company(ies) to look up")

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        found = list(zip(want, pool.map(lambda t: look(t, get), want)))

    hits = [(t, f) for t, f in found if f]
    for t, (source, slug, n) in hits:
        print(f"  {t:<16} {source}:{slug} ({n} jobs)")
    lost = [t for t, f in found if not f]
    print(f"{len(hits)} found, {len(lost)} not on a board jobbot can read: {', '.join(lost)}")

    if a.add and hits:
        have = {(b.get("source"), b.get("org")) for b in reg.get("boards", [])}
        for t, (source, slug, n) in hits:
            if (source, slug) in have:
                continue
            reg.setdefault("boards", []).append({"org": slug, "source": source, "target": True})
        store.save_registry(reg)
        print(f"registry now holds {len(reg['boards'])} boards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
