"""Offline checks for jobbot.apply's safety rules (no browser, no network)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JOBBOT_DATA"] = tempfile.mkdtemp()
from jobbot import apply

fails = []
def check(name, ok):
    print(f"{'ok ' if ok else 'BAD'} {name}")
    if not ok:
        fails.append(name)

q = lambda how, answer=None, label="Q": {"id": "x", "label": label, "type": "text", "required": True,
                                        "options": [], "how": how, "answer": answer}
check("clean application has no blockers", apply.blockers({"questions": [q("rule", "a"), q("draft", "b")]}) == [])
check("knockout blocks", apply.blockers({"knockouts": ["Are you a US citizen?"], "questions": []}) != [])
check("needs_you blocks", apply.blockers({"questions": [q("needs_you", label="Salary")]}) != [])
check("missing draft blocks", apply.blockers({"questions": [q("draft", None, "Why us?")]}) != [])

for text in ["Thank you for applying!", "Your application has been submitted", "We've received your application",
             "Thanks for your interest in DoorDash"]:
    check(f"confirmation recognised: {text}", bool(apply.CONFIRM_RE.search(text)))
check("form page is not a confirmation", not apply.CONFIRM_RE.search("Apply for this job * indicates a required field Submit application"))

with open(os.path.join(os.environ["JOBBOT_DATA"], "applications.jsonl"), "w") as fh:
    fh.write(json.dumps({"uid": "done", "status": "submitted"}) + "\n" + json.dumps({"uid": "handed", "status": "needs_you"}) + "\n")
check("never submits the same job twice", apply.already_attempted("done"))
check("a hand-back can be retried", not apply.already_attempted("handed"))

print()
if fails:
    print(f"{len(fails)} failure(s)"); sys.exit(1)
print("apply suite OK")

# A site refusing automated submits (Greenhouse answers 428) is reported as
# blocked, never worked around.
check("428 is a refusal", apply.blocked_by_site([("POST", "https://boards.greenhouse.io/x/jobs/1", 428)]) != [])
check("403/429 are refusals", apply.blocked_by_site([("POST", "u", 403), ("POST", "u", 429)]) == 
      ["POST u -> 403", "POST u -> 429"])
check("200 is not a refusal", apply.blocked_by_site([("POST", "u", 200)]) == [])
if fails:
    print(f"{len(fails)} failure(s)"); sys.exit(1)
print("apply extras OK")

# A human-verification step (Greenhouse emails an 8-character code) is never
# completed by jobbot - it is recognised and handed back.
check("verification prompt recognised", bool(apply.VERIFY_RE.search(
    "A verification code was sent to you. To submit your application, enter the 8-character code to confirm you're a human.")))
check("ordinary form text is not a verification prompt", not apply.VERIFY_RE.search("Submit application"))
if fails:
    print(f"{len(fails)} failure(s)"); sys.exit(1)
print("verification checks OK")
