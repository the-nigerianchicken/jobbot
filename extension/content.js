/**
 * jobbot, on the page he is applying from.
 *
 * He applies on his laptop, in a tab that knows nothing about jobbot: the
 * resume it wrote is in another tab, the answers are in another tab, and
 * marking the job applied means going back to find it. This puts all three
 * where the form is.
 *
 * Two shapes, decided by whether jobbot already knows this page:
 *   it does   - the resume, every answer it wrote, a fill, and "I applied".
 *   it does not - one button that hands the posting over, which is how Meta
 *                 and Tesla get onto the board at all: their careers sites
 *                 answer a browser and nothing else.
 *
 * Nothing here submits anything. It fills what he has already read and leaves
 * the send to him.
 */
(() => {
  if (window.__jobbot) return window.__jobbot.open();
  const ask = (msg) => new Promise((go) => chrome.runtime.sendMessage(msg, (r) => go(r || { error: "no answer" })));

  /* ------------------------------------------------------------- the page -- */

  const meta = (name) => {
    const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
    return el ? el.getAttribute("content") || "" : "";
  };

  // A posting that publishes itself properly says so in schema.org, and that is
  // better than anything guessed from the page.
  function published() {
    for (const tag of document.querySelectorAll('script[type="application/ld+json"]')) {
      let data;
      try { data = JSON.parse(tag.textContent); } catch (e) { continue; }
      for (const node of Array.isArray(data) ? data : [data]) {
        if (node && node["@type"] === "JobPosting") return node;
      }
    }
    return null;
  }

  function readPage() {
    const ld = published() || {};
    const where = [].concat(ld.jobLocation || []).map((l) => {
      const a = (l && l.address) || {};
      return [a.addressLocality, a.addressRegion, a.addressCountry].filter(Boolean).join(", ");
    }).filter(Boolean).join("; ");
    const body = document.querySelector("main, article, [role=main]") || document.body;
    const text = String(ld.description || body.innerText || "").replace(/\s*\n\s*\n\s*/g, "\n\n").trim();
    return {
      url: location.href.split("#")[0],
      title: ld.title || (document.querySelector("h1") || {}).innerText || meta("og:title") || document.title,
      company: (ld.hiringOrganization && ld.hiringOrganization.name) || meta("og:site_name") ||
               location.hostname.replace(/^(www|jobs|careers|apply)\./, "").split(".")[0],
      location: where,
      posted_at: ld.datePosted || null,
      description: text.slice(0, 40000),
      where: location.hostname.replace(/^www\./, ""),
    };
  }

  /* --------------------------------------------------------- filling in --- */

  // What a field will actually take. An input with a type validates what is put
  // in it, and writing "Mississauga, Ontario, Canada" into a number or a date
  // leaves the field invalid and the form refusing to send - which is what an
  // Ashby application did on 2026-09-26. If it does not fit, leave it alone.
  const FREE = new Set(["", "text", "search"]);
  function accepts(el, value) {
    if (el.tagName === "TEXTAREA") return true;
    const t = (el.type || "text").toLowerCase();
    if (FREE.has(t)) return true;
    if (t === "email") return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim());
    if (t === "url") return /^https?:\/\/\S+$/i.test(value.trim());
    if (t === "tel") return /^[0-9+().\-\s]{6,}$/.test(value.trim());
    if (t === "number") return /^-?\d+(\.\d+)?$/.test(value.trim());
    if (t === "date") return /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
    if (t === "month") return /^\d{4}-\d{2}$/.test(value.trim());
    return false;                 // time, week, colour, range, and anything new
  }

  // React and friends listen for their own setter, not for a changed value.
  function put(el, value) {
    if (!accepts(el, value)) return false;
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const set = Object.getOwnPropertyDescriptor(proto, "value");
    if (set && set.set) set.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function labelOf(el) {
    const bits = [];
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) bits.push(l.textContent);
    }
    const wrap = el.closest("label");
    if (wrap) bits.push(wrap.textContent);
    for (const a of ["aria-label", "placeholder", "name", "id"]) bits.push(el.getAttribute(a) || "");
    const by = el.getAttribute("aria-labelledby");
    if (by) for (const id of by.split(/\s+/)) {
      const n = document.getElementById(id);
      if (n) bits.push(n.textContent);
    }
    return bits.join(" ").replace(/\s+/g, " ").trim().toLowerCase();
  }

  // The fields every form asks for, in the order that stops "name" from
  // catching "first name".
  const ME = [
    [/first\s*-?\s*name|given\s*name|\bfname\b/, (me) => (me.name || "").split(" ")[0]],
    [/last\s*-?\s*name|family\s*name|surname|\blname\b/, (me) => (me.name || "").split(" ").slice(1).join(" ")],
    [/full\s*name|^name$|\byour name\b|applicant name/, (me) => me.name],
    [/e-?mail/, (me) => me.email],
    [/phone|mobile|telephone/, (me) => me.phone],
    [/linked\s*-?in/, (me) => me.linkedin],
    [/git\s*-?hub/, (me) => me.github],
    [/portfolio|personal\s*(web)?site|^website/, (me) => me.website || me.github],
    [/school|university|college|institution/, (me) => me.school],
    [/\bmajor\b|field of study|discipline|course of study/, (me) => me.major],
    [/\bdegree\b/, (me) => me.degree],
    [/\bgpa\b|grade point/, (me) => me.gpa],
    [/city|current location|where are you based/, (me) => me.location],
  ];

  const bare = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();

  // A question jobbot answered is the same question as one on the form when
  // most of its words are. Exact text never matches: forms add "*", "(required)"
  // and their own wording.
  function sameQuestion(a, b) {
    const one = new Set(bare(a).split(" ").filter((w) => w.length > 3));
    const two = bare(b);
    if (!one.size) return 0;
    let hits = 0;
    for (const w of one) if (two.includes(w)) hits += 1;
    return hits / one.size;
  }

  // labelOf throws everything into one string so matching has the best chance -
  // including the field's name and id, which are not words. This is the part a
  // person would read, for saying which questions were left.
  function humanLabel(el) {
    const bits = [];
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) bits.push(l.textContent);
    }
    const wrap = el.closest("label");
    if (wrap && !bits.length) bits.push(wrap.textContent);
    if (!bits.length) bits.push(el.getAttribute("aria-label") || el.getAttribute("placeholder") || "");
    const said = bits.join(" ").replace(/\s+/g, " ").replace(/\s*\*\s*$/, "").trim();
    return said || labelOf(el);
  }

  // How close an answer is to an option's text, for picking one of a list.
  // "Yes" must not win "No, I do not require sponsorship", so an exact match
  // beats a contained one, and a contained one beats sharing words.
  function optionScore(answer, text) {
    const a = bare(answer), t = bare(text);
    if (!a || !t) return 0;
    if (a === t) return 1;
    if (t === "yes" || t === "no") return 0;          // never guess a yes or a no
    if (t.includes(a) || a.includes(t)) return 0.8;
    const words = a.split(" ").filter((w) => w.length > 3);
    if (!words.length) return 0;
    return 0.6 * (words.filter((w) => t.includes(w)).length / words.length);
  }

  function bestOption(answer, texts) {
    let at = -1, best = 0;
    texts.forEach((t, i) => { const sc = optionScore(answer, t); if (sc > best) { best = sc; at = i; } });
    return best >= 0.6 ? at : -1;
  }

  // Radios and checkboxes are often styled, with the real input hidden behind a
  // label, so being invisible does not mean being absent.
  const seen = (el) => !!(el.offsetParent || el.getClientRects().length ||
                          el.closest("label, fieldset, [role=group], [role=radiogroup]"));

  // The question a group of radios or checkboxes is asking. Their own labels are
  // the answers, so the question is whatever text the group sits under.
  function groupLabel(els) {
    let node = els[0];
    const own = new Set(els.map((e) => bare(labelOf(e))));
    for (let up = 0; up < 6 && node; up++) {
      node = node.parentElement;
      if (!node) break;
      const head = node.querySelector(":scope > legend, :scope > label, :scope > .label, :scope > h2, :scope > h3, :scope > p");
      if (head) {
        const text = bare(head.textContent);
        if (text && text.length > 3 && !own.has(text)) return text;
      }
    }
    return "";
  }

  // One of a set of radios, or a checkbox, chosen by what the answer says.
  function pickOne(els, answer) {
    const at = bestOption(answer, els.map((e) => labelOf(e) || e.value || ""));
    if (at < 0) return false;
    const el = els[at];
    if (el.checked) return false;
    el.click();                              // a click is what the form listens for
    if (!el.checked) {
      el.checked = true;
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return !!el.checked;
  }

  const rest = (ms) => new Promise((go) => setTimeout(go, ms));

  // Click the way a person does. react-select, Downshift and Radix all open on
  // mousedown and never see a bare .click(), so most of the dropdowns on these
  // forms would not even open (2026-09-26).
  function press(el) {
    const how = { bubbles: true, cancelable: true, view: window, button: 0 };
    el.dispatchEvent(new PointerEvent("pointerdown", how));
    el.dispatchEvent(new MouseEvent("mousedown", how));
    if (el.focus) el.focus();
    el.dispatchEvent(new PointerEvent("pointerup", how));
    el.dispatchEvent(new MouseEvent("mouseup", how));
    el.dispatchEvent(new MouseEvent("click", how));
  }

  // Options are often put at the end of the body rather than inside the control,
  // so look where it points first and then anywhere on the page.
  function optionsFor(el) {
    const owns = el.getAttribute("aria-controls") || el.getAttribute("aria-owns");
    const box = owns && document.getElementById(owns);
    const here = box ? [...box.querySelectorAll('[role="option"]')] : [];
    const all = here.length ? here : [...document.querySelectorAll('[role="option"]')];
    return all.filter((o) => o.getClientRects().length);
  }

  // A dropdown that is not a <select>: a control that opens a list of options.
  // Greenhouse, Ashby and Workday all build their own, and none of them were
  // being filled at all.
  async function pickFromListbox(el, answer) {
    let options = [];
    for (let go = 0; go < 2 && !options.length; go++) {
      press(el);
      for (let tries = 0; tries < 10 && !options.length; tries++) {
        await rest(40);
        options = optionsFor(el);
      }
    }
    if (!options.length) { if (el.blur) el.blur(); return false; }
    const at = bestOption(answer, options.map((o) => o.textContent || ""));
    if (at < 0) {
      document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      if (el.blur) el.blur();
      return false;
    }
    press(options[at]);
    await rest(60);
    return true;
  }

  // Where a resume goes on this form. Prefer a picker that says what it wants;
  // otherwise the first one on the page, which on Greenhouse and Lever is the
  // resume every time.
  function resumeInput() {
    const files = [...document.querySelectorAll('input[type="file"]')]
      .filter((el) => !el.disabled && (el.offsetParent !== null || el.closest("label, .field, [class*=upload]")));
    if (!files.length) return null;
    const wants = /resume|cv\b|curriculum/i;
    return files.find((el) => wants.test(labelOf(el) + " " + (el.name || "") + " " + (el.id || "")
                                        + " " + (el.getAttribute("aria-label") || ""))) || files[0];
  }

  async function resumeFile(j, me) {
    const name = ((me && me.name ? me.name + " " : "") + "Resume " + j.company)
      .replace(/[^A-Za-z0-9 _.-]+/g, "").replace(/\s+/g, "_") + ".pdf";
    const r = await ask({ kind: "resume", path: j.pdf });
    if (r.error || !r.b64) return { error: r.error || "could not read your resume" };
    const raw = atob(r.b64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return { file: new File([bytes], name, { type: "application/pdf" }), name };
  }

  // A file input cannot be typed into, but it can be given files - the same way
  // a drop would. Some forms listen for the drop rather than the change, so both
  // are sent. Nothing is submitted: the form is his to send.
  function attach(input, file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    try {
      input.files = dt.files;
    } catch (e) {
      return false;
    }
    if (!input.files || !input.files.length) return false;
    for (const kind of ["input", "change"])
      input.dispatchEvent(new Event(kind, { bubbles: true }));
    const zone = input.closest("[class*=drop], [class*=upload], label") || input.parentElement;
    if (zone) {
      const drop = new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt });
      zone.dispatchEvent(drop);
    }
    return true;
  }

  function save(file) {
    const url = URL.createObjectURL(file);
    const a = document.createElement("a");
    a.href = url;
    a.download = file.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  // The answer for a question: jobbot's tailored one first, then his own facts.
  function answerFor(label, me, questions) {
    let best = 0, value = "";
    for (const q of questions) {
      const score = sameQuestion(q.label, label);
      if (q.answer && score > best && score >= 0.6) { best = score; value = q.answer; }
    }
    if (value) return value;
    if (!me) return "";
    for (const [pattern, pick] of ME) if (pattern.test(label)) return pick(me) || "";
    return "";
  }

  // Everything jobbot had no answer for, so the panel can say what it missed.
  let unanswered = [];

  async function fill(me, questions) {
    unanswered = [];
    let done = 0;
    const claimed = new Set();

    // Radios and checkboxes first. They are whole questions - their own labels
    // are the answers - so they must not be read as fields of their own. They
    // were skipped entirely until now, which is every yes/no on the form.
    const groups = new Map();
    for (const el of document.querySelectorAll('input[type="radio"], input[type="checkbox"]')) {
      if (el.disabled || !seen(el)) continue;
      const key = el.type === "radio" && el.name ? "r:" + el.name : "c:" + (el.name || labelOf(el));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(el);
    }
    for (const els of groups.values()) {
      els.forEach((e) => claimed.add(e));
      if (els.some((e) => e.checked)) continue;         // he has already answered
      const label = groupLabel(els) || (els.length === 1 ? labelOf(els[0]) : "");
      if (!label) continue;
      const shown = groupLabel(els) || humanLabel(els[0]);
      const options = els.map((e) => humanLabel(e) || e.value);
      const value = answerFor(label, me, questions);
      if (!value) { unanswered.push({ label: shown, options }); continue; }
      if (pickOne(els, value)) done += 1;
      else unanswered.push({ label: shown, options, tried: value });
    }

    // Everything that takes typing or is a real <select>.
    const fields = [...document.querySelectorAll("input, textarea, select")].filter((el) => {
      if (el.disabled || el.readOnly || claimed.has(el) || !seen(el)) return false;
      if (["hidden", "file", "password", "submit", "button", "image", "reset"].includes(el.type)) return false;
      return !el.value;                       // never write over something he typed
    });
    for (const el of fields) {
      const label = labelOf(el);
      if (!label) continue;
      const value = answerFor(label, me, questions);
      if (!value) continue;
      if (el.tagName === "SELECT") {
        const texts = [...el.options].map((o) => o.textContent || "");
        const at = bestOption(value, texts);
        if (at < 0 || !bare(texts[at])) {     // the first option is usually "Select..."
          unanswered.push({ label: humanLabel(el), options: texts.filter((t) => bare(t)), tried: value });
          continue;
        }
        el.value = el.options[at].value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
        done += 1;
      } else if (put(el, value)) {
        done += 1;
      } else {
        unanswered.push({ label: humanLabel(el), tried: value, why: "the field would not take it" });
      }
    }

    // And the dropdowns that are not <select>.
    const combos = [...document.querySelectorAll('[role="combobox"], [aria-haspopup="listbox"]')]
      .filter((el) => !claimed.has(el) && seen(el) && !el.disabled);
    for (const el of combos) {
      const shown = bare(el.value || el.textContent || "");
      if (shown && !/^(select|choose|pick|search|start typing)\b/.test(shown)) continue;  // answered
      const label = labelOf(el);
      if (!label) continue;
      const value = answerFor(label, me, questions);
      if (!value) { unanswered.push({ label: humanLabel(el), why: "a dropdown jobbot has no answer for" }); continue; }
      if (await pickFromListbox(el, value)) done += 1;
      else unanswered.push({ label: humanLabel(el), tried: value, why: "none of its options matched" });
    }
    return done;
  }

  /* ------------------------------------------------------------- the panel -- */

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const root = document.createElement("div");
  root.id = "jobbot-root";
  root.innerHTML = '<button id="jobbot-tab" type="button">jobbot</button><div id="jobbot-panel" hidden></div>';
  (document.body || document.documentElement).appendChild(root);
  const tab = root.querySelector("#jobbot-tab");
  const panel = root.querySelector("#jobbot-panel");

  let found = null, me = null, questions = [], open = false, busy = false;

  function say(text, kind) {
    const note = panel.querySelector("#jobbot-said");
    if (!note) return;
    note.textContent = text;
    note.className = kind || "";
    clearTimeout(say.timer);
    say.timer = setTimeout(() => { note.textContent = ""; note.className = ""; }, 4000);
  }

  function draw() {
    if (found === "setup") {
      panel.innerHTML = '<div class="jb-head"><b>jobbot</b></div>' +
        '<p class="jb-quiet">Tell the extension where jobbot lives and it will work on every application form.</p>' +
        '<div class="jb-do"><button class="jb-btn jb-primary" data-go="options">Set jobbot up</button></div>';
      return;
    }
    if (!found) {
      const page = readPage();
      panel.innerHTML = '<div class="jb-head"><b>jobbot</b><span>Not on your board</span></div>' +
        '<div class="jb-title">' + esc(page.title) + "</div>" +
        '<p class="jb-quiet">' + esc(page.company) +
        (me ? ". Fill in what jobbot knows about you, or add the posting and it will write you a resume."
            : ". Add it and jobbot will treat it like any other posting: you can ask for a resume.") + "</p>" +
        '<div class="jb-do">' +
          // His own details do not need a posting behind them. Most apply forms
          // are not recognised - Workday and iCIMS rewrite the address - and
          // until now that meant the panel offered nothing but a bookmark.
          (me ? '<button class="jb-btn jb-primary" data-go="fill">Fill what I can</button>' : "") +
          '<button class="jb-btn" data-go="add">Add to jobbot</button>' +
        "</div>" +
        '<div id="jobbot-said"></div>';
      return;
    }
    const j = found;
    const answered = questions.filter((q) => q.answer);
    panel.innerHTML =
      '<div class="jb-head"><b>jobbot</b><span>' + esc(j.company) + "</span></div>" +
      '<div class="jb-title">' + esc(j.title) + "</div>" +
      (j.note ? '<p class="jb-quiet">' + esc(j.note) + "</p>" : "") +
      '<div class="jb-do">' +
        (j.pdf && resumeInput()
          ? '<button class="jb-btn jb-primary" data-go="attach">Put my resume in</button>' : "") +
        '<button class="jb-btn' + (j.pdf && resumeInput() ? "" : " jb-primary") +
          '" data-go="fill">Fill what I can</button>' +
        (j.pdf ? '<button class="jb-btn" data-go="resume">Save resume</button>' : "") +
      "</div>" +
      (answered.length
        ? '<div class="jb-qs">' + answered.map((q, i) =>
            '<div class="jb-q" data-copy="' + i + '"><div class="jb-label">' + esc(q.label) +
            (q.how === "you" ? '<i>yours</i>' : q.how === "draft" ? "<i>a draft</i>" : "") + "</div>" +
            '<div class="jb-a">' + esc(q.answer) + "</div></div>").join("") + "</div>" +
          '<div class="jb-do"><button class="jb-btn" data-go="copy-all">Copy every answer</button></div>'
        : '<p class="jb-quiet">No answers written for this one yet.</p>') +
      '<div class="jb-do jb-end">' +
        (j.state === "done"
          ? '<span class="jb-quiet">Marked applied.</span>'
          : '<button class="jb-btn" data-go="applied">I applied</button>') +
        '<button class="jb-btn jb-link" data-go="app">Open in jobbot</button>' +
      "</div>" +
      '<div id="jobbot-said"></div>';
  }

  async function act(go) {
    if (busy) return;
    const j = found;
    if (go === "options") return void ask({ kind: "options" });
    if (go === "add") {
      busy = true;
      say("Adding");
      const r = await ask({ kind: "capture", posting: readPage() });
      busy = false;
      if (r.error) return say(r.error === "setup" ? "Set jobbot up first" : r.error, "bad");
      say(r.said || "Added to your jobs");
      const again = await ask({ kind: "lookup", url: location.href });
      if (again && again.job) { found = again.job; questions = again.questions || []; draw(); }
      return;
    }
    if (go === "resume") {
      busy = true;
      say("Saving");
      const got = await resumeFile(j, me);
      busy = false;
      if (got.error) return say(got.error === "setup" ? "Set jobbot up first" : got.error, "bad");
      save(got.file);
      say("Saved as " + got.name);
      return;
    }
    if (go === "attach") {
      const input = resumeInput();
      if (!input) return say("No file picker on this page - use Save resume", "bad");
      busy = true;
      say("Reading your resume");
      const got = await resumeFile(j, me);
      busy = false;
      if (got.error) return say(got.error === "setup" ? "Set jobbot up first" : got.error, "bad");
      if (!attach(input, got.file)) {
        save(got.file);
        return say("This picker would not take it - saved to your downloads instead", "bad");
      }
      say("Resume attached as " + got.name + ". Check it before you send.");
      return;
    }
    if (go === "fill") {
      if (!me) return say("Set jobbot up first", "bad");
      const n = await fill(me, questions);
      // The resume is the one field that is always asked for and can never be
      // typed, so filling a form without it leaves the tedious part undone.
      const input = j && j.pdf && resumeInput();
      let withResume = "";
      if (input) {
        busy = true;
        const got = await resumeFile(j, me);
        busy = false;
        if (!got.error && attach(input, got.file)) withResume = ", and your resume";
      }
      // Say what it could not do as well. A form half filled without a word
      // about the rest is how you send an application with a blank question.
      const left = unanswered.length
        ? " " + unanswered.length + (unanswered.length === 1 ? " question is" : " questions are") + " still yours: "
          + unanswered.slice(0, 3).map((u) => u.label.slice(0, 40)).join("; ")
        : "";
      say(n || withResume
        ? "Filled " + n + (n === 1 ? " field" : " fields") + withResume + "." + (left || " Read it before you send.")
        : "Nothing here matched what jobbot knows about you." + left);
      return;
    }
    if (go === "copy-all") {
      const text = questions.filter((q) => q.answer).map((q) => q.label + "\n" + q.answer).join("\n\n");
      navigator.clipboard.writeText(text).then(() => say("Copied"), () => say("Could not copy", "bad"));
      return;
    }
    if (go === "applied") {
      busy = true;
      const r = await ask({ kind: "command", uid: j.uid, command: "applied" });
      busy = false;
      if (r.error) return say(r.error, "bad");
      found = { ...j, state: "done" };
      draw();
      say("Recorded as applied");
      return;
    }
    if (go === "app") {
      const s = await ask({ kind: "settings" });
      if (s.base) window.open(s.base.replace(/\/$/, "") + "/", "_blank", "noopener");
      return;
    }
  }

  panel.addEventListener("click", (e) => {
    const go = e.target.closest("[data-go]");
    if (go) return act(go.dataset.go);
    const copy = e.target.closest("[data-copy]");
    if (copy) {
      const q = questions.filter((x) => x.answer)[Number(copy.dataset.copy)];
      if (q) navigator.clipboard.writeText(q.answer).then(() => say("Copied that answer"),
                                                          () => say("Could not copy", "bad"));
    }
  });

  function show(next) {
    open = next === undefined ? !open : next;
    panel.hidden = !open;
    root.classList.toggle("jb-open", open);
    if (open) draw();
  }
  tab.addEventListener("click", () => show());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open) show(false); });

  window.__jobbot = { open: () => show(true) };

  // Ask once, quietly. The tab only says anything if jobbot has something for
  // this page; otherwise it sits in the corner and waits to be asked.
  ask({ kind: "lookup", url: location.href }).then((r) => {
    if (r.error === "setup") { found = "setup"; tab.textContent = "jobbot"; return; }
    if (r.error) return;
    me = r.me || null;
    if (r.job) {
      found = r.job;
      questions = r.questions || [];
      tab.textContent = "jobbot · " + r.job.company;
      root.classList.add("jb-known");
    } else if (me && document.querySelector("input, textarea")) {
      // Not a posting it knows, but a form it can still help with.
      tab.textContent = "jobbot · fill";
      root.classList.add("jb-known");
    }
  });
})();
