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

  // React and friends listen for their own setter, not for a changed value.
  function put(el, value) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const set = Object.getOwnPropertyDescriptor(proto, "value");
    if (set && set.set) set.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
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

  function fill(me, questions) {
    const fields = [...document.querySelectorAll("input, textarea, select")].filter((el) => {
      if (el.disabled || el.readOnly || el.offsetParent === null) return false;
      if (["hidden", "file", "password", "submit", "button", "checkbox", "radio"].includes(el.type)) return false;
      return !el.value;                       // never write over something he typed
    });
    let done = 0;
    for (const el of fields) {
      const label = labelOf(el);
      if (!label) continue;
      let value = "";
      // What jobbot wrote for this job comes first: it is the tailored answer.
      let best = 0;
      for (const q of questions) {
        const score = sameQuestion(q.label, label);
        if (q.answer && score > best && score >= 0.6) { best = score; value = q.answer; }
      }
      if (!value && me) {
        for (const [pattern, pick] of ME) {
          if (pattern.test(label)) { value = pick(me) || ""; break; }
        }
      }
      if (!value) continue;
      if (el.tagName === "SELECT") {
        const want = bare(value);
        const hit = [...el.options].find((o) => bare(o.textContent) === want) ||
                    [...el.options].find((o) => bare(o.textContent).includes(want) && want);
        if (!hit) continue;
        el.value = hit.value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        put(el, value);
      }
      done += 1;
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
        '<p class="jb-quiet">' + esc(page.company) + ". Add it and jobbot will treat it like any other posting: " +
        "you can ask it for a resume.</p>" +
        '<div class="jb-do"><button class="jb-btn jb-primary" data-go="add">Add to jobbot</button></div>' +
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
        (j.pdf ? '<button class="jb-btn jb-primary" data-go="resume">Save resume</button>' : "") +
        '<button class="jb-btn" data-go="fill">Fill what I can</button>' +
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
      const name = ((me && me.name ? me.name + " " : "") + "Resume " + j.company)
        .replace(/[^A-Za-z0-9 _.-]+/g, "").replace(/\s+/g, "_") + ".pdf";
      const r = await ask({ kind: "resume", path: j.pdf, name });
      busy = false;
      say(r.error || "Saved to your downloads", r.error ? "bad" : "");
      return;
    }
    if (go === "fill") {
      const n = fill(me, questions);
      say(n ? "Filled " + n + (n === 1 ? " field. Read it before you send." : " fields. Read them before you send.")
            : "Nothing here matched anything jobbot knows");
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
    }
  });
})();
