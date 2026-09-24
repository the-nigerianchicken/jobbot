/**
 * Connecting the extension to jobbot, once.
 *
 * The passcode is traded for the key the app's own cookie carries and then
 * dropped: what gets stored is the key, which is what every later request
 * sends. A wrong passcode is told plainly rather than being stored and failing
 * silently on the first form he opens.
 */
const base = document.getElementById("base");
const pc = document.getElementById("pc");
const said = document.getElementById("said");

function tell(text, bad) {
  said.textContent = text;
  said.className = bad ? "bad" : "";
}

chrome.storage.local.get(["base", "key"]).then(({ base: had, key }) => {
  if (had) base.value = had;
  if (had && key) tell("Connected to " + had.replace(/^https?:\/\//, ""));
});

document.getElementById("save").addEventListener("click", async () => {
  const where = base.value.trim().replace(/\/$/, "");
  if (!/^https?:\/\/.+/.test(where)) return tell("That does not look like an address", true);
  if (!pc.value) return tell("The passcode goes in the second box", true);
  tell("Asking jobbot");
  const r = await fetch(where + "/api/key", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ passcode: pc.value }),
  }).catch(() => null);
  if (!r) return tell("Nothing answered at that address", true);
  if (r.status === 401) return tell("That passcode does not match", true);
  if (!r.ok) return tell("jobbot answered " + r.status, true);
  const { key } = await r.json();
  if (!key) return tell("jobbot did not send a key", true);
  await chrome.storage.local.set({ base: where, key });
  pc.value = "";
  tell("Connected. Open an application and jobbot will be in the corner.");
});

pc.addEventListener("keydown", (e) => { if (e.key === "Enter") document.getElementById("save").click(); });
