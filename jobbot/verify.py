"""
Fabrication verifier for generated resumes.

Contract: every bullet in a generated resume must cite the profile fact ids it was
derived from, and must not introduce numbers, technologies, employers, titles or
dates that are absent from those facts. Deterministic - no model in the loop, so
it cannot be talked out of a finding.

Two allowances follow the user's swap policy (profile.yaml), and both are
reported as INFO so the approval queue can label them rather than hide them:
  SWAPPED_TECH   - a tool from the fact's `swap_tech` (an equivalent he may
                   honestly name) instead of the one actually used.
  COINED_METRIC  - a figure supported only by the fact's `coined_metrics`
                   (ledgered, reused verbatim across applications).
Anything outside those lists still FAILs.

Exit code 0 = PASS, 1 = FAIL.
"""
import json, re, sys
from collections import defaultdict

WORD_NUM = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "twelve": "12",
    "dozen": "12", "hundred": "100", "thousand": "1000", "million": "1000000",
}

# Claims of scope/ownership that need explicit support in the source fact.
SCOPE_VERBS = {
    "led", "leading", "owned", "architected", "designed", "spearheaded", "founded",
    "managed", "mentored", "directed", "drove", "pioneered", "established",
}
SCOPE_MARKERS = SCOPE_VERBS | {
    "lead", "owner", "ownership", "architecture", "sole", "solely", "first",
    "team", "mentor", "design",
}

# Tokens that look like technologies. Anything CamelCase, dotted, or containing
# digits/symbols typical of tech names.
TECH_RE = re.compile(r"\b([A-Z][A-Za-z0-9+.#-]{1,}(?:\.[a-z]+)?)\b")
# A number glued to letters ("20Hz", "5TB") used to be invisible because \b
# never fired between digit and letter, so "60Hz" passed unchecked; "35%"
# lost its unit for the same reason. Digits inside tech names (S3, GPT-4o,
# H100, v2.1) are still skipped by the lookbehind; percentiles like p95 are
# matched as their own token.
NUM_RE = re.compile(r"(?:(?<![A-Za-z0-9.,])(?<![A-Za-z]-)|(?<=[\s(]p))(\d+(?:[.,]\d+)*)(?!\d)"
                    r"\s*(%|(?:x|ms|s|k|m|b|gb|mb|tb|min|hrs?|hours?|hz|fps)(?![A-Za-z]))?", re.I)

STOPWORD_CAPS = {
    "A", "An", "The", "And", "Or", "For", "To", "With", "By", "In", "On", "Of",
    "Built", "Designed", "Developed", "Implemented", "Created", "Reduced",
    "Improved", "Added", "Wrote", "Shipped", "Migrated", "Refactored", "Led",
    "Owned", "Architected", "Integrated", "Automated", "Deployed", "Optimized",
    "Delivered", "Increased", "Decreased", "Launched", "Maintained", "Tested",
}


def normalize_nums(text):
    """Return the set of numeric tokens in text, with word-numbers folded in."""
    out = set()
    for m in NUM_RE.finditer(text):
        val = m.group(1).replace(",", "")
        val = val.rstrip("0").rstrip(".") if "." in val else val
        if text[max(0, m.start() - 1):m.start()] in ("p", "P"):
            val = f"p{val}"
        unit = (m.group(2) or "").lower()
        out.add(val)
        if unit:
            out.add(f"{val}{unit}")
    for w, d in WORD_NUM.items():
        if re.search(rf"\b{w}\b", text, re.I):
            out.add(d)
    return out


def tech_tokens(text, known_tech=frozenset()):
    """Capitalized tokens that plausibly name a technology.

    A capitalized word is only treated as a tech claim when it is (a) a known
    skill, (b) internally punctuated or digit-bearing the way tech names are
    (PyTorch, Node.js, C++, S3), or (c) capitalized mid-sentence. Rule (c) keeps
    ordinary sentence-initial verbs like "Cut" or "Shipped" from being read as
    products, which was producing false accusations of fabrication.
    """
    out = set()
    sentence_start = True
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9+.#-]*)|([.!?;]+)", text):
        if m.group(2):
            sentence_start = True
            continue
        tok = m.group(1).rstrip(".")
        if not tok:
            continue
        # Letters glued to a number are a unit ("20Hz", "5GB"), which the
        # number check already covers - not a technology claim.
        if m.start() > 0 and text[m.start() - 1].isdigit():
            continue
        is_first = sentence_start
        sentence_start = False
        if not tok[0].isupper() or len(tok) <= 1:
            continue
        internal = bool(re.search(r"[A-Z0-9+.#]", tok[1:]))
        if tok.lower() in known_tech or internal or not is_first:
            if tok.lower() in GENERIC_CAPS:
                continue
            if tok in STOPWORD_CAPS and not internal and tok.lower() not in known_tech:
                continue
            out.add(tok)
    return out


