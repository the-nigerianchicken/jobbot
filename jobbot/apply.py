"""Submit an approved application: fill the form, attach the resume, submit.

Runs from approve.yml after the user comments /approve (his per-job permission to
fill in his details, accept the listed agreements and submit). Supports the
three ATSs whose forms questions.py reads: Greenhouse, Ashby, Lever.

Hard stops - it hands the job back to him instead of pushing through:
  - a likely knockout, a question marked needs_you, or a missing draft
  - a visible CAPTCHA challenge. It never solves or evades one.
  - no confirmation after submit (validation error, unknown page)

    python -m jobbot.apply <issue-number>                 # submit
    python -m jobbot.apply --folder "<folder>" --dry-run  # fill + screenshot only
"""
import argparse, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

from . import questions, store, tailor

# Greenhouse emails an 8-character code and asks for it "to confirm you're a
# human" before it will accept a submission (Scale AI, 2026-09-17). That is a
# human check: jobbot never types such a code, even one the user has. It fills the
# form in his own browser (--handoff) and he finishes it.
VERIFY_RE = re.compile(r"verification code was sent|enter the \d+.character code|confirm you.?re a human|"
                       r"security code", re.I)
CONFIRM_RE = re.compile(r"thank(s| you) for (applying|your (application|interest))|application (has been |was )?"
                        r"(submitted|received)|we('ve| have) received your application|successfully submitted", re.I)
# Ashby screens submissions with a fraud check and answers a script with
# "flagged as possible spam" (Fable, 2026-09-21). Nothing was sent, so this is
# a refusal, not an unconfirmed submit - and it is not something to retry.
REFUSED_RE = re.compile(r"flagged as (possible )?spam|couldn.?t submit your application|"
                        r"unable to (submit|process) your application", re.I)


# --------------------------------------------------------------------------- #
# per-ATS field filling. Each returns a list of problems (empty = all filled).
# --------------------------------------------------------------------------- #

def _pick_combobox(page, box, text, first_if_no_match=False, wait=8.0):
    """Type into a combobox and click the matching option in ITS listbox.

    Options are looked up only inside the listbox this combobox controls: a
    page-wide [role=option] search found the phone field's country list while
    typing a school name. Typed key by key, because async searches (Greenhouse
    schools) ignore a pasted value, and polled, because results arrive late.
    """
    text = str(text)
    box.click()
    box.fill("")
    box.press_sequentially(text, delay=30)
    deadline = time.time() + wait
    pattern_exact = re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)
    pattern_loose = re.compile(re.escape(text), re.I)
    while time.time() < deadline:
        time.sleep(0.5)
        controls = box.get_attribute("aria-controls") or box.get_attribute("aria-owns")
        if not controls:
            continue
        opts = page.locator(f'[id="{controls}"] [role=option]')
        if opts.count() == 0 or re.search(r"loading|searching", opts.first.inner_text(), re.I):
            continue
        exact, loose = opts.filter(has_text=pattern_exact), opts.filter(has_text=pattern_loose)
        pick = exact if exact.count() else loose if loose.count() else (opts if first_if_no_match else None)
        if pick is not None:
            pick.first.click()
            return True
    box.fill("")
    return False


def _attach(page, selector, resume, problems, label):
    """Attach the resume and wait for the page to register it.

    A submit once failed with "Resume/CV is required. Cannot read properties of
    undefined (reading 'uploadFile')": the file was set but the uploader had
    not finished, so the page is given time and the filename is checked.
    """
    try:
        page.locator(selector).first.set_input_files(str(resume))
    except Exception as e:                       # noqa: BLE001 - reported
        problems.append(f"could not attach the resume ({type(e).__name__}): {label[:40]}")
        return False
    stem = Path(resume).name
    for _ in range(15):
        page.wait_for_timeout(1000)
        if stem in page.inner_text("body"):
            return True
    problems.append(f"the page never showed the attached resume: {label[:40]}")
    return False


