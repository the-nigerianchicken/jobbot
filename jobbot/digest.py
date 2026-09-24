"""Morning list of matching jobs posted in the last 24 hours, by tier.

Posted as a GitHub issue that @mentions the user, so GitHub emails it to him and
it shows in the mobile app. The previous digest issue is closed. "Posted" is
the employer's own ATS timestamp, never an aggregator's.

Each job reaches him once (tailor.notified): jobs already sent as a tier 1/2
alert, or in an earlier digest, are left out, and so is anything he applied
to (Tracker.xlsx, manual folders, /approve). Jobs listed here are recorded so
a later resume issue for them stays silent.

    python -m jobbot.digest            # fetch, build, open the issue
    python -m jobbot.digest --print    # just print the markdown
"""
import argparse, sys
from datetime import datetime, timedelta, timezone

from . import match, sources, store, tailor, watch

TIER_NAMES = {1: "Tier 1 - target companies", 2: "Tier 2 - Canada", 3: "Tier 3 - US"}


def resume_cell(uid, ledger, pending):
    v = ledger.get(uid)
    if v and v["status"] == "resume_ready" and v.get("issue"):
        return f"ready #{v['issue']}"
    if v and v["status"] == "already_applied":
        return "applied"
    if v and v["status"] in ("skipped", "dropped"):
        return "skipped"
    if v and v["status"] in ("in_progress", "retry"):
        return "building"
    if uid in pending:
        return "queued"
    return ""


def build(hours=24):
    crit, targets = watch.load_criteria(), watch.load_targets()
    postings, health = sources.fetch_all(store.active_boards(store.load_registry()))
    matches, _ = match.run(postings, crit, targets)
    matches, _expired = sources.drop_expired(matches)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    ledger, pending = tailor._load("tailored.json", {}), tailor._load("pending.json", {})
    told, approved, prior = tailor.notified(), tailor.approved_uids(), tailor.prior_applications()
    recent, skipped_told, skipped_applied = [], 0, 0
    for m in matches:
        p = m.posting
        if not p.posted_at or p.posted_at < cutoff:
            continue
        if p.uid in told:
            skipped_told += 1
            continue
        t = {"company": tailor.display_company(p.company, p.org), "org": p.org, "title": p.title,
             "location": p.location, "raw_id": p.raw_id}
        if (p.uid in approved or ledger.get(p.uid, {}).get("status") == "already_applied"
                or tailor.already_applied(t, prior)):
            skipped_applied += 1
            continue
        recent.append(m)

    date = now.strftime("%Y-%m-%d")
    lines = [f"@{tailor.OWNER} {len(recent)} new matching job(s) posted in the last {hours} hours "
             f"(employer timestamps, as of {now:%H:%M} UTC).", ""]
    for tier in (1, 2, 3):
        rows = sorted((m for m in recent if m.tier == tier), key=lambda m: m.posting.posted_at, reverse=True)
        lines += [f"### {TIER_NAMES[tier]} ({len(rows)})", ""]
        if not rows:
            lines += ["None new.", ""]
            continue
        lines += ["| Posted | Company | Role | Location | Resume |", "|---|---|---|---|---|"]
        for m in rows:
            p = m.posting
            age = (now - p.posted_at).total_seconds() / 3600
            esc = lambda s: (s or "?").replace("|", "/")
            lines.append(f"| {age:.0f}h ago | {esc(tailor.display_company(p.company, p.org))} | "
                         f"[{esc(p.title)}]({p.apply_url or p.url}) | {esc(p.location)[:40]} | "
                         f"{resume_cell(p.uid, ledger, pending)} |")
        lines.append("")
    undated = sum(1 for m in matches if not m.posting.posted_at)
    failed = sum(1 for h in health.values() if not h["ok"])
    lines += ["---", f"Not repeated: {skipped_told} already sent as an alert or earlier digest, "
              f"{skipped_applied} already applied to. {len(matches)} open matches in total; "
              f"{undated} without an employer timestamp. {len(health)} boards polled, {failed} failed."]
    return (f"Jobs posted in the last 24h - {date} ({len(recent)})", "\n".join(lines),
            [m.posting.uid for m in recent])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--hours", type=int, default=24)
    a = ap.parse_args(argv)
    title, body, uids = build(a.hours)
    if a.print:
        print(title, body, sep="\n\n")
        return 0
    if not uids:
        print("no new jobs to send - no digest today")
        return 0
    gh = tailor.gh
    gh("label", "create", "digest", "--color", "5319e7", "--force", "-R", tailor.REPO)
    old = gh("issue", "list", "-R", tailor.REPO, "--label", "digest", "--state", "open",
             "--json", "number", "--jq", ".[].number").stdout.split()
    r = gh("issue", "create", "-R", tailor.REPO, "--title", title, "--body", body, "--label", "digest")
    if r.returncode != 0:
        print(f"ERROR: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"opened {r.stdout.strip()}")
    tailor.mark_notified(uids, "digest", issue=r.stdout.strip().rsplit("/", 1)[-1])
    for n in old:
        gh("issue", "close", n, "-R", tailor.REPO, "--comment", f"Superseded by {r.stdout.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