def index_profile(profile):
    """Map fact_id -> fact dict, and entry_id -> entry dict."""
    facts, entries = {}, {}
    for section in ("experience", "projects", "education"):
        for entry in profile.get(section, []):
            entries[entry["id"]] = entry
            for fact in entry.get("facts", []):
                facts[fact["id"]] = {**fact, "_entry": entry["id"]}
    return facts, entries


# Capitalized words that are generic engineering nouns, not a product claim.
GENERIC_CAPS = {"api", "apis", "rest", "ui", "ux", "ci", "cd", "sdk", "sdks", "cli", "http",
                "https", "json", "url", "urls", "io", "os", "vm", "vms", "etl", "elt", "orm",
                "crud", "saas", "oop", "mvp", "mvps", "qa", "agile", "scrum", "ai", "ml", "llm",
                "llms", "rag", "gpu", "gpus", "cpu", "hpc", "rbac", "sql", "nosql"}


def tech_words(names):
    """Each tech name plus its words: "GitHub Actions" also yields github, actions."""
    out = set()
    for t in names:
        t = t.lower()
        out.add(t)
        out.update(w for w in re.split(r"[\s/(),]+", t) if w)
    return out


def all_known_tech(profile):
    known = set()
    for group in profile.get("skills", {}).values():
        known.update(group)
    for f in index_profile(profile)[0].values():
        known.update(f.get("tech", []))
    return tech_words(known)


