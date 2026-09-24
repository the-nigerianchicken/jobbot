"""Entrypoint. `python -m jobbot.watch`

Deterministic end to end: same inputs produce the same output, every run. The
scheduled task's only job is to run this and relay stdout - which is what makes
the report format stable instead of re-improvised each fire.
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import community, discover, match, sources, store

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_criteria(path=None):
    """criteria.yaml, with what he set in the app's Settings on top."""
    from . import paths
    crit = yaml.safe_load(open(path or paths.CRITERIA, encoding="utf-8"))
    if path:
        return crit
    from . import settings
    return settings.apply_search(crit)


def load_targets():
    from . import paths
    with open(paths.TARGETS, encoding="utf-8") as fh:
        return [w for w in fh.read().split() if w]


def cmd_seed(args):
    reg = store.load_registry()
    paths = args.listings or discover.clone_lists()
    if not paths:
        print("SEED FAILED: could not obtain any aggregator listings.json", file=sys.stderr)
        return 1
    pairs = discover.from_listings(paths)
    added = discover.merge_into_registry(reg, pairs, load_targets())
    store.save_registry(reg)
    print(f"registry: {len(reg['boards'])} boards ({added} new) from {len(paths)} list(s)")
    return 0


def cmd_watch(args):
    crit = load_criteria(args.criteria)
    targets = load_targets()
    reg = store.load_registry()
    boards = store.active_boards(reg, workday=args.workday, targets_only=args.targets)
    if args.limit:
        boards = boards[: args.limit]
    if args.only:
        boards = [b for b in boards if b[0] == args.only]

    postings, health = sources.fetch_all(boards, max_workers=args.workers)
    # The community lists repeat postings jobbot reads itself; keep the native copy.
    postings = community.dedupe(postings, store.load_seen())
    dropped = []
    matches, drops = match.run(postings, crit, targets, dropped)
    # Workday and Ashby only reveal the employer's date (and Ashby's deadline)
    # per posting, so matches are enriched and then re-checked against the
    # criteria - a "Posted Today" Workday job can turn out to be from August.
    sources.enrich(matches)
    rechecked, stale = [], 0
    for m in matches:
        again, why = match.classify(m.posting, crit, targets)
        if again is None:
            stale += 1
            drops[why] = drops.get(why, 0) + 1
            dropped.append((m.posting, why))
        else:
            rechecked.append(again)
    matches = rechecked
    matches, expired = sources.drop_expired(matches)
    if expired:
        drops["application deadline passed"] = len(expired)

    seen = store.load_seen()
    new = [m for m in matches if m.posting.uid not in seen]
    # A posting from a community list arrives without its description. He
    # decides whether to apply by reading it, so fetch it now for the handful
    # that are new, rather than only when he asks for a resume.
    bare = [m for m in new if m.posting.source == "community" and len(m.posting.description or "") < 300]
    if bare and not args.dry_run:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            for m, text in zip(bare[:40], pool.map(lambda m: community.describe(m.posting.url), bare[:40])):
                if text:
                    m.posting.description = ((m.posting.description or "") + "\n\n" + text).strip()

    matched_keys = {}
    for m in matches:
        k = f"{m.posting.source}:{m.posting.org}"
        matched_keys[k] = matched_keys.get(k, 0) + 1
    store.update_health(reg, health, matched_keys)
    store.save_registry(reg)

    if not args.dry_run:
        write_filtered(dropped, crit)
        for m in new:
            store.mark_seen(seen, m.posting)
        store.save_seen(seen)
        backlog = [m for m in matches if m.tier in (args.backlog_tiers or [])]
        if args.backlog_hours:
            backlog += [m for m in matches
                        if m.posting.age_hours is not None and m.posting.age_hours <= args.backlog_hours]
        enqueue(new + backlog)

    report(boards, postings, matches, new, drops, health, crit, args)
    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump([{"tier": m.tier, "reasons": m.reasons, **m.posting.to_dict()}
                       for m in new], fh, indent=2)
    return 0


FILTERED = Path(store.DATA) / "filtered.json"


