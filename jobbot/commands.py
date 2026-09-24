"""Actions the user takes on a job from the phone app (or by commenting on the issue).

The app posts a comment; commands.yml runs this. Keeping the app's buttons and
the issue comments on the same channel means both work, and neither needs extra
permissions on his token.

    /apply      submit it for me            (handled by approve.yml)
    /applied    I applied myself            - recorded, no submission
    /rebuild    write the resume again      - requeue and start a resume run
    /stop       cancel the apply run        - and leave the job ready again
    /skip       not interested              - closes the issue
    /reopen     put it back in the queue

    python -m jobbot.commands <issue> <command>
"""
import json, subprocess, sys
from datetime import datetime, timezone

from . import store, tailor


def find(issue):
    ledger = tailor._load("tailored.json", {})
    for uid, v in ledger.items():
        if str(v.get("issue")) == str(issue):
            return uid, v
    return None, None


def say(issue, body):
    tailor.gh("issue", "comment", str(issue), "-R", tailor.REPO, "--body", body)
    print(body)


def cmd_applied(uid, v, issue):
    """He applied by hand: record it exactly as an approval, without applying."""
    with open(tailor.DATA / "approvals.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"uid": uid, "issue": int(issue), "company": v.get("company"),
                             "title": v.get("title"), "apply_url": v.get("apply_url"),
                             "pdf": v.get("pdf"), "by_hand": True,
                             "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
    store.log_application({"uid": uid, "issue": str(issue), "company": v.get("company"),
                           "title": v.get("title"), "apply_url": v.get("apply_url"),
                           "status": "submitted", "notes": ["marked applied by hand"],
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    tailor.gh("issue", "edit", str(issue), "-R", tailor.REPO, "--add-label", "approved")
    tailor.gh("issue", "close", str(issue), "-R", tailor.REPO, "--reason", "completed")
    say(issue, "Recorded as applied by you. It will not appear in alerts or digests again, and it is "
               "added to Tracker.xlsx the next time `python -m jobbot.sync_pipeline` runs on the laptop.")


def cmd_rebuild(uid, v, issue):
    tailor._mark(uid, "retry")
    tailor.gh("issue", "close", str(issue), "-R", tailor.REPO, "--reason", "not_planned")
    say(issue, "Rebuilding the resume from scratch. A new issue opens when it is ready; this one is closed.")
    subprocess.run(["gh", "workflow", "run", "resume.yml", "-R", tailor.REPO], capture_output=True)


def cmd_stop(uid, v, issue):
    """Cancel an apply run in flight and leave the job ready to try again."""
    runs = subprocess.run(["gh", "run", "list", "-R", tailor.REPO, "-w", "approve.yml", "-L", "5",
                           "--json", "databaseId,status"], capture_output=True, text=True).stdout
    live = [r["databaseId"] for r in json.loads(runs or "[]") if r["status"] != "completed"]
    for run_id in live:
        subprocess.run(["gh", "run", "cancel", str(run_id), "-R", tailor.REPO], capture_output=True)
    say(issue, f"Stopped {len(live)} apply run(s). Nothing was submitted unless the form had already gone "
               "through; check the screenshots above if one was posted.")


def cmd_skip(uid, v, issue):
    tailor._mark(uid, "skipped", reason="not interested (from the app)")
    tailor.gh("issue", "close", str(issue), "-R", tailor.REPO, "--reason", "not_planned")
    say(issue, "Skipped. It will not come back.")


def cmd_reopen(uid, v, issue):
    tailor._mark(uid, "resume_ready")
    tailor.gh("issue", "reopen", str(issue), "-R", tailor.REPO)
    say(issue, "Back in the queue.")


COMMANDS = {"applied": cmd_applied, "rebuild": cmd_rebuild, "stop": cmd_stop,
            "skip": cmd_skip, "reopen": cmd_reopen}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("usage: python -m jobbot.commands <issue> <command>", file=sys.stderr)
        return 2
    issue, command = argv[0], argv[1].lstrip("/").lower()
    if command not in COMMANDS:
        print(f"unknown command {command!r}; known: {', '.join(sorted(COMMANDS))}", file=sys.stderr)
        return 0
    uid, v = find(issue)
    if not uid:
        say(issue, f"Could not run /{command}: no job is linked to this issue.")
        return 0
    COMMANDS[command](uid, v, issue)
    return 0


if __name__ == "__main__":
    sys.exit(main())
