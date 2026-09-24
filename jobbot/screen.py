"""Reading the two sentences a keyword cannot.

Some postings rule him out in words no list of phrases can catch, and catch
others that never ruled him out at all. On his board on 2026-09-24, of 191
postings:

  Entrust   "Citizen Remote Identity Verification team"      - a product name
  Klaviyo   "do not discriminate on the basis of citizenship" - EEO boilerplate
  Astranis  "U.S. Citizenship, Lawful Permanent Residency, or Refugee/Asylee
            Status Required"                                  - a real blocker,
            and one the phrase list missed
  Waymo     "Currently enrolled in an MS or PhD program"      - a real blocker,
            which the rules could only flag, never drop

The distinction is not a keyword, which is why the PhD rule only ever flagged:
someone rightly decided a silent drop was too dangerous. It is a question about
one paragraph, so a model answers it.

What keeps this cheap is what it does NOT do. It never sees a posting that the
rules already decided, never sees one it has judged before, never sees one
whose text has no trigger word in it at all, and never sees more than the few
hundred characters around the trigger. Most sweeps have nothing to send and
cost nothing.

The verdict is durable: judged once, kept in data/screened.json, and a posting
it turns away lands in Filtered out with its reason in his own words, one tap
from coming back - like every other filter, because a model that is wrong must
cost him a tap and not a job.
"""
import argparse
import json
import os
import re
import sys

from . import paths

ASK = "data/screen_ask.json"          # what the model is being asked about
SAY = "data/screen_say.json"          # what it answered
KEPT = "data/screened.json"           # what has been decided, for good

# Words that mean "this posting may rule him out, and the word alone does not
# say whether it does". Anything with none of these is never sent.
TRIGGERS = re.compile(
    r"\b(citizen(?:ship)?|permanent resident|green card|u\.?s\.? person|national(?:ity)?|"
    r"clearance|polygraph|itar|ear\b|export control|"
    r"ph\.?d|doctoral|doctorate|master'?s|masters|m\.?s\.?c?\b|graduate program|"
    r"graduating in|graduation date|class of|degree)\b", re.I)

ROOM = 240        # characters either side of a trigger
MOST = 900        # per posting, whatever it hits


def excerpt(text):
    """The parts of the posting that made it a candidate, and nothing else."""
    text = re.sub(r"\s+", " ", str(text or ""))
    spans = []
    for m in TRIGGERS.finditer(text):
        lo, hi = max(0, m.start() - ROOM), min(len(text), m.end() + ROOM)
        if spans and lo <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], hi))
        else:
            spans.append((lo, hi))
        if sum(b - a for a, b in spans) > MOST:
            break
    out = " ... ".join(text[a:b].strip() for a, b in spans)
    return out[:MOST]


def _load(name, default):
    p = paths.at(name)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(name, data):
    p = paths.at(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def verdicts():
    """What has already been decided, by uid. Nothing is ever asked twice."""
    return _load(KEPT, {})


def allow(uid, why="you put it back"):
    """He overrules the screening on one posting, for good.

    Without this, bringing a posting back from Filtered out lasted until the
    next sweep: the verdict still said no, so it was taken away again. His tap
    beats the model, and the posting is never asked about again.
    """
    kept = verdicts()
    from datetime import datetime, timezone
    kept[uid] = {"ok": True, "why": why,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _save(KEPT, kept)


def candidates(rows, decided, limit=40):
    """Postings worth asking about: a trigger in the text, no verdict yet."""
    out = []
    for t in rows:
        uid = t.get("uid")
        if not uid or uid in decided:
            continue
        text = " ".join(filter(None, [t.get("title"), t.get("description") or t.get("jd")]))
        if not TRIGGERS.search(text):
            continue
        out.append({"uid": uid, "company": t.get("company"), "title": t.get("title"),
                    "location": t.get("location") or "", "term": t.get("term") or "",
                    "in_canada": bool(re.search(r"canada|ontario|toronto|vancouver|montr|quebec|alberta|"
                                                r"waterloo|ottawa|calgary|winnipeg|halifax|, on\b|, bc\b|, qc\b",
                                                (t.get("location") or ""), re.I)),
                    "text": excerpt(text)})
        if len(out) >= limit:
            break
    return out


def still_standing(rows):
    """The postings the rules have not already decided.

    Measured on the first real batch (2026-09-24): of ten the model turned
    away, seven were ones the phrase rules caught anyway. Asking about those
    costs tokens and tells him nothing - the only verdicts worth paying for are
    on postings that are still on his board after every free rule has run.
    """
    from . import match, tailor, watch
    crit, targets = watch.load_criteria(None), watch.load_targets()
    match.screened(refresh=True)
    out = []
    for t in rows:
        try:
            m, _ = match.classify(tailor.to_posting(t), crit, targets)
        except Exception:                      # noqa: BLE001 - a row we cannot read is a row we ask about
            out.append(t)
            continue
        if m is not None:
            out.append(t)
    return out


def cmd_plan(a):
    """Write the batch, if there is one. Prints the count for the workflow."""
    rows = still_standing(list(_load("data/pending.json", {}).values()))
    ask = candidates(rows, verdicts(), a.limit)
    _save(ASK, ask)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"count={len(ask)}\n")
    print(f"to screen: {len(ask)} posting(s)" +
          (f" ({sum(len(x['text']) for x in ask)} characters in all)" if ask else ""))
    return 0


def cmd_apply(a):
    """Take the answers, keep them for good, and say what changed."""
    said = _load(SAY, [])
    if isinstance(said, dict):
        said = said.get("postings") or said.get("verdicts") or []
    asked = {x["uid"]: x for x in _load(ASK, [])}
    kept, added, turned = verdicts(), 0, []
    from datetime import datetime, timezone
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for row in said:
        uid = str((row or {}).get("uid") or "")
        if uid not in asked or uid in kept:
            continue
        ok = bool(row.get("ok"))
        why = str(row.get("why") or "").strip()[:120]
        kept[uid] = {"ok": ok, "why": why if not ok else "", "at": at}
        added += 1
        if not ok:
            turned.append(f"{asked[uid]['company']}: {asked[uid]['title'][:44]} - {why}")
    # A posting asked about but not answered is left undecided rather than
    # assumed fine: it will be asked again next time.
    _save(KEPT, kept)
    print(f"screened: {added} judged, {len(turned)} he cannot take")
    for line in turned:
        print("  " + line)
    return 0


def cmd_forget(a):
    """Drop verdicts whose reason matches, so they are judged again.

    A verdict is kept for good, which is what stops the same posting costing
    tokens twice - but it also means a change to what "not eligible" means
    never reaches the postings already decided under the old wording.
    """
    kept = verdicts()
    gone = [uid for uid, v in kept.items()
            if not v.get("ok") and a.matching.lower() in (v.get("why") or "").lower()]
    for uid in gone:
        kept.pop(uid, None)
    _save(KEPT, kept)
    print(f"forgot {len(gone)} verdict(s) mentioning {a.matching!r}; they will be judged again")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot.screen", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("forget", help="re-judge verdicts whose reason matches some text")
    p.add_argument("--matching", required=True)
    p.set_defaults(fn=cmd_forget)
    p = sub.add_parser("plan", help="write the batch of postings to ask about")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("apply", help="record the answers")
    p.set_defaults(fn=cmd_apply)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
