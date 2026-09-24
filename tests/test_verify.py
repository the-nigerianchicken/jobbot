"""The fabrication verifier must pass honest resumes and block each fabrication class.

Runs against samples/ (placeholder profile, stable fixtures) and, when present,
data/profile.json built from the real master profile.
"""
import copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jobbot.verify import verify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = lambda n: json.load(open(os.path.join(ROOT, "samples", n), encoding="utf-8"))
profile = S("profile.json")
failures = []


def codes(resume, severity="FAIL", prof=None):
    return {f["code"] for f in verify(prof or profile, resume) if f["severity"] == severity}


def check(name, got, want):
    ok = want <= got if want else not got
    print(f"{'ok ' if ok else 'BAD'} {name}: got {sorted(got)}")
    if not ok:
        failures.append(f"{name}: wanted {sorted(want) or 'none'}, got {sorted(got)}")


check("honest passes", codes(S("resume_honest.json")), set())
check("fabricated blocked", codes(S("resume_fabricated.json")),
      {"ENTRY_FIELD_ALTERED", "UNSUPPORTED_NUMBER", "UNSUPPORTED_TECH",
       "NO_PROVENANCE", "CROSS_ENTRY_SOURCE"})
check("subtle blocked", codes(S("resume_subtle.json")),
      {"REVERSED_METRIC", "UNSUPPORTED_NUMBER"})
check("subtle warns", codes(S("resume_subtle.json"), "WARN"),
      {"TECH_NOT_IN_SOURCE", "SCOPE_INFLATION"})

r = copy.deepcopy(S("resume_honest.json"))
r["sections"][0]["bullets"][0]["source_ids"] = ["f_does_not_exist"]
check("unknown source", codes(r), {"UNKNOWN_SOURCE"})

# A figure the writer invents for this resume is allowed - he reads them all
# before sending - but only when the resume declares it (2026-09-23).
coined_ok = copy.deepcopy(S("resume_honest.json"))
first = coined_ok["sections"][0]["bullets"][0]
first["text"] = first["text"].rstrip(".") + ", cutting escalations by 40%."
coined_ok["coined"] = [{"source_id": first["source_ids"][0], "number": "40%",
                        "claim": "escalations after the assistant shipped", "why": "plausible at this scale"}]
check("a declared coined figure passes", codes(coined_ok), set())
check("and is labelled for him", {f["code"] for f in verify(profile, coined_ok) if f["severity"] == "INFO"},
      {"NEW_COINED_METRIC"})
undeclared = copy.deepcopy(coined_ok)
undeclared.pop("coined")
check("an undeclared invented figure is still blocked", codes(undeclared), {"UNSUPPORTED_NUMBER"})

r = copy.deepcopy(S("resume_honest.json"))
r["identity"]["name"] = "the user, PhD"
check("identity altered", codes(r), {"IDENTITY_MISMATCH"})

# Real profile: every fact must be self-consistent, i.e. a bullet that restates
# a fact verbatim under its own entry passes.
real = os.path.join(ROOT, "data", "profile.json")
if os.path.exists(real):
    prof = json.load(open(real, encoding="utf-8"))
    for sec in ("experience", "projects"):
        for e in prof[sec]:
            for f in e["facts"]:
                res = {"sections": [{"entry_id": e["id"], "bullets": [
                    {"text": f["text"], "source_ids": [f["id"]]}]}]}
                check(f"real fact restates cleanly: {f['id']}", codes(res, prof=prof), set())
    rev = {"sections": [{"entry_id": "helix", "bullets": [
        {"text": "Raised backend test coverage from 80% to 35% with Pytest.",
         "source_ids": ["helix.testing_ci"]}]}]}
    check("real: percent metric reversed", codes(rev, prof=prof), {"REVERSED_METRIC"})

    # Swap policy: ledgered swaps and coined figures pass but are labelled;
    # anything outside those lists still fails.
    def one(entry, fid, text):
        return {"sections": [{"entry_id": entry, "bullets": [{"text": text, "source_ids": [fid]}]}]}
    b = one("helix", "helix.testing_ci", "Raised backend test coverage from 35% to 80% in Jenkins.")
    check("swap: Jenkins passes", codes(b, prof=prof), set())
    check("swap: Jenkins labelled", codes(b, "INFO", prof), {"SWAPPED_TECH"})
    b = one("helix", "helix.testing_ci", "Raised backend test coverage from 35% to 80% in Bazel.")
    check("swap: unlisted tool still fails", codes(b, prof=prof), {"UNSUPPORTED_TECH"})
    b = one("rfp_platform", "rfp_platform",
            "Built an eval harness scored by an LLM judge, raising grounded-answer rate from 71% to 94%.")
    check("coined: ledger figure passes", codes(b, prof=prof), set())
    check("coined: ledger figure labelled", codes(b, "INFO", prof), {"COINED_METRIC"})
    b = one("rfp_platform", "rfp_platform",
            "Built an eval harness scored by an LLM judge, raising grounded-answer rate from 94% to 71%.")
    check("coined: reversal still fails", codes(b, prof=prof), {"REVERSED_METRIC"})
    b = one("rfp_platform", "rfp_platform",
            "Built an eval harness scored by an LLM judge, raising grounded-answer rate from 71% to 97%.")
    check("coined: unledgered figure fails", codes(b, prof=prof), {"UNSUPPORTED_NUMBER"})
    b = one("helix", "helix.testing_ci", "Raised backend test coverage to 94% with Pytest.")
    check("coined: figure from another fact fails", codes(b, prof=prof), {"UNSUPPORTED_NUMBER"})

    # Numbers glued to units were once invisible to the verifier.
    b = one("multiplayer_server", "multiplayer_server",
            "Streamed state to 200+ concurrent players on a 20Hz tick, p95 update latency under 80ms.")
    check("units: ledgered 20Hz/p95 pass", codes(b, prof=prof), set())
    b = one("multiplayer_server", "multiplayer_server",
            "Streamed state to 200+ concurrent players on a 60Hz tick, p95 update latency under 80ms.")
    check("units: invented 60Hz fails", codes(b, prof=prof), {"UNSUPPORTED_NUMBER"})
    b = one("multiplayer_server", "multiplayer_server",
            "Streamed state to 200+ concurrent players on a 20Hz tick, p99 update latency under 80ms.")
    check("units: p95 -> p99 fails", codes(b, prof=prof), {"UNSUPPORTED_NUMBER"})
    b = one("multiplayer_server", "multiplayer_server",
            "Streamed state to 200+ concurrent players on a 20Hz tick, p95 update latency under 80ms.")
    check("provenance: unbuilt project labelled", codes(b, "INFO", prof), {"COINED_METRIC"})

print()
if failures:
    print(f"{len(failures)} failure(s):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("verify suite OK")
