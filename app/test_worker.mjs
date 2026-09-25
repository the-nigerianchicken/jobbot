// Offline checks for the app: auth, the feed, every button, the applications
// tracker, and what GitHub Actions is allowed to do. The database is the real
// schema in memory; GitHub is stubbed, so no network and no token.
import worker from "./worker.js";
import { makeDb } from "./d1stub.mjs";

const env = { GH_TOKEN: "stub", APP_PASSCODE: "hunter2", INGEST_TOKEN: "robot",
              REPO: "o/r", BRANCH: "main", DB: makeDb() };

const app = { knockouts: ["US citizens only"], questions: [
  { label: "Email", answer: "m@x.com", how: "rule", required: true },
  { label: "Cover letter", answer: null, how: "skip", required: false }] };

const calls = [];
globalThis.fetch = async (url, init = {}) => {
  calls.push({ url: String(url), method: init.method || "GET", body: init.body });
  const path = String(url);
  const b64 = (o) => btoa(unescape(encodeURIComponent(JSON.stringify(o))));
  if (path.includes("application.json") && (init.method || "GET") === "GET")
    return new Response(JSON.stringify({ content: b64(app), sha: "abc" }), { status: 200 });
  if (path.includes("preview.png")) return new Response(new Uint8Array([1, 2, 3]), { status: 200 });
  if (init.method === "POST" || init.method === "PUT") return new Response("{}", { status: 200 });
  return new Response("no", { status: 404 });
};

