"""Application questions: read each form, answer what rules can, flag the rest.

Every supported ATS exposes its form without a browser:
  greenhouse  boards-api .../jobs/{id}?questions=true (questions, location, EEOC)
  ashby       jobs.ashbyhq.com/api/non-user-graphql, ApiJobPosting.applicationForm
  lever       the /apply page: standard inputs plus each custom card's JSON
              template in a hidden `cards[...][baseTemplate]` input

answers.yaml decides the answers (the user's rules, e.g. US sponsorship = yes,
demographics = decline). Free text the rules cannot answer is marked `draft`
for Claude to write from the profile and JD; consent and salary questions are
`needs_you`. A "No" on a citizenship/clearance/authorization question is
flagged as a likely knockout so he can skip the job instead of applying.

    python -m jobbot.questions prepare "<folder>"   # writes application.json
    python -m jobbot.questions show "<folder>"      # prints the Q&A
"""
import argparse, html, json, re, sys
from pathlib import Path

import requests
import yaml

from . import paths, tailor

ROOT = tailor.ROOT
UA = {"User-Agent": "Mozilla/5.0 (jobbot; application prep)"}
DECLINE_RE = re.compile(r"decline|prefer not|don.?t wish|do not wish|not to (answer|say|disclose)|choose not|"
                        r"i do not want|rather not|not specified", re.I)
# Only questions no sponsorship can fix. "Authorized to work in the US? No" is
# the normal answer for every US internship he applies to, so it is not one.
KNOCKOUT_RE = re.compile(r"citizen|clearance", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                      "oct", "nov", "dec"], start=1)}


# --------------------------------------------------------------------------- #
# fetching forms -> [{id, label, type, options, required}]
# type: text | textarea | select | multiselect | boolean | file | date | location
# --------------------------------------------------------------------------- #

def greenhouse(org, job_id):
    d = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{org}/jobs/{job_id}?questions=true",
                     headers=UA, timeout=30).json()
    kind = {"input_text": "text", "textarea": "textarea", "input_file": "file", "input_hidden": None,
            "multi_value_single_select": "select", "multi_value_multi_select": "multiselect"}
    out = []
    groups = list(d.get("questions") or []) + list(d.get("location_questions") or [])
    for c in d.get("compliance") or []:
        groups += c.get("questions") or []
    # Not in `questions`, but rendered as required fields on many forms.
    if d.get("education") in ("education_required", "education_optional"):
        req = d["education"] == "education_required"
        # Greenhouse renders an education block whose fields are not in
        # `questions`. A missing "End date year" silently failed a submit.
        out_edu = [{"id": "school--0", "label": "School", "type": "select", "required": req, "options": []},
                   {"id": "degree--0", "label": "Degree", "type": "select", "required": req, "options": []},
                   {"id": "discipline--0", "label": "Discipline", "type": "select", "required": False, "options": []},
                   {"id": "start-month--0", "label": "Start date month", "type": "text", "required": False, "options": []},
                   {"id": "start-year--0", "label": "Start date year", "type": "text", "required": False, "options": []},
                   {"id": "end-month--0", "label": "End date month", "type": "text", "required": False, "options": []},
                   {"id": "end-year--0", "label": "End date year", "type": "text", "required": req, "options": []}]
    else:
        out_edu = []
    demo = (d.get("demographic_questions") or {}).get("questions") or []
    for q in groups:
        fields = q.get("fields") or []
        # A file question often offers a paste-text alternative; keep the file.
        main = next((f for f in fields if f["type"] == "input_file"), fields[0] if fields else None)
        if not main or kind.get(main["type"]) is None:
            continue
        out.append({"id": main["name"], "label": html.unescape(q.get("label") or main["name"]),
                    "type": kind.get(main["type"], "text"), "required": bool(q.get("required")),
                    "options": [v["label"] for v in main.get("values") or []]})
    out += out_edu
    for q in demo:
        out.append({"id": str(q["id"]), "label": html.unescape(q.get("label") or ""),
                    "type": kind.get(q.get("type"), "select"), "required": bool(q.get("required")),
                    "options": [o["label"] for o in q.get("answer_options") or []]})
    return out


