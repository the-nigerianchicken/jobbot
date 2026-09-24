"""Commit and push workflow state without losing a concurrent writer's changes.

Several writers push to main: watch (every 15 min), resume runs, approve runs,
and occasional laptop commands. A plain `git pull --rebase` inside a retry loop
left a half-finished rebase with conflict markers in data/tailored.json on
2026-09-17, which crashed the next step.

Instead: move HEAD to the remote tip without touching the working tree, stage
only the paths this writer owns, and merge data/tailored.json entry by entry
(newest `at` wins). Retry from the top when the push races someone else.

    python -m jobbot.gitsync "resumes: built" resumes data/tailored.json
"""
import json, os, subprocess, sys, time
from pathlib import Path

# Commits land in the checkout his things live in, which is a separate private
# repo once the code is public.
from .paths import PRIVATE as ROOT
# JSON files shaped {uid: {..., "at": iso}} that several writers update; merged
# entry by entry instead of overwritten.
MERGED = ("data/tailored.json", "data/notified.json", "data/requested.json", "data/hints.json")
# Append-only logs: the remote's lines, then any of ours it lacks.
APPENDED = ("data/approvals.jsonl", "data/applications.jsonl")


def git(*args, check=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def merge_ledgers(theirs, mine):
    out = dict(theirs)
    for uid, v in mine.items():
        if uid not in out or (v.get("at") or "") >= (out[uid].get("at") or ""):
            out[uid] = v
    return out


def push(message, paths, attempts=5):
    # A job step that skipped `git config` (approve.yml retries) once lost an
    # application log this way; never depend on the caller for identity.
    if not git("config", "user.name").stdout.strip():
        git("config", "user.name", "jobbot")
        git("config", "user.email", "jobbot@users.noreply.github.com")
    mine = {p: json.loads((ROOT / p).read_text(encoding="utf-8"))
            for p in MERGED if p in paths and (ROOT / p).exists()}
    tails = {p: (ROOT / p).read_text(encoding="utf-8").splitlines()
             for p in APPENDED if p in paths and (ROOT / p).exists()}
    for attempt in range(1, attempts + 1):
        if (ROOT / ".git" / "rebase-merge").exists() or (ROOT / ".git" / "rebase-apply").exists():
            git("rebase", "--abort")
        git("fetch", "-q", "origin", "main", check=True)
        git("reset", "-q", "--mixed", "origin/main", check=True)
        for p, ours in mine.items():
            shown = git("show", f"origin/main:{p}")
            theirs = json.loads(shown.stdout) if shown.returncode == 0 and shown.stdout.strip() else {}
            (ROOT / p).write_text(json.dumps(merge_ledgers(theirs, ours), indent=2, sort_keys=True),
                                  encoding="utf-8")
        for p, ours in tails.items():
            shown = git("show", f"origin/main:{p}")
            theirs = shown.stdout.splitlines() if shown.returncode == 0 else []
            have = set(theirs)
            lines = theirs + [l for l in ours if l.strip() and l not in have]
            (ROOT / p).write_text("\n".join(lines) + "\n", encoding="utf-8")
        existing = [p for p in paths if (ROOT / p).exists()]
        if existing:
            # --ignore-removal: this checkout may predate files another writer
            # pushed (e.g. a newer resume folder); never stage their deletion.
            git("add", "--ignore-removal", "--", *existing, check=True)
        if git("diff", "--cached", "--quiet").returncode == 0:
            print("nothing to commit")
            return 0
        git("commit", "-q", "-m", message, check=True)
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            print(f"pushed: {message}")
            return 0
        print(f"push raced another writer (attempt {attempt}), retrying")
        time.sleep(3 * attempt)
    print("ERROR: could not push after retries", file=sys.stderr)
    return 1


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: python -m jobbot.gitsync <message> <path> [<path> ...]", file=sys.stderr)
        return 2
    return push(argv[0], argv[1:])


if __name__ == "__main__":
    sys.exit(main())