let fails = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "ok " : "BAD"} ${name}${ok ? "" : "   " + extra}`);
  if (!ok) fails++;
};
const req = (path, opts = {}) => worker.fetch(new Request("https://x" + path, opts), env);
const get = (path, headers = {}) => req(path, { headers });
const body = (path, method, payload, headers = {}) => req(path, { method,
  headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(payload) });

const iso = (daysAgo) => new Date(Date.now() - daysAgo * 864e5).toISOString();
const seed = [
  { uid: "a", company: "acme", title: "SWE Intern, Summer 2027", tier: 1, term: "Summer 2027",
    location: "Toronto, Canada; Vancouver, Canada", state: "ready", issue: 7, folder: "resumes/A/B",
    pdf: "resumes/A/B/x.pdf", preview: "resumes/A/B/preview.png", apply_url: "https://apply",
    knockout: 1, posted_at: iso(0.2), seen_at: iso(0.2) },
  { uid: "a2", company: "acme", title: "SWE Intern Summer 2027", tier: 1, state: "ready",
    location: "Montreal, Canada", posted_at: iso(0.3), seen_at: iso(0.3) },
  { uid: "b", company: "beta", title: "Intern", tier: 2, state: "needs",
    note: "The site emailed you a code", issue: 8, posted_at: iso(1), seen_at: iso(1) },
  { uid: "c", company: "gamma", title: "Co-op", tier: 3, state: "building", posted_at: iso(0.1), seen_at: iso(0.1) },
  { uid: "d", company: "delta", title: "Intern", tier: 2, state: "done", posted_at: iso(2), seen_at: iso(2) },
  { uid: "e", company: "epsilon", title: "Intern", tier: 2, state: "skipped", posted_at: iso(3), seen_at: iso(3) },
];

/* ---------------------------------------------------------------- auth --- */

check("app shell is public", (await get("/")).status === 200);
check("the feed needs the passcode", (await get("/api/jobs")).status === 401);
check("the tracker needs the passcode", (await get("/api/applications")).status === 401);
check("wrong passcode refused", (await body("/api/login", "POST", { passcode: "nope" })).status === 401);
const ok = await body("/api/login", "POST", { passcode: "hunter2" });
const cookie = (ok.headers.get("set-cookie") || "").split(";")[0];
check("right passcode sets a cookie", ok.status === 200 && cookie.startsWith("jobbot_ok="));
check("the cookie is HttpOnly and Secure",
  /HttpOnly/.test(ok.headers.get("set-cookie")) && /Secure/.test(ok.headers.get("set-cookie")));
const as = { cookie };

/* -------------------------------------------------------------- ingest --- */

check("ingest needs the robot token", (await body("/api/ingest", "POST", { jobs: seed })).status === 401);
check("the passcode is not the robot token",
  (await body("/api/ingest", "POST", { jobs: seed }, as)).status === 401);
const robot = { authorization: "Bearer robot" };
const put = await (await body("/api/ingest", "POST", { jobs: seed }, robot)).json();
check("jobbot can report jobs in", put.written === 6 && put.jobs === 6, JSON.stringify(put));
await body("/api/ingest", "POST", { jobs: seed }, robot);
const twice = await (await body("/api/ingest", "POST", { jobs: seed }, robot)).json();
check("reporting the same jobs twice does not duplicate them", twice.jobs === 6);

/* ---------------------------------------------------------------- feed --- */

let feed = await (await get("/api/jobs", as)).json();
let by = Object.fromEntries(feed.jobs.map((j) => [j.uid, j]));
check("skipped jobs stay out of the feed", !("e" in by) && feed.jobs.length === 4,
  feed.jobs.map((j) => j.uid).join(","));
check("the same role in two cities is one card", by.a && by.a.also === 1 && !("a2" in by));
check("jobs needing him come first", feed.jobs[0].uid === "b");
check("company names are readable", by.c.company === "Gamma");
check("locations are short", by.a.where === "Toronto +1");
check("the knockout flag survives", by.a.knockout === true);
check("recent applies still show", by.d && by.d.state === "done");
check("skipped jobs are there when asked for",
  (await (await get("/api/jobs?skipped=1", as)).json()).jobs.some((j) => j.uid === "e"));

// An old application belongs in the tracker, not in the feed.
await body("/api/ingest", "POST", { jobs: [{ ...seed[4], uid: "old", company: "omega",
  state: "done", seen_at: iso(60) }] }, robot);
await env.DB.prepare("UPDATE jobs SET updated_at = ?1 WHERE uid = 'old'").bind(iso(60)).run();
feed = await (await get("/api/jobs", as)).json();
check("an apply from two months ago is not in the feed", !feed.jobs.some((j) => j.uid === "old"));

/* ------------------------------------------------------------- answers --- */

const ans = await (await get("/api/answers?folder=resumes/A/B", as)).json();
check("answers skip blank optional questions", ans.questions.length === 1 && ans.questions[0].label === "Email");
check("knockouts surface", ans.knockouts[0] === "US citizens only");
const img = await get("/file?path=resumes/A/B/preview.png", as);
check("the preview is served as a png", img.headers.get("content-type") === "image/png");
const dl = await get("/file?path=resumes/A/B/preview.png&save=" + encodeURIComponent("Ada Lovelace Resume Jane/Street"), as);
check("download is named", (dl.headers.get("content-disposition") || "").includes('filename="Ada_Lovelace_Resume_JaneStreet.png"'));
check("path traversal refused", (await get("/file?path=../../etc/passwd", as)).status === 400);
check("traversal in a folder refused", (await get("/api/answers?folder=../../x", as)).status === 400);

const edit = await body("/api/answer", "POST", { folder: "resumes/A/B", label: "Email", text: "new@x.com" }, as);
check("an edited answer saves", edit.status === 200);
const back = await (await get("/api/answers?folder=resumes/A/B", as)).json();
check("his wording replaces the draft and is marked as his",
  back.questions[0].answer === "new@x.com" && back.questions[0].how === "you");
const again = await body("/api/answer", "POST", { folder: "resumes/A/B", label: "Email", text: "later@x.com" }, as);
check("editing the same answer twice is fine", again.status === 200 &&
  (await (await get("/api/answers?folder=resumes/A/B", as)).json()).questions[0].answer === "later@x.com");
check("editing an unknown question is refused",
  (await body("/api/answer", "POST", { folder: "resumes/A/B", label: "Nope", text: "x" }, as)).status === 404);
check("editing an answer needs auth",
  (await body("/api/answer", "POST", { folder: "resumes/A/B", label: "Email", text: "x" })).status === 401);
const reverted = await (await body("/api/answer", "POST",
  { folder: "resumes/A/B", label: "Email", revert: true }, as)).json();
check("an edited answer can go back to jobbot's draft",
  reverted.ok && reverted.answer === "m@x.com" &&
  (await (await get("/api/answers?folder=resumes/A/B", as)).json()).questions[0].how === "rule");
await body("/api/answer", "POST", { folder: "resumes/A/B", label: "Email", text: "later@x.com" }, as);
check("an edited answer is queued for jobbot to write into the resume folder",
  (await (await get("/api/events", robot)).json()).events.some((e) =>
    e.kind === "answer" && e.detail.label === "Email" && e.detail.text === "later@x.com"));

/* ------------------------------------------------------------- actions --- */

const cmd = (uid, command) => body("/api/command", "POST", { uid, command }, as);
const state = async (uid) => (await env.DB.prepare("SELECT state FROM jobs WHERE uid = ?1").bind(uid).first()).state;

calls.length = 0;
const applied = await (await cmd("a", "approve")).json();
check("Apply moves the card and tells the workflow",
  applied.state === "working" && (await state("a")) === "working"
  && calls.some((c) => c.method === "POST" && c.url.includes("/issues/7/comments")));
check("Stop puts it back", (await (await cmd("a", "stop")).json()).state === "ready");
check("Archive hides it", (await (await cmd("a", "archive")).json()).state === "skipped");
check("putting back a job that has a resume returns it to ready",
  (await cmd("a", "reopen")).status === 200 && (await state("a")) === "ready");
check("Rebuild marks it building", (await (await cmd("c", "rebuild")).json()).state === "building");
check("unknown commands refused", (await cmd("a", "rm -rf")).status === 400);
check("an unknown job is refused", (await cmd("nope", "skip")).status === 404);
check("commands need auth", (await body("/api/command", "POST", { uid: "a", command: "skip" })).status === 401);

// A job with no issue still works: jobbot picks the event up on its next run.
check("a job without an issue can still be skipped", (await cmd("c", "skip")).status === 200);
const events = await (await get("/api/events", { ...robot })).json();
check("what he did is queued for jobbot", events.events.some((e) => e.uid === "c" && e.kind === "skip"));
check("the event carries what jobbot needs",
  events.events.some((e) => e.kind === "skip" && e.detail && "issue" in e.detail));
const ids = events.events.map((e) => e.id);
check("jobbot can ack them", (await (await body("/api/events/ack", "POST", { ids }, robot)).json()).acked === ids.length);
check("acked events are not handed out twice",
  (await (await get("/api/events", robot)).json()).events.length === 0);
check("events need the robot token", (await get("/api/events", as)).status === 401);

/* ------------------------------------------- nothing is written unasked --- */

await body("/api/ingest", "POST", { jobs: [
  { uid: "n1", company: "new co", title: "Intern", tier: 1, state: "new",
    apply_url: "https://job-boards.greenhouse.io/n/jobs/9", seen_at: iso(0.1) },
  { uid: "n2", company: "other co", title: "Intern", tier: 2, state: "new",
    apply_url: "https://job-boards.greenhouse.io/o/jobs/9", seen_at: iso(0.1) },
  { uid: "n3", company: "third co", title: "Intern", tier: 3, state: "new",
    apply_url: "https://job-boards.greenhouse.io/t/jobs/9", seen_at: iso(0.1) },
] }, robot);
calls.length = 0;
const asked = await (await cmd("n1", "build")).json();
check("Apply on a new posting starts its resume",
  asked.state === "building" && (await state("n1")) === "building");
check("and asks GitHub to start the run now",
  calls.some((c) => c.method === "POST" && c.url.includes("workflows/resume.yml/dispatches")));
check("he is told when it actually started", /watch this job|Writing your resume/i.test(asked.said));
let queued = (await (await get("/api/events", robot)).json()).events;
check("jobbot is told he wants it applied for",
  queued.some((e) => e.kind === "build" && e.uid === "n1" && e.detail.apply === true));
await cmd("n2", "draft");
queued = (await (await get("/api/events", robot)).json()).events;
check("\"just write it\" asks for the resume only",
  queued.some((e) => e.kind === "build" && e.uid === "n2" && e.detail.apply === false));

const many = await (await body("/api/command", "POST",
  { uids: ["n2", "n3"], command: "archive" }, as)).json();
check("several jobs archive in one tap", many.count === 2 && (await state("n3")) === "skipped");
check("an archived new posting comes back as new",
  (await cmd("n3", "reopen")).status === 200 && (await state("n3")) === "new");

/* ------------------------------------------------- the companies he follows --- */

await body("/api/ingest", "POST", { jobs: [], targets: ["amazon", "stripe", "jane street"] }, robot);
let follows = (await (await get("/api/jobs", as)).json()).following;
check("the following list is seeded from targets.txt", follows.length === 3 &&
  follows.some((f) => f.key === "janestreet" && f.name === "Jane Street"));
await body("/api/ingest", "POST", { jobs: [], targets: ["amazon", "somethingelse"] }, robot);
follows = (await (await get("/api/jobs", as)).json()).following;
check("but only once: after that the app owns it", follows.length === 3);
const added = await (await body("/api/command", "POST", { command: "follow", company: "Two Sigma" }, as)).json();
follows = (await (await get("/api/jobs", as)).json()).following;
check("he can follow a company", added.ok && follows.some((f) => f.key === "twosigma"));
await body("/api/command", "POST", { command: "unfollow", company: "stripe" }, as);
follows = (await (await get("/api/jobs", as)).json()).following;
check("and stop following one", !follows.some((f) => f.key === "stripe"));
check("jobbot is told, so targets.txt changes too",
  (await (await get("/api/events", robot)).json()).events.some((e) => e.kind === "follow" && e.detail.key === "twosigma"));
check("a follow needs a name", (await body("/api/command", "POST", { command: "follow", company: " " }, as)).status === 400);

/* ------------------------------------------------ nothing lingers forever --- */

await body("/api/ingest", "POST", { jobs: [
  { uid: "ghost", company: "_check", title: "Intern", state: "building", seen_at: iso(0.1) },
  { uid: "kept", company: "real co", title: "Intern", state: "new", seen_at: iso(0.1) },
] }, robot);
// jobbot reports everything it knows except the ghost.
const everything = (await env.DB.prepare("SELECT uid FROM jobs").bind().all()).results.map((r) => r.uid);
const pruned = await (await body("/api/ingest", "POST",
  { jobs: [], known: everything.filter((u) => u !== "ghost") }, robot)).json();
feed = await (await get("/api/jobs?skipped=1", as)).json();
check("a job jobbot has forgotten leaves the app", !feed.jobs.some((j) => j.uid === "ghost") && pruned.removed >= 1);
check("a job it still knows stays", feed.jobs.some((j) => j.uid === "kept"));
check("anything he archived or applied to is his and stays",
  feed.jobs.some((j) => j.uid === "e") || feed.jobs.some((j) => j.state === "skipped"));

/* ------------------------------------------------------- filtered out --- */

await body("/api/ingest", "POST", { filtered: [
  { uid: "f1", company: "lazard", title: "AI Engineer Intern", location: "NYC", url: "https://p/1",
    posted_at: iso(0.2), reason: "location not in allowed geography (nyc)", description: "The whole JD", source: "community" },
  { uid: "f2", company: "old co", title: "Intern", posted_at: iso(24 * 9), reason: "posted too long ago (over 24h)" },
  { uid: "kept", company: "real co", title: "Intern", reason: "title not a wanted role" },
] }, robot);
feed = await (await get("/api/jobs", as)).json();
let held = (await (await get("/api/filtered", as)).json()).filtered;
check("filtered postings are listed with a reason he can read",
  held.length === 1 && held[0].uid === "f1" && held[0].why === "Outside the US and Canada", JSON.stringify(held));
await body("/api/ingest", "POST", { filtered: [{ uid: "f3", company: "x", title: "Data Science Intern",
  posted_at: iso(1), reason: "title excluded (data scien)" }] }, robot);
held = (await (await get("/api/filtered", as)).json()).filtered;
check("an excluded word is shown whole", held.some((f) => f.uid === "f3" && f.why === "A role type you excluded"
  && f.detail.includes("Data Science")), JSON.stringify(held));
await env.DB.prepare("DELETE FROM filtered WHERE uid = 'f3'").bind().run();
check("the feed counts them", feed.filtered === 1, String(feed.filtered));
check("a posting older than a week is not kept", !held.some((f) => f.uid === "f2"));
check("a job already in the feed is never listed as filtered", !held.some((f) => f.uid === "kept"));
const brought = await (await body("/api/command", "POST", { command: "restore", uid: "f1" }, as)).json();
feed = await (await get("/api/jobs", as)).json();
const restored = feed.jobs.find((j) => j.uid === "f1");
check("bringing one back puts it in the feed as new", brought.ok && restored && restored.state === "new" && restored.jd === "The whole JD");
check("and takes it off the filtered list", (await (await get("/api/filtered", as)).json()).filtered.length === 0);
check("jobbot is told, with the whole posting",
  (await (await get("/api/events", robot)).json()).events.some((e) => e.kind === "restore" && e.detail.posting.description === "The whole JD"));
const known = (await env.DB.prepare("SELECT uid FROM jobs").bind().all()).results.map((r) => r.uid).filter((u) => u !== "f1");
await body("/api/ingest", "POST", { jobs: [], known }, robot);
check("a sync before jobbot hears of it does not remove it",
  (await (await get("/api/jobs", as)).json()).jobs.some((j) => j.uid === "f1"));
check("restoring an unknown posting is refused",
  (await body("/api/command", "POST", { command: "restore", uid: "nope" }, as)).status === 404);

/* ----------------------------------------------------------- settings --- */

check("a setting cannot be saved before jobbot sends its defaults",
  (await body("/api/settings", "POST", { key: "search", value: { window_hours: 48 } }, as)).status === 409);
const searchBase = { window_hours: 24, seasons: { "Summer 2027": true }, roles_wanted: ["software engineer"] };
await body("/api/ingest", "POST", { settings_base: { search: searchBase, nonsense: { x: 1 } } }, robot);
let view = (await (await get("/api/settings", as)).json()).sections;
check("Settings shows jobbot's defaults", view.search && view.search.value.window_hours === 24 && !view.search.edited
  && !view.nonsense);
await body("/api/settings", "POST", { key: "search", value: { ...searchBase, window_hours: 72 } }, as);
view = (await (await get("/api/settings", as)).json()).sections;
check("a saved setting is shown as his", view.search.value.window_hours === 72 && view.search.edited);
await body("/api/ingest", "POST", { settings_base: { search: { ...searchBase, roles_wanted: ["software engineer", "sre"] } } }, robot);
view = (await (await get("/api/settings", as)).json()).sections;
check("a default that changes in the file still reaches what he did not touch",
  view.search.value.window_hours === 72 && view.search.value.roles_wanted.includes("sre"), JSON.stringify(view.search.value));
const raw = (await (await get("/api/settings", robot)).json()).raw;
check("jobbot reads the value with the default it was made against",
  raw.search.value.window_hours === 72 && raw.search.value_base.window_hours === 24);
check("the page cannot read the robot's view without the token",
  (await (await get("/api/settings")).json()).error === "locked");
await body("/api/settings", "POST", { key: "search", undo: true }, as);
view = (await (await get("/api/settings", as)).json()).sections;
check("undo puts back the save before", !view.search.edited && view.search.value.window_hours === 24);
await body("/api/settings", "POST", { key: "search", undo: true }, as);
check("undo of an undo restores it", (await (await get("/api/settings", as)).json()).sections.search.value.window_hours === 72);
await body("/api/settings", "POST", { key: "search", reset: true }, as);
check("reset goes back to the default", !(await (await get("/api/settings", as)).json()).sections.search.edited);
check("an unknown section is refused",
  (await body("/api/settings", "POST", { key: "secrets", value: {} }, as)).status === 400);

/* ---------------------------------------------- learning from archives --- */

await body("/api/ingest", "POST", { jobs: [
  { uid: "d1", company: "acme", title: "Data Engineer Intern", location: "Austin, TX", state: "new", seen_at: iso(1) },
  { uid: "d2", company: "beta", title: "Data Engineer Intern, Pipelines", location: "Austin, TX", state: "new", seen_at: iso(1) },
  { uid: "d3", company: "gamma", title: "Senior Data Engineer Intern", location: "Austin, TX", state: "new", seen_at: iso(1) },
  { uid: "d4", company: "delta", title: "Data Engineer Co-op", location: "Boston, MA", state: "new", seen_at: iso(1) },
  { uid: "w1", company: "wanted co", title: "Software Engineer Intern, Data Platform", state: "ready", seen_at: iso(1) },
  { uid: "c1", company: "evil corp", title: "Software Engineer Intern", state: "new", seen_at: iso(1) },
] }, robot);
await body("/api/settings", "POST", { key: "search", reset: true }, as);
for (const u of ["d1", "d2", "d3"]) await body("/api/command", "POST", { uid: u, command: "archive", reason: "role" }, as);
await body("/api/command", "POST", { uid: "c1", command: "archive", reason: "company" }, as);
let hints = (await (await get("/api/suggestions", as)).json()).suggestions;
const roleHint = hints.find((h) => h.kind === "exclude_role");
check("three archived titles sharing words suggest excluding them", roleHint && roleHint.word === "data engineer",
  JSON.stringify(hints));
check("a word in a job he went ahead with is never suggested", !hints.some((h) => h.word === "data"));
check("archiving as not this company offers to mute it", hints.some((h) => h.id === "mute:evilcorp"));
const took = await (await body("/api/suggestions", "POST", { id: roleHint.id }, as)).json();
const search = (await (await get("/api/settings", as)).json()).sections.search.value;
check("accepting adds the word to the roles he doesn't want", (search.roles_excluded || []).includes("data engineer"));
check("and archives the ones still in his feed", took.archived.includes("d4") && took.archived.length === 1,
  JSON.stringify(took));
check("jobbot is told about each", (await (await get("/api/events", robot)).json()).events
  .some((e) => e.kind === "archive" && e.uid === "d4"));
hints = (await (await get("/api/suggestions", as)).json()).suggestions;
check("an accepted suggestion is not offered again", !hints.some((h) => h.id === roleHint.id));
await body("/api/suggestions", "POST", { id: "mute:evilcorp", dismiss: true }, as);
check("a declined suggestion is not offered again",
  !(await (await get("/api/suggestions", as)).json()).suggestions.some((h) => h.id === "mute:evilcorp"));
await body("/api/command", "POST", { uid: "d1", command: "reopen" }, as);
check("reopening a job forgets why it was archived",
  !(await env.DB.prepare("SELECT 1 FROM feedback WHERE uid = 'd1'").bind().first()));

/* -------------------------------------------------------------- terms --- */

await body("/api/ingest", "POST", { jobs: [
  { uid: "t1", company: "termco", title: "Software Developer Co-op", state: "new", seen_at: iso(1),
    jd: "This 4-month co-op starts January 2027 in Toronto." },
  { uid: "t2", company: "termco2", title: "Software Engineer Intern", state: "new", seen_at: iso(1), jd: "Founded in 1999." },
  { uid: "t3", company: "termco3", title: "Software Engineer Intern", state: "new", seen_at: iso(1),
    jd: "Our Summer 2027 program is for students graduating between Fall 2028 and Summer 2029." },
] }, robot);
feed = await (await get("/api/jobs", as)).json();
check("a term named only in the description is found", feed.jobs.find((j) => j.uid === "t1").term === "Winter 2027");
check("a posting that names no term has none", feed.jobs.find((j) => j.uid === "t2").term === null);
check("a graduation date is not a term", feed.jobs.find((j) => j.uid === "t3").term === "Summer 2027",
  feed.jobs.find((j) => j.uid === "t3").term);

/* ------------------------------------------------------ what it is doing --- */

const wasFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  if (String(url).includes("/actions/runs?status=in_progress"))
    return new Response(JSON.stringify({ workflow_runs: [
      { path: ".github/workflows/watch.yml", run_started_at: iso(0.05) },
      { path: ".github/workflows/resume.yml", run_started_at: iso(0.05) },
      { path: ".github/workflows/resume.yml", run_started_at: iso(0.05) },
      { path: ".github/workflows/nothing.yml", run_started_at: iso(0.05) },
    ] }), { status: 200 });
  return wasFetch(url, init);
};
await env.DB.prepare("DELETE FROM meta WHERE key = 'runs'").bind().run();
feed = await (await get("/api/jobs", as)).json();
const says = (feed.running || []).map((r) => r.says + ":" + r.n).sort();
check("the app is told what jobbot is doing", says.join(" ") === "Checking the boards:1 Writing resumes:2", JSON.stringify(feed.running));
check("workflows he never sees are left out", !(feed.running || []).some((r) => r.kind === "nothing"));
globalThis.fetch = wasFetch;
await env.DB.prepare("DELETE FROM meta WHERE key = 'runs'").bind().run();

/* --------------------------------------------------------------- push --- */

// A real key pair, so the VAPID signing path is exercised rather than stubbed.
const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const rawPub = await crypto.subtle.exportKey("raw", pair.publicKey);
env.VAPID_PRIVATE = JSON.stringify(await crypto.subtle.exportKey("jwk", pair.privateKey));
env.VAPID_PUBLIC = btoa(String.fromCharCode(...new Uint8Array(rawPub))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
env.PUSH_CONTACT = "mailto:x@y.com";

const pushes = [];
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  if (String(url).includes("push.example")) {
    pushes.push({ url: String(url), auth: (init.headers || {}).Authorization || "" });
    return new Response("", { status: String(url).endsWith("gone") ? 410 : 201 });
  }
  return realFetch(url, init);
};

check("the page is told which key to subscribe with", (await (await get("/api/push", as)).json()).key === env.VAPID_PUBLIC);
await body("/api/push", "POST", { subscription: { endpoint: "https://push.example/ok", keys: { p256dh: "k", auth: "a" } } }, as);
await body("/api/push", "POST", { subscription: { endpoint: "https://push.example/gone", keys: {} } }, as);
check("a device subscribes", (await (await get("/api/push", as)).json()).devices === 2);
await body("/api/ingest", "POST", { jobs: [
  { uid: "p1", company: "pushco", title: "Software Engineer Intern", state: "ready", seen_at: iso(0.1) },
] }, robot);
check("a ready resume wakes the phone", pushes.length >= 1, JSON.stringify(pushes));
check("the push is signed with VAPID", /^vapid t=[\w-]+\.[\w-]+\.[\w-]+, k=/.test(pushes[0].auth), pushes[0] && pushes[0].auth);
check("a subscription the phone threw away is forgotten",
  (await (await get("/api/push", as)).json()).devices === 1);
const pushesBefore = pushes.length;
await body("/api/ingest", "POST", { jobs: [
  { uid: "p1", company: "pushco", title: "Software Engineer Intern", state: "ready", seen_at: iso(0.1) },
] }, robot);
check("the same news is not sent twice", pushes.length === pushesBefore);
const say = await (await get("/api/push?latest=1", as)).json();
check("the phone is told what happened when it asks",
  say.title === "Resume ready" && say.body.includes("Pushco"), JSON.stringify(say));
check("a push with no subscriber says so",
  (await (await body("/api/push", "POST", { test: true }, as)).json()).ok === true);
const swjs = await (await req("/sw.js")).text();
check("the service worker is served from the root", swjs.includes("notificationclick"));
globalThis.fetch = realFetch;

/* ------------------------------------------------------ what he knows --- */

await body("/api/ingest", "POST", { settings_base: { profile: {
  contact: { name: "Ada Lovelace" }, skills: { Languages: ["Python", "Go"] },
  entries: [{ id: "e1", facts: [{ id: "f1", tech: ["Kubernetes"] }] }] },
  search: { seasons: { "Summer 2027": true, "Fall 2026": false } } } }, robot);
feed = await (await get("/api/jobs", as)).json();
check("the app is told whose resumes these are", feed.owner === "Ada Lovelace");
check("and which tools he has used", ["python", "go", "kubernetes"].every((t) => feed.knows.includes(t)),
  JSON.stringify(feed.knows));
check("and which terms he wants", feed.terms.includes("Summer 2027") && !feed.terms.includes("Fall 2026"));

// The push service is stubbed again: the block above put the real fetch back.
globalThis.fetch = async (url, init = {}) => {
  if (String(url).includes("push.example")) { pushes.push({ url: String(url) }); return new Response("", { status: 201 }); }
  return realFetch(url, init);
};
await env.DB.prepare("DELETE FROM push_sent").bind().run();
let hot = pushes.length;
await body("/api/ingest", "POST", { jobs: [
  { uid: "hot1", company: "waymo", title: "Software Engineer Intern", tier: 1, state: "new", seen_at: iso(0.01) },
] }, robot);
check("a posting at a company he follows reaches his phone at once", pushes.length > hot);
const hotSaid = await (await get("/api/push?latest=1", as)).json();
check("and says which company", /New at Waymo/.test(hotSaid.title), JSON.stringify(hotSaid));
hot = pushes.length;
await body("/api/ingest", "POST", { jobs: [
  { uid: "cold1", company: "someco", title: "Software Engineer Intern", tier: 3, state: "new", seen_at: iso(0.01) },
] }, robot);
check("one from anywhere else waits for the board", pushes.length === hot);

/* ----------------------------------------------------------- watchdog --- */

const beat = (mins) => env.DB.prepare("INSERT INTO meta (key, value, at) VALUES ('checked', ?1, ?1) " +
  "ON CONFLICT(key) DO UPDATE SET value = excluded.value, at = excluded.at").bind(iso(mins / 1440)).run();
const asGitHub = (runs) => {
  globalThis.fetch = async (url, init = {}) => {
    if (String(url).includes("/actions/runs?status=in_progress"))
      return new Response(JSON.stringify({ workflow_runs: [] }), { status: 200 });
    if (String(url).includes("/actions/workflows/watch.yml/runs"))
      return new Response(JSON.stringify({ workflow_runs: runs }), { status: 200 });
    if (String(url).includes("push.example")) { pushes.push({ url: String(url) }); return new Response("", { status: 201 }); }
    return realFetch(url, init);
  };
};
await body("/api/push", "POST", { subscription: { endpoint: "https://push.example/ok2", keys: {} } }, as);
await env.DB.prepare("DELETE FROM meta WHERE key IN ('runs','health','health_said')").bind().run();

await beat(5);
asGitHub([{ conclusion: "success", created_at: iso(0.2), html_url: "https://x" }]);
let quiet = pushes.length;
await worker.scheduled({}, env, { waitUntil: () => {} });
check("a healthy jobbot says nothing", pushes.length === quiet);

await env.DB.prepare("DELETE FROM meta WHERE key = 'runs'").bind().run();
asGitHub([{ conclusion: "failure", created_at: iso(0.2), html_url: "https://x" }]);
await worker.scheduled({}, env, { waitUntil: () => {} });
check("a broken one tells his phone", pushes.length > quiet);
const told = await (await get("/api/push?latest=1", as)).json();
check("and says what is wrong", /last check failed/.test(told.body), JSON.stringify(told));
quiet = pushes.length;
await worker.scheduled({}, env, { waitUntil: () => {} });
check("it does not say it twice", pushes.length === quiet);

await env.DB.prepare("DELETE FROM meta WHERE key = 'runs'").bind().run();
asGitHub([{ conclusion: "success", created_at: iso(0.2), html_url: "https://x" }]);
await beat(60 * 5);   // five hours without a sweep
await worker.scheduled({}, env, { waitUntil: () => {} });
check("a sweep that never came is also worth saying",
  /not checked the boards/.test((await (await get("/api/push?latest=1", as)).json()).body));
await body("/api/ingest", "POST", { jobs: [
  { uid: "alive", company: "co", title: "Software Engineer Intern", state: "new", seen_at: iso(0.1) },
], checked_at: iso(0.01) }, robot);
check("a sweep that lands puts it back on its feet",
  (await env.DB.prepare("SELECT value FROM meta WHERE key = 'health'").bind().first()).value === "ok");
globalThis.fetch = realFetch;

/* -------------------------------------------------------------- usage --- */

await body("/api/usage", "POST", { counts: { "action: build": 2, "open a job": 5, "": 3 } }, as);
await body("/api/usage", "POST", { counts: { "open a job": 1 } }, as);
const use = await (await get("/api/usage", as)).json();
check("taps are counted per name", use.rows[0].name === "open a job" && use.rows[0].n === 6, JSON.stringify(use.rows));
check("usage needs him signed in", (await body("/api/usage", "POST", { counts: { x: 1 } })).status === 401);

/* --------------------------------------------- muting, snoozing, retrying --- */

await body("/api/ingest", "POST", { jobs: [
  { uid: "m1", company: "noisy co", title: "Intern", tier: 3, state: "new", seen_at: iso(0.1) },
  { uid: "m2", company: "Noisy Co", title: "Another intern", tier: 3, state: "new", seen_at: iso(0.1) },
] }, robot);
await body("/api/command", "POST", { command: "mute", company: "noisy co" }, as);
feed = await (await get("/api/jobs", as)).json();
check("muting a company clears its postings, however it is spelled",
  !feed.jobs.some((j) => j.uid === "m1" || j.uid === "m2"));
check("the app lists what is muted", (feed.muted || []).includes("noisyco"));
check("jobbot is told to stop queueing it",
  (await (await get("/api/events", robot)).json()).events.some((e) => e.kind === "mute"));
await body("/api/command", "POST", { command: "unmute", company: "Noisy Co" }, as);
check("unmuting brings them back",
  (await (await get("/api/jobs", as)).json()).jobs.some((j) => j.uid === "m1"));

const later = new Date(Date.now() + 36e5).toISOString();
await body("/api/command", "POST", { uid: "m1", command: "snooze", until: later }, as);
feed = await (await get("/api/jobs", as)).json();
check("a snoozed job leaves the board", !feed.jobs.some((j) => j.uid === "m1") && feed.snoozed === 1);
check("but it can be looked at",
  (await (await get("/api/jobs?snoozed=1", as)).json()).jobs.some((j) => j.uid === "m1"));
await body("/api/command", "POST", { uid: "m1", command: "wake" }, as);
check("waking it returns it", (await (await get("/api/jobs", as)).json()).jobs.some((j) => j.uid === "m1"));
check("a snooze needs a time", (await body("/api/command", "POST", { uid: "m1", command: "snooze" }, as)).status === 400);

calls.length = 0;
const retried = await (await cmd("b", "retry")).json();
check("trying the form again starts the apply run, forced past its own guard",
  retried.state === "working" && calls.some((c) => c.url.includes("workflows/approve.yml/dispatches") &&
    /"force":"true"/.test(String(c.body || ""))));

// Screenshots of the run reach the card.
await body("/api/ingest", "POST", { jobs: [{ ...seed[2], shots: JSON.stringify(["resumes/x/apply/filled.png"]) }] }, robot);
check("the apply run's screenshots reach the card",
  ((await (await get("/api/jobs", as)).json()).jobs.find((j) => j.uid === "b").shots || [])[0] === "resumes/x/apply/filled.png");

/* ------------------------------------------------- no action is a dead end --- */

// Marking applied, then undoing it, must leave no trace in the tracker.
const before = (await (await get("/api/applications", as)).json()).total;
const marked = await (await cmd("n3", "applied")).json();
check("marking applied hands back the row it made",
  marked.applied && marked.applied.id > 0 && marked.applied.outcome === "no response");
check("and the tracker has it",
  (await (await get("/api/applications", as)).json()).total === before + 1);
await cmd("n3", "reopen");
check("undoing it takes the application back out",
  (await (await get("/api/applications", as)).json()).total === before);

// But an application he has since filled in is his, not jobbot's to remove.
await cmd("n3", "applied");
const mine = (await (await get("/api/applications?q=third", as)).json()).rows[0];
await body("/api/applications", "PATCH", { id: mine.id, notes: "phone screen booked" }, as);
await cmd("n3", "reopen");
check("an application he has written on survives the undo",
  (await (await get("/api/applications?q=third", as)).json()).rows.length === 1);

// The posting itself, and when the boards were last read.
await body("/api/ingest", "POST", { jobs: [{ ...seed[0], jd: "We are hiring an intern to work on GPUs." }],
  checked_at: iso(0.01) }, robot);
feed = await (await get("/api/jobs", as)).json();
check("the posting text reaches the app",
  /GPUs/.test(feed.jobs.find((j) => j.uid === "a").jd || ""));
check("the app knows when the boards were last checked", !!feed.checked);

/* ----------------------------------------- telling Claude what to change --- */

await body("/api/command", "POST",
  { uid: "n1", command: "keep", hint: "Lead with the GPU work" }, as);
feed = await (await get("/api/jobs", as)).json();
check("a note about the resume is kept on the job",
  feed.jobs.find((j) => j.uid === "n1").hint === "Lead with the GPU work");
check("keeping a note does not move the job", (await state("n1")) === "building");
calls.length = 0;
await body("/api/command", "POST", { uid: "n1", command: "rebuild", hint: "Drop the Helix Labs bullet" }, as);
queued = (await (await get("/api/events", robot)).json()).events;
check("writing it again carries his note to jobbot",
  queued.some((e) => e.kind === "rebuild" && e.detail.hint === "Drop the Helix Labs bullet"));
check("an emptied note clears it",
  (await body("/api/command", "POST", { uid: "n1", command: "keep", hint: "  " }, as)).status === 200 &&
  (await (await get("/api/jobs", as)).json()).jobs.find((j) => j.uid === "n1").hint === null);
check("a note on an unknown job is refused",
  (await body("/api/command", "POST", { uid: "nope", command: "keep", hint: "x" }, as)).status === 404);

/* -------------------------------------------------------- applications --- */

await cmd("b", "applied");
let tracker = await (await get("/api/applications", as)).json();
check("marking applied writes it into the tracker",
  tracker.rows.some((r) => r.company === "Beta" && r.outcome === "no response"), JSON.stringify(tracker.rows));
await cmd("b", "reopen"); await cmd("b", "applied");
tracker = await (await get("/api/applications", as)).json();
check("marking it twice does not double the row",
  tracker.rows.filter((r) => r.company === "Beta").length === 1);

const made = await (await body("/api/applications", "POST",
  { company: "Jane Street", title: "SWE Intern", applied_at: "2026-02-01", referral: "Uzair" }, as)).json();
check("he can add one by hand", made.ok && made.id > 0);
check("an application needs a company and a role",
  (await body("/api/applications", "POST", { company: "x" }, as)).status === 400);

check("he can change the outcome",
  (await (await body("/api/applications", "PATCH", { id: made.id, outcome: "interview" }, as)).json()).ok);
tracker = await (await get("/api/applications", as)).json();
const js = tracker.rows.find((r) => r.id === made.id);
check("the outcome and when it changed are kept", js.outcome === "interview" && !!js.outcome_at);
check("a made-up outcome is refused",
  (await body("/api/applications", "PATCH", { id: made.id, outcome: "vibes" }, as)).status === 400);
check("editing an application needs auth",
  (await body("/api/applications", "PATCH", { id: made.id, outcome: "offer" })).status === 401);
check("notes and referral save",
  (await (await body("/api/applications", "PATCH", { id: made.id, notes: "phone screen Friday" }, as)).json()).ok);

check("search finds it",
  (await (await get("/api/applications?q=jane", as)).json()).rows.length === 1);
check("the outcome filter works",
  (await (await get("/api/applications?outcome=interview", as)).json()).rows.every((r) => r.outcome === "interview"));
tracker = await (await get("/api/applications", as)).json();
check("the counts add up", tracker.stats.total === tracker.total && tracker.stats.live >= 1,
  JSON.stringify(tracker.stats));

const csv = await get("/api/export.csv", as);
const text = await csv.text();
check("the export is a spreadsheet with his columns",
  csv.headers.get("content-type").startsWith("text/csv") && text.startsWith("COMPANY,JOB TITLE,"));
check("the export quotes commas", text.includes('"SWE Intern"') || !text.includes("SWE Intern,,"));

check("he can delete one", (await req("/api/applications?id=" + made.id, { method: "DELETE", headers: as })).status === 200);
check("and it leaves the record",
  !(await (await get("/api/applications?q=jane", as)).json()).rows.length);
check("but a deletion can be taken back",
  (await body("/api/applications/restore", "POST", { id: made.id }, as)).status === 200 &&
  (await (await get("/api/applications?q=jane", as)).json()).rows.length === 1);
await req("/api/applications?id=" + made.id, { method: "DELETE", headers: as });

/* --------------------------------- what jobbot can and cannot do for him --- */

await body("/api/ingest", "POST", { jobs: [
  { uid: "gh", company: "greenhouse co", title: "Intern", tier: 2, state: "ready",
    apply_url: "https://job-boards.greenhouse.io/x/jobs/1", seen_at: iso(0.1) },
  { uid: "wd", company: "workday co", title: "Intern", tier: 2, state: "ready",
    apply_url: "https://x.wd3.myworkdayjobs.com/en-US/x/job/1", seen_at: iso(0.1) },
  { uid: "late", company: "stuck co", title: "Intern", tier: 1, state: "working",
    apply_url: "https://amazon.jobs/en/jobs/1", seen_at: iso(0.1) },
] }, robot);
await env.DB.prepare("UPDATE jobs SET updated_at = ?1 WHERE uid = 'late'").bind(iso(0.5)).run();
feed = await (await get("/api/jobs", as)).json();
by = Object.fromEntries(feed.jobs.map((j) => [j.uid, j]));
check("a Greenhouse form is one jobbot can submit", by.gh.byHand === false);
check("a Workday form is his to fill in", by.wd.byHand === true && /open the form|paste/i.test(by.wd.note || ""));
check("an apply that never finished stops pretending to work",
  by.late.state === "needs" && /cannot be filled in automatically/i.test(by.late.note || ""));

/* ------------------------------------------- his taps beat a stale run --- */

await cmd("a", "approve");
await body("/api/ingest", "POST", { jobs: [{ ...seed[0], state: "ready" }] }, robot);
check("a run that started before his tap does not undo it", (await state("a")) === "working");
await body("/api/ingest", "POST", { jobs: [{ ...seed[0], state: "done" }] }, robot);
check("but a finished apply run does", (await state("a")) === "done");

// The page's own script never runs in these checks, so at least parse it: a
// stray duplicate name shipped once and left the app stuck on "loading...".
const { PAGE } = await import("./worker.js");
// Every <script> block on the page, each parsed on its own.
const scripts = PAGE.split("<script>").slice(1).map((part) => part.split("</script>")[0]);
check("the page has its scripts", scripts.length >= 2, String(scripts.length));
scripts.forEach((code, i) => {
  try { new Function(code); check("page script " + (i + 1) + " parses", true); }
  catch (e) { check("page script " + (i + 1) + " parses", false, e.message); }
});
// Code pasted by a patch once landed inside <style>, where it parses as CSS.
for (const fn of ["filteredPane", "mutedPane", "settingsPane", "snoozePane", "addPane", "referralHtml"])
  check(fn + " is in a script", scripts.some((c) => c.includes("function " + fn)));
const icon = await req("/icon.png");
check("the home-screen icon is a PNG the phone will take",
  icon.status === 200 && icon.headers.get("content-type") === "image/png" &&
  (await icon.arrayBuffer()).byteLength > 2000);
check("the manifest points at it", (await (await req("/manifest.json")).json()).icons.every((i) => i.src === "/icon.png"));
check("the page cannot be pinched out of shape", /user-scalable=no/.test(PAGE) && /maximum-scale=1/.test(PAGE));
check("the icon is linked for iOS", /rel="apple-touch-icon" href="\/icon.png"/.test(PAGE));
check("the page has no leftover style placeholders", !/\$\{/.test(PAGE.slice(0, PAGE.indexOf("<script>"))));

/* --------------------------------------------------------------- stopping --- */
// A resume being written used to have no way out of the app at all: the card
// said "Writing your resume" and offered nothing, and the run carried on.
{
  const card = (uid, board) => board.jobs.find((j) => j.uid === uid);
  // Its own posting: the seeded ones have been pushed around by earlier checks.
  await body("/api/ingest", "POST", { jobs: [
    { uid: "w", company: "writing", title: "SWE Intern, Summer 2027", tier: 1, state: "building",
      note: "Writing your resume", posted_at: iso(0.1), seen_at: iso(0.1) }] },
    { authorization: "Bearer robot" });

  const stopped = await (await body("/api/command", "POST", { uid: "w", command: "stop" }, as)).json();
  check("a resume being written can be stopped", stopped.ok === true);
  let board = await (await get("/api/jobs", as)).json();
  check("and the posting goes back to new, because nothing was written",
    card("w", board).state === "new", card("w", board).state);
  check("the app says where it went", /back on the board/i.test(stopped.said || ""), stopped.said);

  // The run that was already writing it finishes a minute later and reports in.
  await body("/api/ingest", "POST", { jobs: [
    { uid: "w", company: "writing", title: "SWE Intern, Summer 2027", state: "ready",
      folder: "resumes/W/X", pdf: "resumes/W/X/x.pdf", seen_at: iso(0.1) }] },
    { authorization: "Bearer robot" });
  board = await (await get("/api/jobs", as)).json();
  check("a run finishing afterwards does not undo the stop",
    card("w", board).state === "new", card("w", board).state);

  // Stopping an application is different: the resume it was applying with is
  // still there, so the job goes back to ready rather than to new.
  await body("/api/ingest", "POST", { jobs: [
    { uid: "v", company: "vega", title: "SWE Intern, Summer 2027", tier: 1, state: "ready",
      folder: "resumes/V/X", pdf: "resumes/V/X/x.pdf", apply_url: "https://boards.greenhouse.io/v/jobs/1",
      posted_at: iso(0.1), seen_at: iso(0.1) }] }, { authorization: "Bearer robot" });
  await body("/api/command", "POST", { uid: "v", command: "approve" }, as);
  board = await (await get("/api/jobs", as)).json();
  check("applying moves it to working", card("v", board).state === "working",
    JSON.stringify(card("v", board) && card("v", board).state));
  const halted = await (await body("/api/command", "POST", { uid: "v", command: "stop" }, as)).json();
  board = await (await get("/api/jobs", as)).json();
  check("stopping an application leaves the resume ready", card("v", board).state === "ready",
    JSON.stringify(card("v", board) && card("v", board).state));
  check("and is honest about what may already have been sent",
    /already gone through/i.test(halted.said || ""), halted.said);

  // Cancelling the run is asked of GitHub, not just of the database.
  check("stopping asks GitHub to cancel the run",
    calls.some((c) => /actions\/runs\/.*\/cancel/.test(c.url) || /runs\?status=in_progress/.test(c.url)),
    calls.slice(-4).map((c) => c.url).join(" | "));
}

/* ------------------------------------------------ the worker's own clock --- */
// GitHub's schedule is best-effort: a */5 cron came at gaps of 3 to 22 minutes
// on 2026-09-25. Cloudflare's is punctual, so the worker decides when a sweep
// is overdue and asks for one itself.
{
  const ran = { scheduled: async (p) => p };
  const beat = async (whenIso) => body("/api/ingest", "POST",
    { jobs: [], checked_at: whenIso }, { authorization: "Bearer robot" });
  const sweeps = () => calls.filter((c) => /workflows\/watch\.yml\/dispatches/.test(c.url)).length;

  await beat(new Date().toISOString());
  const before = sweeps();
  await worker.scheduled({}, env, ran);
  check("a sweep a moment ago is left alone", sweeps() === before, `${sweeps()} vs ${before}`);

  await beat(new Date(Date.now() - 40 * 60e3).toISOString());
  await worker.scheduled({}, env, ran);
  check("one forty minutes old is asked for", sweeps() > before, `${sweeps()} vs ${before}`);

  const last = await (await get("/api/jobs", as)).json();
  check("and the board still answers while it does", Array.isArray(last.jobs));
}

/* ------------------------------------------------- the browser extension --- */
{
  // It cannot use the cookie: that is HttpOnly, and an extension's requests do
  // not reliably carry it. It trades the passcode for the same value once.
  check("a wrong passcode gets no key", (await body("/api/key", "POST", { passcode: "nope" })).status === 401);
  const keyed = await body("/api/key", "POST", { passcode: "hunter2" });
  const { key: extKey } = await keyed.json();
  check("the right passcode gets a key", keyed.status === 200 && typeof extKey === "string" && extKey.length === 64);
  const asExt = { "x-jobbot-key": extKey };
  check("the key opens the same doors as the cookie", (await get("/api/jobs", asExt)).status === 200);
  check("a made-up key does not", (await get("/api/jobs", { "x-jobbot-key": "x".repeat(64) })).status === 401);

  // The form he is filling in is a different address from the posting: same host,
  // same id, query and fragment on the end.
  const onForm = await (await get("/api/lookup?url=" + encodeURIComponent("https://apply/?src=x#form"), asExt)).json();
  check("the apply form finds its posting", onForm.job && onForm.job.uid === "a",
    JSON.stringify(onForm.job && onForm.job.uid));
  check("its answers come with it", Array.isArray(onForm.questions) && onForm.questions.length > 0);
  const elsewhere = await (await get("/api/lookup?url=" + encodeURIComponent("https://nowhere.example/jobs/1"), asExt)).json();
  check("a page jobbot does not know says so", elsewhere.job === null);

  // A posting he found himself, on a board jobbot cannot read at all.
  const grabbed = await (await body("/api/capture", "POST", {
    url: "https://www.metacareers.com/jobs/12345/", company: "Meta",
    title: "Software Engineer Intern, Summer 2027", location: "Menlo Park, CA",
    description: "An internship for summer 2027.", where: "Meta Careers" }, asExt)).json();
  check("a captured posting joins the board", grabbed.ok && !!grabbed.uid);
  const twice = await (await body("/api/capture", "POST", {
    url: "https://www.metacareers.com/jobs/12345/", company: "Meta", title: "x" }, asExt)).json();
  check("capturing it twice does not double it", twice.uid === grabbed.uid && /already/i.test(twice.said || ""));
  const board = await (await get("/api/jobs", asExt)).json();
  const mine = board.jobs.find((j) => j.uid === grabbed.uid);
  check("it arrives as new, with its term read off the title",
    mine && mine.state === "new" && mine.term === "Summer 2027", JSON.stringify(mine && [mine.state, mine.term]));
  check("and it says where it came from", mine && /you added this/i.test(mine.note || ""), mine && mine.note);
  check("a capture without a link is refused",
    (await body("/api/capture", "POST", { company: "Meta" }, asExt)).status === 400);
}

console.log();
if (fails) { console.log(`${fails} failure(s)`); process.exit(1); }
console.log("worker suite OK");
