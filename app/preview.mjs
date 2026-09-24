// Run the real app on this laptop, against a copy of the real data: the worker
// itself, the real schema, seed.sql, and the repo's own resumes and answers.
// No secrets, no network, no Cloudflare.
//
//   python -m jobbot.seed_store        # refresh app/seed.sql
//   node app/preview.mjs               # open http://localhost:8787 (passcode: preview)
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import worker from "./worker.js";
import { makeDb } from "./d1stub.mjs";

const root = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const files = existsSync(new URL("./seed.sql", import.meta.url)) ? ["schema.sql", "seed.sql"] : ["schema.sql"];
const env = { APP_PASSCODE: "preview", INGEST_TOKEN: "preview", GH_TOKEN: "none",
              REPO: "local/repo", BRANCH: "main", DB: makeDb(files) };

// Anything the worker asks GitHub for is answered from the working copy.
globalThis.fetch = async (url, init = {}) => {
  const u = String(url);
  const m = u.match(/\/contents\/(.+?)(\?|$)/);
  if (!m || (init.method && init.method !== "GET"))
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  const path = decodeURIComponent(m[1]);
  const body = await readFile(root + path).catch(() => null);
  if (!body) return new Response("no", { status: 404 });
  if ((init.headers || {}).accept === "application/vnd.github.raw")
    return new Response(body, { status: 200 });
  return new Response(JSON.stringify({ sha: "local", content: body.toString("base64") }), { status: 200 });
};

createServer(async (node, res) => {
  const chunks = [];
  for await (const c of node) chunks.push(c);
  const request = new Request("http://localhost:8787" + node.url, {
    method: node.method,
    headers: node.headers,
    body: chunks.length ? Buffer.concat(chunks) : undefined,
  });
  const out = await worker.fetch(request, env);
  res.writeHead(out.status, Object.fromEntries(out.headers));
  res.end(Buffer.from(await out.arrayBuffer()));
}).listen(8787, () => console.log(`preview on http://localhost:8787  (${files.join(" + ")}, passcode: preview)`));
