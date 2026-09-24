/**
 * jobbot - one Cloudflare Worker, free tier, no server.
 *
 * This is the whole system's front door: new postings arrive here, resumes and
 * prepared answers are read here, applying starts here, and every application
 * he has ever sent lives here. There is no email digest and no spreadsheet to
 * keep in step - the app is the tracker.
 *
 * State lives in D1 (binding DB):
 *   jobs          one row per posting, with the state he sees on the card
 *   applications  everything he has applied to, editable, his real record
 *   events        what he did in the app; jobbot pulls these and catches up
 *
 * The resume PDFs, previews and prepared answers stay in the repo and are
 * proxied through /file and /api/answers, so nothing large is stored here.
 *
 * Secrets (npx wrangler secret put NAME - never in this file):
 *   GH_TOKEN       fine-grained PAT for this repo: Contents read/write, Issues write
 *   APP_PASSCODE   what you type to open the app
 *   INGEST_TOKEN   what GitHub Actions uses to report in (/api/ingest, /api/events)
 */

import { PAGE } from "./page.js";

export { PAGE };

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };
const TYPES = { png: "image/png", pdf: "application/pdf", json: "application/json", txt: "text/plain" };

export default {
  async fetch(request, env, ctx) {
    // Work that can finish after the answer has been sent.
    const later = (p) => { if (ctx && ctx.waitUntil) ctx.waitUntil(p.catch(() => {})); return p; };
    env = { ...env, later };
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (path === "/api/login") return login(request, env);
      if (path === "/api/key") return issueKey(request, env);
      if (path === "/manifest.json") return json(MANIFEST);
      if (path === "/icon.png")
        return new Response(Uint8Array.from(atob(ICON_PNG), (c) => c.charCodeAt(0)),
          { headers: { "content-type": "image/png", "cache-control": "public, max-age=86400" } });
      if (path === "/" || path === "/index.html") return html(PAGE);
      // The service worker must be served from the root to cover the whole app.
      if (path === "/sw.js") return new Response(SW, { headers: { "content-type": "application/javascript",
                                                                  "cache-control": "no-cache" } });

      // jobbot reads his settings at the start of every run.
      if (path === "/api/settings" && machine(request, env)) return settingsRaw(env);

      // GitHub Actions reporting in - a token, not the passcode.
      if (path === "/api/ingest" || path.startsWith("/api/events")) {
        if (!machine(request, env)) return json({ error: "no" }, 401);
        if (path === "/api/ingest") return ingest(request, env);
        if (path === "/api/events") return listEvents(env);
        if (path === "/api/events/ack") return ackEvents(request, env);
      }

      if (!(await authed(request, env))) return json({ error: "locked" }, 401);
      if (path === "/api/lookup") return lookup(env, url.searchParams.get("url"));
      if (path === "/api/capture") return capture(request, env);
      if (path === "/api/me") return profileNow(env).then((m) =>
        json(m ? { ...m.contact, ...m.education } : {}));
      if (path === "/api/jobs") return jobs(env, url);
      if (path === "/api/applications") return applications(request, env, url);
      if (path === "/api/applications/restore") return restoreApplication(request, env);
      if (path === "/api/export.csv") return exportCsv(env);
      if (path === "/api/answers") return answers(env, url.searchParams.get("folder"));
      if (path === "/file") return file(env, url.searchParams.get("path"), url.searchParams.get("save"));
      if (path === "/api/command") return command(request, env);
      if (path === "/api/filtered") return filteredList(env);
      if (path === "/api/answer") return editAnswer(request, env);
      if (path === "/api/settings") return request.method === "POST" ? saveSetting(request, env) : settingsView(env);
      if (path === "/api/suggestions") return request.method === "POST" ? actOnSuggestion(request, env) : suggestions(env);
      if (path === "/api/usage") return request.method === "POST" ? countUsage(request, env) : usageView(env);
      if (path === "/api/push") return pushRoute(request, env, url);
      if (path === "/api/check") return checkNow(env);
      return json({ error: "not found" }, 404);
    } catch (err) {
      return json({ error: String((err && err.message) || err) }, 500);
    }
  },

  // Every half hour, whether jobbot is alive. On 2026-09-23 it was dead for
  // seven hours and nothing said so; now his phone does.
  async scheduled(event, env, ctx) {
    const later = (p) => { if (ctx && ctx.waitUntil) ctx.waitUntil(p.catch(() => {})); return p; };
    await health({ ...env, later });
  },
};

// Alive means: the last sweep succeeded, and one has run in the last two hours.
async function health(env) {
  const on = await wants(env).catch(() => ({ problems: true }));
  const [beat, was] = await Promise.all([
    one(env, `SELECT value FROM meta WHERE key = 'checked'`),
    one(env, `SELECT value FROM meta WHERE key = 'health'`),
  ]);
  const runs = await askGitHub(env).catch(() => []);
  const broken = runs.find((r) => r.kind === "broken");
  const since = beat ? Date.now() - new Date(beat.value).getTime() : null;
  const state = broken ? "failed" : since !== null && since > 2 * 3600e3 ? "stale" : "ok";
  const said = state === "failed" ? "jobbot's last check failed. Nothing new is coming in."
    : state === "stale" ? "jobbot has not checked the boards in over two hours."
    : "";
  if ((was && was.value) === state) return state;          // already said, or still fine
  await run(env, `INSERT INTO meta (key, value, at) VALUES ('health', ?1, ?2)
                  ON CONFLICT(key) DO UPDATE SET value = excluded.value, at = excluded.at`, state, now());
  if (state === "ok") return state;
  await run(env, `INSERT INTO meta (key, value, at) VALUES ('health_said', ?1, ?2)
                  ON CONFLICT(key) DO UPDATE SET value = excluded.value, at = excluded.at`, said, now());
  if (on.problems !== false) await wake(env);
  return state;
}

/* ---------------------------------------------------------------- auth --- */

const COOKIE = "jobbot_ok";