ASHBY_Q = """query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {
  jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) {
    applicationForm { sections { fieldEntries { ... on FormFieldEntry { id field isRequired } } } }
  }
}"""


def ashby(org, job_id):
    d = requests.post("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting", headers=UA, timeout=30,
                      json={"operationName": "ApiJobPosting", "query": ASHBY_Q,
                            "variables": {"organizationHostedJobsPageName": org, "jobPostingId": job_id}}).json()
    kind = {"String": "text", "Email": "text", "Phone": "text", "Url": "text", "Number": "text",
            "LongText": "textarea", "File": "file", "Boolean": "boolean", "ValueSelect": "select",
            "MultiValueSelect": "multiselect", "Date": "date", "Location": "location"}
    out = []
    posting = (d.get("data") or {}).get("jobPosting") or {}
    for s in (posting.get("applicationForm") or {}).get("sections") or []:
        for e in s.get("fieldEntries") or []:
            f = e.get("field") or {}
            if not f or f.get("isDeactivated"):
                continue
            out.append({"id": f.get("path") or f.get("id"), "label": f.get("title") or "",
                        "type": kind.get(f.get("type"), "text"), "required": bool(e.get("isRequired")),
                        "options": [v.get("label") for v in f.get("selectableValues") or []]})
    return out


def lever(org, job_id):
    page = requests.get(f"https://jobs.lever.co/{org}/{job_id}/apply", headers=UA, timeout=30).text
    out = [{"id": n, "label": l, "type": t, "required": r, "options": []} for n, l, t, r in (
        ("name", "Full name", "text", True), ("email", "Email", "text", True),
        ("phone", "Phone", "text", False), ("location", "Current location", "location", False),
        ("org", "Current company", "text", False), ("resume", "Resume/CV", "file", True),
        ("urls[LinkedIn]", "LinkedIn URL", "text", False), ("urls[GitHub]", "GitHub URL", "text", False))
        if f'name="{n}"' in page]
    kind = {"text": "text", "textarea": "textarea", "multiple-choice": "select", "dropdown": "select",
            "multiple-select": "multiselect", "file-upload": "file"}
    for raw, card_id in re.findall(r'value="([^"]*)" name="cards\[([^\]]+)\]\[baseTemplate\]"', page):
        tmpl = json.loads(html.unescape(raw))
        for i, f in enumerate(tmpl.get("fields") or []):
            out.append({"id": f"cards[{card_id}][field{i}]", "label": f.get("text") or "",
                        "type": kind.get(f.get("type"), "text"), "required": bool(f.get("required")),
                        "options": [o.get("text") for o in f.get("options") or []]})
    for name in ("gender", "race", "veteran", "disability"):
        block = re.search(rf'name="eeo\[{name}\]"(.*?)(</select>|</ul>)', page, re.S)
        if block:
            opts = re.findall(r'value="([^"]+)"', block.group(1))
            out.append({"id": f"eeo[{name}]", "label": name.capitalize(), "type": "select",
                        "required": False, "options": [html.unescape(o) for o in opts]})
    return out


FETCHERS = {"greenhouse": greenhouse, "ashby": ashby, "lever": lever}

ATS_URL = [("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)")),
           ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})")),
           ("lever", re.compile(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})"))]


def locate(*urls):
    """(source, org, job_id) from a posting or apply URL, or None."""
    for url in urls:
        for source, pat in ATS_URL:
            m = pat.search(url or "")
            if m:
                return source, m.group(1), m.group(2)
    return None


# --------------------------------------------------------------------------- #
# answering
# --------------------------------------------------------------------------- #