def fill_greenhouse(page, app, resume, upload):
    problems = []
    for q in app["questions"]:
        ans, fid = q.get("answer"), q["id"]
        if q["how"] == "skip" or ans is None:
            continue
        if q["type"] == "file":
            if upload:
                _attach(page, f'input[type=file][id="{fid}"]', resume, problems, q["label"])
            continue
        target = "candidate-location" if fid == "location" else fid
        el = page.locator(f'[id="{target}"]')
        if el.count() == 0:
            if q["required"]:
                problems.append(f"field not found: {q['label'][:60]}")
            continue
        answers = [a.strip() for a in str(ans).split(";")] if q["type"] == "multiselect" else [ans]
        try:
            tag = el.first.evaluate("e => e.tagName")
            if tag == "FIELDSET":                        # multi-select rendered as checkboxes
                for a in answers:
                    box = el.first.get_by_label(a, exact=True)
                    if box.count():
                        box.first.check()
                    else:
                        problems.append(f"option {a!r} not found: {q['label'][:60]}")
            elif el.first.get_attribute("role") == "combobox":
                for a in answers:
                    if not _pick_combobox(page, el.first, a, first_if_no_match=(fid == "location")):
                        problems.append(f"option {a!r} not selectable: {q['label'][:60]}")
            else:
                el.first.fill(str(ans))
        except Exception as e:                   # noqa: BLE001 - reported per field
            problems.append(f"{type(e).__name__} on {q['label'][:60]}")
    return problems


def fill_lever(page, app, resume, upload):
    problems = []
    for q in app["questions"]:
        ans, name = q.get("answer"), q["id"]
        if q["how"] == "skip" or ans is None:
            continue
        sel = f'[name="{name}"]'
        if q["type"] == "file":
            if upload:
                _attach(page, f"input[type=file]{sel}", resume, problems, q["label"])
            continue
        els = page.locator(sel)
        if els.count() == 0:
            if q["required"]:
                problems.append(f"field not found: {q['label'][:60]}")
            continue
        try:
            _lever_one(page, q, els, sel, ans, problems)
        except Exception as e:                   # noqa: BLE001 - reported per field
            problems.append(f"{type(e).__name__} on {q['label'][:60]}")
    return problems


def _lever_one(page, q, els, sel, ans, problems):
    tag = els.first.evaluate("e => e.tagName + ':' + (e.type || '')")
    if tag.startswith("SELECT"):
        # questions.py records option values; labels can differ.
        try:
            els.first.select_option(value=str(ans), timeout=5000)
        except Exception:                    # noqa: BLE001
            els.first.select_option(label=str(ans), timeout=5000)
    elif tag.endswith(("radio", "checkbox")):
        for a in ([x.strip() for x in str(ans).split(";")] if q["type"] == "multiselect" else [ans]):
            box = page.locator(f'{sel}[value="{a}"]')
            if box.count() == 0:
                problems.append(f"option {a!r} not found: {q['label'][:60]}")
            else:
                box.first.check()
    elif q["type"] == "location":
        els.first.fill(str(ans))
        time.sleep(1)
        sugg = page.locator(".dropdown-location, [class*=location-result], [role=option]")
        if sugg.count():
            sugg.first.click()
    else:
        els.first.fill(str(ans))


def _ashby_container(page, q):
    """The field's wrapper: Ashby keys inputs by field path; fall back to the label text."""
    fid = q["id"]
    by_id = page.locator(f'[id="{fid}"], [name="{fid}"], [id$="_{fid}"], [name$="_{fid}"], [id*="_{fid}-labeled"]')
    if by_id.count():
        return by_id.first.locator("xpath=ancestor::*[contains(@class,'fieldEntry') or contains(@class,'_field')][1]"), by_id
    label = page.get_by_text(q["label"].strip()[:80], exact=False)
    if label.count():
        return label.first.locator("xpath=ancestor::*[.//input or .//textarea or .//button][1]"), None
    return None, None


def fill_ashby(page, app, resume, upload):
    problems = []
    for q in app["questions"]:
        ans = q.get("answer")
        if q["how"] == "skip" or ans is None:
            continue
        if q["type"] == "file":
            if upload:
                _attach(page, "input[type=file]#_systemfield_resume", resume, problems, q["label"])
            continue
        box, direct = _ashby_container(page, q)
        if box is None:
            if q["required"]:
                problems.append(f"field not found: {q['label'][:60]}")
            continue
        try:
            if q["type"] in ("text", "textarea", "date") and direct is not None and direct.count():
                direct.first.fill(str(ans))
            elif q["type"] == "boolean":
                box.get_by_role("button", name=re.compile(rf"^{'Yes' if str(ans).lower().startswith('y') else 'No'}$")).first.click()
            elif q["type"] in ("select", "multiselect"):
                for a in ([x.strip() for x in str(ans).split(";")] if q["type"] == "multiselect" else [ans]):
                    choice = box.get_by_label(a, exact=True)
                    if choice.count():
                        choice.first.check()
                    else:
                        combo = box.get_by_role("combobox")
                        if not (combo.count() and _pick_combobox(page, combo.first, a)):
                            problems.append(f"option {a!r} not selectable: {q['label'][:60]}")
            elif q["type"] == "location":
                combo = box.get_by_role("combobox")
                if not (combo.count() and _pick_combobox(page, combo.first, str(ans).split(",")[0], first_if_no_match=True)):
                    problems.append(f"location not selectable: {q['label'][:60]}")
            else:
                (direct.first if direct is not None and direct.count() else box.locator("input,textarea").first).fill(str(ans))
        except Exception as e:                   # noqa: BLE001 - reported per field
            problems.append(f"{type(e).__name__} on {q['label'][:60]}")
    return problems