def verify(profile, resume):
    facts, entries = index_profile(profile)
    known_tech = all_known_tech(profile)
    findings = []

    def fail(bullet_ref, code, msg):
        findings.append({"severity": "FAIL", "bullet": bullet_ref, "code": code, "detail": msg})

    def info(bullet_ref, code, msg):
        findings.append({"severity": "INFO", "bullet": bullet_ref, "code": code, "detail": msg})

    def warn(bullet_ref, code, msg):
        findings.append({"severity": "WARN", "bullet": bullet_ref, "code": code, "detail": msg})

    # --- header fields must be copied verbatim, never generated -------------
    ident = resume.get("identity", {})
    for k, v in profile.get("identity", {}).items():
        if k in ident and ident[k] != v:
            fail("identity", "IDENTITY_MISMATCH",
                 f"{k}: resume says {ident[k]!r}, profile says {v!r}")

    for sec in resume.get("sections", []):
        entry_id = sec.get("entry_id")
        entry = entries.get(entry_id)
        if entry is None:
            fail(entry_id or "?", "UNKNOWN_ENTRY", f"entry_id {entry_id!r} not in profile")
            continue

        # employer / title / dates must match the profile exactly
        for k in ("employer", "title", "start", "end", "institution", "degree", "gpa"):
            if k in sec and k in entry and sec[k] != entry[k]:
                fail(entry_id, "ENTRY_FIELD_ALTERED",
                     f"{k}: resume says {sec[k]!r}, profile says {entry[k]!r}")

        for i, bullet in enumerate(sec.get("bullets", [])):
            ref = f"{entry_id}[{i}]"
            text = bullet.get("text", "")
            src_ids = bullet.get("source_ids") or []

            if not src_ids:
                fail(ref, "NO_PROVENANCE", "bullet cites no source fact")
                continue

            unknown = [s for s in src_ids if s not in facts]
            if unknown:
                fail(ref, "UNKNOWN_SOURCE", f"cites non-existent fact id(s): {unknown}")
                continue

            wrong_entry = [s for s in src_ids if facts[s]["_entry"] != entry_id]
            if wrong_entry:
                fail(ref, "CROSS_ENTRY_SOURCE",
                     f"cites facts from a different role/project: {wrong_entry} "
                     f"(this bullet sits under {entry_id})")

            src_text = " ".join(facts[s]["text"] for s in src_ids)
            # Figures this resume coins, declared in its own "coined" list. His
            # call (2026-09-23): the writer may put a plausible number on his own
            # work, as long as it says which ones so he can check them.
            fresh_nums = set()
            for c in resume.get("coined") or []:
                if c.get("source_id") in src_ids or c.get("entry_id") == entry_id:
                    fresh_nums |= normalize_nums(str(c.get("number", ""))) | {str(c.get("number", "")).lower()}
            src_nums, coined_nums = set(), set()
            for s in src_ids:
                src_nums |= normalize_nums(facts[s]["text"])
                for m in facts[s].get("metrics", []):
                    src_nums |= normalize_nums(m) | {m.lower()}
                for m in facts[s].get("coined_metrics", []):
                    coined_nums |= normalize_nums(m) | {m.lower()}
            coined_nums -= src_nums
            src_tech = tech_words(t for s in src_ids for t in facts[s].get("tech", []))
            src_tech |= {t.lower() for t in tech_tokens(src_text, known_tech)}
            swap_tech = {t.lower() for s in src_ids for t in facts[s].get("swap_tech", [])}
            swap_words = {w for t in swap_tech for w in re.split(r"[\s/()]+", t) if w}

            # --- numbers -------------------------------------------------
            for num in normalize_nums(text):
                if num in src_nums or num.rstrip("%") in src_nums:
                    continue
                if num in coined_nums or num.rstrip("%") in coined_nums:
                    info(ref, "COINED_METRIC", f"{num!r} is a ledgered coined figure, not measured")
                elif num in fresh_nums or num.rstrip("%") in fresh_nums:
                    info(ref, "NEW_COINED_METRIC", f"{num!r} was coined for this resume - check it before sending")
                else:
                    fail(ref, "UNSUPPORTED_NUMBER",
                         f"{num!r} appears in the bullet but not in its source fact(s)")

            # --- technologies --------------------------------------------
            for tok in tech_tokens(text, known_tech):
                low = tok.lower()
                if low in src_tech:
                    continue
                if low in swap_tech or low in swap_words:
                    info(ref, "SWAPPED_TECH", f"{tok!r} is a policy swap for this fact's actual stack")
                    continue
                if low in known_tech:
                    warn(ref, "TECH_NOT_IN_SOURCE",
                         f"{tok!r} is a real skill of yours but is not attached to this "
                         f"role's facts - check you actually used it here")
                else:
                    fail(ref, "UNSUPPORTED_TECH",
                         f"{tok!r} does not appear anywhere in your profile")

            # --- metric direction ----------------------------------------
            fm = re.search(r"from\s+([\w.,%]+?)[.,]?\s+to\s+([\w.,%]+?)[.,]?(?=\s|$)", text, re.I)
            if fm:
                b_from, b_to = fm.group(1).lower(), fm.group(2).lower()
                for s, key in ((s, k) for s in src_ids for k in ("metrics", "coined_metrics")):
                    ordered = [m.lower() for m in facts[s].get(key, [])]
                    if len(ordered) >= 2 and b_from in ordered and b_to in ordered:
                        if ordered.index(b_from) > ordered.index(b_to):
                            fail(ref, "REVERSED_METRIC",
                                 f"bullet reads 'from {b_from} to {b_to}' but the fact "
                                 f"records the move as {ordered[0]} -> {ordered[1]}")

            # --- scope inflation -----------------------------------------
            claimed = {w for w in SCOPE_VERBS if re.search(rf"\b{w}\b", text, re.I)}
            if claimed:
                supported = any(re.search(rf"\b{m}\b", src_text, re.I) for m in SCOPE_MARKERS)
                if not supported:
                    warn(ref, "SCOPE_INFLATION",
                         f"claims {sorted(claimed)} but the source fact describes no "
                         f"leadership or ownership")

    return findings


def main():
    if len(sys.argv) != 3:
        print("usage: verify.py <profile.json> <resume.json>", file=sys.stderr)
        return 2
    profile = json.load(open(sys.argv[1]))
    resume = json.load(open(sys.argv[2]))
    findings = verify(profile, resume)

    fails = [f for f in findings if f["severity"] == "FAIL"]
    warns = [f for f in findings if f["severity"] == "WARN"]
    infos = [f for f in findings if f["severity"] == "INFO"]

    for f in findings:
        print(f"{f['severity']:4} {f['code']:22} {f['bullet']:22} {f['detail']}")

    print()
    if fails:
        print(f"RESULT: FAIL - {len(fails)} blocking, {len(warns)} warning(s)")
        return 1
    print(f"RESULT: PASS - 0 blocking, {len(warns)} warning(s), "
          f"{len(infos)} swap/coined label(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