def load_bank():
    """answers.yaml, with his contact details and standard answers from the app."""
    from . import settings
    return settings.apply_bank(yaml.safe_load(paths.ANSWERS.read_text(encoding="utf-8")),
                               tailor.load_profile(raw=True))


def fill_vars(text, bank, grad):
    ids = dict(bank["identity"])
    import re as _re
    year = _re.search(r"(20\d\d)", str(grad))
    ids.update(grad_month_year=grad, grad_year=year.group(1) if year else "",
               grad_month=_re.sub(r"\s*20\d\d", "", str(grad)).strip(),
               sponsorship_us=bank["sponsorship_text"]["us"],
               sponsorship_canada=bank["sponsorship_text"]["canada"])
    return re.sub(r"\{(\w+)\}", lambda m: str(ids.get(m.group(1), m.group(0))), str(text))


def pick_option(options, pattern, fallback_text):
    """`pattern` may be a list of regexes in priority order."""
    if not options:
        return None
    for pat in ([pattern] if isinstance(pattern, str) else pattern or []):
        for o in options:
            if re.search(pat, o, re.I):
                return o
    for o in options:
        if o.strip().lower() == str(fallback_text).strip().lower():
            return o
    return None


def _month_index(text):
    """'Dec 2027' / 'December 2027' -> 2027*12+12, else None."""
    m = re.search(r"([a-z]{3})[a-z]*\.?\s+(\d{4})", text.lower())
    return int(m.group(2)) * 12 + MONTHS[m.group(1)] if m and m.group(1) in MONTHS else None