async function token(env) {
  const bytes = new TextEncoder().encode(`jobbot:${env.APP_PASSCODE}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function authed(request, env) {
  const want = await token(env);
  const key = request.headers.get("x-jobbot-key");
  if (key && key === want) return true;              // the browser extension
  const cookie = request.headers.get("cookie") || "";
  const found = cookie.split(";").map((c) => c.trim()).find((c) => c.startsWith(`${COOKIE}=`));
  return !!found && found.slice(COOKIE.length + 1) === want;
}

// The extension asks for the key once, with the passcode, and keeps it.
async function issueKey(request, env) {
  const { passcode } = await request.json().catch(() => ({}));
  if (!env.APP_PASSCODE || passcode !== env.APP_PASSCODE) return json({ ok: false }, 401);
  return json({ ok: true, key: await token(env) });
}

async function login(request, env) {
  const { passcode } = await request.json().catch(() => ({}));
  if (!env.APP_PASSCODE || passcode !== env.APP_PASSCODE) return json({ ok: false }, 401);
  return new Response(JSON.stringify({ ok: true }), {
    headers: {
      ...JSON_HEADERS,
      "set-cookie": `${COOKIE}=${await token(env)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=31536000`,
    },
  });
}

function machine(request, env) {
  const auth = request.headers.get("authorization") || "";
  return !!env.INGEST_TOKEN && auth === `Bearer ${env.INGEST_TOKEN}`;
}

/* ------------------------------------------------------------------ db --- */

const all = (env, sql, ...args) => env.DB.prepare(sql).bind(...args).all().then((r) => r.results || []);
const one = (env, sql, ...args) => env.DB.prepare(sql).bind(...args).first();
const run = (env, sql, ...args) => env.DB.prepare(sql).bind(...args).run();
const now = () => new Date().toISOString();

/* ---------------------------------------------------------------- jobs --- */

// What he sees, in the order he should deal with it.
const RANK = { needs: 0, new: 1, ready: 2, working: 3, building: 4, done: 5, skipped: 6 };
// jobbot can fill and submit these three. Everywhere else he finishes the form
// himself, so the card must not offer to do it for him.
// Ashby flags scripted submits as spam (Fable, 2026-09-21), so it is his to send.
const AUTOFILL = /greenhouse|lever/i;
// An apply run takes a few minutes. Much longer than that and it is not coming
// back - a workflow failed, or the site refused it - and he should be told.
const STUCK_MINUTES = 45;

// What jobbot is doing right this second, so the app can say so rather than
// looking asleep. Asked of GitHub at most once every 15 seconds, and a failure
// is simply "nothing running" - never an error in his face.
const RUN_SAYS = { watch: "Checking the boards", resume: "Writing resumes", approve: "Filling in an application" };

async function running(env) {
  const cached = await one(env, `SELECT value, at FROM meta WHERE key = 'runs'`);
  const fresh = cached && Date.now() - new Date(cached.at).getTime() < 15e3;
  // Never make him wait on GitHub for this: serve what is known and refresh
  // behind the reply.
  if (cached && !fresh && env.later) { env.later(askGitHub(env)); return JSON.parse(cached.value); }
  if (fresh) return JSON.parse(cached.value);
  return askGitHub(env);
}

async function askGitHub(env) {
  // What is running now, and whether the last sweep failed - a run that never
  // starts (no minutes left, a broken workflow) must not look like silence.
  const [live, last] = await Promise.all([
    gh(env, `/repos/${codeRepo(env)}/actions/runs?status=in_progress&per_page=20`).catch(() => null),
    gh(env, `/repos/${codeRepo(env)}/actions/workflows/watch.yml/runs?per_page=1`).catch(() => null),
  ]);
  let out = [];
  if (live && live.ok) {
    const body = await live.json().catch(() => ({}));
    const seen = new Map();
    for (const one_run of body.workflow_runs || []) {
      const kind = String(one_run.path || "").split("/").pop().replace(".yml", "");
      if (!RUN_SAYS[kind]) continue;
      const have = seen.get(kind);
      seen.set(kind, { kind, says: RUN_SAYS[kind], since: have ? have.since : one_run.run_started_at,
                       n: (have ? have.n : 0) + 1 });
    }
    out = [...seen.values()];
  }
  if (!out.length && last && last.ok) {
    const body = await last.json().catch(() => ({}));
    const r0 = (body.workflow_runs || [])[0];
    if (r0 && r0.conclusion && r0.conclusion !== "success")
      out.push({ kind: "broken", says: "The last check failed", at: r0.created_at, url: r0.html_url });
  }
  await run(env, `INSERT INTO meta (key, value, at) VALUES ('runs', ?1, ?2)
                  ON CONFLICT(key) DO UPDATE SET value = excluded.value, at = excluded.at`,
    JSON.stringify(out), now());
  return out;
}

async function profileNow(env) {
  const row = await one(env, `SELECT base, value, value_base FROM settings WHERE key = 'profile'`);
  if (!row || !row.base) return null;
  return row.value ? merge3(parse(row.base), parse(row.value_base), parse(row.value)) : parse(row.base);
}

// Every tool named in his skills rows or attached to something he built.
function knownTech(profile) {
  const out = new Set();
  for (const row of Object.values(profile.skills || {}))
    for (const word of String(row).split(/[,;/]| and /))
      if (word.trim().length > 1) out.add(word.trim().toLowerCase());
  for (const entry of profile.entries || [])
    for (const fact of entry.facts || [])
      for (const t of fact.tech || []) if (String(t).trim()) out.add(String(t).trim().toLowerCase());
  return [...out].slice(0, 120);
}

async function wantedTerms(env) {
  const row = await one(env, `SELECT base, value, value_base FROM settings WHERE key = 'search'`);
  if (!row || !row.base) return [];
  const search = row.value ? merge3(parse(row.base), parse(row.value_base), parse(row.value)) : parse(row.base);
  return Object.entries(search.seasons || {}).filter(([, on]) => on).map(([k]) => k);
}

async function jobs(env, url) {
  const wantSkipped = url.searchParams.get("skipped") === "1";
  const wantSnoozed = url.searchParams.get("snoozed") === "1";
  const [rows, muted, follows] = await Promise.all([
    all(env, `SELECT * FROM jobs WHERE state != 'skipped' OR ?1 = 1 ORDER BY seen_at DESC`,
        wantSkipped ? 1 : 0),
    all(env, `SELECT company FROM muted`),
    all(env, `SELECT key, name FROM following ORDER BY name`),
  ]);
  const quiet = new Set(muted.map((m) => m.company));
  const cutoff = new Date(Date.now() - 7 * 864e5).toISOString();
  const stale = new Date(Date.now() - STUCK_MINUTES * 60e3).toISOString();
  const nowIso = now();
  let snoozed = 0;
  const out = [];
  for (const r of rows) {
    // "Applied" is a short list of what just happened, not a history: the whole
    // history is the Applications tab.
    if (r.state === "done" && (r.updated_at || r.seen_at || "") < cutoff) continue;
    // A company he muted only disappears while nothing is happening with it:
    // a resume he asked for still comes back.
    if (quiet.has(key(r.company)) && (r.state === "new" || r.state === "skipped")) continue;
    const naps = r.snoozed_until && r.snoozed_until > nowIso;
    if (naps && !wantSnoozed) { snoozed++; continue; }
    let state = r.state, note = r.note;
    const byHand = !AUTOFILL.test(`${r.source || ""} ${r.apply_url || ""} ${r.url || ""}`);
    if (state === "working" && (r.updated_at || "") < stale) {
      state = "needs";
      note = byHand
        ? "This site cannot be filled in automatically - open the form and finish it"
        : "The apply run did not finish - open the form and finish it, or try again";
    } else if (state === "ready" && byHand) {
      note = note || "You finish this one: open the form, the answers below are ready to paste";
    }
    out.push({
      byHand,
      uid: r.uid, state, note, company: pretty(r.company), title: r.title,
      tier: r.tier, term: r.term || termOf(r.title, r.jd), location: r.location, where: shortLocation(r.location),
      since: r.updated_at,
      posted_at: r.posted_at, deadline: r.deadline, url: r.url, apply_url: r.apply_url,
      issue: r.issue, folder: r.folder, pdf: r.pdf, preview: r.preview, knockout: !!r.knockout,
      hint: r.hint, jd: r.jd, says: r.says, snoozed_until: r.snoozed_until, referred_at: r.referred_at,
      shots: r.shots ? JSON.parse(r.shots) : [],
    });
  }
  collapse(out);
  out.sort((a, b) => (RANK[a.state] - RANK[b.state]) || ((a.tier || 9) - (b.tier || 9))
    || String(b.posted_at || "").localeCompare(String(a.posted_at || "")));
  const counts = {};
  for (const j of out) counts[j.state] = (counts[j.state] || 0) + 1;
  const beat = await one(env, `SELECT value FROM meta WHERE key = 'checked'`);
  // When anything was last posted anywhere, so a quiet night reads as a quiet
  // night rather than as jobbot being asleep.
  const newest = await one(env, `SELECT MAX(posted_at) at FROM jobs WHERE state != 'skipped'`);
  const held = await one(env, `SELECT COUNT(*) n FROM filtered WHERE uid NOT IN (SELECT uid FROM jobs)`);
  // Whose resumes these are, for the file names. It comes from his settings, so
  // the code carries no name of its own.
  const who = await one(env, `SELECT base, value, value_base FROM settings WHERE key = 'profile'`);
  const mine = who && who.base
    ? (who.value ? merge3(parse(who.base), parse(who.value_base), parse(who.value)) : parse(who.base))
    : null;
  const busy = await running(env).catch(() => []);
  return json({ jobs: out, counts, snoozed, muted: muted.map((m) => m.company), following: follows,
                filtered: held ? held.n : 0, running: busy,
                owner: (mine && mine.contact && mine.contact.name) || null,
                // His school and his LinkedIn, so the app can point him at the
                // people who could refer him.
                me: mine ? { name: (mine.contact || {}).name || "", school: (mine.education || {}).school || "",
                             major: (mine.education || {}).major || "",
                             linkedin: (mine.contact || {}).linkedin || "" } : null,
                // The tools he has actually used, so the app can say which of
                // them a posting asks for.
                knows: mine ? knownTech(mine) : [],
                // The terms he wants, so a posting for one he does not can be
                // ranked below the rest rather than sitting at the top.
                terms: await wantedTerms(env),
                checked: beat ? beat.value : null, newest: newest ? newest.at : null, at: now() });
}

// Boards list the same role once per city; he should see one card.
// The terms a posting is for, when jobbot did not record one: the same rule as
// jobbot/seed_store.py term_of. "January 2027" is Winter 2027.
const SEASON_OF = ["Winter", "Winter", "Winter", "Winter", "Summer", "Summer", "Summer", "Summer",
                   "Fall", "Fall", "Fall", "Fall"];
const MONTH_AT = "jan feb mar apr may jun jul aug sep oct nov dec".split(" ");
function termOf(...texts) {
  const re = /\b(?:(summer|winter|fall|autumn|spring)\s*'?\s*(20\d\d|\d\d)\b|(20\d\d)\s+(summer|winter|fall|autumn|spring)\b|(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?,?\s+(20\d\d)\b)/gi;
  for (const t of texts) {
    const found = [];
    const text = String(t || "").slice(0, 6000);
    for (const m of text.matchAll(re)) {
      // A date after these words is when the student graduates, not the term.
      if (/graduat|degree|class of|complet|enrolled|pursuing|expected|returning to|remaining/i
          .test(text.slice(Math.max(0, m.index - 90), m.index))) continue;
      let season, year;
      if (m[1]) { season = m[1]; year = m[2]; }
      else if (m[3]) { season = m[4]; year = m[3]; }
      else { season = SEASON_OF[MONTH_AT.indexOf(m[5].slice(0, 3).toLowerCase())]; year = m[6]; }
      season = season.toLowerCase() === "autumn" ? "Fall" : season[0].toUpperCase() + season.slice(1).toLowerCase();
      year = year.length === 4 ? year : "20" + year;
      if (+year < 2025 || +year > 2029) continue;
      const name = season + " " + year;
      if (!found.includes(name)) found.push(name);
    }
    if (found.length) return found.slice(0, 3).join(" / ");
  }
  return null;
}

function collapse(out) {
  const seen = new Map();
  for (const j of out) {
    const key = `${j.company}|${(j.title || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()}`;
    const first = seen.get(key);
    if (!first) { j.also = 0; seen.set(key, j); continue; }
    first.also = (first.also || 0) + 1;
    if ((RANK[j.state] ?? 9) < (RANK[first.state] ?? 9)) { j.also = first.also; seen.set(key, j); }
  }
  out.length = 0;
  out.push(...seen.values());
}

// Board slugs arrive as "doordashusa" or "Together Ai"; these are the names he
// reads on a card.
const WORDS = { ai: "AI", usa: "USA", us: "US", uk: "UK", ml: "ML", hq: "HQ", io: "io", tv: "TV",
                bmo: "BMO", rbc: "RBC", td: "TD", cibc: "CIBC", amd: "AMD", asml: "ASML", adp: "ADP",
                cae: "CAE", ea: "EA", hp: "HP", ge: "GE", ups: "UPS", kpmg: "KPMG", pwc: "PwC",
                nvidia: "NVIDIA", ibm: "IBM", sap: "SAP", aws: "AWS", occ: "OCC", npx: "NPX",
                doordash: "DoorDash", github: "GitHub", gitlab: "GitLab", openai: "OpenAI",
                scaleai: "Scale AI", hmhw: "HMH", theocc: "The OCC", intactfc: "Intact",
                youtube: "YouTube", tiktok: "TikTok", paypal: "PayPal", ebay: "eBay",
                linkedin: "LinkedIn", snapchat: "Snapchat", shopify: "Shopify",
                hashicorp: "HashiCorp", pagerduty: "PagerDuty", mongodb: "MongoDB", "1password": "1Password",
                xai: "xAI", anysphere: "Anysphere", janestreet: "Jane Street", twosigma: "Two Sigma" };

// Muting is by company, and a board's spelling of a name wanders.
const key = (name) => String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "");

export { pretty, shortLocation };

function pretty(name) {
  const raw = String(name || "").trim();
  if (!raw) return "";
  const whole = WORDS[raw.toLowerCase().replace(/[^a-z0-9]/g, "")];
  if (whole) return whole;
  return raw.split(/[\s_-]+/).map((w) => {
    const k = w.toLowerCase();
    if (WORDS[k]) return WORDS[k];
    if (/^[A-Z]{2,}$/.test(w)) return w;                      // already an acronym
    return w.charAt(0).toUpperCase() + w.slice(1);
  }).join(" ");
}

function shortLocation(loc) {
  const parts = String(loc || "").split(/;|•/).map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return "";
  const first = parts[0].replace(/,\s*(United States|USA|US|Canada|CAN)$/i, "");
  return parts.length > 1 ? `${first} +${parts.length - 1}` : first;
}

/* -------------------------------------------------------- applications --- */

const OUTCOMES = ["no response", "OA", "interview", "offer", "accepted", "rejected", "withdrawn"];
const LIVE = ["no response", "OA", "interview", "offer"];    // still in play
const FIELDS = ["company", "title", "applied_at", "outcome", "referral", "notes", "apply_url"];

async function applications(request, env, url) {
  if (request.method === "POST") return addApplication(request, env);
  if (request.method === "PATCH") return editApplication(request, env);
  if (request.method === "DELETE") return dropApplication(env, url);

  const q = (url.searchParams.get("q") || "").trim();
  const outcome = url.searchParams.get("outcome") || "";
  const limit = Math.min(Number(url.searchParams.get("limit")) || 60, 200);
  const offset = Number(url.searchParams.get("offset")) || 0;
  const like = `%${q.replace(/[%_]/g, " ")}%`;
  const where = `WHERE deleted_at IS NULL AND (?1 = '' OR company LIKE ?2 OR title LIKE ?2)
                 AND (?3 = '' OR outcome = ?3)`;
  const rows = await all(env,
    `SELECT a.*, j.folder, j.preview, j.jd, j.location FROM applications a
     LEFT JOIN jobs j ON j.uid = a.uid ${where.replace(/\b(deleted_at|company|title|outcome)\b/g, "a.$1")}
     ORDER BY a.applied_at DESC, a.id DESC LIMIT ?4 OFFSET ?5`,
    q, like, outcome, limit, offset);
  const total = await one(env, `SELECT COUNT(*) n FROM applications ${where}`, q, like, outcome);
  const byOutcome = await all(env,
    `SELECT outcome, COUNT(*) n FROM applications WHERE deleted_at IS NULL GROUP BY outcome`);
  const stats = { total: 0, live: 0 };
  for (const r of byOutcome) {
    stats[r.outcome] = r.n;
    stats.total += r.n;
    if (LIVE.includes(r.outcome)) stats.live += r.n;
  }
  return json({
    rows: rows.map((r) => ({ ...r, company: pretty(r.company) })),
    total: total ? total.n : 0, stats, outcomes: OUTCOMES,
  });
}

async function addApplication(request, env) {
  const b = await request.json().catch(() => ({}));
  if (!b.company || !b.title) return json({ error: "company and title required" }, 400);
  const at = now();
  const r = await run(env,
    `INSERT INTO applications (uid, company, title, applied_at, outcome, referral, notes, apply_url, how, updated_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'by hand', ?9)`,
    b.uid || null, b.company, b.title, (b.applied_at || at).slice(0, 10),
    OUTCOMES.includes(b.outcome) ? b.outcome : "no response",
    b.referral || null, b.notes || null, b.apply_url || null, at);
  return json({ ok: true, id: r.meta ? r.meta.last_row_id : null });
}

async function editApplication(request, env) {
  const b = await request.json().catch(() => ({}));
  if (!b.id) return json({ error: "id required" }, 400);
  const sets = [], args = [];
  for (const f of FIELDS) {
    if (!(f in b)) continue;
    if (f === "outcome" && !OUTCOMES.includes(b[f])) return json({ error: "unknown outcome" }, 400);
    sets.push(`${f} = ?${args.length + 1}`);
    args.push(b[f] === "" ? null : b[f]);
  }
  if (!sets.length) return json({ error: "nothing to change" }, 400);
  // When the outcome changes, remember when - that is the date he will want.
  if ("outcome" in b) { sets.push(`outcome_at = ?${args.length + 1}`); args.push(now().slice(0, 10)); }
  sets.push(`updated_at = ?${args.length + 1}`); args.push(now());
  args.push(b.id);
  const r = await run(env, `UPDATE applications SET ${sets.join(", ")} WHERE id = ?${args.length}`, ...args);
  return (r.meta ? r.meta.changes : 1) ? json({ ok: true }) : json({ error: "not found" }, 404);
}

async function dropApplication(env, url) {
  const id = Number(url.searchParams.get("id"));
  if (!id) return json({ error: "id required" }, 400);
  // Set aside rather than destroyed, so "Undo" in the toast means something.
  // Anything set aside for a month is gone for good.
  await run(env, `UPDATE applications SET deleted_at = ?1 WHERE id = ?2`, now(), id);
  await run(env, `DELETE FROM applications WHERE deleted_at IS NOT NULL AND deleted_at < ?1`,
    new Date(Date.now() - 30 * 864e5).toISOString());
  return json({ ok: true, id });
}

async function restoreApplication(request, env) {
  const b = await request.json().catch(() => ({}));
  if (!b.id) return json({ error: "id required" }, 400);
  const r = await run(env, `UPDATE applications SET deleted_at = NULL, updated_at = ?1 WHERE id = ?2`,
    now(), b.id);
  return (r.meta ? r.meta.changes : 1) ? json({ ok: true }) : json({ error: "not found" }, 404);
}

// The spreadsheet becomes an export: the same columns, so it still opens in Excel.
async function exportCsv(env) {
  const rows = await all(env,
    `SELECT company, title, applied_at, referral, outcome, notes FROM applications
     ORDER BY applied_at DESC, id DESC`);
  const cell = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const body = ["COMPANY,JOB TITLE,Application Date,Referral,Response,Notes",
    ...rows.map((r) => [r.company, r.title, r.applied_at, r.referral, r.outcome, r.notes].map(cell).join(",")),
  ].join("\n");
  return new Response(body, { headers: {
    "content-type": "text/csv; charset=utf-8",
    "content-disposition": `attachment; filename="applications-${now().slice(0, 10)}.csv"`,
  } });
}

/* ------------------------------------------------------------- actions --- */

// What each button does to the card, and what jobbot is told afterwards.
const COMMANDS = {
  approve: { state: "working", note: "Applying", said: "Applying - watch this job" },
  retry: { state: "working", note: "Trying again", said: "Trying the form again" },
  applied: { state: "done", note: "You applied", said: "Recorded as applied" },
  rebuild: { state: "building", note: "Writing the resume again", said: "Rebuilding the resume" },
  stop: { state: "ready", note: null, said: "Stopped" },
  archive: { state: "skipped", note: "Archived", said: "Archived" },
  skip: { state: "skipped", note: "Archived", said: "Archived" },     // the issue comment still says /skip
  reopen: { state: "new", note: null, said: "Back in the list" },
  // Nothing is written until he asks. Both of these ask; only one goes on to
  // apply once the resume exists.
  build: { state: "building", note: "Writing your resume", said: "Writing your resume - this takes a few minutes" },
  draft: { state: "building", note: "Writing your resume", said: "Writing it - you will apply yourself" },
};
const ASKS = { build: true, draft: false };

async function command(request, env) {
  const b = await request.json().catch(() => ({}));

  // Quiet a whole company, rather than archiving its postings one at a time.
  // The companies he follows are his list to edit. jobbot is told, and writes
  // the change into targets.txt so the next sweep ranks them first.
  if (b.command === "follow" || b.command === "unfollow") {
    const name = String(b.company || "").trim().slice(0, 80);
    const k = key(name);
    if (!k) return json({ error: "company required" }, 400);
    if (b.command === "follow") {
      await run(env, `INSERT INTO following (key, name, at) VALUES (?1, ?2, ?3)
                      ON CONFLICT(key) DO UPDATE SET name = excluded.name`, k, name, now());
    } else {
      await run(env, `DELETE FROM following WHERE key = ?1`, k);
    }
    await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (NULL, ?1, ?2, ?3)`,
      now(), b.command, JSON.stringify({ company: name, key: k }));
    return json({ ok: true, said: (b.command === "follow" ? "Following " : "Stopped following ") + name });
  }

  if (b.command === "mute" || b.command === "unmute") {
    const name = key(b.company);
    if (!name) return json({ error: "company required" }, 400);
    if (b.command === "mute") {
      await run(env, `INSERT INTO muted (company, at) VALUES (?1, ?2)
                      ON CONFLICT(company) DO UPDATE SET at = excluded.at`, name, now());
      await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (NULL, ?1, 'mute', ?2)`,
        now(), JSON.stringify({ company: b.company }));
      return json({ ok: true, said: pretty(b.company) + " muted" });
    }
    await run(env, `DELETE FROM muted WHERE company = ?1`, name);
    await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (NULL, ?1, 'unmute', ?2)`,
      now(), JSON.stringify({ company: b.company }));
    return json({ ok: true, said: pretty(b.company) + " is back" });
  }

  // Not now, but not never.
  if (b.command === "snooze" || b.command === "wake") {
    if (!b.uid) return json({ error: "uid required" }, 400);
    const until = b.command === "snooze" ? String(b.until || "").slice(0, 40) : null;
    if (b.command === "snooze" && !until) return json({ error: "until required" }, 400);
    const r = await run(env, `UPDATE jobs SET snoozed_until = ?1, updated_at = ?2 WHERE uid = ?3`,
      until, now(), b.uid);
    if (!(r.meta ? r.meta.changes : 1)) return json({ error: "no such job" }, 404);
    return json({ ok: true, said: until ? "Back later" : "Back on the board" });
  }

  // A posting the rules turned away, which he wants after all. It joins the
  // feed now; jobbot is told, and keeps it from then on.
  if (b.command === "restore") {
    const f = b.uid && await one(env, `SELECT * FROM filtered WHERE uid = ?1`, b.uid);
    if (!f) return json({ error: "no such posting" }, 404);
    const p = f.data ? JSON.parse(f.data) : {};
    const at = now();
    await run(env, `INSERT OR IGNORE INTO jobs (uid, company, title, tier, location, source, org, raw_id, url,
                    apply_url, posted_at, deadline, state, note, knockout, seen_at, jd, updated_at)
                    VALUES (?1, ?2, ?3, 3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, 'new', 'Added from Filtered out', 0, ?12, ?13, ?12)`,
      f.uid, f.company, f.title, f.location, p.source || null, p.org || null, p.raw_id || null,
      f.url, f.apply_url, f.posted_at, p.deadline || null, at, p.description || null);
    await run(env, `DELETE FROM filtered WHERE uid = ?1`, f.uid);
    await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (?1, ?2, 'restore', ?3)`,
      f.uid, at, JSON.stringify({ posting: { ...p, uid: f.uid, company: f.company, title: f.title } }));
    return json({ ok: true, said: "Added to your jobs", uid: f.uid });
  }

  // He asked someone at the company, or he changed his mind about having done.
  // Nothing else about the job moves: this is a fact about him, not a state.
  if (b.command === "referred") {
    if (!b.uid) return json({ error: "uid required" }, 400);
    const when = b.off ? null : now();
    const r = await run(env, `UPDATE jobs SET referred_at = ?1, updated_at = ?2 WHERE uid = ?3`,
      when, now(), b.uid);
    if (!(r.meta ? r.meta.changes : 1)) return json({ error: "no such job" }, 404);
    return json({ ok: true, said: when ? "Noted - you asked for a referral" : "Cleared", referred_at: when });
  }

  // "keep" only stores what he wants said differently; nothing else moves.
  if (b.command === "keep") {
    if (!b.uid) return json({ error: "uid required" }, 400);
    const text = typeof b.hint === "string" ? b.hint.trim().slice(0, 2000) : "";
    const r = await run(env, `UPDATE jobs SET hint = ?1, updated_at = ?2 WHERE uid = ?3`,
      text || null, now(), b.uid);
    return (r.meta ? r.meta.changes : 1) ? json({ ok: true, said: "Saved" }) : json({ error: "no such job" }, 404);
  }
  const c = COMMANDS[b.command];
  if (!c) return json({ error: "unknown command" }, 400);
  // Archiving a pile of look-alike postings should take one tap, not ten.
  const ids = Array.isArray(b.uids) ? b.uids.filter(Boolean) : (b.uid ? [b.uid] : []);
  if (!ids.length && !b.issue) return json({ error: "uid and a known command required" }, 400);
  const jobs = ids.length
    ? (await all(env, `SELECT * FROM jobs WHERE uid IN (${ids.map((_, i) => `?${i + 1}`).join(",")})`, ...ids))
    : [await one(env, `SELECT * FROM jobs WHERE issue = ?1`, b.issue)].filter(Boolean);
  if (!jobs.length) return json({ error: "no such job" }, 404);

  // What he wants said differently, in his own words, kept on the job and sent
  // along with the request so the model writing the resume reads it.
  const hint = typeof b.hint === "string" ? b.hint.trim().slice(0, 2000) : null;
  if (hint !== null && jobs.length === 1) {
    await run(env, `UPDATE jobs SET hint = ?1 WHERE uid = ?2`, hint || null, jobs[0].uid);
    jobs[0].hint = hint;
  }

  let ok = true, applied = null;
  for (const job of jobs) {
    // Reopening a job he archived: back to wherever it actually got to.
    const state = b.command === "reopen" && job.folder ? "ready" : c.state;
    await run(env, `UPDATE jobs SET state = ?1, note = ?2, updated_at = ?3 WHERE uid = ?4`,
      state, c.note, now(), job.uid);
    await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (?1, ?2, ?3, ?4)`,
      job.uid, now(), b.command in ASKS ? "build" : b.command,
      JSON.stringify({ issue: job.issue || null, company: job.company, title: job.title,
                       apply_url: job.apply_url, pdf: job.pdf,
                       ...(b.command in ASKS ? { apply: ASKS[b.command] } : {}),
                       ...(job.hint ? { hint: job.hint } : {}) }));
    if (b.command === "applied") applied = await recordApplied(env, job, "by hand");
    if (b.command === "archive" && REASONS.includes(b.reason)) {
      await run(env, `INSERT INTO feedback (uid, company, title, location, reason, at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
                      ON CONFLICT(uid) DO UPDATE SET reason = excluded.reason, at = excluded.at`,
        job.uid, job.company, job.title, job.location, b.reason, now());
    }
    if (b.command === "reopen") await run(env, `DELETE FROM feedback WHERE uid = ?1`, job.uid);
    // Undoing "I applied" has to take the application back out, or the tracker
    // keeps a row for something he never sent. Anything he has since edited -
    // an outcome, a note - is his, and stays.
    if (b.command === "reopen") {
      await run(env, `DELETE FROM applications WHERE uid = ?1 AND outcome = 'no response'
                      AND referral IS NULL AND notes IS NULL`, job.uid);
    }
    if (job.issue) {
      const note = gh(env, `/repos/${env.REPO}/issues/${job.issue}/comments`,
        { method: "POST", body: JSON.stringify({ body: `/${b.command === "archive" ? "skip" : b.command}` }) });
      if (env.later) env.later(note); else ok = ok && (await note).ok;
    }
  }
  // Asking for a resume should start one now, not at the next poll. If the
  // app's token may not start workflows, the next watch run picks it up.
  // If the app is not allowed to start a run, say so instead of leaving him
  // looking at "writing" while nothing happens.
  let said = c.said;
  if (b.command in ASKS || b.command === "rebuild") {
    const started = await startResumes(env);
    if (!started) said = "Asked for. It starts at the next check, within five minutes.";
  }
  if (b.command === "retry") {
    const issue = jobs[0] && jobs[0].issue;
    const started = issue && await startApply(env, issue);
    if (!started) said = "Could not start it. Open the form and finish it yourself.";
  }
  return json({ ok, state: c.state, said, count: jobs.length, applied });
}

