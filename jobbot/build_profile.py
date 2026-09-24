"""Build data/profile.json from the master profile.yaml.

profile.yaml (resume-pipeline, Applications 2026) stays the single source of
truth; this is a deterministic projection into the atomic-fact schema verify.py
checks against. Rerun it whenever profile.yaml changes - never hand-edit the
output.

Each work record becomes one fact: stable id "<entry>.<record>", text = the
record's plain `what` plus its canonical numbers, metrics = numbers with any
"a -> b" split into ordered before/after tokens, tech = actual stack.

Swap policy (the user's call, 2026-09-16: generated resumes follow the same rules
as his existing pipeline):
  - swap alternatives go in `swap_tech`; verify.py accepts them as INFO.
  - coined figures come from metric_policy.coined_metrics, attached to the fact
    named by each entry's `record`. They go in `coined_metrics`, never in
    `text`/`metrics`; verify.py accepts them as INFO. Each fact carries
    `provenance` (real | real+coined | coined | unbuilt) so the approval queue
    can label it. Projects marked `status: unbuilt` are tagged unbuilt.
  - the generator never coins a new figure. New numbers go through
    resume_mcp.record_coined_metric by hand first.
--strict drops coined and unbuilt records entirely.

Usage: python -m jobbot.build_profile [--source PATH] [--out PATH] [--strict]
"""
import argparse, json, os, re, sys

import yaml

from .paths import DATA, PIPELINE, at as _at

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# His profile lives with the rest of his things. On the laptop that is still
# the OneDrive folder, when there is one; in a run it is the private checkout.
DEFAULT_SOURCE = str(PIPELINE / "profile.yaml") if (PIPELINE / "profile.yaml").exists() else \
    os.path.expanduser(r"~/OneDrive/Desktop/Resumes/Applications 2026/profile.yaml")

NUM_TOKEN = re.compile(r"~?\d[\d,.]*\+?\s*(?:%|(?:x|ms|s|hours?|hrs?|k|m)(?![a-z]))?|weekly|daily|minutes|hour|week", re.I)


FROM_TO = re.compile(r"from\s+(\S+)\s+to\s+(\S+?)[.,;]?(?=\s|$)", re.I)


def ordered_metrics(numbers):
    """Numbers plus explicit before/after tokens, in order, for REVERSED_METRIC."""
    out = []
    for n in numbers:
        pairs = [n.split("->")] if "->" in n else [list(m) for m in FROM_TO.findall(n)]
        for pair in pairs:
            for side in pair:
                m = NUM_TOKEN.search(side)
                if m:
                    out.append(m.group(0).strip().lstrip("~").rstrip("+"))
        out.append(n)
    return out


def ledger_by_record(src):
    """record id -> ledgered coined metric strings (user_reported/sharpened excluded)."""
    out = {}
    for e in (src.get("metric_policy") or {}).get("coined_metrics") or []:
        if e.get("record") and e.get("kind", "coined") == "coined":
            out.setdefault(e["record"], []).append(e["metric"])
    return out


def _nums(s):
    from .verify import normalize_nums
    return normalize_nums(s)


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def swap_values(swap):
    out = []
    for v in (swap or {}).values():
        for t in (v if isinstance(v, list) else [v]):
            if t not in out:
                out.append(t)
    return out


def canonical_nums(entry, ledger):
    """Figures from sibling records (same role) that have no ledger entries.

    Scoped to one role on purpose: bare numbers collide across the profile
    ("70%" vs "70+ tests"), but within a role a shared figure like "12 cell
    categories" is the same canonical fact.
    """
    return set().union(set(), *(_nums(n) for w in entry["work"]
                                if f"{entry['id']}.{w['id']}" not in ledger
                                for n in w.get("numbers") or []))


def fact(fid, rec, ledger, canonical=frozenset()):
    """A record number is coined when every figure in it appears in that
    record's ledger entries and nowhere canonical; otherwise it is real."""
    led = ledger.get(fid, [])
    led_nums = set().union(*(_nums(m) for m in led)) - canonical if led else set()
    nums = rec.get("numbers") or []
    real = [n for n in nums if not (_nums(n) and _nums(n) <= led_nums)]
    coined = [n for n in nums if n not in real] + led
    prov = ("unbuilt" if rec.get("status") == "unbuilt" else
            "coined" if coined and nums and not real else
            "real+coined" if coined else "real")
    text = clean(rec["what"])
    if real:
        text = f"{text.rstrip('.')} ({'; '.join(real)})."
    f = {"id": fid, "text": text, "metrics": ordered_metrics(real),
         "coined_metrics": ordered_metrics(coined),
         "tech": list(rec.get("stack") or []), "swap_tech": swap_values(rec.get("swap")),
         "frames": rec.get("frames") or [], "provenance": prov}
    if rec.get("rule"):
        f["rule"] = clean(rec["rule"])
    return f


def build(src, strict=False):
    keep = lambda f: not strict or f["provenance"] in ("real", "real+coined")
    ledger = ledger_by_record(src)
    ident = src["identity"]
    edu = src["education"]
    out = {
        "_generated_from": "profile.yaml via jobbot.build_profile - do not hand-edit",
        "identity": {k: ident[k] for k in ("name", "email", "phone", "location",
                                           "linkedin", "github") if k in ident},
        "availability": src.get("availability", {}),
        "education": [{
            "id": "edu_uoft", "institution": edu["school"], "degree": edu["degree"],
            "gpa": edu["gpa"], "start": edu["start"], "grad_by_term": edu["grad_by_term"],
            "coursework": edu.get("coursework", ""), "latex": edu.get("latex", ""),
            "facts": []}],
        "latex": src.get("latex", {}),
        "experience": [], "projects": [],
        "banned_claims": src.get("banned_claims", []),
    }
    for e in src["experiences"]:
        facts = [f for f in (fact(f"{e['id']}.{w['id']}", w, ledger, canonical_nums(e, ledger)) for w in e["work"]) if keep(f)]
        if strict:
            for f in facts:
                f["coined_metrics"] = []
        start, _, end = e["dates"].partition("--")
        out["experience"].append({
            "id": e["id"], "employer": e["company"], "title": e["title"],
            "location": e["location"], "start": start.strip(), "end": end.strip(),
            "rule": clean(e.get("rule")), "facts": facts})
    for p in src["projects"]:
        f = fact(p["id"], p, ledger)
        if strict:
            f["coined_metrics"] = []
        if not keep(f):
            continue
        out["projects"].append({"id": p["id"], "name": p["name"], "repo": p.get("repo"),
                                "rule": clean(p.get("rule")), "facts": [f]})
    skills = {}
    for tmpl in src.get("skills_templates", {}).values():
        for label, row in tmpl.items():
            skills.setdefault(label, [])
            for s in re.split(r",\s*(?![^()]*\))", row):
                if s and s not in skills[label]:
                    skills[label].append(s.strip())
    out["skills"] = skills
    out["skills_templates"] = src.get("skills_templates", {})
    return out


def load_source(path):
    return yaml.safe_load(open(path, encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--out", default=str(DATA / "profile.json"))
    ap.add_argument("--strict", action="store_true", help="drop coined figures and unbuilt work")
    a = ap.parse_args(argv)
    # "pipeline/profile.yaml" on a command line means his pipeline folder,
    # wherever that is now.
    source, out = _at(a.source), _at(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prof = build(load_source(source), a.strict)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(prof, fh, indent=2, ensure_ascii=False)
    n = sum(len(e["facts"]) for s in ("experience", "projects") for e in prof[s])
    print(f"wrote {out}: {len(prof['experience'])} roles, {len(prof['projects'])} projects, {n} facts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
