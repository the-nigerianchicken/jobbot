"""Keep the phone app and jobbot's own files in step.

The app is what the user looks at, so every run ends by telling it what happened,
and starts by picking up whatever he tapped while the laptop was off.

    python -m jobbot.appsync push     # send the current jobs to the app
    python -m jobbot.appsync pull     # apply what he tapped, then ack it
    python -m jobbot.appsync sync     # pull, then push (what the workflows run)

Needs two environment variables, set from repository secrets:
    APP_URL     https://jobbot.<subdomain>.workers.dev
    APP_TOKEN   the same value as the worker's INGEST_TOKEN secret

Without them it prints one line and exits 0, so a run never fails because the
app is unreachable - the repo files stay the source of truth for jobbot itself.
"""
import json, os, sys, urllib.error, urllib.request
from datetime import datetime, timezone

from . import gitsync, seed_store, store, tailor

BASE = (os.environ.get("APP_URL") or "").rstrip("/")
TOKEN = os.environ.get("APP_TOKEN") or ""
CHUNK = 40                      # one request is one D1 write per job; keep them small


def call(path, payload=None, method="GET"):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        # Cloudflare turns away the default urllib agent.
        headers={"authorization": f"Bearer {TOKEN}", "content-type": "application/json",
                 "user-agent": "jobbot/1.0 (+github actions)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def push():
    """Send the jobs, and say when the boards were last looked at.

    The app shows that time, so he can tell the difference between "nothing
    new" and "nothing is running".
    """
    rows = seed_store.job_rows()
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sent = 0
    for i in range(0, len(rows), CHUNK):
        batch = rows[i:i + CHUNK]
        sent += call("/api/ingest", {"jobs": batch, "checked_at": checked}, "POST").get("written", 0)
    # Everything jobbot knows about, so the app can drop what it has forgotten.
    from . import watch
    from . import settings
    gone = call("/api/ingest", {"jobs": [], "checked_at": checked, "targets": watch.load_targets(),
                                "known": [r["uid"] for r in rows],
                                # What Settings shows as each default. Unchanged, it costs no write.
                                "settings_base": settings.bases()}, "POST").get("removed", 0)
    print(f"app: sent {sent} job(s)" + (f", removed {gone} it no longer tracks" if gone else ""))
    if watch.FILTERED.exists():
        held = json.loads(watch.FILTERED.read_text(encoding="utf-8"))
        for i in range(0, len(held), CHUNK):
            call("/api/ingest", {"filtered": held[i:i + CHUNK]}, "POST")
        print(f"app: sent {len(held)} filtered-out posting(s)")
    return sent


# What he tapped, and what that means for jobbot's own files. The app has
# already moved the card; this is only about keeping the repo in step.
def _applied(uid, detail):
    if uid in tailor.approved_uids():
        return
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(tailor.DATA / "approvals.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"uid": uid, "issue": detail.get("issue"), "company": detail.get("company"),
                             "title": detail.get("title"), "apply_url": detail.get("apply_url"),
                             "pdf": detail.get("pdf"), "by_hand": True, "approved_at": at}) + "\n")
    MARKED.add(uid)
    store.log_application({"uid": uid, "issue": str(detail.get("issue") or ""),
                           "company": detail.get("company"), "title": detail.get("title"),
                           "apply_url": detail.get("apply_url"), "status": "submitted",
                           "notes": ["marked applied in the app"], "at": at})


def _answer(uid, detail):
    """He rewrote an answer in the app: it becomes the answer the form is filled with."""
    folder, label = detail.get("folder"), detail.get("label")
    if not folder or not label:
        return
    path = tailor.ROOT / folder / "application.json"
    if not path.exists():
        print(f"app: no application.json in {folder} - answer kept in the app only", file=sys.stderr)
        return
    app = json.loads(path.read_text(encoding="utf-8"))
    for q in app.get("questions", []):
        if q.get("label") == label:
            q["answer"] = detail.get("text", "")
            q["how"] = "you"                      # his wording is never redrafted
            break
    else:
        return
    path.write_text(json.dumps(app, indent=2, ensure_ascii=False), encoding="utf-8")
    EDITED.add(folder)
    print(f"app: answer rewritten in {folder}: {label[:60]}")


def _hint(uid, detail):
    """What he wants said differently, in his words, kept where the writer reads it."""
    text = (detail.get("hint") or "").strip()
    hints = tailor._load("hints.json", {})
    if text:
        hints[uid] = text
    else:
        hints.pop(uid, None)
    tailor._save("hints.json", hints)
    REQUESTED.add(uid)                      # hints.json rides along with requested.json
    if text:
        print(f"app: note for the resume: {text[:80]}")


def _build(uid, detail):
    """He tapped Apply (or "just write it") on a job with no resume yet."""
    _hint(uid, detail)
    want = tailor.request(uid, apply=detail.get("apply", True),
                          company=detail.get("company"), title=detail.get("title"))
    REQUESTED.add(uid)
    print(f"app: resume requested for {detail.get('company') or uid}"
          + (" (and apply)" if want["apply"] else ""))


def _rebuild(uid, detail):
    """Write it again - usually because he said what to change."""
    _hint(uid, detail)
    tailor._mark(uid, "retry")
    MARKED.add(uid)
    tailor.request(uid, apply=False)
    REQUESTED.add(uid)


