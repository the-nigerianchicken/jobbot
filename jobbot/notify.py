"""Surface new matches to the user.

GitHub only emails on a failed run, so the watcher deliberately exits nonzero
when a new tier-1/2 posting appears: a red Actions tab means good news. Set
notify.fail_on_match: false in criteria.yaml to turn that off.

Usage: python -m jobbot.notify data/queue.json [--test]
  --test  exit 1 regardless of matches, to check the alert actually reaches you
"""
import json, os, sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def summary_markdown(rows):
    if not rows:
        return "### jobbot: no new postings\n"
    lines = [f"### jobbot: {len(rows)} new posting(s)", "",
             "| tier | company | title | location | posted | flags |",
             "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r.get("tier", 9)):
        posted = (r.get("posted_at") or "date-unknown")[:10]
        flags = "; ".join(x for x in r.get("reasons", []) if not x.startswith("posted "))
        title = f"[{r.get('title', '?')}]({r.get('url', '')})"
        lines.append(f"| T{r.get('tier')} | {r.get('company', '?')} | {title} | "
                     f"{r.get('location') or '?'} | {posted} | {flags} |")
    return "\n".join(lines) + "\n"


def _resolve(name):
    from .paths import at
    return str(at(name))


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    test = "--test" in argv
    argv = [a for a in argv if a != "--test"]
    path = str(_resolve(argv[0])) if argv else str(_resolve("data/queue.json"))
    rows = json.load(open(path)) if os.path.exists(path) else []
    from .paths import CRITERIA
    crit = yaml.safe_load(open(CRITERIA, encoding="utf-8"))
    cfg = crit.get("notify") or {}
    alert_tiers = set(cfg.get("alert_tiers", [1, 2]))

    md = summary_markdown(rows)
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(md)
    print(md)

    if test:
        print("TEST ALERT - failing on purpose; if GitHub emailed you, alerts work", file=sys.stderr)
        return 1
    hot = [r for r in rows if r.get("tier") in alert_tiers]
    if hot and cfg.get("fail_on_match", True):
        print(f"{len(hot)} tier {sorted(alert_tiers)} match(es) - exiting 1 so GitHub notifies",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
