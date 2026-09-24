"""Answer rules against question shapes taken from real forms (2026-09-17):
Greenhouse (Covar, DoorDash), Ashby (Notion, Cohere), Lever (Kitware). Offline."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jobbot import questions as Q

bank = Q.load_bank()
fails = []


def ask(label, options=(), kind=None, required=True, country="us", grad="Dec 2027"):
    kind = kind or ("select" if options else "text")
    return Q.answer_field({"id": "x", "label": label, "type": kind, "required": required,
                           "options": list(options)}, bank, country, grad)


def check(name, got, how=None, answer=None, contains=None):
    ok = (how is None or got["how"] == how) and (answer is None or got.get("answer") == answer) \
        and (contains is None or contains in str(got.get("answer")))
    print(f"{'ok ' if ok else 'BAD'} {name}: {got}")
    if not ok:
        fails.append(name)


# Sponsorship: US seats yes (text says why), Canadian seats no.
check("US sponsorship yes/no", ask("Do you now or will you in the future, require Kitware to sponsor an immigration case?", ["Yes", "No"]), "rule", "Yes")
check("US sponsorship text", ask("Will you require visa sponsorship?"), "rule", contains="J-1")
check("Notion internship sponsorship", ask("For this specific internship, will you require any of the below sponsorship?", ["J1", "F1", "None", "Other"]), "rule", "J1")
check("Notion future sponsorship", ask("Will you now or at any time in the future require sponsorship for employment?", ["OPT", "H1B", "TN", "None"]), "rule", "TN")
check("Canada sponsorship", ask("Will you require sponsorship?", ["Yes", "No"], country="canada"), "rule", "No")
check("US authorization", ask("Are you legally authorized to work in the United States?", ["Yes", "No"]), "rule", "No")

# Demographics decline; pronouns never guessed.
check("gender decline", ask("Gender", ["Male", "Female", "Decline To Self Identify"], required=False), "decline", "Decline To Self Identify")
check("pronouns decline", ask("What pronouns would you like our team to use?", ["He/Him", "She/Her", "They/Them", "Prefer not to say"]), "decline", "Prefer not to say")

# Real mis-answers that were fixed.
check("SMS opt-in is not an email field", ask("Would you like to receive communications via SMS and/or WhatsApp? If you select no, we will only communicate via email", ["Yes", "No"]), "rule", "No")
check("grad date range", ask("Please select and confirm your anticipated graduation date (you must be currently enrolled in a program).",
                             ["Before September 2026", "September 2026 - November 2027", "December 2027 - August 2028", "September 2028 or later"]),
      "rule", "December 2027 - August 2028")
check("never worked here", ask("Have you worked at DoorDash?", ["I am a previous employee", "I have not worked at DoorDash"]), "rule", "I have not worked at DoorDash")
check("hear-about is truthful", ask("How did you hear about this opportunity?", ["LinkedIn", "Glassdoor", "Notion Website", "Notion Employee"]), "rule", "Notion Website")
check("qualification claim is not consent", ask("I acknowledge that I've read the required qualifications of this position.",
                                                ["Yes, I meet all of the required qualifications", "No"]), "needs_you")
check("plain consent", ask("I accept that the information provided is collected and processed", ["Yes"]), "consent", "Yes")
check("salary goes to him", ask("What are your salary expectations?"), "needs_you")
check("optional extra skipped", ask("Twitter", required=False), "skip")
check("optional free text skipped", ask("Anything you'd like to share?", required=False), "skip")
check("required free text drafted", ask("Why do you want to work at Notion?", kind="textarea"), "draft")
check("education level", ask("Please select the current level of education you are pursuing", ["High school", "Undergrad", "Masters"]), "rule", "Undergrad")

# Knockouts: citizenship/clearance only.
check("citizen knockout regex", {"how": "rule", "answer": str(bool(Q.KNOCKOUT_RE.search("Are you a US citizen?")))}, answer="True")
check("authorization is not a knockout", {"how": "rule", "answer": str(bool(Q.KNOCKOUT_RE.search("Are you authorized to work in the United States?")))}, answer="False")

# Posting URL -> reader.
check("locate greenhouse", {"how": "x", "answer": Q.locate("https://job-boards.greenhouse.io/covar/jobs/5240360007")},
      answer=("greenhouse", "covar", "5240360007"))
check("locate ashby", {"how": "x", "answer": Q.locate("https://jobs.ashbyhq.com/notion/e66c6658-9e65-4c58-8db2-844628b6e8f8/application")},
      answer=("ashby", "notion", "e66c6658-9e65-4c58-8db2-844628b6e8f8"))

# Terms instead of months (Mercury's form, 2026-09-21).
TERMS = ["Spring 2027", "Summer 2027", "Fall 2027", "Spring 2028", "Summer 2029 or beyond",
         "Recently graduated - 2026 or prior"]
for label, when, want in [("a December graduation picks the Fall term", "Dec 2027", "Fall 2027"),
                          ("an April graduation picks Spring", "Apr 2028", "Spring 2028"),
                          ("'or beyond' is not picked by accident", "Jul 2029", None)]:
    got = Q.pick_date_option(TERMS, when)
    print(("ok " if got == want else "BAD"), label, got)
    if got != want:
        fails.append(label)

print()
if fails:
    print(f"{len(fails)} failure(s)"); sys.exit(1)
print("questions suite OK")