// The apply run refuses a job it has already tried, so a deliberate retry
// says so explicitly.
async function startApply(env, issue) {
  const r = await gh(env, `/repos/${codeRepo(env)}/actions/workflows/approve.yml/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: env.BRANCH || "main", inputs: { issue: String(issue), force: "true" } }),
  }).catch(() => null);
  return !!(r && r.ok);
}

// Workflows live in the code repo; his resumes, issues and state in the private
// one. With only REPO set, they are the same repo, as before the split.
const codeRepo = (env) => env.CODE_REPO || env.REPO;

async function startResumes(env) {
  const p = gh(env, `/repos/${codeRepo(env)}/actions/workflows/resume.yml/dispatches`, {
    method: "POST", body: JSON.stringify({ ref: env.BRANCH || "main" }),
  }).catch(() => null);
  if (env.later) { env.later(p); return true; }        // he sees the card move; the run follows
  const r = await p;
  return !!(r && r.ok);
}

// "Check now": start a boards sweep rather than only re-reading what the app
// already has. jobbot runs every five minutes anyway, so this is for when he is
// looking and does not want to wait.
async function checkNow(env) {
  const last = await one(env, `SELECT value FROM meta WHERE key = 'asked'`);
  if (last && Date.now() - new Date(last.value).getTime() < 60e3)
    return json({ ok: true, said: "Already checking - give it a minute" });
  const go = gh(env, `/repos/${codeRepo(env)}/actions/workflows/watch.yml/dispatches`, {
    method: "POST", body: JSON.stringify({ ref: env.BRANCH || "main" }),
  }).catch(() => null);
  await run(env, `INSERT INTO meta (key, value, at) VALUES ('asked', ?1, ?1)
                  ON CONFLICT(key) DO UPDATE SET value = excluded.value, at = excluded.at`, now());
  // The next status poll shows whether it really started, so answer now.
  if (env.later) env.later(go.then(() => run(env, `DELETE FROM meta WHERE key = 'runs'`)));
  else {
    const r = await go;
    if (!r || !r.ok) return json({ ok: false, said: "Could not start a check - jobbot tries again within five minutes" });
  }
  return json({ ok: true, said: "Checking the boards" });
}

async function recordApplied(env, job, how) {
  const at = now();
  // If he asked someone before applying, that belongs on the record: it is the
  // first thing he will want to know if an interview comes of it.
  const asked = job.referred_at ? "Asked for a referral on " + String(job.referred_at).slice(0, 10) : null;
  const r = await run(env,
    `INSERT INTO applications (uid, company, title, applied_at, outcome, apply_url, pdf, referral, how, updated_at)
     SELECT ?1, ?2, ?3, ?4, 'no response', ?5, ?6, ?9, ?7, ?8
     WHERE NOT EXISTS (SELECT 1 FROM applications WHERE uid = ?1
                       OR (company = ?2 AND title = ?3 AND applied_at = ?4))`,
    job.uid, job.company, job.title, at.slice(0, 10), job.apply_url || null, job.pdf || null, how, at, asked);
  if (!r.meta || !r.meta.changes) return null;                  // already recorded
  const row = await one(env, `SELECT * FROM applications WHERE uid = ?1 ORDER BY id DESC LIMIT 1`, job.uid);
  return row ? { ...row, company: pretty(row.company) } : null;
}

/* ------------------------------------------------------ what jobbot says --- */

const JOB_COLS = ["uid", "company", "title", "tier", "term", "location", "source", "org", "raw_id",
                  "url", "apply_url", "posted_at", "deadline", "state", "note", "knockout", "folder",
                  "pdf", "preview", "issue", "seen_at", "jd", "shots", "says"];
// He has just tapped something; a run that started before that must not undo it.
const HIS = new Set(["working", "done", "skipped"]);

async function ingest(request, env) {
  const b = await request.json().catch(() => ({}));
  const rows = Array.isArray(b.jobs) ? b.jobs : [];
  const fresh = new Date(Date.now() - 15 * 60e3).toISOString();
  const at = now();
  let written = 0, removed = 0;
  for (const j of rows) {
    if (!j || !j.uid || !j.company) continue;
    const have = await one(env, `SELECT state, updated_at FROM jobs WHERE uid = ?1`, j.uid);
    const keep = !!have && HIS.has(have.state) && (have.updated_at || "") > fresh && !HIS.has(j.state);
    const values = JOB_COLS.map((c) => (c === "knockout" ? (j[c] ? 1 : 0) : (j[c] ?? null)));
    const marks = JOB_COLS.map((_, i) => `?${i + 1}`).join(", ");
    const updates = JOB_COLS.slice(1).filter((c) => !(keep && (c === "state" || c === "note")))
      .map((c) => `${c} = excluded.${c}`).join(", ");
    await run(env,
      `INSERT INTO jobs (${JOB_COLS.join(", ")}, updated_at) VALUES (${marks}, ?${JOB_COLS.length + 1})
       ON CONFLICT(uid) DO UPDATE SET ${updates}, updated_at = excluded.updated_at`,
      ...values, at);
    if (j.state === "done") await recordApplied(env, j, j.how || "jobbot");
    written++;
  }
  for (const e of (Array.isArray(b.events) ? b.events : [])) {
    if (!e || !e.kind) continue;
    await run(env, `INSERT INTO events (uid, at, kind, detail, handled) VALUES (?1, ?2, ?3, ?4, 1)`,
      e.uid || null, e.at || at, e.kind, e.detail ? JSON.stringify(e.detail) : null);
  }
  // A job jobbot no longer knows about must not sit in the app forever - a
  // test posting once said "writing your resume" for a whole day. Only jobs
  // in jobbot's own states are removed; anything he archived, applied to or
  // snoozed is his.
  if (Array.isArray(b.known)) {
    const known = new Set(b.known.map(String));
    // Not one changed in the last 15 minutes: a posting he just brought back
    // is in the app before jobbot has heard about it.
    const mine = await all(env, `SELECT uid FROM jobs WHERE state IN ('new','building','ready','needs')
                                 AND (snoozed_until IS NULL)
                                 AND NOT (note IS 'Added from Filtered out' AND updated_at > ?1)`, fresh);
    const gone = mine.map((r) => r.uid).filter((u) => !known.has(u));
    for (const uid of gone) await run(env, `DELETE FROM jobs WHERE uid = ?1`, uid);
    removed = gone.length;
  }
  if (Array.isArray(b.filtered)) {
    for (const f of b.filtered) {
      if (!f || !f.uid || !f.company) continue;
      await run(env, `INSERT INTO filtered (uid, company, title, location, url, apply_url, posted_at, reason, data, seen_at)
                      SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10 WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE uid = ?1)
                      ON CONFLICT(uid) DO UPDATE SET reason = excluded.reason WHERE filtered.reason IS NOT excluded.reason`,
        f.uid, f.company, f.title || "", f.location || null, f.url || null, f.apply_url || null,
        f.posted_at || null, f.reason || null, JSON.stringify(f), at);
    }
    // A week, the same as the feed. jobbot sends the same few hundred every
    // 15 minutes; one it already sent, for the same reason, costs no write -
    // D1's free tier allows 100,000 a day.
    const week = new Date(Date.now() - 7 * 864e5).toISOString();
    await run(env, `DELETE FROM filtered WHERE COALESCE(posted_at, seen_at) < ?1`, week);
  }
  // The defaults Settings shows. The same every run unless a file changed,
  // and then an unchanged one costs no write.
  if (b.settings_base && typeof b.settings_base === "object") {
    for (const [k, v] of Object.entries(b.settings_base)) {
      if (!SETTINGS.includes(k)) continue;
      await run(env, `INSERT INTO settings (key, base, updated_at) VALUES (?1, ?2, ?3)
                      ON CONFLICT(key) DO UPDATE SET base = excluded.base WHERE settings.base IS NOT excluded.base`,
        k, JSON.stringify(v), at);
    }
  }
  if (Array.isArray(b.targets) && b.targets.length) {
    const have = await one(env, `SELECT COUNT(*) n FROM following`);
    if (!have || !have.n) {
      for (const t of b.targets) {
        const k = key(t);
        if (k) await run(env, `INSERT OR IGNORE INTO following (key, name, at) VALUES (?1, ?2, ?3)`,
          k, pretty(t), now());
      }
    }
  }
  // A sweep that reports in is proof jobbot is alive again.
  if (b.jobs && b.jobs.length) {
    await run(env, `INSERT INTO meta (key, value, at) VALUES ('health', 'ok', ?1)
                    ON CONFLICT(key) DO UPDATE SET value = 'ok', at = excluded.at`, at);
  }
  if (b.checked_at) {
    await run(env, `INSERT INTO meta (key, value, at) VALUES ('checked', ?1, ?1)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, at = excluded.at`,
      String(b.checked_at));
  }
  if (rows.length) await announce(env, rows);
  const total = await one(env, `SELECT COUNT(*) n FROM jobs`);
  return json({ ok: true, written, removed, jobs: total ? total.n : 0 });
}

// jobbot pulls what he did in the app, applies it to its own files, and acks.
async function listEvents(env) {
  const rows = await all(env, `SELECT * FROM events WHERE handled = 0 ORDER BY id LIMIT 200`);
  return json({ events: rows.map((r) => ({ ...r, detail: r.detail ? JSON.parse(r.detail) : null })) });
}

async function ackEvents(request, env) {
  const b = await request.json().catch(() => ({}));
  const ids = (Array.isArray(b.ids) ? b.ids : []).map(Number).filter(Boolean);
  if (!ids.length) return json({ ok: true, acked: 0 });
  await run(env, `UPDATE events SET handled = 1 WHERE id IN (${ids.map((_, i) => `?${i + 1}`).join(",")})`, ...ids);
  return json({ ok: true, acked: ids.length });
}

// The postings the rules turned away, newest first. The description stays
// behind: it is only needed if he brings one back.
async function filteredList(env) {
  const rows = await all(env, `SELECT uid, company, title, location, url, apply_url, posted_at, reason
                               FROM filtered WHERE uid NOT IN (SELECT uid FROM jobs)
                               ORDER BY posted_at DESC LIMIT 500`);
  return json({ filtered: rows.map((r) => ({ ...r, company: pretty(r.company),
                                             where: shortLocation(r.location),
                                             why: plainReason(r.reason, r.title)[0],
                                             detail: plainReason(r.reason, r.title)[1] })) });
}

// jobbot's reasons are written for its log; these are written for him, as a
// few groups (the chips) and the specific word or limit (on the row).
function plainReason(r, title) {
  const s = String(r || "");
  let m;
  if ((m = s.match(/posted too long ago \(over (\d+)h\)/)))
    return ["Posted before your window", "Your window for this kind of job is " + (+m[1] >= 48 ? +m[1] / 24 + " days" : m[1] + " hours")];
  if (s.startsWith("title not a wanted role")) return ["Role not on your list", ""];
  if ((m = s.match(/^title excluded \((.+)\)/))) {
    // Show the whole word from the title: the rule "data scien" reads as "Data Science".
    const t = String(title || ""), at = t.toLowerCase().indexOf(m[1].toLowerCase());
    const word = at < 0 ? m[1] : t.slice(at, at + m[1].length) + (t.slice(at + m[1].length).match(/^[A-Za-z]*/) || [""])[0];
    return ["A role type you excluded", "“" + word + "” is on your excluded list"];
  }
  if ((m = s.match(/^wrong term \((.+)\)/))) return ["Wrong term", m[1]];
  if (s.startsWith("no matching term")) return ["Wrong term", "No 2027 term mentioned"];
  if (s.startsWith("location")) return ["Outside the US and Canada", ""];
  if (s.startsWith("needs US work authorization")) return ["Will not sponsor a US visa", ""];
  if (s.startsWith("application deadline")) return ["Deadline has passed", ""];
  return ["Other rules", s];
}

/* ------------------------------------------------------------- settings --- */

const SETTINGS = ["search", "profile", "resume", "answers", "alerts"];
const parse = (s) => (s == null ? null : JSON.parse(s));

// His value where he changed it from the default he saw; the current default
// everywhere else. The same rule as jobbot/settings.py merge3.
function merge3(now, then, mine) {
  if (mine === null || mine === undefined) return now;
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  if (then !== null && then !== undefined && same(mine, then)) return now;
  const isObj = (x) => x && typeof x === "object" && !Array.isArray(x);
  if (isObj(mine) && isObj(now)) {
    const t = isObj(then) ? then : {};
    const out = {};
    for (const k of Object.keys(mine)) out[k] = merge3(now[k], t[k], mine[k]);
    for (const k of Object.keys(now)) if (!(k in mine)) out[k] = now[k];
    return out;
  }
  const records = (xs) => Array.isArray(xs) && xs.length && xs.every((x) => isObj(x) && "id" in x);
  if (records(mine) && records(now)) {
    const before = new Map((Array.isArray(then) ? then : []).filter(isObj).map((x) => [x.id, x]));
    const current = new Map(now.map((x) => [x.id, x]));
    const out = mine.map((x) => merge3(current.get(x.id), before.get(x.id), x));
    const seen = new Set(mine.map((x) => x.id));
    return out.concat(now.filter((x) => !seen.has(x.id) && !before.has(x.id)));
  }
  return mine;
}

async function settingsRaw(env) {
  const rows = await all(env, `SELECT key, value, value_base FROM settings`);
  const raw = {};
  for (const r of rows) raw[r.key] = { value: parse(r.value), value_base: parse(r.value_base) };
  return json({ raw });
}

async function settingsView(env) {
  const rows = await all(env, `SELECT * FROM settings`);
  const sections = {};
  for (const r of rows) {
    const base = parse(r.base);
    if (base === null) continue;
    const value = parse(r.value);
    sections[r.key] = { value: value === null ? base : merge3(base, parse(r.value_base), value),
                        base, edited: value !== null, undo: r.was !== null || value !== null,
                        updated_at: r.updated_at };
  }
  return json({ sections });
}

// Save, reset to the default, or undo the last save of one section.
async function saveSetting(request, env) {
  const b = await request.json().catch(() => ({}));
  if (!SETTINGS.includes(b.key)) return json({ error: "unknown setting" }, 400);
  const row = await one(env, `SELECT * FROM settings WHERE key = ?1`, b.key);
  if (!row || row.base === null) return json({ error: "jobbot has not sent its defaults yet" }, 409);
  let value, valueBase, said;
  if (b.undo) {
    if (row.was === null && row.value === null) return json({ error: "nothing to undo" }, 409);
    value = row.was; valueBase = row.was_base; said = "Put back";
  } else if (b.reset) {
    value = null; valueBase = null; said = "Back to the default";
  } else {
    if (b.value === undefined || b.value === null || typeof b.value !== "object")
      return json({ error: "value required" }, 400);
    value = JSON.stringify(b.value);
    // Saving exactly the default is the same as not having changed it.
    if (value === row.base) { value = null; valueBase = null; } else valueBase = row.base;
    said = "Saved";
  }
  if (value !== null && value.length > 400000) return json({ error: "too long to save" }, 413);
  await run(env, `UPDATE settings SET value = ?1, value_base = ?2, was = ?3, was_base = ?4, updated_at = ?5
                  WHERE key = ?6`, value, valueBase, row.value, row.value_base, now(), b.key);
  await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (NULL, ?1, 'settings', ?2)`,
    now(), JSON.stringify({ key: b.key, how: b.undo ? "undo" : b.reset ? "reset" : "save" }));
  return json({ ok: true, said });
}