FILLERS = {"greenhouse": fill_greenhouse, "lever": fill_lever, "ashby": fill_ashby}
SUBMIT = re.compile(r"^\s*submit( application)?\s*$", re.I)


def captcha_challenge(page):
    """A challenge a human must solve is showing. Invisible scoring is not one."""
    for frame_sel in ('iframe[src*="recaptcha/api2/bframe"]', 'iframe[src*="recaptcha/enterprise/bframe"]',
                      'iframe[src*="hcaptcha.com"][src*="challenge"]', 'iframe[title*="challenge" i]'):
        f = page.locator(frame_sel)
        if f.count() and f.first.is_visible():
            return True
    return False


# --------------------------------------------------------------------------- #

def blockers(app):
    out = []
    if app.get("knockouts"):
        out.append("likely knockout: " + "; ".join(app["knockouts"]))
    for q in app["questions"]:
        if q["how"] == "needs_you":
            out.append(f"needs your answer: {q['label'][:80]}")
        elif q["how"] == "draft" and not q.get("answer"):
            out.append(f"no draft answer: {q['label'][:80]}")
    out += app.get("problems") or []
    return out


def blocked_by_site(posts):
    """Greenhouse answers an automated submit with 428 Precondition Required
    (verified 2026-09-17 from a GitHub runner and from the user's own laptop, so
    it is the bot check, not the IP). Nothing here tries to get around it."""
    return [f"{m} {u.split('?')[0][:80]} -> {c}" for m, u, c in posts if c in (403, 428, 429)]