def pick_date_option(options, when):
    """Choose the option whose date or date range contains `when`."""
    target = _month_index(when)
    if target is None:
        return None
    for o in options:
        points = [int(y) * 12 + MONTHS[mo[:3]] for mo, y in
                  re.findall(r"([a-z]{3,9})\.?\s+(\d{4})", o.lower()) if mo[:3] in MONTHS]
        low = o.lower()
        if len(points) >= 2 and points[0] <= target <= points[1]:
            return o
        if len(points) == 1 and (("before" in low and target < points[0]) or
                                 (("or later" in low or "after" in low) and target >= points[0]) or
                                 (not any(w in low for w in ("before", "after", "later")) and target == points[0])):
            return o
    # Terms instead of months: "Fall 2027". December is the end of the fall
    # term, so a December graduation is Fall (Mercury, 2026-09-21).
    for o in options:
        m = re.search(r"\b(spring|summer|fall|autumn|winter)\s+(\d{4})\b", o.lower())
        if not m or re.search(r"or (beyond|later)|prior|before", o.lower()):
            continue
        first, last = SEASONS[m.group(1)]
        year = int(m.group(2)) * 12
        if year + first <= target <= year + last:
            return o
    years = [o for o in options if re.fullmatch(r"\s*%d\s*" % (target // 12 if target % 12 else target // 12 - 1), o)]
    return years[0] if years else None


# Months each academic term covers, as MONTHS numbers.
SEASONS = {"winter": (1, 2), "spring": (3, 5), "summer": (6, 8), "fall": (9, 12), "autumn": (9, 12)}


def answer_field(f, bank, country, grad):
    """-> dict(answer, how) where how is rule | decline | draft | needs_you | file | unanswered."""
    label = re.sub(r"\s+", " ", f["label"]).strip()
    if f["type"] == "file":
        is_resume = re.search(r"resume|\bcv\b", label, re.I)
        return {"answer": "resume PDF" if is_resume else None, "how": "file" if is_resume else "skip"}
    for rule in bank["rules"]:
        if not re.search(rule["match"], label.lower()):
            continue
        if rule.get("decline"):
            opt = next((o for o in f["options"] if DECLINE_RE.search(o)), None)
            if opt or f["type"] in ("text", "textarea"):
                return {"answer": opt or "Prefer not to say", "how": "decline"}
            return {"answer": None, "how": "needs_you", "note": "no decline option offered"}
        if rule.get("needs_you"):
            return {"answer": None, "how": "needs_you"}
        if rule.get("consent"):
            # Only plain acknowledgements. "Yes, I meet all of the required
            # qualifications" is a claim about him, not consent - he decides it.
            plain = [o for o in f["options"] if not re.search(r"meet|qualif|eligib|citizen", o, re.I)]
            opt = pick_option(plain, ["agree", "acknowledg", "accept", "confirm", "i have read", "^yes"], "")
            if f["options"] and not opt:
                return {"answer": None, "how": "needs_you", "note": "agreement with unexpected options"}
            return {"answer": opt or "Agree", "how": "consent"}
        if rule.get("skip"):
            return {"answer": None, "how": "skip"}
        if rule.get("draft"):
            # Optional free text is left blank rather than padded.
            return {"answer": None, "how": "draft" if f["required"] else "skip"}
        spec = rule["by_country"][country] if "by_country" in rule else rule
        value = fill_vars(spec.get("value", ""), bank, grad)
        if f["options"] and spec.get("date_option"):
            opt = pick_date_option(f["options"], value)
            if opt:
                return {"answer": opt, "how": "rule"}
        if f["options"]:
            opt = pick_option(f["options"], spec.get("option"), value)
            if not opt:
                return {"answer": None, "how": "needs_you",
                        "note": f"rule says {value!r} but no option matches: {f['options']}"}
            value = opt
        elif f["type"] == "boolean":
            value = "Yes" if re.match(r"yes", value, re.I) else "No"
        return {"answer": value, "how": "rule"}
    return {"answer": None, "how": "draft" if f["required"] else "skip"}


def grad_for(folder, profile):
    rj = folder / "resume.json"
    term = json.loads(rj.read_text(encoding="utf-8")).get("term") if rj.exists() else None
    grad = profile["education"][0]["grad_by_term"]
    return grad.get(term) or grad.get("summer_2027")


def seat(location):
    markers = tailor.watch.load_criteria()["locations"]["canada_markers"]
    return "canada" if tailor.match._any_in(markers, (location or "").lower()) else "us"


def answer_all(fields, folder, location, keep=None):
    """Rule answers for every field; `keep` preserves Claude's drafts by id."""
    bank, grad = load_bank(), grad_for(folder, tailor.load_profile())
    country = seat(location)
    items, knockouts = [], []
    for f in fields:
        base = {k: f[k] for k in ("id", "label", "type", "required", "options")}
        ans = answer_field(base, bank, country, grad)
        item = {**base, **ans}
        prev = (keep or {}).get(f["id"])
        if ans["how"] == "draft" and prev and prev.get("answer"):
            item["answer"] = prev["answer"]
        if ans["how"] == "rule" and f["required"] and KNOCKOUT_RE.search(f["label"]) \
                and re.match(r"no\b", str(ans["answer"]), re.I):
            item["knockout"] = True
            knockouts.append(f["label"])
        items.append(item)
    return {"seat": country, "grad": grad, "knockouts": knockouts, "questions": items}


def prepare(folder, uid, url, apply_url, location, keep_drafts=True):
    """(Re-)read the form. Always re-read before applying: a stored field list
    goes stale when jobbot learns about fields it used to miss (the Greenhouse
    education block), and a stale list silently fails validation."""
    where = locate(apply_url, url)
    if not where:
        print(f"no question reader for {apply_url or url}")
        return None
    source, org, job_id = where
    try:
        fields = FETCHERS[source](org, job_id)
    except Exception as e:                       # noqa: BLE001 - optional, reported
        print(f"could not read the form: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    path = folder / "application.json"
    keep = {}
    if keep_drafts and path.exists():
        keep = {q["id"]: q for q in json.loads(path.read_text(encoding="utf-8"))["questions"]}
    app = {"uid": uid, "source": source, "apply_url": apply_url, "location": location,
           **answer_all(fields, folder, location, keep)}
    (folder / "application.json").write_text(json.dumps(app, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {}
    for i in app["questions"]:
        counts[i["how"]] = counts.get(i["how"], 0) + 1
    print(f"  {len(app['questions'])} questions: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
          + (f"; likely knockout: {app['knockouts']}" if app["knockouts"] else ""))
    return app


def refresh(folder):
    """Re-apply the rules now that resume.json fixes the term (graduation date),
    keeping Claude's drafts. Returns problems a human should see."""
    path = folder / "application.json"
    if not path.exists():
        return []
    app = json.loads(path.read_text(encoding="utf-8"))
    keep = {q["id"]: q for q in app["questions"]}
    app.update(answer_all(app["questions"], folder, app.get("location"), keep))
    problems = []
    for q in app["questions"]:
        if q["how"] == "draft" and not q.get("answer"):
            problems.append(f"no draft answer: {q['label'][:80]}")
        if q.get("answer") and q["options"] and q["type"] in ("select", "multiselect"):
            picked = [x.strip() for x in str(q["answer"]).split(";")] if q["type"] == "multiselect" else [q["answer"]]
            bad = [x for x in picked if x not in q["options"]]
            if bad:
                problems.append(f"answer {bad} is not an option for: {q['label'][:80]}")
    app["problems"] = problems
    path.write_text(json.dumps(app, indent=2, ensure_ascii=False), encoding="utf-8")
    return problems


def cmd_prepare(a):
    folder = tailor.resolve_folder(a.folder)
    uid = json.loads((folder / "resume.json").read_text(encoding="utf-8")).get("uid")
    v = tailor._load("tailored.json", {}).get(uid) or tailor._load("pending.json", {}).get(uid) or {}
    prepare(folder, uid, v.get("url"), v.get("apply_url"), v.get("location"))
    return 0


def summary_markdown(app):
    """Issue section: decisions first, then every answer, copy-ready."""
    qs = [q for q in app["questions"] if q["how"] != "skip"]
    lines = []
    if app.get("knockouts"):
        lines += [f"**Likely knockout:** answering honestly, this form asks {', '.join(app['knockouts'])} - "
                  "probably not worth applying.", ""]
    mine = [q for q in qs if q["how"] == "needs_you" or (q["how"] == "draft" and not q.get("answer"))]
    consents = [q for q in qs if q["how"] == "consent"]
    if consents:
        lines += ["**Agreements** (accepted only when you `/approve`):"] + [f"- {q['label'][:160]}" for q in consents] + [""]
    if mine:
        lines += ["**Needs you:**"] + [f"- {q['label']}" + (f" _(options: {', '.join(q['options'])})_" if q["options"] else "")
                                       + (f" - {q['note']}" if q.get("note") else "") for q in mine] + [""]
    if app.get("problems"):
        lines += ["**Check:** " + "; ".join(app["problems"][:5]), ""]
    lines += ["<details><summary>Application answers ({})</summary>".format(len(qs)), ""]
    tag = {"rule": "", "decline": " _(declined)_", "draft": " _(draft - check)_", "file": "", "needs_you": "",
           "consent": " _(on /approve)_"}
    for q in qs:
        ans = q.get("answer") or "-"
        req = " *" if q["required"] else ""
        lines.append(f"**{q['label']}**{req}  \n{ans}{tag.get(q['how'], '')}")
        lines.append("")
    lines += ["</details>", ""]
    return lines


def cmd_show(a):
    folder = tailor.resolve_folder(a.folder)
    app = json.loads((folder / "application.json").read_text(encoding="utf-8"))
    print("\n".join(summary_markdown(app)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot.questions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("prepare"); s.add_argument("folder"); s.set_defaults(func=cmd_prepare)
    s = sub.add_parser("show"); s.add_argument("folder"); s.set_defaults(func=cmd_show)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
