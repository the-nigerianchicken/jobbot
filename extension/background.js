/**
 * The only thing here that talks to jobbot.
 *
 * A content script runs on the careers site's own origin, so anything it asked
 * jobbot for would be a cross-origin request and would need jobbot to invite
 * every site on the web in. A service worker with host permissions is not
 * bound by that, so every request goes through this file and the page only
 * ever sees the answer.
 *
 * The passcode is never kept. It is exchanged once, at Options, for the same
 * key the app's cookie carries, and that is what is stored.
 */

const settings = () => chrome.storage.local.get(["base", "key"]);

async function ask(path, body) {
  const { base, key } = await settings();
  if (!base || !key) return { error: "setup" };
  const r = await fetch(base.replace(/\/$/, "") + path, {
    method: body ? "POST" : "GET",
    headers: { "x-jobbot-key": key, ...(body ? { "content-type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  }).catch(() => null);
  if (!r) return { error: "offline" };
  if (r.status === 401) return { error: "setup" };
  if (!r.ok) return { error: "jobbot said no (" + r.status + ")" };
  return r.json().catch(() => ({ error: "jobbot sent something unreadable" }));
}

// Chrome cannot download from another origin with a header on the request, so
// the file is fetched here, where the key can be sent, and handed to the page
// as text.
//
// It is not saved here. A service worker has no URL.createObjectURL, so this
// used to pass a data: URL to chrome.downloads - which Chrome refuses, and the
// fallback opened the PDF in a tab, where Windows offered to share it instead
// of saving it (2026-09-26). The page can make a blob and save it properly, and
// it can also put the file straight into the form's file picker.
async function resume(path) {
  const { base, key } = await settings();
  if (!base || !key) return { error: "setup" };
  const url = base.replace(/\/$/, "") + "/file?path=" + encodeURIComponent(path);
  const r = await fetch(url, { headers: { "x-jobbot-key": key } }).catch(() => null);
  if (!r || !r.ok) return { error: "could not fetch your resume" };
  const bytes = new Uint8Array(await r.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
  return { ok: true, b64: btoa(binary) };
}

const HANDLERS = {
  lookup: (m) => ask("/api/lookup?url=" + encodeURIComponent(m.url)),
  capture: (m) => ask("/api/capture", m.posting),
  command: (m) => ask("/api/command", { uid: m.uid, command: m.command }),
  resume: (m) => resume(m.path),
  options: async () => { chrome.runtime.openOptionsPage(); return { ok: true }; },
  settings: async () => {
    const { base } = await settings();
    return { base: base || "" };
  },
};

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const go = HANDLERS[msg && msg.kind];
  if (!go) return false;
  go(msg).then(reply, (e) => reply({ error: String(e && e.message || e) }));
  return true;                        // the answer comes later
});

// The toolbar button puts the panel on a page the content script does not
// cover - a company's own careers site, anywhere.
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !/^https?:/.test(tab.url || "")) return;
  try {
    await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["panel.css"] });
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
  } catch (e) {
    chrome.runtime.openOptionsPage();
  }
});