def _mute(uid, detail):
    """A company he does not want to hear from. watch stops queueing it."""
    name = (detail.get("company") or "").strip()
    if not name:
        return
    muted = tailor._load("muted.json", {})
    muted[tailor._key(name)] = {"name": name,
                                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    tailor._save("muted.json", muted)
    MUTED.add(name)
    print(f"app: muted {name}")


def _unmute(uid, detail):
    name = (detail.get("company") or "").strip()
    muted = tailor._load("muted.json", {})
    if muted.pop(tailor._key(name), None) is not None:
        tailor._save("muted.json", muted)
        MUTED.add(name)
        print(f"app: unmuted {name}")


from . import paths
TARGETS = paths.TARGETS


def _follow(uid, detail, on=True):
    """He changed who he follows in the app. targets.txt is what the sweep reads."""
    k = (detail.get("key") or "").strip().lower()
    if not k:
        return
    words = TARGETS.read_text(encoding="utf-8").split()
    if on and k not in words:
        words.append(k)
    elif not on and k in words:
        words.remove(k)
    else:
        return
    # Keep the file readable: about eighty characters a line.
    lines, line = [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > 80:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    TARGETS.write_text("\n".join(lines + [line]) + "\n", encoding="utf-8")
    FOLLOWED.add(k)
    print(f"app: {'following' if on else 'stopped following'} {detail.get('company') or k}")


EDITED, REQUESTED, MUTED, FOLLOWED = set(), set(), set(), set()
# Archived, reopened or applied. The watch workflow commits its state before it
# reads his taps, so these must be committed here or the next run - checked
# out fresh - forgets them and puts the job back in his feed (2026-09-21).
MARKED = set()
RESTORED = set()

def _archive(uid, detail):
    # Kept with the job: watch drops a posting from pending.json once it is
    # decided, and a row without a company never reaches the app.
    pending = tailor._load("pending.json", {}).get(uid, {})
    keep = {k: detail.get(k) or pending.get(k) for k in ("company", "title", "url", "apply_url", "location")}
    tailor._mark(uid, "skipped", reason="Archived", **{k: v for k, v in keep.items() if v})
    MARKED.add(uid)


def _reopen(uid, detail):
    """Back to wherever it actually got to: a written resume, or just a posting."""
    had = tailor._load("tailored.json", {}).get(uid, {})
    tailor._mark(uid, "resume_ready" if had.get("folder") else "retry")
    MARKED.add(uid)


def _restore(uid, detail):
    """He wants a posting the rules turned away: it joins the feed as new."""
    t = detail.get("posting") or {}
    if not t.get("uid") or not t.get("company"):
        return
    # The curated lists carry no description; he will want to read it.
    if len(t.get("description") or "") < 300 and t.get("url"):
        from . import community
        t["description"] = ((t.get("description") or "") + "\n\n" + (community.describe(t["url"]) or "")).strip()
    pending = tailor._load("pending.json", {})
    pending.setdefault(uid, {**{k: t.get(k) for k in ("uid", "source", "org", "company", "title",
                                                       "location", "url", "apply_url", "posted_at",
                                                       "deadline", "raw_id", "description")},
                             "tier": 3, "reasons": ["brought back from Filtered out"],
                             "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    tailor._save("pending.json", pending)
    RESTORED.add(uid)


HANDLERS = {
    "restore": _restore,
    # The app says "archive"; issue comments and older app builds say "skip".
    "archive": _archive,
    "skip": _archive,
    "rebuild": _rebuild,
    "reopen": _reopen,
    "applied": _applied,
    "answer": _answer,
    "build": _build,
    "mute": _mute,
    "unmute": _unmute,
    "follow": lambda uid, d: _follow(uid, d, True),
    "unfollow": lambda uid, d: _follow(uid, d, False),
    # approve and stop are carried out by the workflows the issue comment starts;
    # there is nothing to write here.
    "approve": lambda uid, d: None,
    "stop": lambda uid, d: None,
}


def pull():
    from . import settings
    if settings.pull():
        gitsync.push("settings changed in the app", ["data/settings.json"])
    events = call("/api/events").get("events", [])
    done, acted = [], 0
    for e in events:
        handler = HANDLERS.get(e.get("kind"))
        done.append(e["id"])
        # An answer or a mute arrives without a job attached to it.
        if not handler or (not e.get("uid") and e.get("kind") not in
                           ("answer", "mute", "unmute", "follow", "unfollow")):
            continue
        handler(e.get("uid"), e.get("detail") or {})
        acted += 1
        print(f"app: {e['kind']} {e['uid']}")
    if EDITED:
        gitsync.push("answers edited in the app", sorted(EDITED))
        EDITED.clear()
    if FOLLOWED:
        gitsync.push(f"following list changed in the app ({len(FOLLOWED)})", [paths.inside(TARGETS)])
        FOLLOWED.clear()
    if MUTED:
        gitsync.push(f"muted {len(MUTED)} company(ies) from the app", ["data/muted.json"])
        MUTED.clear()
    if REQUESTED:
        gitsync.push(f"{len(REQUESTED)} resume(s) requested from the app",
                     ["data/requested.json", "data/hints.json"])
        REQUESTED.clear()
    if RESTORED:
        gitsync.push(f"{len(RESTORED)} posting(s) brought back from Filtered out", ["data/pending.json"])
        RESTORED.clear()
    if MARKED:
        gitsync.push(f"{len(MARKED)} job(s) archived, reopened or applied in the app",
                     ["data/tailored.json", "data/approvals.jsonl", "data/applications.jsonl"])
        MARKED.clear()
    if done:
        call("/api/events/ack", {"ids": done}, "POST")
    print(f"app: {acted} action(s) from the phone")
    return acted


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    what = (argv[0] if argv else "sync").lower()
    if not BASE or not TOKEN:
        print("app: APP_URL/APP_TOKEN not set - skipping")
        return 0
    try:
        if what in ("pull", "sync"):
            pull()
        if what in ("push", "sync"):
            push()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
        print(f"app: could not reach the app ({err}) - state is still in the repo", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
