"""Durable state. This is what makes novelty exact and dedup real.

seen.json      uid -> {first_seen, company, title, url}
applications.jsonl  append-only log of everything applied to
registry.json  boards to poll + health stats (the self-improving part)
"""
import json, os
from datetime import datetime, timezone

from .paths import DATA as _DATA
DATA = str(_DATA)


def _path(name):
    return os.path.abspath(os.path.join(DATA, name))


def _load(name, default):
    try:
        with open(_path(name)) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
    os.replace(tmp, _path(name))


def load_seen():
    return _load("seen.json", {})


def save_seen(seen):
    _save("seen.json", seen)


def mark_seen(seen, posting):
    seen[posting.uid] = {
        "first_seen": datetime.now(timezone.utc).isoformat(),
        "company": posting.company,
        "title": posting.title,
        "url": posting.url,
        "posted_at": posting.posted_at.isoformat() if posting.posted_at else None,
    }


def load_registry():
    reg = _load("registry.json", {"boards": [], "stats": {}})
    # The boards with a fetcher of their own are part of the code, so they are
    # here whatever the file says.
    from .direct import BUILTIN
    have = {(b.get("source"), b.get("org")) for b in reg["boards"]}
    for b in BUILTIN:
        if (b["source"], b["org"]) not in have:
            reg["boards"].append(dict(b))
    return reg


def save_registry(reg):
    _save("registry.json", reg)


# A board is only "gone" when the server says so. Timeouts and dropped
# connections are the poller's own fault (2026-09-18: a 24-worker local sweep
# made 1,406 of 2,184 boards look dead), so they must never disable anything.
HARD_ERROR = ("404", "410", "JSONDecodeError", "Invalid URL", "NameResolutionError")


def update_health(reg, health, matched_keys):
    """Fold this run's outcome into per-board stats.

    Boards that fail repeatedly get disabled; boards that produce matches get
    priority. Bookkeeping that compounds - not learning, but it does mean the
    registry gets better instead of drifting.
    """
    now = datetime.now(timezone.utc).isoformat()
    stats = reg.setdefault("stats", {})
    for key, h in health.items():
        s = stats.setdefault(key, {"ok_runs": 0, "fail_runs": 0, "consecutive_failures": 0,
                                   "postings_seen": 0, "matches_ever": 0, "last_ok": None,
                                   "last_error": None, "enabled": True})
        if h["ok"]:
            s["ok_runs"] += 1
            s["consecutive_failures"] = 0
            s["last_ok"] = now
            s["postings_seen"] += h["count"]
            s["last_error"] = None
        else:
            s["fail_runs"] += 1
            s["last_error"] = h["error"]
            if any(tag in (h["error"] or "") for tag in HARD_ERROR):
                s["consecutive_failures"] += 1
                if s["consecutive_failures"] >= 5:
                    s["enabled"] = False
            else:
                s["soft_failures"] = s.get("soft_failures", 0) + 1
        s["matches_ever"] += matched_keys.get(key, 0)
    return reg


# Workday needs a request per tenant per run and there are ~1,200 of them
# (about 6 minutes), so they are polled in two tiers: the ones worth watching
# minute to minute, and everything else on a twice-daily sweep.
def is_hot(board, stats):
    key = f"{board['source']}:{board['org']}"
    s = stats.get(key, {})
    return bool(board.get("target") or s.get("matches_ever", 0) or s.get("last_ok") is None)


def active_boards(reg, workday="hot", targets_only=False):
    """workday: hot (targets + ever-matched + never-tried) | all | none.

    targets_only keeps the companies he actually wants (targets.txt) plus
    Amazon, which he named specifically. That sweep is ~80 boards instead of
    2,200, so it is cheap enough to run every few minutes.
    """
    stats = reg.get("stats", {})
    out = []
    for b in reg.get("boards", []):
        key = f"{b['source']}:{b['org']}"
        if not stats.get(key, {}).get("enabled", True):
            continue
        if targets_only and not (b.get("target") or b["source"] == "amazon"):
            continue
        if b["source"] == "workday":
            if workday == "none" or (workday == "hot" and not is_hot(b, stats)):
                continue
        out.append((b["source"], b["org"]))
    return out


def log_application(record):
    os.makedirs(DATA, exist_ok=True)
    with open(_path("applications.jsonl"), "a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