def run(folder, resume, dry_run, shots, headed=False):
    from playwright.sync_api import sync_playwright
    app = json.loads((folder / "application.json").read_text(encoding="utf-8"))
    result = {"source": app["source"], "url": app["apply_url"], "shots": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(app["apply_url"], wait_until="networkidle", timeout=90000)
        if app["source"] == "greenhouse" and page.locator("#first_name").count() == 0:
            page.get_by_role("button", name=re.compile("apply", re.I)).first.click()
        problems = FILLERS[app["source"]](page, app, resume, upload=not dry_run)
        shot = shots / "filled.png"
        page.screenshot(path=str(shot), full_page=True)
        result["shots"].append(shot)
        result["fill_problems"] = problems
        if dry_run or problems:
            result["status"] = "dry_run" if dry_run and not problems else "fill_failed"
            browser.close()
            return result
        if headed:
            # Hand-off: the form is filled, the user clicks Submit himself.
            print("Browser open with the form filled. Check it, click Submit, and enter the emailed "
                  "code if the site asks for one.")
            deadline = time.time() + 900
            status = "handoff"
            while time.time() < deadline:
                time.sleep(3)
                try:
                    if CONFIRM_RE.search(page.inner_text("body")):
                        status = "submitted"
                        break
                except Exception:                # noqa: BLE001 - he may close the tab
                    break
            result["status"] = status
            try:
                page.screenshot(path=str(shots / "handoff.png"), full_page=True)
                result["shots"].append(shots / "handoff.png")
                browser.close()
            except Exception:                    # noqa: BLE001
                pass
            return result
        # Watch what the server says about the submission itself: a page that
        # never changes leaves no other evidence of accepted vs rejected.
        posts = []
        page.on("response", lambda r: posts.append((r.request.method, r.url, r.status))
                if r.request.method == "POST"
                and not re.search(r"recaptcha|google|analytics|sentry|segment|datadog", r.url) else None)
        page.get_by_role("button", name=SUBMIT).last.click()
        deadline = time.time() + 45
        status = "unconfirmed"
        while time.time() < deadline:
            time.sleep(2)
            if captcha_challenge(page):
                status = "captcha"
                break
            if CONFIRM_RE.search(page.inner_text("body")) or re.search(r"confirm|thank", page.url, re.I):
                status = "submitted"
                break
        result["submit_responses"] = [f"{m} {u.split('?')[0][:90]} -> {code}" for m, u, code in posts[-6:]]
        refused = blocked_by_site(posts)
        body_text = page.inner_text("body")
        if status == "unconfirmed" and VERIFY_RE.search(body_text):
            status = "verification"
        elif status == "unconfirmed" and REFUSED_RE.search(body_text):
            status = "blocked"
            result["refused"] = [REFUSED_RE.search(body_text).group(0)]
        elif status == "unconfirmed" and refused:
            status = "blocked"
            result["refused"] = refused
        if status == "unconfirmed":
            # Say why, when the page says: validation messages and invalid fields.
            errors = page.evaluate("""() => {
                const out = new Set();
                document.querySelectorAll('[role=alert], .error, .error-message, [class*="error"], [class*="invalid"]')
                    .forEach(e => { const t = (e.innerText || '').trim(); if (t && t.length < 200) out.add(t); });
                document.querySelectorAll('[aria-invalid="true"]').forEach(e => {
                    const l = document.getElementById(e.id + '-label') || e.closest('label');
                    out.add('invalid: ' + ((l && l.innerText) || e.name || e.id).trim().slice(0, 120));
                });
                return [...out].slice(0, 15);
            }""")
            result["page_errors"] = errors
        shot = shots / "after_submit.png"
        page.screenshot(path=str(shot), full_page=True)
        result["shots"].append(shot)
        result["status"] = status
        browser.close()
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot.apply")
    ap.add_argument("issue", nargs="?")
    ap.add_argument("--folder")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--handoff", action="store_true",
                    help="open a real browser window with the form filled and let the user submit")
    ap.add_argument("--force", action="store_true",
                    help="submit again after an inconclusive attempt (risks a duplicate)")
    ap.add_argument("--prepare-only", action="store_true",
                    help="read the form if never read, then report how many answers need drafting")
    a = ap.parse_args(argv)

    ledger = tailor._load("tailored.json", {})
    if a.folder:
        folder = tailor.resolve_folder(a.folder)
        uid = json.loads((folder / "resume.json").read_text(encoding="utf-8")).get("uid")
        v = ledger.get(uid, {})
    else:
        uid, v = next(((u, x) for u, x in ledger.items() if str(x.get("issue")) == str(a.issue)), (None, None))
        if not v:
            print(f"ERROR: no resume linked to issue #{a.issue}", file=sys.stderr)
            return 1
        folder = tailor.ROOT / v["folder"]
    resume = tailor.ROOT / v["pdf"] if v.get("pdf") else next(folder.glob("*.pdf"), None)
    app_path = folder / "application.json"

    def comment(body):
        if a.issue and not a.dry_run:
            tailor.gh("issue", "comment", str(a.issue), "-R", tailor.REPO, "--body", body)
        print(body)

    # Always re-read the form (keeping drafts): issues built before questions
    # existed have none, and a stored list can predate fields jobbot has since
    # learned to fill.
    questions.prepare(folder, uid, v.get("url"), v.get("apply_url"), v.get("location"))
    if app_path.exists():
        questions.refresh(folder)
    if a.prepare_only:
        app = json.loads(app_path.read_text(encoding="utf-8")) if app_path.exists() else {"questions": []}
        need = sum(1 for q in app["questions"] if q["how"] == "draft" and not q.get("answer"))
        print(f"{need} answer(s) need drafting in {tailor.rel(folder)}")
        out = __import__("os").environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as fh:
                fh.write(f"drafts={need}\nfolder={tailor.rel(folder)}\n")
        return 0

    if not app_path.exists() or not resume or not resume.exists():
        comment(f"Could not apply automatically: {'no application form was read' if not app_path.exists() else 'no resume PDF'}. "
                f"Apply here: {v.get('apply_url')}")
        return 0
    # --handoff submits nothing by itself: the user does, in his own browser, so
    # the never-twice guard does not apply to it.
    if not a.dry_run and not a.handoff and not a.force and already_attempted(uid):
        print(f"already attempted {uid} - not submitting twice (use --handoff or --force)")
        return 0
    app = json.loads(app_path.read_text(encoding="utf-8"))
    if app.get("source") not in FILLERS:
        comment(f"Automatic applying does not support this site. Apply here: {v.get('apply_url')}")
        return 0
    v = {**v, "issue": a.issue}
    auto = set((tailor.watch.load_criteria().get("apply") or {}).get("submit_sources")
               or ["greenhouse", "lever", "ashby"])
    if not a.dry_run and not a.handoff and app.get("source") not in auto:
        comment(f"{app['source'].title()} does not accept automated submissions, so nothing was sent. "
                f"Everything is ready - apply here with the answers above: {v.get('apply_url')}")
        record(uid, v, a.issue, "needs_you", [f"{app['source']} is not in apply.submit_sources"])
        return 0
    stop = blockers(app)
    if stop and not a.dry_run:
        comment("Not submitted - needs you first:\n" + "\n".join(f"- {s}" for s in stop)
                + f"\n\nApply here with the answers above: {v.get('apply_url')}")
        record(uid, v, a.issue, "needs_you", stop)
        return 0

    shots = folder / "apply"
    shots.mkdir(exist_ok=True)
    try:
        res = run(folder, resume, a.dry_run, shots, headed=a.handoff)
    except Exception as e:                       # noqa: BLE001 - reported to him
        comment(f"Automatic apply crashed ({type(e).__name__}: {str(e)[:200]}). Apply here: {v.get('apply_url')}")
        record(uid, v, a.issue, "error", [str(e)[:300]])
        return 0

    blob = f"https://github.com/{tailor.REPO}/blob/main"
    pics = " | ".join(f"[{s.stem}]({blob}/{tailor.quote(tailor.rel(s))})" for s in res["shots"])
    msg = {
        "submitted": "Submitted. The application page confirmed it.",
        "captcha": "Stopped at a CAPTCHA challenge - finish it yourself (the form is not saved, so "
                   f"re-enter with the answers above): {v.get('apply_url')}",
        "unconfirmed": "Clicked submit but saw no confirmation - check your email and the screenshot. "
                       f"If it did not go through, apply here: {v.get('apply_url')}",
        "verification": "Not submitted. The site emailed you a code and asks for it to confirm you are "
                        "a human - jobbot does not complete human checks. Everything is filled in; "
                        "finish it yourself, on the site or with a filled browser window on the laptop:"
                        f"\n`python -m jobbot.apply {v.get('issue') or ''} --handoff`"
                        f"\n\nApply link: {v.get('apply_url')}",
        "blocked": "The site refused an automated submission (its bot check, not a CAPTCHA to solve, "
                   "and not something jobbot will work around). Everything is ready - apply here with "
                   f"the answers above: {v.get('apply_url')}",
        "handoff": "Filled in your browser; submit was left to you. Nothing was sent unless you "
                   "clicked Submit.",
        "fill_failed": "Not submitted - some fields could not be filled:\n"
                       + "\n".join(f"- {p}" for p in res.get("fill_problems", []))
                       + f"\n\nApply here with the answers above: {v.get('apply_url')}",
        "dry_run": "Dry run: form filled, nothing submitted.",
    }[res["status"]]
    if res.get("page_errors"):
        msg += "\n\nThe page showed:\n" + "\n".join(f"- {e}" for e in res["page_errors"])
    if res["status"] != "submitted" and res.get("submit_responses"):
        msg += "\n\nServer responses:\n" + "\n".join(f"- `{r}`" for r in res["submit_responses"])
    comment(f"{msg}\n\nScreenshots: {pics}")
    if not a.dry_run:
        record(uid, v, a.issue, res["status"], (res.get("fill_problems") or []) + (res.get("page_errors") or [])
               + (res.get("submit_responses") or []))
        if a.issue and res["status"] == "submitted":
            tailor.gh("issue", "close", str(a.issue), "-R", tailor.REPO, "--reason", "completed")
        elif a.issue:
            tailor.gh("label", "create", "apply-by-hand", "--color", "e99695", "--force", "-R", tailor.REPO)
            tailor.gh("issue", "edit", str(a.issue), "-R", tailor.REPO, "--add-label", "apply-by-hand")
    return 0


def already_attempted(uid):
    """True if any run already tried to submit this job. Reads the newest log on
    the remote too: a /approve comment plus the approved label start two runs,
    and the second one's checkout may predate the first one's push."""
    import subprocess
    logs = []
    local = Path(store._path("applications.jsonl"))
    if local.exists():
        logs.append(local.read_text(encoding="utf-8"))
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=tailor.ROOT, capture_output=True)
    shown = subprocess.run(["git", "show", "origin/main:data/applications.jsonl"], cwd=tailor.ROOT,
                           capture_output=True, text=True, encoding="utf-8")
    if shown.returncode == 0:
        logs.append(shown.stdout)
    attempted = {"submitted", "unconfirmed", "captcha"}
    return any(json.loads(l).get("uid") == uid and json.loads(l).get("status") in attempted
               for text in logs for l in text.splitlines() if l.strip())


def record(uid, v, issue, status, notes=None):
    store.log_application({"uid": uid, "issue": issue, "company": v.get("company"), "title": v.get("title"),
                           "apply_url": v.get("apply_url"), "status": status, "notes": notes or [],
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


if __name__ == "__main__":
    sys.exit(main())