def write_filtered(dropped, crit):
    """What the rules turned away this run, for the app's "Filtered out" list.

    Not committed: the sync step at the end of this same job sends it, and a
    rule that is wrong shows up there instead of as a job he never hears of.
    """
    from .tailor import display_company
    seen, out = set(), []
    for p, why in dropped:
        if p.uid in seen or not match.near_miss(p, why, crit):
            continue
        seen.add(p.uid)
        out.append({"uid": p.uid, "company": display_company(p.company, p.org), "title": p.title,
                    "location": p.location, "source": p.source, "org": p.org, "raw_id": p.raw_id,
                    "url": p.url, "apply_url": p.apply_url, "reason": why,
                    "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                    "deadline": p.deadline.isoformat() if p.deadline else None,
                    "description": (p.description or "")[:12000]})
    FILTERED.write_text(json.dumps(out[:400], indent=1), encoding="utf-8")
    print(f"filtered out, worth a look: {len(out)}")


def enqueue(new):
    """Queue new matches for the resume workflow, with the full JD.

    watch is the only writer of pending.json and tailor the only writer of
    tailored.json, so the two workflows never conflict on a file. Entries the
    resume side has finished with are pruned here.
    """
    from .tailor import posting_dict, _key
    pending = store._load("pending.json", {})
    done = store._load("tailored.json", {})
    # Companies he muted in the app never reach the board again.
    quiet = set(store._load("muted.json", {}))
    from .tailor import requested
    asked = requested()
    for uid in [u for u in pending if u in done and done[u]["status"] not in ("in_progress", "retry")
                and not (u in asked and not done[u].get("folder"))]:
        del pending[uid]
    for m in new:
        if _key(m.posting.company) in quiet or _key(m.posting.org) in quiet:
            continue
        pending.setdefault(m.posting.uid, posting_dict(m))
    store._save("pending.json", pending)


def report(boards, postings, matches, new, drops, health, crit, args):
    failed = {k: v["error"] for k, v in health.items() if not v["ok"]}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"jobbot watch  {now}")
    print(f"criteria: {crit['profile_label']}")
    print(f"boards polled: {len(boards)}  postings seen: {len(postings)}  "
          f"passing filter: {len(matches)}  NEW: {len(new)}")
    print()

    if not new:
        print("NO NEW POSTINGS")
    else:
        for m in new:
            p = m.posting
            when = p.posted_at.strftime("%Y-%m-%d") if p.posted_at else "date-unknown"
            print(f"[T{m.tier}] {p.company} | {p.title} | {p.location or '?'} | "
                  f"posted {when}")
            print(f"       {p.url}")
            for r in m.reasons:
                print(f"       - {r}")
    if failed:
        print()
        print(f"{len(failed)} board(s) failed:")
        for k, e in list(failed.items())[:10]:
            print(f"  {k}: {e}")
    if args.verbose and drops:
        print()
        print("drop reasons:")
        for why, n in sorted(drops.items(), key=lambda x: -x[1])[:12]:
            print(f"  {n:5}  {why}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed", help="populate the board registry from aggregator lists")
    s.add_argument("--listings", nargs="*", help="local listings.json paths")
    s.set_defaults(func=cmd_seed)

    w = sub.add_parser("watch", help="poll boards and report new matches")
    w.add_argument("--limit", type=int, help="poll only the first N boards")
    w.add_argument("--only", choices=sorted(sources.FETCHERS))
    w.add_argument("--workers", type=int, default=24)
    w.add_argument("--workday", choices=["hot", "all", "none"], default="hot",
                   help="which Workday tenants to poll: targets/productive ones (hot), every one "
                        "(all - the twice-daily sweep), or skip them")
    w.add_argument("--targets", action="store_true",
                   help="only target companies and Amazon - a fast sweep to run often")
    w.add_argument("--criteria")
    w.add_argument("--json-out")
    w.add_argument("--dry-run", action="store_true", help="do not write seen.json")
    w.add_argument("--backlog-tiers", type=int, nargs="*",
                   help="also queue EVERY current match in these tiers for a resume, not just new ones")
    w.add_argument("--backlog-hours", type=int,
                   help="also queue every current match posted within this many hours")
    w.add_argument("-v", "--verbose", action="store_true")
    w.set_defaults(func=cmd_watch)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