/* ------------------------------------------------ learning from archives --- */

const REASONS = ["role", "level", "place", "term", "company", "other"];
// Words every title shares, which say nothing about why he turned one down.
const PLAIN = new Set(("intern interns internship internships co op coop student students software engineer engineers " +
  "engineering developer development summer winter fall spring autumn 2025 2026 2027 2028 the and of for in " +
  "at with to a an i ii iii team program new grad graduate university undergraduate term months month " +
  "4 8 12 16 part time full remote hybrid us usa canada").split(" "));

function grams(title) {
  // Pairs are taken before the common words are dropped: "data engineer" is
  // the phrase that matters, though "engineer" alone says nothing.
  const all = String(title || "").toLowerCase().replace(/[^a-z0-9+#.]+/g, " ").trim().split(/\s+/).filter(Boolean);
  const telling = (w) => !PLAIN.has(w) && !/^\d+$/.test(w);
  const out = new Set(all.filter((w) => telling(w) && w.length > 2));
  for (let i = 0; i + 1 < all.length; i++) {
    const [a, b] = [all[i], all[i + 1]];
    if ((telling(a) || telling(b)) && !/^\d+$/.test(a) && !/^\d+$/.test(b) && a.length > 1 && b.length > 1)
      out.add(a + " " + b);
  }
  return out;
}

// What his archives suggest, as changes he can make with one tap. Plain
// counting, no model: a word in three or more titles he turned down as the
// wrong role, and in none he went ahead with, is a word he does not want.
async function suggestions(env) {
  const [fb, gone, kept, row, quiet] = await Promise.all([
    all(env, `SELECT * FROM feedback ORDER BY at DESC LIMIT 500`),
    all(env, `SELECT id FROM dismissed`),
    all(env, `SELECT title FROM jobs WHERE state NOT IN ('new', 'skipped')`),
    one(env, `SELECT * FROM settings WHERE key = 'search'`),
    all(env, `SELECT company FROM muted`),
  ]);
  const no = new Set(gone.map((r) => r.id));
  const muted = new Set(quiet.map((m) => m.company));
  const search = row && row.base ? (row.value ? merge3(parse(row.base), parse(row.value_base), parse(row.value)) : parse(row.base)) : null;
  const out = [];
  for (const f of fb) {
    const id = "mute:" + key(f.company);
    if (f.reason === "company" && !muted.has(key(f.company)) && !no.has(id) && !out.some((s) => s.id === id))
      out.push({ id, kind: "mute", company: f.company,
                 text: "You archived a job at " + pretty(f.company) + " as not a company you want.",
                 action: "Mute " + pretty(f.company) });
  }
  if (search) {
    const wanted = new Set();
    for (const k of kept) for (const g of grams(k.title)) wanted.add(g);
    const have = new Set((search.roles_excluded || []).map((w) => w.toLowerCase()));
    const count = new Map();
    for (const f of fb.filter((x) => x.reason === "role" || x.reason === "level")) {
      for (const g of grams(f.title)) {
        if (wanted.has(g) || have.has(g)) continue;
        if (!count.has(g)) count.set(g, []);
        count.get(g).push(f.title);
      }
    }
    // Two words beat one when they cover the same titles ("data engineer" over "data").
    const ranked = [...count.entries()].filter(([, t]) => t.length >= 3)
      .sort((a, b) => b[1].length - a[1].length || b[0].split(" ").length - a[0].split(" ").length);
    const taken = [];
    for (const [g, titles] of ranked) {
      if (no.has("role:" + g) || taken.some((t) => t.includes(g) || g.includes(t))) continue;
      taken.push(g);
      out.push({ id: "role:" + g, kind: "exclude_role", word: g, examples: titles.slice(0, 3),
                 text: "You archived " + titles.length + " roles with \u201c" + g + "\u201d in the title.",
                 action: "Stop showing them" });
      if (taken.length >= 3) break;
    }
    const places = new Map();
    for (const f of fb.filter((x) => x.reason === "place")) {
      for (const p of new Set(String(f.location || "").split(/[;,]/).map((s) => s.trim().toLowerCase()).filter(Boolean))) {
        if ((search.places_excluded || []).includes(p) || /^(us|usa|united states|canada|remote|[a-z]{2})$/.test(p)) continue;
        if (!places.has(p)) places.set(p, 0);
        places.set(p, places.get(p) + 1);
      }
    }
    for (const [p, n] of [...places.entries()].sort((a, b) => b[1] - a[1])) {
      if (n < 3 || no.has("place:" + p)) continue;
      out.push({ id: "place:" + p, kind: "exclude_place", word: p,
                 text: "You archived " + n + " jobs in " + pretty(p) + " as the wrong location.",
                 action: "Stop showing " + pretty(p) });
      break;
    }
  }
  return json({ suggestions: out });
}

async function actOnSuggestion(request, env) {
  const b = await request.json().catch(() => ({}));
  const id = String(b.id || "");
  if (!id) return json({ error: "id required" }, 400);
  if (b.dismiss) {
    await run(env, `INSERT OR IGNORE INTO dismissed (id, at) VALUES (?1, ?2)`, id, now());
    return json({ ok: true, said: "Won\u2019t suggest that again" });
  }
  if (b.undismiss) { await run(env, `DELETE FROM dismissed WHERE id = ?1`, id); return json({ ok: true }); }
  const [kind, ...rest] = id.split(":");
  const word = rest.join(":");
  if (kind === "mute") {
    return command(new Request("https://x/api/command", { method: "POST",
      body: JSON.stringify({ command: "mute", company: word }) }), env);
  }
  if (kind !== "role" && kind !== "place") return json({ error: "unknown suggestion" }, 400);
  const row = await one(env, `SELECT * FROM settings WHERE key = 'search'`);
  if (!row || !row.base) return json({ error: "jobbot has not sent its defaults yet" }, 409);
  const base = parse(row.base);
  const value = row.value ? merge3(base, parse(row.value_base), parse(row.value)) : clone(base);
  const field = kind === "role" ? "roles_excluded" : "places_excluded";
  value[field] = [...new Set([...(value[field] || []), word])];
  await run(env, `UPDATE settings SET value = ?1, value_base = ?2, was = ?3, was_base = ?4, updated_at = ?5 WHERE key = 'search'`,
    JSON.stringify(value), row.base, row.value, row.value_base, now());
  await run(env, `INSERT OR IGNORE INTO dismissed (id, at) VALUES (?1, ?2)`, id, now());
  // What is already in his feed goes too, archived for the same reason.
  const feed = await all(env, `SELECT uid, company, title, location, issue, apply_url, pdf FROM jobs WHERE state = 'new'`);
  const hit = feed.filter((j) => kind === "role" ? grams(j.title).has(word) :
    String(j.location || "").toLowerCase().split(/[;,]/).map((s) => s.trim()).includes(word));
  for (const j of hit) {
    await run(env, `UPDATE jobs SET state = 'skipped', note = 'Archived', updated_at = ?1 WHERE uid = ?2`, now(), j.uid);
    await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (?1, ?2, 'archive', ?3)`, j.uid, now(),
      JSON.stringify({ company: j.company, title: j.title, apply_url: j.apply_url, reason: "settings" }));
  }
  return json({ ok: true, archived: hit.map((j) => j.uid),
                said: (kind === "role" ? "No more \u201c" + word + "\u201d roles" : "No more jobs in " + pretty(word)) +
                      (hit.length ? ", " + hit.length + " archived" : "") });
}
const clone = (x) => JSON.parse(JSON.stringify(x));

/* ------------------------------------------------------------- push --- */

// Notifications, so he is not the one checking. The push itself carries no
// payload: the phone wakes the service worker, which asks the app what to say.
// That keeps everything he is told behind his own sign-in.
const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function vapidHeader(env, endpoint) {
  if (!env.VAPID_PRIVATE || !env.VAPID_PUBLIC) return null;
  const aud = new URL(endpoint).origin;
  const head = b64url(new TextEncoder().encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const body = b64url(new TextEncoder().encode(JSON.stringify({
    aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: env.PUSH_CONTACT || "mailto:jobbot@example.com" })));
  const key = await crypto.subtle.importKey("jwk", JSON.parse(env.VAPID_PRIVATE),
    { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key,
    new TextEncoder().encode(head + "." + body));
  return { Authorization: "vapid t=" + head + "." + body + "." + b64url(sig) + ", k=" + env.VAPID_PUBLIC };
}

// One wake-up per subscribed device. A subscription the phone has thrown away
// (404/410) is removed rather than retried forever.
async function wake(env) {
  const subs = await all(env, `SELECT endpoint FROM push_subs`);
  let sent = 0;
  for (const s of subs) {
    const auth = await vapidHeader(env, s.endpoint);
    if (!auth) return 0;
    const r = await fetch(s.endpoint, { method: "POST", headers: { ...auth, TTL: "3600", "content-length": "0" } })
      .catch(() => ({ status: 0 }));
    if (r.status === 404 || r.status === 410) await run(env, `DELETE FROM push_subs WHERE endpoint = ?1`, s.endpoint);
    else if (r.status >= 200 && r.status < 300) sent++;
  }
  return sent;
}

// What is worth interrupting him for, and what it should say.
const TELL = {
  // A posting at a company he follows is the one thing worth interrupting him
  // for the moment it appears: those are the ones that fill fastest. Whether
  // the rest of the board reaches him too is a setting.
  new: (j) => ["New at " + pretty(j.company), j.title],
  ready: (j) => ["Resume ready", pretty(j.company) + " - " + j.title],
  needs: (j) => ["Needs you", pretty(j.company) + " - " + (j.note || "this one needs you")],
  done: (j) => ["Applied", pretty(j.company) + " - " + j.title],
};

// What he has asked to hear about. Anything not set yet follows the default:
// a company he follows, and anything that needs him.
async function wants(env) {
  const row = await one(env, `SELECT base, value, value_base FROM settings WHERE key = 'alerts'`);
  const fallback = { followed: true, any_new: false, ready: true, needs: true, applied: true, problems: true };
  if (!row || !row.base) return fallback;
  const base = parse(row.base);
  return { ...fallback, ...(row.value ? merge3(base, parse(row.value_base), parse(row.value)) : base) };
}

async function announce(env, jobs) {
  if (!env.VAPID_PRIVATE) return 0;
  const on = await wants(env);
  const subs = await one(env, `SELECT COUNT(*) n FROM push_subs`);
  if (!subs || !subs.n) return 0;
  let fresh = 0;
  for (const j of jobs) {
    if (!TELL[j.state] || !TELL[j.state](j)) continue;
    if (j.state === "new" && !(on.followed && j.tier === 1) && !on.any_new) continue;
    if (j.state !== "new" && on[j.state] === false) continue;
    const had = await one(env, `SELECT 1 x FROM push_sent WHERE uid = ?1 AND state = ?2`, j.uid, j.state);
    if (had) continue;
    await run(env, `INSERT OR REPLACE INTO push_sent (uid, state, at) VALUES (?1, ?2, ?3)`, j.uid, j.state, now());
    fresh++;
  }
  return fresh ? wake(env) : 0;
}

// What the phone should show, built when it asks - never sent over the wire
// with the push itself.
async function pushLatest(env) {
  const hurt = await one(env, `SELECT value, at FROM meta WHERE key = 'health'`);
  if (hurt && hurt.value !== "ok") {
    const said = await one(env, `SELECT value FROM meta WHERE key = 'health_said'`);
    return json({ title: "jobbot needs a look", body: (said && said.value) || "Something stopped working.", uid: null });
  }
  const since = new Date(Date.now() - 6 * 3600e3).toISOString();
  const rows = await all(env, `SELECT p.uid, p.state, j.company, j.title, j.note, j.tier FROM push_sent p
                               JOIN jobs j ON j.uid = p.uid WHERE p.at >= ?1 ORDER BY p.at DESC LIMIT 8`, since);
  const items = rows.filter((r) => TELL[r.state] && TELL[r.state](r)).map((r) => {
    const [title, body] = TELL[r.state](r);
    return { uid: r.uid, title, body };
  });
  if (!items.length) return json({ title: "jobbot", body: "Something changed on your board", uid: null });
  if (items.length === 1) return json(items[0]);
  return json({ title: items.length + " updates", body: items.map((i) => i.body).join("\n"), uid: null });
}

async function pushRoute(request, env, url) {
  if (request.method === "GET" && url.searchParams.get("latest")) return pushLatest(env);
  if (request.method === "GET")
    return json({ key: env.VAPID_PUBLIC || null,
                  devices: (await one(env, `SELECT COUNT(*) n FROM push_subs`)).n });
  const b = await request.json().catch(() => ({}));
  const endpoint = String((b.subscription && b.subscription.endpoint) || b.endpoint || "");
  if (b.off) {
    if (endpoint) await run(env, `DELETE FROM push_subs WHERE endpoint = ?1`, endpoint);
    return json({ ok: true, said: "Notifications off on this device" });
  }
  if (b.test) {
    const sent = await wake(env);
    return json({ ok: !!sent, said: sent ? "Sent - it should arrive in a moment" : "No device is subscribed" });
  }
  if (!endpoint.startsWith("https://")) return json({ error: "a subscription is required" }, 400);
  await run(env, `INSERT INTO push_subs (endpoint, keys, added_at) VALUES (?1, ?2, ?3)
                  ON CONFLICT(endpoint) DO UPDATE SET keys = excluded.keys`,
    endpoint, JSON.stringify((b.subscription && b.subscription.keys) || {}), now());
  return json({ ok: true, said: "Notifications on for this device" });
}

/* ---------------------------------------------------------------- usage --- */

// Which parts of the app he uses: a count per day per action, sent in small
// batches by the page. Names only - never what he typed.
async function countUsage(request, env) {
  const b = await request.json().catch(() => ({}));
  const day = now().slice(0, 10);
  const counts = b && typeof b.counts === "object" ? Object.entries(b.counts).slice(0, 60) : [];
  for (const [name, n] of counts) {
    const clean = String(name).slice(0, 80), k = Math.max(0, Math.min(500, Number(n) || 0));
    if (!clean || !k) continue;
    await run(env, `INSERT INTO usage (day, name, n) VALUES (?1, ?2, ?3)
                    ON CONFLICT(day, name) DO UPDATE SET n = n + excluded.n`, day, clean, k);
  }
  return json({ ok: true });
}

async function usageView(env) {
  const since = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const rows = await all(env, `SELECT name, SUM(n) n, COUNT(*) days, MAX(day) last FROM usage WHERE day >= ?1
                               GROUP BY name ORDER BY n DESC`, since);
  const first = await one(env, `SELECT MIN(day) d FROM usage`);
  return json({ since, first: first ? first.d : null, rows });
}

/* --------------------------------------------------------------- github --- */

function gh(env, path, init = {}) {
  return fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${env.GH_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "jobbot-app",
      ...(init.headers || {}),
    },
  });
}

async function repoFile(env, path, raw = false) {
  const r = await gh(env, `/repos/${env.REPO}/contents/${encodeURI(path)}?ref=${env.BRANCH || "main"}`,
    raw ? { headers: { accept: "application/vnd.github.raw" } } : {});
  if (!r.ok) return null;
  if (raw) return r.arrayBuffer();
  const d = await r.json();
  return JSON.parse(decodeURIComponent(escape(atob((d.content || "").replace(/\n/g, "")))));
}

async function answers(env, folder) {
  if (!folder || folder.includes("..")) return json({ error: "folder required" }, 400);
  return json(await answersFor(env, folder));
}

async function answersFor(env, folder) {
  const [app, mine, coined] = await Promise.all([
    repoFile(env, `${folder}/application.json`).catch(() => null),
    all(env, `SELECT label, text FROM answers WHERE folder = ?1`, folder),
    // Figures the writer put on the page that his facts did not carry.
    repoFile(env, `${folder}/coined.json`).catch(() => null),
  ]);
  if (!app) return { questions: [], knockouts: [], none: true, coined: coined || [] };
  const edited = new Map(mine.map((r) => [r.label, r]));
  return {
    knockouts: app.knockouts || [], problems: app.problems || [], coined: coined || [],
    // What he typed wins over what was drafted for him, here and in the form.
    questions: (app.questions || []).filter((q) => q.how !== "skip").map((q) => ({
      label: q.label, required: q.required,
      answer: edited.has(q.label) ? edited.get(q.label).text : q.answer,
      how: edited.has(q.label) ? "you" : q.how,
      was: edited.has(q.label) ? edited.get(q.label).was : null,
    })),
  };
}

// Which posting is this page, if any.
//
// He applies on his laptop, in another tab, and what he needs there is what
// jobbot already wrote for this job. The page's address is the only thing the
// extension can go on, so match on the host first and then on any id the two
// addresses share: a Greenhouse form is /jobs/8123225 where the posting was
// /jobs/8123225#app, and a Workday form drops the whole path.
const IDS = /[0-9a-f]{6,}|\d{4,}|R-?\d{3,}/gi;

async function lookup(env, page) {
  if (!page) return json({ error: "url required" }, 400);
  let host = "";
  try { host = new URL(page).hostname.replace(/^www\./, ""); } catch (e) { return json({ error: "bad url" }, 400); }
  const rows = await all(env, `SELECT uid, company, title, state, url, apply_url, raw_id, folder, pdf, note,
                                      term, location, posted_at FROM jobs
                               WHERE state != 'skipped' AND (url LIKE ?1 OR apply_url LIKE ?1)
                               ORDER BY updated_at DESC LIMIT 60`, "%" + host + "%");
  const mine = new Set((page.match(IDS) || []).map((s) => s.toLowerCase()));
  const bare = (u) => String(u || "").split(/[?#]/)[0].replace(/\/$/, "");
  let best = null, score = 0;
  for (const j of rows) {
    let n = 0;
    if (bare(j.url) === bare(page) || bare(j.apply_url) === bare(page)) n += 10;
    if (j.raw_id && mine.has(String(j.raw_id).toLowerCase())) n += 6;
    for (const id of (String(j.url || "") + " " + String(j.apply_url || "")).match(IDS) || [])
      if (mine.has(id.toLowerCase())) n += 3;
    if (n > score) { score = n; best = j; }
  }
  const me = await profileNow(env).catch(() => null);
  const facts = me ? { ...me.contact, ...me.education } : null;
  if (!best) return json({ job: null, host, me: facts });
  const said = best.folder ? await answersFor(env, best.folder) : { questions: [] };
  return json({ job: best, me: facts, questions: said.questions || [], knockouts: said.knockouts || [] });
}

// A posting he found himself, on a board jobbot cannot read. It joins the feed
// as if jobbot had found it: he can ask for a resume on it like any other.
async function capture(request, env) {
  const b = await request.json().catch(() => ({}));
  const link = String(b.url || "").slice(0, 900);
  if (!/^https?:\/\//.test(link)) return json({ error: "a link is required" }, 400);
  const company = String(b.company || "").trim().slice(0, 120) || "Unknown";
  const title = String(b.title || "").trim().slice(0, 300) || "Role";
  const digest = await crypto.subtle.digest("SHA-1", new TextEncoder().encode("you:" + link));
  const uid = [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("").slice(0, 16);
  const had = await one(env, `SELECT uid, state FROM jobs WHERE uid = ?1`, uid);
  if (had) return json({ ok: true, uid, said: "Already on your board" });
  const at = now();
  await run(env, `INSERT INTO jobs (uid, company, title, tier, term, location, source, org, raw_id, url,
                  apply_url, posted_at, state, note, knockout, seen_at, jd, updated_at)
                  VALUES (?1, ?2, ?3, 1, ?4, ?5, 'you', 'you', ?1, ?6, ?7, ?8, 'new', ?9, 0, ?10, ?11, ?10)`,
    uid, company, title, termOf(title + " " + (b.description || "")), String(b.location || "").slice(0, 200),
    link, String(b.apply_url || link).slice(0, 900), b.posted_at || null,
    "You added this from " + (b.where || "your browser"), at, String(b.description || "").slice(0, 60000));
  await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (?1, ?2, 'found', ?3)`,
    uid, at, JSON.stringify({ posting: { uid, company, title, url: link, source: "you" } }));
  return json({ ok: true, uid, said: "Added to your jobs" });
}

// ?save=Name downloads the file as Name.<ext> instead of opening it.
async function file(env, path, save) {
  if (!path || path.includes("..")) return json({ error: "bad path" }, 400);
  const body = await repoFile(env, path, true);
  if (!body) return json({ error: "not found" }, 404);
  const ext = path.split(".").pop().toLowerCase();
  const headers = { "content-type": TYPES[ext] || "application/octet-stream",
                    "cache-control": "private, max-age=600" };
  if (save) {
    const name = (save.replace(/[^A-Za-z0-9 _.-]+/g, "").replace(/\s+/g, "_").slice(0, 100) || "file") + "." + ext;
    headers["content-disposition"] = 'attachment; filename="' + name + '"';
  }
  return new Response(body, { headers });
}

// Saving an answer must never depend on the app's GitHub token being allowed
// to write: it is kept here, shown here, and jobbot writes it into the folder's
// application.json on its next run, before anything is filled in for him.
async function editAnswer(request, env) {
  const { folder, label, text, revert } = await request.json().catch(() => ({}));
  if (!folder || !label || folder.includes("..")) return json({ error: "folder and label required" }, 400);
  const app = await repoFile(env, `${folder}/application.json`).catch(() => null);
  if (revert) {
    const kept = await one(env, `SELECT was FROM answers WHERE folder = ?1 AND label = ?2`, folder, label);
    if (!kept) return json({ error: "nothing to put back" }, 404);
    await run(env, `DELETE FROM answers WHERE folder = ?1 AND label = ?2`, folder, label);
    await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (NULL, ?1, 'answer', ?2)`,
      now(), JSON.stringify({ folder, label, text: kept.was ?? "", drafted: true }));
    return json({ ok: true, answer: kept.was ?? "" });
  }
  if (app && !(app.questions || []).some((q) => q.label === label))
    return json({ error: "question not found" }, 404);
  const at = now();
  const drafted = (app && (app.questions || []).find((q) => q.label === label)) || {};
  // Keep what was drafted, so "Use jobbot's answer" can put it back.
  await run(env, `INSERT INTO answers (folder, label, text, was, updated_at) VALUES (?1, ?2, ?3, ?4, ?5)
                  ON CONFLICT(folder, label) DO UPDATE SET text = excluded.text, updated_at = excluded.updated_at`,
    folder, label, text ?? "", drafted.answer ?? null, at);
  await run(env, `INSERT INTO events (uid, at, kind, detail) VALUES (NULL, ?1, 'answer', ?2)`,
    at, JSON.stringify({ folder, label, text: text ?? "" }));
  return json({ ok: true });
}

/* ------------------------------------------------------------- responses --- */

const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });
const html = (body) => new Response(body, { headers: { "content-type": "text/html; charset=utf-8" } });

// Woken by a push with nothing in it: it asks the app what happened, which
// keeps the text behind his sign-in rather than in the push service's logs.
const SW = `self.addEventListener("push", (e) => {
  e.waitUntil((async () => {
    let d = { title: "jobbot", body: "Something changed on your board", uid: null };
    try { d = await (await fetch("/api/push?latest=1", { credentials: "include" })).json(); } catch (err) {}
    await self.registration.showNotification(d.title, {
      body: d.body, tag: d.uid || "jobbot", renotify: true, data: { uid: d.uid },
    });
  })());
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const uid = e.notification.data && e.notification.data.uid;
  const url = uid ? "/?job=" + encodeURIComponent(uid) : "/";
  e.waitUntil((async () => {
    const open = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of open) if (c.url.includes(self.registration.scope)) { await c.focus(); return c.navigate(url); }
    return clients.openWindow(url);
  })());
});`;


// A stack of postings with the app's own "not opened yet" dot on the top one.
// PNG, because iOS ignores SVG for a Home Screen icon.
const ICON_PNG = "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";

const MANIFEST = {
  name: "jobbot", short_name: "jobbot", start_url: "/", display: "standalone",
  background_color: "#101d34", theme_color: "#101d34",
  icons: [{ src: "/icon.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/icon.png", sizes: "192x192", type: "image/png", purpose: "any" }],
};
