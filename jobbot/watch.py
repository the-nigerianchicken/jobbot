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

    # Say what the screening has decided, so a verdict that never reaches the
    # rules shows up here rather than as silence.
    from . import screen as _screen
    _said = _screen.verdicts()
    print(f"screened: {len(_said)} judged, {sum(1 for v in _said.values() if not v.get('ok'))} he cannot take")

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
        write_filtered(dropped, crit, withdrawn=recheck_queue(crit, targets))
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
        from . import paths
        out_path = paths.at(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as fh:
            json.dump([{"tier": m.tier, "reasons": m.reasons, **m.posting.to_dict()}
                       for m in new], fh, indent=2)
    return 0


FILTERED = Path(store.DATA) / "filtered.json"


def recheck_queue(crit, targets):
    """Postings already queued that the current rules would no longer take.

    The board is rebuilt from the queue on every sweep, but the queue was only
    ever checked on the way in. So editing a rule changed what arrived next and
    nothing that had already arrived: on 2026-09-26, 32 postings for terms that
    had ended and 6 asking for a PhD stayed in New, and would have until they
    aged out a week later.

    Only postings he has not touched. Anything he asked for, anything with a
    resume, and anything he has applied to is his decision, not the rules'.
    """
    from . import tailor
    pending = store._load("pending.json", {})
    keep, out = {}, []
    want, approved = tailor.requested(), tailor.approved_uids()
    ledger = tailor._load("tailored.json", {})
    for uid, row in pending.items():
        if uid in want or uid in approved or uid in ledger:
            keep[uid] = row
            continue
        try:
            posting = tailor.to_posting(row)
        except Exception:
            keep[uid] = row                     # unreadable row: not ours to drop
            continue
        dead = match.dead_terms(posting.title, posting.description or "", crit,
                                said=" / ".join(row.get("terms") or []))
        if dead:
            out.append((posting, f"wrong term ({dead})"))
            continue
        m, why = match.classify(posting, crit, targets)
        if m is not None or not why or why.startswith("posted too long ago"):
            keep[uid] = row                     # age is handled elsewhere, by date
            continue
        out.append((posting, why))
    if out:
        store._save("pending.json", keep)
        print(f"queue: {len(out)} no longer match the rules")
    return out


def write_filtered(dropped, crit, withdrawn=()):
    """What the rules turned away this run, for the app's "Filtered out" list.

    Not committed: the sync step at the end of this same job sends it, and a
    rule that is wrong shows up there instead of as a job he never hears of.

    `withdrawn` is the postings that were on his board until this run took them
    off. near_miss exists to keep the bulk of every board out of this list, and
    it needs a posted date to do that - but these are not board noise, they are
    cards disappearing from under him, and a card that vanishes without a reason
    is the thing he asked never to happen. They are always listed.
    """
    from .tailor import display_company
    always = {p.uid for p, _ in withdrawn}
    seen, out = set(), []
    for p, why in list(withdrawn) + list(dropped):
        if p.uid in seen or (p.uid not in always and not match.near_miss(p, why, crit)):
            continue
        seen.add(p.uid)
        out.append({"uid": p.uid, "company": display_company(p.company, p.org), "title": p.title,
                    "location": p.location, "source": p.source, "org": p.org, "raw_id": p.raw_id,
                    "url": p.url, "apply_url": p.apply_url, "reason": why,
                    "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                    "deadline": p.deadline.isoformat() if p.deadline else None,
                    "description": (p.description or "")[:12000]})
    # Withdrawals first, so the cap never drops the one posting whose absence
    # he would otherwise have to guess at.
    out.sort(key=lambda f: f["uid"] not in always)
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
    # A posting leaves the queue when the resume side has finished with it. It
    # used to count a folder as finished - but the folder is made before the
    # writing starts, so a run that died halfway looked done and the posting was
    # dropped. It could then never be built again, and the card said "Waiting
    # its turn" for ever (2026-09-25, Snowflake). What he asked for stays until
    # there is a resume, or until he archives it.
    keep_until_written = ("in_progress", "retry", "build_failed", "cannot_build")
    for uid in [u for u in pending if u in done
                and done[u]["status"] not in ("in_progress", "retry")
                and not (u in asked and done[u]["status"] in keep_until_written)]:
        del pending[uid]
    for m in new:
        if _key(m.posting.company) in quiet or _key(m.posting.org) in quiet:
            continue
        pending.setdefault(m.posting.uid, posting_dict(m))
    # Anything he has asked to have written again, which an older prune dropped
    # out of the queue before its resume existed.
    from .tailor import complete, requeue
    store._save("pending.json", pending)
    put_back = 0
    for uid, v in done.items():
        if v.get("status") == "retry" and uid not in pending:
            put_back += requeue(uid)
    # requeue writes the file itself, so read it back before saving over it.
    if put_back:
        pending = store._load("pending.json", {})
    mended = sum(complete(row) for row in pending.values())
    if mended:
        print(f"queue: filled in {mended} row(s) that were missing fields")
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
