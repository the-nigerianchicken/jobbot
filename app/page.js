/**
 * The page: a list of jobs beside the job itself.
 *
 * On a laptop the posting sits on the right, in full, next to the list - the
 * way every job site worth using works - so reading a description is never a
 * tap away. On a phone the list fills the screen and a job opens over it.
 * The look is deliberately quiet: one typeface, neutral greys, real company
 * logos, and colour only where it means something.
 */
export const PAGE = String.raw`<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#f7f7f8"><link rel="manifest" href="/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="jobbot">
<link rel="apple-touch-icon" href="/icon.png"><link rel="icon" href="/icon.png" type="image/png">
<title>jobbot</title>
<script>
  // Appearance is kept on this device, and applied before anything is drawn.
  try {
    const look = JSON.parse(localStorage.getItem("jobbot-look") || "{}");
    if (look.theme && look.theme !== "system") document.documentElement.dataset.theme = look.theme;
    if (look.accent && look.accent !== "graphite") document.documentElement.dataset.accent = look.accent;
  } catch (e) { /* storage unavailable: the phone's own setting applies */ }
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  /* Appearance is chosen in Settings: a mode (follow the phone, light, dark,
     or dim - a softer dark for reading at night) and an accent for the one
     button that matters on each screen. */
  :root {
    color-scheme: light;
    --bg:#f7f7f8; --panel:#ffffff; --line:#e7e7ea; --line-2:#d9d9de; --hover:#f3f3f5; --sel:#eeeef1;
    --text:#18181b; --text-2:#52525b; --text-3:#8b8b94;
    --primary:#18181b; --on-primary:#ffffff; --accent:#2563eb;
    --blue:#2563eb; --amber:#c2410c; --amber-bg:#fff7ed; --green:#15803d; --violet:#6d28d9; --red:#dc2626;
    --font: "Geist", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --rail: 420px;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme]) {
      color-scheme: dark;
      --bg:#09090b; --panel:#111114; --line:#232328; --line-2:#2f2f35; --hover:#18181c; --sel:#1d1d22;
      --text:#fafafa; --text-2:#b4b4bc; --text-3:#7d7d86;
      --primary:#fafafa; --on-primary:#09090b; --accent:#60a5fa;
      --blue:#60a5fa; --amber:#fb923c; --amber-bg:#221811; --green:#4ade80; --violet:#a78bfa; --red:#f87171;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --bg:#09090b; --panel:#111114; --line:#232328; --line-2:#2f2f35; --hover:#18181c; --sel:#1d1d22;
    --text:#fafafa; --text-2:#b4b4bc; --text-3:#7d7d86;
    --primary:#fafafa; --on-primary:#09090b; --accent:#60a5fa;
    --blue:#60a5fa; --amber:#fb923c; --amber-bg:#221811; --green:#4ade80; --violet:#a78bfa; --red:#f87171;
  }
  :root[data-theme="dim"] {
    color-scheme: dark;
    --bg:#1c1f24; --panel:#23272e; --line:#323740; --line-2:#3d434d; --hover:#2a2f37; --sel:#303641;
    --text:#e6e8eb; --text-2:#aeb4bd; --text-3:#808792;
    --primary:#e6e8eb; --on-primary:#1c1f24; --accent:#7aa7ff;
    --blue:#7aa7ff; --amber:#f0a868; --amber-bg:#2e2923; --green:#6fcf97; --violet:#b39dff; --red:#f28b82;
  }
  :root[data-accent="blue"]   { --primary:#2563eb; --on-primary:#ffffff; --accent:#2563eb; }
  :root[data-accent="teal"]   { --primary:#0f766e; --on-primary:#ffffff; --accent:#0f766e; }
  :root[data-accent="green"]  { --primary:#15803d; --on-primary:#ffffff; --accent:#15803d; }
  :root[data-accent="violet"] { --primary:#6d28d9; --on-primary:#ffffff; --accent:#6d28d9; }
  :root[data-accent="rose"]   { --primary:#e11d48; --on-primary:#ffffff; --accent:#e11d48; }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html, body { height:100%; }
  body { margin:0; background:var(--bg); color:var(--text); font:400 14px/1.45 var(--font);
         -webkit-font-smoothing:antialiased; }
  button, input, select, textarea { font:inherit; color:inherit; }
  button, a { cursor:pointer; }
  button:disabled { cursor:default; opacity:.5; }
  :focus-visible { outline:2px solid var(--blue); outline-offset:1px; border-radius:6px; }
  a { color:inherit; }

  /* ------------------------------------------------------------ top bar -- */
  .top { height:56px; display:flex; align-items:center; gap:18px; padding:0 20px;
         background:var(--panel); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:10; }
  .brand { font-weight:700; font-size:16px; letter-spacing:-.3px; }
  .seg { display:flex; background:var(--hover); border-radius:8px; padding:3px; }
  .seg button { border:0; background:none; padding:5px 12px; border-radius:6px; font-size:13px;
                font-weight:500; color:var(--text-2); }
  .seg button.on { background:var(--panel); color:var(--text); box-shadow:0 1px 2px rgba(0,0,0,.08); }
  .beat-row { display:flex; align-items:center; gap:10px; min-height:18px; }
  .working { display:flex; align-items:center; gap:7px; font-size:12px; color:var(--text-2); }
  .broken { font-size:12px; color:var(--red); }
  .broken a { color:inherit; }
  .spin { width:11px; height:11px; border-radius:50%; border:1.6px solid var(--line-2);
    border-top-color:var(--accent); animation:spin .8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .spin { animation-duration:2.4s; } }
  .beat { font-size:12px; color:var(--text-3); white-space:nowrap; }
  .beat.cold { color:var(--amber); }

  /* ------------------------------------------------------------- layout -- */
  .shell { display:grid; grid-template-columns:var(--rail) 1fr; height:calc(100vh - 56px); }
  .rail { background:var(--panel); border-right:1px solid var(--line); overflow-y:auto; }
  .detail { overflow-y:auto; }

  /* ---------------------------------------------------------- the list -- */
  .tools { position:sticky; top:0; z-index:2; background:var(--panel); padding:12px 14px 10px;
           border-bottom:1px solid var(--line); display:flex; flex-direction:column; gap:10px; }
  .search { display:flex; gap:8px; }
  .search input { flex:1; min-width:0; height:34px; padding:0 11px; border:1px solid var(--line-2); border-radius:8px;
                  background:var(--panel); font-size:13.5px; }
  .search input:focus { outline:none; border-color:var(--text-3); }
  .chips { display:flex; gap:6px; flex-wrap:wrap; }
  .chips button .n { color:inherit; opacity:.6; font-variant-numeric:tabular-nums; margin-left:2px; }
  .chips button:disabled { opacity:.4; cursor:default; }
  .viewbar { display:flex; gap:8px; align-items:center; margin-top:10px; }
  .fbtn { height:32px; padding:0 12px; border:1px solid var(--line-2); border-radius:8px; background:var(--panel);
    font-size:13px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
  .fbtn:hover, .fbtn.open { border-color:var(--text-3); }
  .fbtn .badge { min-width:18px; height:18px; padding:0 5px; border-radius:9px; background:var(--primary);
    color:var(--on-primary); font-size:11px; display:inline-flex; align-items:center; justify-content:center; }
  #sort { height:32px; padding:0 8px; border:1px solid var(--line-2); border-radius:8px; background:var(--panel);
    font-size:13px; min-width:0; flex:1; max-width:220px; }
  .viewbar .small { height:32px; margin-left:auto; font-size:13px; }
  .fpanel { margin-top:10px; display:flex; flex-direction:column; gap:12px; padding-top:10px; border-top:1px solid var(--line); }
  .ftitle { font-size:12px; color:var(--text-3); margin-bottom:6px; }
  .chips.active { margin-top:10px; align-items:center; }
  .slide-l { animation:from-right .16s ease-out; }
  .slide-r { animation:from-left .16s ease-out; }
  @keyframes from-right { from { transform:translateX(18px); opacity:.6; } }
  @keyframes from-left { from { transform:translateX(-18px); opacity:.6; } }
  @media (prefers-reduced-motion: reduce) { .slide-l, .slide-r { animation:none; } }
  .unread { display:inline-block; width:7px; height:7px; border-radius:50%; background:var(--accent);
    margin-left:7px; vertical-align:middle; }
  /* What a swipe reveals under the row. */
  .swipe { position:relative; overflow:hidden; }
  .swipe::before { content:attr(data-label); position:absolute; inset:0; display:flex; align-items:center;
    padding:0 20px; font-size:13px; font-weight:600; color:#fff; opacity:0; }
  .swipe[data-side="left"]::before { justify-content:flex-end; background:var(--red); opacity:1; }
  .swipe[data-side="right"]::before { justify-content:flex-start; background:var(--primary);
    color:var(--on-primary); opacity:1; }
  .swipe .row { position:relative; background:var(--panel); }
  .chips button { border:1px solid var(--line-2); background:var(--panel); border-radius:999px;
                  padding:3px 10px; font-size:12.5px; color:var(--text-2); }
  .chips button:hover { color:var(--text); border-color:var(--text-3); }
  .chips button.on { background:var(--primary); border-color:var(--primary); color:var(--on-primary); }
  .ghost { border:1px solid var(--line-2); background:var(--panel); border-radius:8px; padding:0 11px;
           height:34px; font-size:13px; font-weight:500; color:var(--text-2); white-space:nowrap; }
  .ghost:hover { background:var(--hover); color:var(--text); }

  .zones { display:flex; gap:4px; margin-top:12px; overflow-x:auto; scrollbar-width:none; }
  .zones::-webkit-scrollbar { display:none; }
  .zones button { flex:none; border:0; background:none; color:var(--text-2); font-size:13.5px; font-weight:500;
    padding:6px 10px; border-radius:8px; cursor:pointer; white-space:nowrap; }
  .zones button:hover { background:var(--hover); color:var(--text); }
  .zones button.on { background:var(--sel); color:var(--text); }
  .zones button .n { color:var(--text-3); font-variant-numeric:tabular-nums; }
  .zones button.urgent .n { background:var(--red); color:#fff; border-radius:9px; padding:0 6px; }
  .finish .steps { margin:0; padding:0 0 0 20px; display:flex; flex-direction:column; gap:14px; }
  .finish .steps li { font-size:13.5px; line-height:1.5; color:var(--text-2); }
  .finish .steps .row-btns { margin-top:8px; }
  .group { padding:14px 16px 6px; font-size:12px; font-weight:600; color:var(--text-3);
           display:flex; gap:6px; align-items:center; }
  .group .n { font-weight:500; }
  .row { width:100%; display:flex; gap:12px; padding:12px 16px; border:0; background:none; text-align:left;
         border-left:2px solid transparent; }
  .row + .row { box-shadow:inset 0 1px 0 var(--line); }
  .row:hover { background:var(--hover); }
  .row.sel { background:var(--sel); border-left-color:var(--primary); }
  .row .main { flex:1; min-width:0; display:block; }
  .row .main > span { display:block; }
  .row .main > .line1, .row .main > .line3 { display:flex; }
  .line1 { align-items:baseline; gap:8px; }
  .co { font-weight:600; font-size:14px; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .age { font-size:12px; color:var(--text-3); flex:none; font-variant-numeric:tabular-nums; }
  .title { color:var(--text-2); font-size:13.5px; margin-top:1px; display:-webkit-box; -webkit-line-clamp:2;
           -webkit-box-orient:vertical; overflow:hidden; }
  .row .main > .title { display:-webkit-box; }
  .line3 { margin-top:4px; font-size:12px; color:var(--text-3); gap:10px; white-space:nowrap; overflow:hidden; }
  .line3 span { overflow:hidden; text-overflow:ellipsis; }
  .why { margin-top:5px; font-size:12.5px; color:var(--amber); font-weight:500; }
  .tick { flex:none; width:18px; height:18px; border-radius:5px; border:1.5px solid var(--line-2); margin-top:2px; }
  .row.picked .tick { background:var(--primary); border-color:var(--primary); }
  .held { margin-top:16px; border-top:1px solid var(--line); }
  .held-row { display:flex; gap:12px; align-items:flex-start; padding:14px 0; border-bottom:1px solid var(--line); }
  .held-row .main { flex:1; min-width:0; display:flex; flex-direction:column; gap:2px; }
  .held-row .line1 { display:flex; justify-content:space-between; gap:8px; }
  .held-row .line3 { display:flex; flex-wrap:wrap; gap:4px 12px; color:var(--text-3); font-size:13px; }
  .held-do { display:flex; gap:8px; flex-shrink:0; }
  .held-why { margin-top:14px; flex-wrap:wrap; }
  .held-detail { color:var(--text-3); font-size:13px; }
  @media (max-width: 600px) { .held-row { flex-wrap:wrap; } .held-do { width:100%; padding-left:44px; } }
  .foot { padding:16px; display:flex; gap:14px; flex-wrap:wrap; border-top:1px solid var(--line); }
  .link { background:none; border:0; padding:0; color:var(--text-2); font-size:12.5px;
          text-decoration:underline; text-underline-offset:3px; text-decoration-color:var(--line-2); }
  .link:hover { color:var(--text); text-decoration-color:currentColor; }
  .none { padding:48px 24px; text-align:center; color:var(--text-3); }
  .skel { padding:14px 16px; display:flex; flex-direction:column; gap:18px; }
  .skel i { display:block; height:44px; border-radius:10px;
    background:linear-gradient(90deg, var(--hover) 25%, var(--line) 37%, var(--hover) 63%);
    background-size:400% 100%; animation:sweep 1.4s ease-in-out infinite; }
  @keyframes sweep { from { background-position:100% 0; } to { background-position:0 0; } }
  .none b { display:block; color:var(--text); font-size:15px; margin-bottom:4px; }

  .logo { flex:none; width:36px; height:36px; border-radius:8px; border:1px solid var(--line);
          background:var(--panel); position:relative; overflow:hidden; display:flex;
          align-items:center; justify-content:center; font-weight:600; font-size:13px; color:var(--text-2); }
  .logo img { position:absolute; inset:5px; width:calc(100% - 10px); height:calc(100% - 10px);
              object-fit:contain; background:var(--panel); }
  .logo.big { width:52px; height:52px; border-radius:11px; font-size:18px; }
  .logo.big img { inset:8px; width:calc(100% - 16px); height:calc(100% - 16px); }

  /* -------------------------------------------------------- the posting -- */
  .d { max-width:880px; margin:0 auto; padding:28px 36px 80px; }
  .back { display:none !important; }
  .d-head { display:flex; gap:16px; align-items:flex-start; }
  .d-co { font-size:14px; font-weight:500; color:var(--text-2); }
  .d-title { margin:2px 0 0; font-size:24px; line-height:1.2; font-weight:650; letter-spacing:-.4px; }
  .d-meta { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; }
  .tag { font-size:12px; color:var(--text-2); background:var(--hover); border-radius:6px; padding:3px 8px; }
  .tag.follow { color:var(--blue); }
  .actions > .menu { position:absolute; top:calc(100% - 6px); right:36px; margin:0; min-width:240px; max-width:calc(100vw - 36px);
    max-height:min(60vh, 460px); overflow:auto; z-index:6; box-shadow:0 12px 32px rgba(0,0,0,.22); }
  .actions { position:sticky; top:0; z-index:3; background:var(--bg); margin:20px -36px 0; padding:12px 36px;
             display:flex; gap:8px; flex-wrap:wrap; border-bottom:1px solid var(--line); }
  .btn { height:36px; padding:0 14px; border-radius:8px; border:1px solid var(--line-2); background:var(--panel);
         font-size:13.5px; font-weight:500; display:inline-flex; align-items:center; gap:6px;
         text-decoration:none; color:var(--text); }
  .btn:hover { background:var(--hover); }
  .btn:active { transform:scale(.97); }
  .btn.busy { position:relative; color:transparent; }
  .btn.busy::after { content:""; position:absolute; left:50%; top:50%; width:14px; height:14px; margin:-7px 0 0 -7px;
    border-radius:50%; border:2px solid currentColor; border-top-color:transparent; animation:spin .7s linear infinite;
    color:var(--text-2); }
  .btn.primary.busy::after { color:var(--on-primary); }
  .btn.primary { background:var(--primary); border-color:var(--primary); color:var(--on-primary); }
  .btn.primary:hover { opacity:.88; background:var(--primary); }
  .btn.danger { color:var(--red); }
  .menu { margin-top:8px; background:var(--panel); border:1px solid var(--line); border-radius:10px;
          overflow:hidden; display:flex; flex-direction:column; max-width:320px; }
  .menu button { text-align:left; background:none; border:0; padding:10px 14px; font-size:13.5px; }
  .menu button:hover { background:var(--hover); }
  .menu button + button { border-top:1px solid var(--line); }
  .menu .danger { color:var(--red); }
  .notice { margin-top:18px; padding:12px 14px; border-radius:10px; background:var(--amber-bg);
            color:var(--amber); font-weight:500; font-size:13.5px; }
  .sec { margin-top:32px; }
  details.fold > summary { list-style:none; cursor:pointer; display:flex; align-items:baseline; gap:8px;
    padding-bottom:4px; }
  details.fold > summary::-webkit-details-marker { display:none; }
  details.fold > summary::before { content:"\25b8"; color:var(--text-3); font-size:11px; transition:transform .12s; }
  details.fold[open] > summary::before { transform:rotate(90deg); }
  details.fold > summary h2 { margin:0; }
  details.fold > summary .hint { font-size:12px; color:var(--text-3); margin-left:auto; }
  .sec h2 { margin:0 0 12px; font-size:13px; font-weight:600; color:var(--text-2); }
  .jd { font-size:15px; line-height:1.65; color:var(--text); max-width:70ch; }
  .jd p { margin:0 0 12px; }
  .jd ul { margin:0 0 14px; padding-left:20px; }
  .jd li { margin:3px 0; }
  .jd .h { font-weight:600; margin:18px 0 6px; }
  .quiet { color:var(--text-3); font-size:13.5px; }
  .said { border-left:2px solid var(--accent); padding-left:14px; }
  .said p { margin:0 0 6px; font-size:13.5px; line-height:1.5; }
  .coined { margin:12px 0; padding:12px 14px; border:1px solid var(--line-2); border-radius:10px; background:var(--panel); }
  .coined b { font-size:13px; }
  .coined p { margin:2px 0 10px; font-size:12.5px; color:var(--text-3); }
  .cnum { display:flex; gap:10px; padding:6px 0; font-size:13px; align-items:baseline; }
  .cnum + .cnum { border-top:1px solid var(--line); }
  .cnum .num { font-weight:600; white-space:nowrap; }
  .cnum .hint { color:var(--text-3); font-style:normal; font-size:12px; }
  .paper { display:block; width:100%; max-width:640px; border:1px solid var(--line); border-radius:10px; background:#fff; }
  .box { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:4px 16px; }
  .qa > div { padding:12px 0; }
  .qa > div + div { border-top:1px solid var(--line); }
  .q { display:flex; gap:12px; align-items:baseline; font-size:12.5px; color:var(--text-3); }
  .q span { flex:1; }
  .a { margin-top:3px; font-size:14px; word-break:break-word; border-radius:6px; padding:2px 6px; margin-left:-6px;
       cursor:copy; }
  .a:hover { background:var(--hover); }
  .mine { color:var(--blue); font-size:11.5px; font-weight:600; }
  textarea { width:100%; min-height:110px; padding:10px 12px; border:1px solid var(--line-2); border-radius:10px;
             background:var(--panel); font-size:14px; line-height:1.5; resize:vertical; }
  textarea:focus, .field input:focus, .field select:focus { outline:none; border-color:var(--text-3); }
  .row-btns { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap; }
  .shots img { display:block; max-width:100%; border:1px solid var(--line); border-radius:10px; margin-bottom:10px; }
  .empty-d { height:100%; min-height:300px; display:flex; align-items:center; justify-content:center; color:var(--text-3); }

  /* ------------------------------------------------------ applications -- */
  .field { display:flex; align-items:center; gap:14px; padding:10px 0; }
  .field + .field { border-top:1px solid var(--line); }
  .field label { flex:0 0 110px; font-size:13px; color:var(--text-2); }
  .field input, .field select { flex:1; min-width:0; height:34px; padding:0 10px; border:1px solid var(--line-2);
                                border-radius:8px; background:var(--panel); font-size:13.5px; }
  .field textarea { flex:1; min-height:80px; }
  .out { font-size:12px; font-weight:500; color:var(--text-3); flex:none; }
  .out.o-OA, .out.o-interview { color:var(--violet); }
  .out.o-offer, .out.o-accepted { color:var(--green); }
  .stats { display:flex; gap:18px; font-size:12.5px; color:var(--text-3); flex-wrap:wrap; }
  .stats b { color:var(--text); font-weight:600; }

  /* ----------------------------------------------------------- settings -- */
  .gear { height:34px; width:34px; padding:0; margin-left:0; display:inline-flex; align-items:center;
    justify-content:center; border-radius:9px; }
  .gear svg { width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:1.4;
    stroke-linecap:round; stroke-linejoin:round; }
  .beat + .gear { margin-left:12px; }
  .opts { display:flex; gap:8px; flex-wrap:wrap; }
  .menu-head { padding:10px 14px 6px; font-size:12px; color:var(--text-3); }
  .learn { margin:12px 12px 4px; padding:14px; border:1px solid var(--line-2); border-radius:12px; background:var(--panel); }
  .learn-text { font-size:13.5px; line-height:1.45; }
  .learn-ex { margin-top:6px; font-size:12px; color:var(--text-3); line-height:1.5; }
  .learn-do { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
  .learn-do .btn { height:32px; font-size:13px; }
  .settings .sub { margin:16px 0 8px; font-size:13px; color:var(--text-2); }
  .usage { display:flex; flex-direction:column; gap:6px; }
  .use-row { display:grid; grid-template-columns:minmax(0, 1.4fr) 1fr 44px; gap:12px; align-items:center; font-size:13px; }
  .use-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .use-bar { height:6px; background:var(--hover); border-radius:3px; overflow:hidden; }
  .use-bar i { display:block; height:100%; background:var(--primary); }
  .use-n { text-align:right; color:var(--text-3); font-variant-numeric:tabular-nums; }
  .settings { padding-bottom:96px; }
  .set-tabs { margin-top:16px; }
  .set-tabs .dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--accent);
    vertical-align:middle; margin-left:2px; }
  .settings .help { margin:-4px 0 12px; }
  .settings .grow { flex:1; min-width:0; display:flex; flex-direction:column; gap:4px; }
  .settings .grow input { width:100%; }
  .settings .hint { font-size:12px; color:var(--text-3); font-weight:400; }
  .settings .field.col { flex-direction:column; align-items:stretch; gap:6px; }
  .settings .field.col label { flex:none; }
  .settings .field label { flex-basis:150px; }
  .settings .opt.on { border-color:var(--primary); box-shadow:inset 0 0 0 1px var(--primary); }
  .toggle { display:flex; gap:12px; align-items:flex-start; padding:10px 0; cursor:pointer; }
  .toggle + .toggle { border-top:1px solid var(--line); }
  .toggle input { margin-top:3px; width:16px; height:16px; accent-color:var(--primary); flex:none; }
  .toggle > span { display:flex; flex-direction:column; gap:2px; font-size:14px; }
  .toggle b { font-weight:500; }
  .words { display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding:8px; border:1px solid var(--line-2);
    border-radius:10px; background:var(--panel); }
  .words span { display:inline-flex; align-items:center; gap:2px; padding:3px 4px 3px 10px; border-radius:999px;
    background:var(--hover); font-size:13px; }
  .words span button { border:0; background:none; color:var(--text-3); width:22px; height:22px; border-radius:50%; cursor:pointer; }
  .words span button:hover { color:var(--text); background:var(--line); }
  .words input { flex:1; min-width:160px; border:0; background:none; height:28px; padding:0 6px; }
  .words input:focus { outline:none; }
  .entry { border:1px solid var(--line-2); border-radius:10px; padding:0 14px; margin-bottom:8px; background:var(--panel); }
  .entry summary { cursor:pointer; padding:12px 0; display:flex; justify-content:space-between; gap:12px; list-style:none; }
  .entry summary::-webkit-details-marker { display:none; }
  .entry summary > span:first-child { display:flex; flex-direction:column; gap:2px; font-size:14px; }
  .entry[open] summary { border-bottom:1px solid var(--line); margin-bottom:6px; }
  .entry .off { font-size:12px; color:var(--text-3); white-space:nowrap; }
  .entry > .btn { margin:6px 0 14px; }
  .fact { padding:12px 0; border-bottom:1px solid var(--line); display:flex; flex-direction:column; gap:8px; }
  .fact textarea { min-height:0; }
  .fact-meta { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .fact-meta label { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--text-3); }
  .fact-meta input { height:34px; padding:0 10px; border:1px solid var(--line-2); border-radius:8px; background:var(--panel); }
  .fact .link { align-self:flex-start; }
  .link.danger { color:var(--red); }
  .skill { margin-bottom:12px; }
  .skill-name { font-size:13px; color:var(--text-2); margin-bottom:6px; }
  .reset-line { margin-top:28px; }
  .savebar { position:sticky; bottom:0; display:flex; align-items:center; gap:8px; margin:24px -4px 0;
    padding:12px 4px calc(12px + env(safe-area-inset-bottom, 0px)); background:var(--bg, var(--panel));
    border-top:1px solid var(--line); }
  .savebar[hidden] { display:none; }
  .savebar span { margin-right:auto; font-size:13px; color:var(--text-2); }
  @media (max-width: 600px) { .fact-meta { grid-template-columns:1fr; } .settings .field { flex-direction:column;
    align-items:stretch; gap:6px; } .settings .field label { flex:none; } }
  .opt { border:1px solid var(--line-2); background:var(--panel); border-radius:10px; padding:10px 14px;
         font-size:13.5px; font-weight:500; display:flex; align-items:center; gap:8px; }
  .opt:hover { background:var(--hover); }
  .opt.on { border-color:var(--primary); box-shadow:0 0 0 1px var(--primary); }
  .swatch { width:16px; height:16px; border-radius:50%; border:1px solid rgba(0,0,0,.12); }
  .follows { display:flex; flex-wrap:wrap; gap:6px; margin-top:12px; }
  .follows span { display:inline-flex; align-items:center; gap:6px; background:var(--panel);
                  border:1px solid var(--line-2); border-radius:999px; padding:4px 6px 4px 11px; font-size:13px; }
  .follows button { border:0; background:none; width:20px; height:20px; border-radius:50%; color:var(--text-3);
                    font-size:15px; line-height:18px; padding:0; }
  .follows button:hover { background:var(--hover); color:var(--red); }
  .addrow { display:flex; gap:8px; max-width:420px; }
  .addrow input { flex:1; min-width:0; height:36px; padding:0 11px; border:1px solid var(--line-2);
                  border-radius:8px; background:var(--panel); font-size:13.5px; }

  .toast { position:fixed; left:50%; bottom:calc(env(safe-area-inset-bottom) + 20px); transform:translateX(-50%);
           z-index:40; display:flex; align-items:center; gap:14px; background:var(--primary); color:var(--on-primary);
           padding:10px 14px; border-radius:10px; font-size:13.5px; box-shadow:0 6px 24px rgba(0,0,0,.18);
           max-width:calc(100vw - 32px); }
  .toast button { background:none; border:0; color:inherit; font-weight:600; text-decoration:underline; }

  .gate { max-width:320px; margin:18vh auto; padding:0 24px; }
  .gate h1 { font-size:26px; margin:0 0 6px; letter-spacing:-.4px; }
  .gate p { color:var(--text-2); margin:0 0 18px; }
  .gate input { width:100%; height:40px; padding:0 12px; border:1px solid var(--line-2); border-radius:8px;
                background:var(--panel); margin-bottom:10px; font-size:15px; }
  .gate .btn { width:100%; justify-content:center; height:40px; }

  /* ------------------------------------------------------------- phone -- */
  @media (max-width: 899px) {
    .top { padding:0 14px; gap:12px; }

    .shell { display:block; height:auto; }
    .rail { border-right:0; min-height:calc(100vh - 56px); }
    .detail { display:none; }
    body.reading .rail { display:none; }
    body.reading .detail { display:block; overflow:visible; }
    .d { padding:16px 18px 90px; }
    .back { display:inline-flex !important; margin-bottom:14px; }
    .d-title { font-size:21px; }
    /* The controls sit where his thumb is, above the tab bar, and the menus
       open upward from them. */
    body.reading .actions { position:fixed; left:0; right:0; top:auto; z-index:25;
      bottom:calc(64px + env(safe-area-inset-bottom, 0px)); margin:0; padding:10px 14px;
      display:flex; flex-wrap:nowrap; gap:8px; overflow-x:auto; scrollbar-width:none;
      background:color-mix(in srgb, var(--panel) 92%, transparent);
      -webkit-backdrop-filter:blur(16px); backdrop-filter:blur(16px);
      border-top:1px solid var(--line); border-bottom:0; }
    body.reading .actions::-webkit-scrollbar { display:none; }
    body.reading .actions .btn { flex:none; height:40px; }
    body.reading .actions > .menu { top:auto; bottom:calc(100% + 6px); right:14px; left:auto !important; }
    body.reading .d { padding-bottom:calc(150px + env(safe-area-inset-bottom, 0px)); }
    .row { padding:12px 14px; }
    .jd { font-size:15.5px; }
  }
  @media (prefers-reduced-motion: no-preference) {
    .toast { animation:rise .16s ease-out; }
    @keyframes rise { from { transform:translate(-50%, 8px); opacity:0; } }
  }

  /* --------------------------------------------------- on a phone, an app -- */
  .tabbar { display:none; }
  @media (max-width: 899px) {
    /* Nothing in the chrome is a web page: a title bar that gets out of the
       way, one screen at a time, and the controls under his thumb. */
    html, body { overscroll-behavior-y:none; }
    .top { height:auto; padding:calc(8px + env(safe-area-inset-top, 0px)) 16px 8px; gap:10px; }
    .brand { font-size:17px; }
    .top .seg, .top .gear { display:none; }
    .shell { min-height:0; }
    .rail, .d { padding-bottom:calc(76px + env(safe-area-inset-bottom, 0px)); }
    .tabbar { display:flex; position:fixed; left:0; right:0; bottom:0; z-index:30;
      padding:6px 8px calc(6px + env(safe-area-inset-bottom, 0px));
      background:color-mix(in srgb, var(--panel) 88%, transparent);
      -webkit-backdrop-filter:saturate(180%) blur(16px); backdrop-filter:saturate(180%) blur(16px);
      border-top:1px solid var(--line); }
    .tabbar button { flex:1; display:flex; flex-direction:column; align-items:center; gap:3px;
      border:0; background:none; padding:6px 0 4px; color:var(--text-3); font-size:11px; font-weight:500;
      border-radius:10px; }
    .tabbar button svg { width:22px; height:22px; fill:none; stroke:currentColor; stroke-width:1.7;
      stroke-linecap:round; stroke-linejoin:round; }
    .tabbar button[data-go="settings"] svg { stroke-width:1.4; }
    .tabbar button.on { color:var(--primary); }
    .tabbar button:active { background:var(--hover); }
    /* Opening a job fades in. It cannot move: a transform on this element
       would make it the anchor for the fixed action bar inside it. */
    body.reading .detail { animation:open-in .18s ease-out; }
    @keyframes open-in { from { opacity:0; } }
    .pull { position:absolute; left:0; right:0; top:0; display:flex; justify-content:center;
      padding-top:8px; color:var(--text-3); font-size:12px; pointer-events:none; opacity:0; transition:opacity .15s; }
    .pull.on { opacity:1; }
  }
  /* A tap should feel like a tap: no grey flash, no text selected by accident,
     no 300ms wait. */
  button, .row, .btn, .chips button, .tabbar button, .zones button { -webkit-tap-highlight-color:transparent;
    touch-action:manipulation; user-select:none; -webkit-user-select:none; }
  .jd, .a, textarea, input, .coined, .qa { user-select:text; -webkit-user-select:text; }
  .rail, .detail { overscroll-behavior:contain; -webkit-overflow-scrolling:touch; }
  @media (prefers-reduced-motion: reduce) {
    body.reading .detail { animation:none; }
  }
</style></head><body>
<div class="top">
  <div class="brand">jobbot</div>
  <div class="seg" id="tabs"><button data-tab="jobs" class="on">Jobs</button><button data-tab="apps">Applied</button></div>

  <button class="ghost gear" id="settings" aria-label="Settings" title="Settings"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.49 10.32 L21.72 9.67 L21.72 14.33 L18.49 13.68 L16.70 16.78 L18.88 19.25 L14.84 21.59 L13.79 18.46 L10.21 18.46 L9.16 21.59 L5.12 19.25 L7.30 16.78 L5.51 13.68 L2.28 14.33 L2.28 9.67 L5.51 10.32 L7.30 7.22 L5.12 4.75 L9.16 2.41 L10.21 5.54 L13.79 5.54 L14.84 2.41 L18.88 4.75 L16.70 7.22 Z"/><circle cx="12" cy="12" r="3.5"/></svg></button>
</div>
<div class="shell">
  <aside class="rail" id="rail"><div class="skel"><i></i><i></i><i></i><i></i><i></i><i></i></div></aside>
  <main class="detail" id="detail"><div class="empty-d">Pick a job to read the posting.</div></main>
</div>
<nav class="tabbar" id="tabbar">
  <button data-go="jobs" class="on"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg><span>Jobs</span></button>
  <button data-go="apps"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5L19 7"/></svg><span>Applied</span></button>
  <button data-go="settings"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.49 10.32 L21.72 9.67 L21.72 14.33 L18.49 13.68 L16.70 16.78 L18.88 19.25 L14.84 21.59 L13.79 18.46 L10.21 18.46 L9.16 21.59 L5.12 19.25 L7.30 16.78 L5.51 13.68 L2.28 14.33 L2.28 9.67 L5.51 10.32 L7.30 7.22 L5.12 4.75 L9.16 2.41 L10.21 5.54 L13.79 5.54 L14.84 2.41 L18.88 4.75 L16.70 7.22 Z"/><circle cx="12" cy="12" r="3.5"/></svg><span>Settings</span></button>
</nav>
<script>
// New postings stand on their own: they are what he came to look at, and used
// to sit among jobs already under way.
// New postings get the screen to themselves; the rest are a tap away, with
// their counts always in view so nothing waiting on him can hide.
const ZONES = [
  ["new", "New", [["new", ""]]],
  ["needs", "Needs you", [["needs", ""]]],
  ["progress", "In progress", [["ready", "Resume ready"], ["building", "Writing your resume"], ["working", "Applying"]]],
  ["done", "Applied", [["done", ""]]],
  ["all", "All", [["new", "New"], ["needs", "Needs you"], ["ready", "Resume ready"],
                  ["building", "Writing your resume"], ["working", "Applying"], ["done", "Applied this week"]]],
];
const OUTCOMES = ["no response","OA","interview","offer","accepted","rejected","withdrawn"];
// How the list is narrowed and ordered. Remembered on this device.
const SEASON_RANK = { Winter: 0, Spring: 1, Summer: 2, Fall: 3 };
const SORTS = [["new", "Newest first"], ["follow", "Companies you follow first"], ["az", "Company A to Z"]];
const POSTED = [["1", "Last 24 hours", 24], ["3", "Last 3 days", 72], ["7", "This week", 168]];
const ROLES = [
  ["ai", "AI and machine learning", /\b(ai|ml|machine learning|deep learning|llm|nlp|genai|generative|computer vision|applied scien|research)/i],
  ["data", "Data", /\bdata\b/i],
  ["back", "Backend and infrastructure", /back[ -]?end|infra|platform|cloud|devops|site reliab|\bsre\b|distributed|database|storage|\bapi\b/i],
  ["front", "Frontend, full stack and mobile", /front[ -]?end|full[ -]?stack|\bweb\b|\bui\b|mobile|\bios\b|android/i],
  ["embedded", "Embedded and robotics", /embedded|firmware|robot|autonom|hardware|fpga|c\+\+/i],
  ["security", "Security", /secur|cyber/i],
];
const CANADA_RE = /\b(canada|ontario|toronto|vancouver|montr[eé]al|waterloo|ottawa|calgary|edmonton|mississauga|markham|kitchener|burnaby|halifax|winnipeg|quebec|victoria, bc)\b|,\s*(ON|BC|QC|AB|MB|NS|NB|SK|NL|PE)\b/i;
const US_RE = /\b(united states|usa|u\.s\.|nyc|sf|new york|san francisco|seattle|boston|austin|chicago)\b|,\s*(?!ON\b|BC\b|QC\b|AB\b|MB\b|NS\b|NB\b|SK\b|NL\b|PE\b)[A-Z]{2}\b/;
function places(j) {
  const loc = String(j.location || "");
  const out = new Set();
  if (CANADA_RE.test(loc)) out.add("canada");
  if (/remote/i.test(loc)) out.add("remote");
  if (US_RE.test(loc) || (loc && !out.size)) out.add("us");
  return out;
}
const roles = (j) => { const r = ROLES.filter(([, , re]) => re.test(j.title || "")).map(([k]) => k); return r.length ? r : ["general"]; };
const terms = (j) => (j.term ? String(j.term).split(" / ") : ["none"]);
let view = { zone: "new", sort: "new", where: [], term: [], role: [], posted: "", follow: false, unopened: false };
try { view = { ...view, ...JSON.parse(localStorage.getItem("jobbot-view") || "{}") }; } catch (e) { /* defaults */ }
let opened = new Set();
try { opened = new Set(JSON.parse(localStorage.getItem("jobbot-opened") || "[]")); } catch (e) { /* none yet */ }
let filtersOpen = false;
const saveView = () => { try { localStorage.setItem("jobbot-view", JSON.stringify(view)); } catch (e) { /* this visit */ } };
function markOpened(uid) {
  opened.add(uid);
  try { localStorage.setItem("jobbot-opened", JSON.stringify([...opened].slice(-2000))); } catch (e) { /* this visit */ }
}

let tab = "jobs", jobs = [], apps = { rows: [], stats: {}, total: 0 };
let current = null, find = "", region = "", showArchived = false, showSnoozed = false;
let selecting = false, picked = new Set(), checked = null, snoozedCount = 0, muted = [];
let appFind = "", appOutcome = "", menuOpen = false, following = [];
let pane = "job", filteredCount = 0, busyNow = [], waitingOn = null, owner = "";

/* -------------------------------------------------------------- helpers -- */
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;" }[c]));
const enc = encodeURIComponent;
const key = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const real = (v) => { const s = String(v ?? "").trim(); return s && !/^(none|n\/a|-|null)$/i.test(s) ? s : ""; };
const pretty = (name) => String(name || "").split(/[\s_-]+/).map((w) => (w ? w[0].toUpperCase() + w.slice(1) : "")).join(" ");
const phone = () => window.matchMedia("(max-width: 899px)").matches;

function age(iso) {
  if (!iso) return "";
  const h = (Date.now() - new Date(iso)) / 36e5;
  if (h < 1) return Math.max(1, Math.round(h * 60)) + "m";
  if (h < 24) return Math.round(h) + "h";
  const d = Math.round(h / 24);
  return d < 7 ? d + "d" : Math.round(d / 7) + "w";
}
const ago = (iso) => { const a = age(iso); return a ? "Posted " + a + " ago" : ""; };
const day = (s) => { const d = new Date((s || "") + "T12:00:00");
  return isNaN(d) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }); };
const month = (s) => { const d = new Date((s || "") + "T12:00:00");
  return isNaN(d) ? "Undated" : d.toLocaleDateString(undefined, { month: "long", year: "numeric" }); };

// A company's own site, from the posting's link or, failing that, its name.
const HOSTED = /greenhouse|lever\.co|ashbyhq|myworkdayjobs|icims|oraclecloud|smartrecruiters|jobvite|workable|rippling|eightfold|bamboohr|paylocity|successfactors|taleo|simplify|linkedin|indeed|dayforce|ultipro|adp\.com/;
// Where the name alone guesses wrong.
const KNOWN = { scaleai: "scale.com", togetherai: "together.ai", openai: "openai.com", xai: "x.ai",
                janestreet: "janestreet.com", twosigma: "twosigma.com", hudsonrivertrading: "hudsonrivertrading.com" };
// Named the way recruiters expect to receive it: Ada_Lovelace_Resume_Mercury.pdf
function saveUrl(pdf, company) {
  return "/file?path=" + enc(pdf) + "&save=" + enc((owner ? owner + " " : "") + "Resume " + (company || ""));
}
const pdfName = (company) => ((owner ? owner + " " : "") + "Resume " + (company || ""))
  .replace(/[^A-Za-z0-9 _.-]+/g, "").replace(/\s+/g, "_") + ".pdf";

// On a phone a downloaded file used to open in the app itself, with no way out
// and nowhere to save it. Handing the file to the phone puts it in the share
// sheet instead: Save to Files, Mail, anywhere.
const pdfWarm = new Map();
function warmPdf(path, company) {
  if (!pdfWarm.has(path)) pdfWarm.set(path, fetch(saveUrl(path, company)).then((r) => r.blob()).catch(() => null));
  return pdfWarm.get(path);
}
async function savePdf(path, company) {
  const name = pdfName(company);
  let blob = null;
  try { blob = await warmPdf(path, company); } catch (e) { blob = null; }
  if (!blob) { window.open(saveUrl(path, company), "_blank"); return; }
  const file = new File([blob], name, { type: "application/pdf" });
  try {
    if (navigator.canShare && navigator.canShare({ files: [file] })) { await navigator.share({ files: [file] }); return; }
  } catch (e) {
    if (e && e.name === "AbortError") return;      // he closed the share sheet
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 20000);
}
function bindPdf(box) {
  box.querySelectorAll("[data-pdf]").forEach((b) => {
    const go = () => warmPdf(b.dataset.pdf, b.dataset.co);
    b.addEventListener("pointerdown", go);
    b.addEventListener("focus", go);
    b.onclick = () => savePdf(b.dataset.pdf, b.dataset.co);
  });
}

function domainFor(company, url) {
  const raw = String(company || "");
  const named = raw.toLowerCase().match(/\b[a-z0-9-]+\.(com|ai|io|co|ca|org|net)\b/);   // "Amazon.com Services LLC"
  if (named) return named[0];
  const name = key(raw.replace(/\b(inc|llc|ltd|corp|corporation|co|usa|canada|us|services|technologies|holdings|group)\b\.?/gi, ""));
  if (KNOWN[name]) return KNOWN[name];
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (!HOSTED.test(host)) {
      const parts = host.split(".").filter((p) => p !== "www" && p !== "careers" && p !== "jobs");
      if (parts.length >= 2) {
        const site = parts.slice(-2).join(".");
        // careers.withwaymo.com is Waymo's; waymo.com has the logo.
        return name && parts[parts.length - 2] !== name && parts[parts.length - 2].includes(name) ? name + ".com" : site;
      }
    }
  } catch (e) { /* no usable link */ }
  return name ? name + ".com" : "";
}
function logo(company, url, big) {
  const d = domainFor(company, url);
  const letter = esc((String(company || "?").trim()[0] || "?").toUpperCase());
  return '<span class="logo' + (big ? " big" : "") + '">' + letter +
    (d ? '<img alt="" loading="lazy" src="https://icons.duckduckgo.com/ip3/' + esc(d) + '.ico" onerror="this.remove()">' : "") +
    "</span>";
}

// Descriptions saved before line breaks were kept arrive as one long line.
// Break them where the posting itself changes subject: an all-caps heading,
// or a label like "Responsibilities:".
function unflatten(text) {
  if (text.includes("\n")) return text;
  return text
    .replace(/\s+((?:[A-Z][A-Z&/+-]{2,}\s){1,4}[A-Z][A-Z&/+-]{2,})\s+/g, "\n\n$1\n")
    .replace(/\s+((?:About|What|Who|Your|Key|Required|Preferred|Minimum|Basic|Our|Why|Benefits|Responsibilities|Requirements|Qualifications|Nice to have)[A-Za-z &',-]{0,40}:)\s*/g, "\n\n$1\n");
}

// The description as paragraphs and lists, the way the company wrote it.
function posting(text) {
  const lines = unflatten(String(text || "")).split("\n").map((l) => l.trim());
  let html = "", list = false;
  for (const line of lines) {
    if (!line) { continue; }
    const bullet = /^[•\-\*·▪◦]\s*/.test(line);
    if (bullet) {
      if (!list) { html += "<ul>"; list = true; }
      html += "<li>" + esc(line.replace(/^[•\-\*·▪◦]\s*/, "")) + "</li>";
      continue;
    }
    if (list) { html += "</ul>"; list = false; }
    const heading = line.length < 60 && !/[.,;]$/.test(line) && /^[A-Z]/.test(line) && line.split(" ").length <= 8;
    html += heading ? '<div class="h">' + esc(line) + "</div>" : "<p>" + esc(line) + "</p>";
  }
  return html + (list ? "</ul>" : "");
}

async function api(path, opts) {
  let r;
  try { r = await fetch(path, opts); }
  catch (e) { toast("No connection. Nothing was changed."); throw e; }
  if (r.status === 401) { gate(); throw new Error("locked"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { body.ok = false; body.failed = body.error || "That did not go through"; }
  return body;
}
const send = (path, method, body) => api(path, { method, headers: { "content-type": "application/json" },
                                                  body: JSON.stringify(body) });

let toastTimer = null;
function toast(text, undo, extra) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  clearTimeout(toastTimer);
  const t = document.createElement("div");
  t.className = "toast";
  const label = undo ? "Undo" : (extra ? extra.label : "");
  t.innerHTML = "<span></span>" + (label ? "<button></button>" : "");
  t.querySelector("span").textContent = text;
  if (label) {
    const b = t.querySelector("button");
    b.textContent = label;
    b.onclick = () => { t.remove(); (undo || extra.run)(); };
  }
  document.body.appendChild(t);
  toastTimer = setTimeout(() => t.remove(), label ? 6000 : 2600);
}

function gate(msg) {
  document.body.innerHTML = '<div class="gate"><h1>jobbot</h1><p>' + (msg || "Enter your passcode.") + "</p>" +
    '<input id="pc" type="password" autocomplete="current-password" placeholder="Passcode">' +
    '<button class="btn primary" id="in">Open</button></div>';
  const go = async () => {
    const r = await fetch("/api/login", { method:"POST", headers:{ "content-type":"application/json" },
      body: JSON.stringify({ passcode: document.getElementById("pc").value }) });
    if (r.ok) location.reload(); else gate("That passcode does not match.");
  };
  document.getElementById("in").onclick = go;
  document.getElementById("pc").addEventListener("keydown", (e) => e.key === "Enter" && go());
}

/* ------------------------------------------------------------ the list -- */

function followed(j) {
  if (!following.length) return j.tier === 1;
  const n = String(j.company || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  if (!n) return false;
  const words = new Set(n.split(" ")), whole = n.replace(/ /g, "");
  return following.some((f) => words.has(f.key) || whole === f.key);
}

// Each filter, as a test. "skip" leaves one out, for the counts beside its own
// options: how many he would see if he picked that option instead.
function passes(j, skip) {
  const needle = find.trim().toLowerCase();
  if (needle && !(j.company + " " + j.title + " " + (j.location || "")).toLowerCase().includes(needle)) return false;
  if (skip !== "where" && view.where.length && !view.where.some((w) => places(j).has(w))) return false;
  if (skip !== "term" && view.term.length && !view.term.some((t) => terms(j).includes(t))) return false;
  if (skip !== "role" && view.role.length && !view.role.some((r) => roles(j).includes(r))) return false;
  if (skip !== "posted" && view.posted) {
    const hours = POSTED.find(([k]) => k === view.posted)[2];
    if (!j.posted_at || Date.now() - new Date(j.posted_at) > hours * 3600e3) return false;
  }
  if (skip !== "follow" && view.follow && !followed(j)) return false;
  if (skip !== "unopened" && view.unopened && opened.has(j.uid)) return false;
  return true;
}
const activeFilters = () => view.where.length + view.term.length + view.role.length +
  (view.posted ? 1 : 0) + (view.follow ? 1 : 0) + (view.unopened ? 1 : 0);

function shown() {
  const list = jobs.filter((j) => passes(j));
  const newest = (a, b) => String(b.posted_at || "").localeCompare(String(a.posted_at || ""));
  const order = view.sort === "az" ? (a, b) => a.company.localeCompare(b.company) || newest(a, b)
    : view.sort === "follow" ? (a, b) => (followed(b) - followed(a)) || newest(a, b)
    : newest;
  return list.sort(order);
}

// The options for one filter, with how many jobs each would show.
const inZone = (j) => (ZONES.find(([k]) => k === view.zone) || ZONES[0])[2].some(([st]) => st === j.state);
function facet(name, options, has) {
  // Counted inside the tab he is on, so a number never promises jobs he
  // would not see.
  const pool = jobs.filter((j) => j.state !== "skipped" && inZone(j) && passes(j, name));
  return options.map(([k, label]) => [k, label, pool.filter((j) => has(j, k)).length]);
}
function filterPanel() {
  const chip = (group, k, label, n, on) => '<button class="' + (on ? "on" : "") + '" data-f="' + group + '" data-k="' +
    esc(k) + '"' + (n || on ? "" : " disabled") + ">" + esc(label) + ' <span class="n">' + n + "</span></button>";
  const termKeys = [...new Set(jobs.flatMap(terms))].sort((a, b) =>
    a === "none" ? 1 : b === "none" ? -1 : a.split(" ")[1] - b.split(" ")[1] || SEASON_RANK[a.split(" ")[0]] - SEASON_RANK[b.split(" ")[0]]);
  const groups = [
    ["Where", "where", facet("where", [["canada", "Canada"], ["us", "United States"], ["remote", "Remote"]], (j, k) => places(j).has(k))],
    ["Term", "term", facet("term", termKeys.map((t) => [t, t === "none" ? "Term not stated" : t]), (j, k) => terms(j).includes(k))],
    ["Role", "role", facet("role", ROLES.map(([k, l]) => [k, l]).concat([["general", "General software"]]), (j, k) => roles(j).includes(k))],
    ["Posted", "posted", facet("posted", POSTED.map(([k, l]) => [k, l]), (j, k) => j.posted_at &&
      Date.now() - new Date(j.posted_at) <= POSTED.find(([x]) => x === k)[2] * 3600e3)],
    ["Show only", "only", [["follow", "Companies you follow", jobs.filter((j) => j.state !== "skipped" && inZone(j) && passes(j, "follow") && followed(j)).length],
                           ["unopened", "Not opened yet", jobs.filter((j) => j.state !== "skipped" && inZone(j) && passes(j, "unopened") && !opened.has(j.uid)).length]]],
  ];
  const isOn = (g, k) => g === "posted" ? view.posted === k : g === "only" ? !!view[k] : view[g].includes(k);
  return '<div class="fpanel">' + groups.map(([title, g, opts]) => '<div class="fgroup"><div class="ftitle">' + title +
    '</div><div class="chips">' + opts.filter(([k, , n]) => n || isOn(g, k))
      .map(([k, l, n]) => chip(g, k, l, n, isOn(g, k))).join("") + "</div></div>").join("") +
    "</div>";
}
function activeChips() {
  const label = (g, k) => g === "where" ? { canada: "Canada", us: "United States", remote: "Remote" }[k]
    : g === "term" ? (k === "none" ? "Term not stated" : k)
    : g === "role" ? (ROLES.find(([x]) => x === k) || [k, "General software"])[1]
    : g === "posted" ? POSTED.find(([x]) => x === k)[1] : { follow: "Companies you follow", unopened: "Not opened yet" }[k];
  const on = [...view.where.map((k) => ["where", k]), ...view.term.map((k) => ["term", k]), ...view.role.map((k) => ["role", k]),
              ...(view.posted ? [["posted", view.posted]] : []), ...(view.follow ? [["only", "follow"]] : []),
              ...(view.unopened ? [["only", "unopened"]] : [])];
  if (!on.length) return "";
  return '<div class="chips active">' + on.map(([g, k]) => '<button class="on" data-f="' + g + '" data-k="' + esc(k) +
    '" title="Remove this filter">' + esc(label(g, k)) + " ×</button>").join("") +
    '<button class="link" id="clear-f">Clear all</button></div>';
}

function rowHtml(j) {
  const bits = [real(j.where), j.term].filter(Boolean).map((b) => "<span>" + esc(b) + "</span>").join("");
  return '<button class="row' + (current === j.uid ? " sel" : "") + (picked.has(j.uid) ? " picked" : "") +
    '" data-uid="' + esc(j.uid) + '">' +
    (selecting ? '<span class="tick"></span>' : logo(j.company, j.url || j.apply_url)) +
    '<span class="main"><span class="line1"><span class="co">' + esc(j.company) +
      (j.state === "new" && !opened.has(j.uid) ? '<i class="unread" title="Not opened yet"></i>' : "") + "</span>" +
      '<span class="age">' + age(j.posted_at) + "</span></span>" +
      '<span class="title">' + esc(j.title) + "</span>" +
      (bits ? '<span class="line3">' + bits + "</span>" : "") +
      (j.note && j.state !== "done" && j.state !== "new"
        ? '<span class="why">' + esc(j.note) + (j.since && (j.state === "building" || j.state === "working")
            ? " \u00b7 " + age(j.since) : "") + "</span>" : "") +
    "</span></button>";
}

function renderRail() {
  const rail = document.getElementById("rail");
  const list = shown();
  const zone = ZONES.find(([k]) => k === view.zone) || ZONES[0];
  const groups = zone[2].map(([state, label]) => {
    const some = list.filter((j) => j.state === state);
    return some.length ? (label ? '<div class="group">' + label + "</div>" : "") + some.map(rowHtml).join("") : "";
  }).join("");
  const archived = list.filter((j) => j.state === "skipped");
  const EMPTY = {
    new: ["Nothing new", "Postings appear here as jobbot finds them, within 15 minutes."],
    needs: ["Nothing needs you", "Applications that stop on a code or a question wait here."],
    progress: ["Nothing under way", "Tap Apply on a posting and its resume starts here."],
    done: ["Nothing applied this week", "Jobs you send go here, and to the Applied tab for good."],
    all: ["Nothing waiting", "New postings appear here on their own."],
  }[zone[0]];
  const empty = find || activeFilters()
    ? '<div class="none"><b>Nothing matches</b>Remove a filter or try fewer words.</div>'
    : '<div class="none"><b>' + EMPTY[0] + "</b>" + EMPTY[1] + "</div>";
  rail.innerHTML =
    '<div class="tools"><div class="search"><input id="q" placeholder="Search company, role or city" value="' +
      esc(find) + '"><button class="ghost" id="sel">' + (selecting ? "Done" : "Select") + "</button></div>" +
      '<div class="beat-row">' + (busyNow.some((b) => b.kind === "broken")
        ? '<span class="broken">jobbot\u2019s last check failed. ' +
          '<a href="' + esc((busyNow.find((b) => b.kind === "broken") || {}).url || "") +
          '" target="_blank" rel="noopener">See why</a></span>' +
          '<button class="link" id="recheck">Try again</button>'
        : busyNow.length
        ? '<span class="working"><i class="spin"></i>' + esc(busyNow.map((b) => b.says +
            (b.n > 1 ? " (" + b.n + ")" : "")).join(", ")) + "</span>"
        : '<span class="beat' + (checked && Date.now() - new Date(checked) > 75 * 60000 ? " cold" : "") + '">' +
          (checked ? "Boards checked " + age(checked) + " ago" : "Waiting for jobbot’s first check") +
          '</span><button class="link" id="recheck">Check now</button>') + "</div>" +
      '<div class="zones">' + ZONES.map(([k, label, states]) => {
        // Counted through his filters, so the number is what the tab will show.
        const n = jobs.filter((j) => states.some(([s]) => s === j.state) && j.state !== "skipped" && passes(j)).length;
        return '<button class="' + (view.zone === k ? "on" : "") + (k === "needs" && n ? " urgent" : "") +
          '" data-zone="' + k + '">' + label + (n ? ' <span class="n">' + n + "</span>" : "") + "</button>";
      }).join("") + "</div>" +
      '<div class="viewbar"><button class="fbtn' + (filtersOpen ? " open" : "") + '" id="ftoggle" aria-expanded="' +
        filtersOpen + '">Filters' + (activeFilters() ? ' <span class="badge">' + activeFilters() + "</span>" : "") + "</button>" +
        '<select id="sort" aria-label="Sort">' + SORTS.map(([k, l]) => '<option value="' + k + '"' +
          (view.sort === k ? " selected" : "") + ">" + l + "</option>").join("") + "</select>" +
        (picked.size ? '<button class="btn primary small" id="do-archive">Archive ' + picked.size + "</button>" : "") +
      "</div>" +
      (filtersOpen ? filterPanel() : activeChips()) +
    "</div>" +
    suggestionCard() +
    (groups || empty) +
    (showArchived && archived.length ? '<div class="group">Archived <span class="n">' + archived.length + "</span></div>" +
      archived.map(rowHtml).join("") : "") +
    '<div class="foot"><button class="link" id="arch">' + (showArchived ? "Hide archived" : "Show archived") + "</button>" +
      (snoozedCount || showSnoozed ? '<button class="link" id="naps">' +
        (showSnoozed ? "Hide snoozed" : "Snoozed (" + snoozedCount + ")") + "</button>" : "") +
      (muted.length ? '<button class="link" id="mutes">Muted companies (' + muted.length + ")</button>" : "") +
      (filteredCount ? '<button class="link" id="held">Filtered out (' + filteredCount + ")</button>" : "") +
    "</div>";

  const q = document.getElementById("q");
  q.oninput = debounce(() => { find = q.value; renderRail(); const box = document.getElementById("q");
    box.focus(); box.setSelectionRange(box.value.length, box.value.length); }, 180);
  document.getElementById("sel").onclick = () => { selecting = !selecting; picked.clear(); renderRail(); };
  rail.querySelectorAll("[data-zone]").forEach((b) => b.onclick = () => {
    view.zone = b.dataset.zone; saveView(); renderRail();
  });
  const again = document.getElementById("recheck");
  if (again) again.onclick = () => checkNow();
  document.getElementById("ftoggle").onclick = () => { filtersOpen = !filtersOpen; renderRail(); };
  document.getElementById("sort").onchange = (e) => { view.sort = e.target.value; saveView(); renderRail(); };
  rail.querySelectorAll("[data-f]").forEach((b) => b.onclick = () => {
    const g = b.dataset.f, k = b.dataset.k;
    if (g === "posted") view.posted = view.posted === k ? "" : k;
    else if (g === "only") view[k] = !view[k];
    else view[g] = view[g].includes(k) ? view[g].filter((x) => x !== k) : [...view[g], k];
    saveView(); renderRail();
  });
  const clearF = document.getElementById("clear-f");
  if (clearF) clearF.onclick = () => {
    view = { ...view, where: [], term: [], role: [], posted: "", follow: false, unopened: false };
    saveView(); renderRail();
  };
  rail.querySelectorAll("[data-uid]").forEach((b) => b.onclick = () => {
    if (!selecting) return openJob(b.dataset.uid);
    picked.has(b.dataset.uid) ? picked.delete(b.dataset.uid) : picked.add(b.dataset.uid);
    renderRail();
  });
  const many = document.getElementById("do-archive");
  if (many) many.onclick = () => { const uids = [...picked]; selecting = false; picked.clear(); archive(uids); };
  document.getElementById("arch").onclick = () => { showArchived = !showArchived; load(); };
  const naps = document.getElementById("naps");
  if (naps) naps.onclick = () => { showSnoozed = !showSnoozed; load(); };
  const mutes = document.getElementById("mutes");
  if (mutes) mutes.onclick = mutedPane;
  bindSuggestion(rail);
  const held = document.getElementById("held");
  if (held) held.onclick = () => filteredPane();
}

/* --------------------------------------------------------- the posting -- */

function openJob(uid, fromHistory) {
  current = uid;
  markOpened(uid);
  pane = "job";
  menuOpen = false;
  renderRail();
  renderJob();
  if (phone()) {
    document.body.classList.add("reading");
    window.scrollTo(0, 0);
    if (!fromHistory) history.pushState({ job: uid }, "");
  }
  document.getElementById("detail").scrollTop = 0;
}

function closeJob() { document.body.classList.remove("reading"); }
window.addEventListener("popstate", () => closeJob());
// A menu closes when he taps anywhere else or presses Escape.
function closeMenus(e) {
  if (e.type === "keydown" && e.key !== "Escape") return;
  if (e.type === "click" && e.target.closest && e.target.closest(".actions .menu, #more, [data-snooze]")) return;
  const naps = document.getElementById("naps-menu");
  if (naps) naps.remove();
  if (menuOpen && pane === "job") {
    const box = document.getElementById("detail"), y = box.scrollTop, wy = window.scrollY;
    menuOpen = false; menuWhy = false; renderJob(); box.scrollTop = y; window.scrollTo(0, wy);
  }
}
document.addEventListener("click", closeMenus);
document.addEventListener("keydown", closeMenus);

function actionsFor(j) {
  const link = (href, label, kind) =>
    '<a class="btn ' + (kind || "") + '" href="' + esc(href) + '" target="_blank" rel="noopener">' + label + "</a>";
  const act = (c, label, kind) => '<button class="btn ' + (kind || "") + '" data-cmd="' + c + '">' + label + "</button>";
  const form = j.apply_url ? link(j.apply_url, "Open application") : (j.url ? link(j.url, "Open posting") : "");
  let main = "";
  if (j.state === "new") main = act("build", j.byHand ? "Write my resume" : "Apply for me", "primary");
  else if (j.state === "ready" && !j.byHand) main = act("approve", "Apply for me", "primary");
  else if (j.state === "ready" && j.byHand && j.apply_url) main = link(j.apply_url, "Open application", "primary");
  else if (j.state === "working") main = act("stop", "Stop applying");
  else if (j.state === "needs") main = act("applied", "I applied", "primary");
  else if (j.state === "skipped") main = act("reopen", "Put it back", "primary");
  const second = main.includes("Open application") ? "" : form;
  return main + second +
    (j.snoozed_until ? act("wake", "Back on the board") : '<button class="btn" data-snooze>Not now</button>') +
    '<button class="btn" id="more">More</button>';
}

// Why he is archiving a job: each answer teaches the suggestions.
const WHY = [["role", "Not a role I want"], ["level", "Wrong level or too senior"], ["place", "Wrong location"],
             ["term", "Wrong term or dates"], ["company", "Not this company"], ["applied", "I already applied"],
             ["other", "Just not interested"]];
let menuWhy = false;

function menuFor(j) {
  if (menuWhy) return '<div class="menu"><div class="menu-head">Why archive it?</div>' +
    WHY.map(([r, label]) => '<button data-why="' + r + '">' + esc(label) + "</button>").join("") + "</div>";
  const items = [
    j.state === "new" && !j.byHand ? ["draft", "Write the resume, don’t apply"] : null,
    j.state === "needs" && j.issue && !j.byHand ? ["retry", "Try the application again"] : null,
    j.state !== "done" ? ["applied", "I applied myself"] : ["reopen", "I didn’t apply after all"],
    followed(j) ? ["unfollow", "Stop following " + j.company] : ["follow", "Follow " + j.company],
    ["share", "Share this posting"],
    ["mute", "Mute " + j.company],
    j.state !== "skipped" ? ["archive", "Archive\u2026", "danger"] : null,
  ].filter(Boolean);
  return '<div class="menu">' + items.map(([c, label, kind]) =>
    '<button class="' + (kind || "") + '" data-menu="' + c + '">' + esc(label) + "</button>").join("") + "</div>";
}

// Everything he needs to send it himself, in the order he does it. Shown when
// an apply run stopped (a code, a CAPTCHA, a field it could not fill) and for
// sites jobbot never submits to.
function finishHtml(j) {
  if (j.state !== "needs" && !(j.state === "ready" && j.byHand)) return "";
  const code = /code/i.test(j.note || "");
  const steps = [
    j.apply_url ? ['<a class="btn primary" href="' + esc(j.apply_url) + '" target="_blank" rel="noopener">Open the application</a>',
                   "The form opens in your browser."] : null,
    j.pdf ? ['<button class="btn" data-pdf="' + esc(j.pdf) + '" data-co="' + esc(j.company) + '">Save your resume</button>',
             "Save it, then attach it as your resume."] : null,
    j.folder ? ['<button class="btn" id="copy-all">Copy every answer</button>',
                "Paste them in, or copy them one at a time below."] : null,
    code ? [null, "The site emailed you a code to confirm it is you. Enter that code on the form - " +
            "jobbot never types a code sent to you."] : null,
    ['<button class="btn primary" data-cmd="applied">I applied</button>', "This moves it to Applied and stops the reminders."],
  ].filter(Boolean);
  return '<section class="sec finish"><h2>Finish this application yourself</h2><ol class="steps">' +
    steps.map(([btn, text]) => "<li>" + (text ? "<span>" + esc(text) + "</span>" : "") +
      (btn ? '<div class="row-btns">' + btn + "</div>" : "") + "</li>").join("") + "</ol></section>";
}

// Sections he can fold, so a long posting does not bury his resume or the
// answers. What he folds is remembered on this device.
let folded = {};
try { folded = JSON.parse(localStorage.getItem("jobbot-folded") || "{}"); } catch (e) { /* defaults */ }
const OPEN_BY_DEFAULT = { finish: true, jd: true, resume: false, answers: true, notes: false };
const isOpen = (k) => (k in folded ? folded[k] : OPEN_BY_DEFAULT[k] !== false);
function fold(key, title, inner, extra) {
  return '<details class="sec fold" data-fold="' + key + '"' + (isOpen(key) ? " open" : "") + ">" +
    "<summary><h2>" + esc(title) + "</h2>" + (extra ? '<span class="hint">' + esc(extra) + "</span>" : "") +
    "</summary>" + inner + "</details>";
}

function renderJob() {
  const box = document.getElementById("detail");
  const j = jobs.find((x) => x.uid === current);
  if (!j) { box.innerHTML = '<div class="empty-d">Pick a job to read the posting.</div>'; return; }
  const locs = String(j.location || "").split(/;|•/).map((s) => s.trim()).filter(Boolean);
  const tags = [
    locs.length ? locs[0] + (locs.length > 1 ? " and " + (locs.length - 1) + " more" : "") : "",
    j.term || "", ago(j.posted_at), j.deadline ? "Closes " + String(j.deadline).slice(0, 10) : "",
  ].filter(Boolean).map((t) => '<span class="tag">' + esc(t) + "</span>").join("") +
    (followed(j) ? '<span class="tag follow">Company you follow</span>' : "");

  box.innerHTML = '<div class="d">' +
    '<button class="btn back" id="back">‹ Jobs</button>' +
    '<div class="d-head">' + logo(j.company, j.url || j.apply_url, true) +
      '<div style="min-width:0"><div class="d-co">' + esc(j.company) + '</div><h1 class="d-title">' + esc(j.title) +
      '</h1><div class="d-meta">' + tags + "</div></div></div>" +
    // The menus open from the bar, which stays on screen as he scrolls; drawn
    // below it, they opened back at the top of the posting, out of view.
    '<div class="actions">' + actionsFor(j) + (menuOpen ? menuFor(j) : "") + "</div>" +
    (j.note && j.state !== "done" ? '<div class="notice">' + esc(j.note) + "</div>" : "") +
    finishHtml(j) +
    (j.knockout ? '<div class="notice">The form asks about citizenship or security clearance.</div>' : "") +

    fold("jd", "About the role",
      (j.jd ? '<div class="jd">' + posting(j.jd) + "</div>"
            : '<p class="quiet">The text of this posting is not available here. Open the posting to read it.</p>')) +

    (j.preview ? fold("resume", "Your resume for this job",
      '<a href="' + (j.pdf ? "/file?path=" + enc(j.pdf) : "#") + '" target="_blank">' +
      '<img class="paper" alt="Your resume for this job" src="/file?path=' + enc(j.preview) + '"></a>' +
      '<div id="coined"></div>' +
      (j.pdf ? '<div class="row-btns"><a class="btn" href="/file?path=' + enc(j.pdf) + '" target="_blank">Open PDF</a>' +
        '<button class="btn" data-pdf="' + esc(j.pdf) + '" data-co="' + esc(j.company) + '">Save PDF</button></div>' : "")) : "") +

    (j.folder ? '<div id="qa">' + fold("answers", "Application answers",
      '<div class="box"><div class="qa"><div class="quiet">Loading</div></div></div>') + "</div>" : "") +

    (j.says ? '<section class="sec said"><h2>Claude says</h2><p>' + esc(j.says) + "</p>" +
      '<p class="quiet">Answer below and it writes the resume again with your reply.</p></section>' : "") +

    fold("notes", "Notes for Claude",
      '<textarea id="hint" placeholder="' + (j.folder
        ? "Lead with the infrastructure work. Drop the oldest role. Say ETL, not pipeline."
        : "Anything the resume should lead with or leave out. Optional.") + '">' + esc(j.hint || "") + "</textarea>" +
      '<div class="row-btns"><button class="btn" id="rewrite">' +
        (j.folder ? "Write the resume again with this" : "Save note") + "</button></div>") +

    ((j.shots || []).length ? '<section class="sec shots"><h2>What the application looked like</h2>' +
      j.shots.map((s) => '<img loading="lazy" alt="The application form" src="/file?path=' + enc(s) + '">').join("") +
      "</section>" : "") +
  "</div>";

  wireJob(j);
  if (j.folder) loadAnswers(j.folder);
}

function wireJob(j) {
  const box = document.getElementById("detail");
  const back = document.getElementById("back");
  if (back) back.onclick = () => history.back();
  const hint = () => { const el = document.getElementById("hint"); return el ? el.value.trim() : ""; };
  bindPdf(box);
  box.querySelectorAll("details.fold").forEach((el) => el.ontoggle = () => {
    folded[el.dataset.fold] = el.open;
    try { localStorage.setItem("jobbot-folded", JSON.stringify(folded)); } catch (e) { /* this visit only */ }
  });
  const all = document.getElementById("copy-all");
  if (all) all.onclick = () => {
    const text = (qa.list || []).filter((q) => q.answer).map((q) => q.label + "\n" + q.answer).join("\n\n");
    if (!text) return toast("The answers are still loading");
    navigator.clipboard.writeText(text).then(() => toast("Every answer copied"), () => toast("Could not copy"));
  };

  box.querySelectorAll("[data-cmd]").forEach((b) => b.onclick = () => {
    b.disabled = true;
    b.classList.add("busy");
    run(j, b.dataset.cmd, hint());
  });
  const more = document.getElementById("more");
  // Under the button that opened it, unless that would run off the right edge.
  const drop = box.querySelector(".actions > .menu");
  if (drop && more) {
    const bar = drop.parentElement.getBoundingClientRect(), at = more.getBoundingClientRect();
    if (at.left - bar.left + drop.offsetWidth < bar.width - 8) {
      drop.style.left = (at.left - bar.left) + "px"; drop.style.right = "auto";
    }
  }
  if (more) more.onclick = (e) => {
    e.stopPropagation();
    const y = box.scrollTop, wy = window.scrollY;
    menuOpen = !menuOpen; menuWhy = false; renderJob();
    box.scrollTop = y; window.scrollTo(0, wy);
  };
  box.querySelectorAll("[data-menu]").forEach((b) => b.onclick = () => {
    const c = b.dataset.menu;
    menuOpen = false;
    if (c === "share") { renderJob(); return share(j); }
    if (c === "mute") return mute(j.company);
    if (c === "follow" || c === "unfollow") return follow(j.company, c === "follow");
    if (c === "archive") {
      menuOpen = true; menuWhy = true;
      const y = box.scrollTop, wy = window.scrollY; renderJob(); box.scrollTop = y; window.scrollTo(0, wy);
      return;
    }
    run(j, c, hint());
  });
  box.querySelectorAll("[data-why]").forEach((b) => b.onclick = () => {
    menuOpen = false; menuWhy = false;
    if (b.dataset.why === "applied") return run(j, "applied", hint());
    archive([j.uid], b.dataset.why);
  });
  const nap = box.querySelector("[data-snooze]");
  if (nap) nap.onclick = () => snoozePane(j);
  document.getElementById("rewrite").onclick = async () => {
    const text = hint();
    j.hint = text;
    if (!j.folder) {
      const r = await send("/api/command", "POST", { uid: j.uid, command: "keep", hint: text });
      toast(r.failed || (text ? "Saved. The resume will follow it." : "Note cleared"));
      return;
    }
    const r = await send("/api/command", "POST", { uid: j.uid, command: "rebuild", hint: text });
    toast(r.failed || (text ? "Writing it again with your note" : "Writing it again"));
    load();
  };
}

// What each command does to the card, so the app can show it before the server
// has answered. A failure puts it back.
const GUESS = { build: ["building", "Writing your resume"], draft: ["building", "Writing your resume"],
                approve: ["working", "Applying"], retry: ["working", "Trying again"],
                applied: ["done", "You applied"], rebuild: ["building", "Writing it again"],
                reopen: ["new", null], stop: ["ready", null] };

async function run(j, c, hint) {
  const was = { state: j.state, note: j.note };
  const guess = GUESS[c];
  if (guess) {
    j.state = guess[0]; j.note = guess[1];
    renderRail(); if (pane === "job") renderJob();
  }
  const r = await send("/api/command", "POST", { uid: j.uid, command: c, hint });
  if (r.failed) {
    Object.assign(j, was); renderRail(); if (pane === "job") renderJob();
    toast(r.failed); load(); return;
  }
  if (c === "applied" && r.applied) {
    toast("Recorded as applied", null, { label: "Add details", run: () => { switchTab("apps"); openApp(r.applied); } });
  } else {
    toast(r.said || "Done");
  }
  load();
}

async function share(j) {
  const url = j.url || j.apply_url, text = j.company + " - " + j.title;
  if (navigator.share) { try { await navigator.share({ title: text, text, url }); } catch (e) { /* closed */ } return; }
  await navigator.clipboard.writeText(text + "\n" + url);
  toast("Link copied");
}

async function follow(company, on) {
  const r = await send("/api/command", "POST", { command: on ? "follow" : "unfollow", company });
  if (r.failed) { toast(r.failed); return; }
  const inSettings = !!document.getElementById("follow-list");
  toast(r.said, async () => {
    await send("/api/command", "POST", { command: on ? "unfollow" : "follow", company });
    await load();
    if (document.getElementById("follow-list")) settingsPane();
  });
  await load();
  if (inSettings) settingsPane();
}

async function mute(company) {
  const r = await send("/api/command", "POST", { command: "mute", company });
  current = null; closeJob();
  toast(r.said || "Muted", async () => { await send("/api/command", "POST", { command: "unmute", company }); load(); });
  load();
}

async function archive(uids, reason) {
  const was = jobs.filter((j) => uids.includes(j.uid)).map((j) => ({ uid: j.uid, state: j.state }));
  jobs = jobs.map((j) => (uids.includes(j.uid) ? { ...j, state: "skipped" } : j));
  if (uids.includes(current)) { current = null; closeJob(); renderJob(); }
  renderRail();
  await send("/api/command", "POST", { uids, command: "archive", reason });
  loadSuggestions();
  toast(uids.length > 1 ? uids.length + " archived" : "Archived", async () => {
    jobs = jobs.map((j) => { const b = was.find((w) => w.uid === j.uid); return b ? { ...j, state: b.state } : j; });
    renderRail();
    await send("/api/command", "POST", { uids, command: "reopen" });
    load(); loadSuggestions();
  });
  load();
}

function snoozePane(j) {
  const at = (days, hour) => { const d = new Date(); d.setDate(d.getDate() + days); d.setHours(hour, 0, 0, 0);
    if (d <= new Date()) d.setDate(d.getDate() + 1); return d; };
  const sat = (() => { const d = at(0, 10); d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7 || 7)); return d; })();
  const when = [["This evening", at(0, 19)], ["Tomorrow morning", at(1, 9)], ["Saturday", sat], ["Next week", at(7, 9)]];
  const old = document.getElementById("naps-menu");
  if (old) { old.remove(); return; }
  document.querySelector(".actions").insertAdjacentHTML("beforeend", '<div class="menu" id="naps-menu">' +
    when.map(([label, d], i) => '<button data-when="' + i + '">' + label + ' <span class="quiet">' +
      d.toLocaleString(undefined, { weekday: "short", hour: "numeric" }) + "</span></button>").join("") + "</div>");
  document.querySelectorAll("[data-when]").forEach((b) => b.onclick = async () => {
    const d = when[Number(b.dataset.when)][1];
    await send("/api/command", "POST", { uid: j.uid, command: "snooze", until: d.toISOString() });
    current = null; closeJob();
    toast("Back " + d.toLocaleString(undefined, { weekday: "long", hour: "numeric" }), async () => {
      await send("/api/command", "POST", { uid: j.uid, command: "wake" }); load(); });
    load();
  });
}

function mutedPane() {
  current = null;
  pane = "muted";
  const box = document.getElementById("detail");
  box.innerHTML = '<div class="d"><button class="btn back" id="back">‹ Jobs</button>' +
    '<h1 class="d-title">Muted companies</h1><p class="quiet">Their postings stay off the board until you bring them back.</p>' +
    '<div class="menu" style="max-width:420px">' + muted.map((m) =>
      '<button data-unmute="' + esc(m) + '">Bring back ' + esc(pretty(m)) + "</button>").join("") + "</div></div>";
  if (phone()) { document.body.classList.add("reading"); history.pushState({ muted: 1 }, ""); }
  document.getElementById("back").onclick = () => history.back();
  box.querySelectorAll("[data-unmute]").forEach((b) => b.onclick = async () => {
    const r = await send("/api/command", "POST", { command: "unmute", company: b.dataset.unmute });
    toast(r.said || "Back on the board"); await load(); mutedPane();
  });
}

/* ------------------------------------------------------- suggestions -- */

// Patterns in what he archives, offered back as one-tap Settings changes.
let hints = [];
async function loadSuggestions() {
  try { hints = (await api("/api/suggestions")).suggestions || []; } catch (e) { hints = []; }
  if (tab === "jobs") renderRail();
}
function suggestionCard() {
  const h = hints[0];
  if (!h) return "";
  return '<div class="learn"><div class="learn-text">' + esc(h.text) + "</div>" +
    (h.examples && h.examples.length ? '<div class="learn-ex">' + h.examples.map(esc).join("<br>") + "</div>" : "") +
    '<div class="learn-do"><button class="btn primary" data-learn="' + esc(h.id) + '">' + esc(h.action) + "</button>" +
    '<button class="btn" data-unlearn="' + esc(h.id) + '">No thanks</button></div></div>';
}
function bindSuggestion(rail) {
  const yes = rail.querySelector("[data-learn]"), no = rail.querySelector("[data-unlearn]");
  if (yes) yes.onclick = async () => {
    yes.disabled = true;
    const id = yes.dataset.learn;
    const r = await send("/api/suggestions", "POST", { id });
    if (r.error) { yes.disabled = false; return toast(r.error); }
    const undo = id.startsWith("mute:")
      ? async () => { await send("/api/command", "POST", { command: "unmute", company: id.slice(5) }); }
      : async () => {
          await send("/api/settings", "POST", { key: "search", undo: true });
          if (r.archived && r.archived.length) await send("/api/command", "POST", { uids: r.archived, command: "reopen" });
          await send("/api/suggestions", "POST", { id, undismiss: true });
        };
    toast(r.said || "Done", async () => { await undo(); setData = null; await load(); loadSuggestions(); });
    setData = null;
    await load(); loadSuggestions();
  };
  if (no) no.onclick = async () => {
    const id = no.dataset.unlearn;
    hints = hints.filter((h) => h.id !== id); renderRail();
    await send("/api/suggestions", "POST", { id, dismiss: true });
    toast("Won\u2019t suggest that again", async () => {
      await send("/api/suggestions", "POST", { id, undismiss: true }); loadSuggestions(); });
  };
}

/* ------------------------------------------------------------- usage -- */

// Which buttons and screens he uses, so what nobody uses can go. Counted
// here, sent every half minute and when the app is hidden. Names only.
const used = {};
function note(name) { if (name) used[name] = (used[name] || 0) + 1; }
function flushUsage() {
  const counts = { ...used };
  if (!Object.keys(counts).length) return;
  for (const k of Object.keys(used)) delete used[k];
  const body = JSON.stringify({ counts });
  if (navigator.sendBeacon) navigator.sendBeacon("/api/usage", new Blob([body], { type: "application/json" }));
  else fetch("/api/usage", { method: "POST", headers: { "content-type": "application/json" }, body, keepalive: true });
}
setInterval(flushUsage, 30000);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flushUsage(); });
document.addEventListener("click", (e) => {
  const el = e.target.closest && e.target.closest("button, a, summary, [data-uid]");
  if (!el) return;
  const d = el.dataset || {};
  const what = d.cmd ? "action: " + d.cmd : d.menu ? "menu: " + d.menu : d.why ? "archive reason: " + d.why
    : d.setTab ? "settings: " + d.setTab : d.region !== undefined ? "filter: " + (d.region || "all")
    : d.uid ? "open a job" : d.learn ? "suggestion: accepted" : d.unlearn ? "suggestion: declined"
    : d.add ? "filtered out: add to jobs" : d.why === undefined && d.flip ? "settings: term"
    : (el.textContent || "").trim().replace(/\s+/g, " ").replace(/\d+/g, "#").slice(0, 40);
  note((pane === "settings" && !d.setTab ? "settings > " : "") + what);
}, true);

/* ------------------------------------------------------- filtered out -- */

// What the rules turned away this week. Grouped by reason: a rule that is
// wrong shows up as one reason with a pile of postings he wanted.
let held = [], heldWhy = "";
async function filteredPane(keep) {
  current = null;
  pane = "filtered";
  const box = document.getElementById("detail");
  if (!keep) {
    box.innerHTML = '<div class="d"><h1 class="d-title">Filtered out</h1><p class="quiet">Loading</p></div>';
    held = (await api("/api/filtered")).filtered || [];
  }
  const reasons = {};
  held.forEach((f) => { reasons[f.why] = (reasons[f.why] || 0) + 1; });
  const order = Object.keys(reasons).sort((a, b) => reasons[b] - reasons[a]);
  if (heldWhy && !reasons[heldWhy]) heldWhy = "";
  const list = held.filter((f) => !heldWhy || f.why === heldWhy);
  box.innerHTML = '<div class="d"><button class="btn back" id="back">‹ Jobs</button>' +
    '<h1 class="d-title">Filtered out</h1>' +
    '<p class="quiet">Internships from the last week that your rules kept off the board. ' +
      "Add any you want, and it joins your jobs like any other.</p>" +
    (held.length ? '<div class="chips held-why"><button class="' + (heldWhy ? "" : "on") + '" data-why="">All ' + held.length +
      "</button>" + order.map((w) => '<button class="' + (heldWhy === w ? "on" : "") + '" data-why="' + esc(w) + '">' +
      esc(w) + " " + reasons[w] + "</button>").join("") + "</div>" : "") +
    (list.length ? '<div class="held">' + list.map((f) =>
      '<div class="held-row">' + logo(f.company, f.url || f.apply_url) +
        '<div class="main"><div class="line1"><span class="co">' + esc(f.company) + '</span><span class="age">' +
          age(f.posted_at) + "</span></div>" +
          '<div class="title">' + esc(f.title) + "</div>" +
          '<div class="line3">' + (real(f.where) ? "<span>" + esc(f.where) + "</span>" : "") +
            (heldWhy ? "" : '<span class="why">' + esc(f.why) + "</span>") + "</div>" +
          (f.detail ? '<div class="held-detail">' + esc(f.detail) + "</div>" : "") + "</div>" +
        '<div class="held-do">' +
          (f.url || f.apply_url ? '<a class="btn" href="' + esc(f.url || f.apply_url) + '" target="_blank" rel="noopener">Open posting</a>' : "") +
          '<button class="btn primary" data-add="' + esc(f.uid) + '">Add to my jobs</button></div></div>').join("") + "</div>"
      : '<p class="quiet">Nothing was filtered out this week.</p>') + "</div>";
  if (phone() && !keep) { document.body.classList.add("reading"); history.pushState({ filtered: 1 }, ""); }
  document.getElementById("back").onclick = () => history.back();
  box.querySelectorAll("[data-why]").forEach((b) => b.onclick = () => { heldWhy = b.dataset.why; filteredPane(true); });
  box.querySelectorAll("[data-add]").forEach((b) => b.onclick = async () => {
    b.disabled = true;
    const r = await send("/api/command", "POST", { command: "restore", uid: b.dataset.add });
    if (r.error) { b.disabled = false; return toast(r.error); }
    held = held.filter((f) => f.uid !== b.dataset.add);
    filteredCount = Math.max(0, filteredCount - 1);
    toast(r.said || "Added to your jobs");
    await loadJobs();
    filteredPane(true);
  });
}

/* ----------------------------------------------------------- settings -- */

const THEMES = [["system", "Match my phone"], ["light", "Light"], ["dark", "Dark"], ["dim", "Dim"]];
const ACCENTS = [["graphite", "Graphite", "#18181b"], ["blue", "Blue", "#2563eb"], ["teal", "Teal", "#0f766e"],
                 ["green", "Green", "#15803d"], ["violet", "Violet", "#6d28d9"], ["rose", "Rose", "#e11d48"]];

function look() {
  try { return JSON.parse(localStorage.getItem("jobbot-look") || "{}"); } catch (e) { return {}; }
}
function setLook(change) {
  const next = { theme: "system", accent: "graphite", ...look(), ...change };
  try { localStorage.setItem("jobbot-look", JSON.stringify(next)); } catch (e) { /* this visit only */ }
  const root = document.documentElement;
  if (next.theme === "system") delete root.dataset.theme; else root.dataset.theme = next.theme;
  if (next.accent === "graphite") delete root.dataset.accent; else root.dataset.accent = next.accent;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = getComputedStyle(root).getPropertyValue("--panel").trim() || "#ffffff";
}

let followFind = "";
// Settings: what jobbot looks for, what it knows about him, how it writes.
// Each section is edited as a draft and saved as a whole; the save bar only
// appears when the draft differs from what is saved.
const SECTIONS = [["search", "Job search"], ["profile", "Profile"], ["resume", "Resume"],
                  ["answers", "Application answers"], ["following", "Following"], ["look", "Appearance"],
                  ["alerts", "Notifications"], ["usage", "Usage"]];
const WINDOWS = [[12, "12 hours"], [24, "24 hours"], [48, "2 days"], [72, "3 days"], [168, "1 week"], [336, "2 weeks"]];
const TERM_LABEL = (k) => k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
let setTab = "search", setData = null, drafts = {};

const clone = (x) => JSON.parse(JSON.stringify(x));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const getAt = (o, path) => path.split(".").reduce((x, k) => (x == null ? x : x[k]), o);
function setAt(o, path, v) {
  const ks = path.split(".");
  let x = o;
  for (let i = 0; i < ks.length - 1; i++) x = x[ks[i]];
  x[ks[ks.length - 1]] = v;
}
const dirty = (k) => !!(setData && setData[k] && drafts[k] && !same(drafts[k], setData[k].value));

async function loadSettings() {
  const d = await api("/api/settings");
  setData = d.sections || {};
  for (const k of Object.keys(setData)) if (!drafts[k] || !dirty(k)) drafts[k] = clone(setData[k].value);
}

// Small building blocks. Each input names the draft field it edits.
function input(path, label, value, hint) {
  return '<div class="field"><label>' + esc(label) + '</label><div class="grow"><input data-path="' + path +
    '" value="' + esc(value ?? "") + '">' + (hint ? '<div class="hint">' + esc(hint) + "</div>" : "") + "</div></div>";
}
function area(path, value, rows, placeholder) {
  return '<textarea data-path="' + path + '" rows="' + (rows || 4) + '" placeholder="' + esc(placeholder || "") + '">' +
    esc(value ?? "") + "</textarea>";
}
function choice(path, label, value, options) {
  return '<div class="field"><label>' + esc(label) + '</label><select data-path="' + path + '">' +
    options.map(([v, l]) => '<option value="' + esc(v) + '"' + (String(v) === String(value) ? " selected" : "") + ">" +
      esc(l) + "</option>").join("") + "</select></div>";
}
function toggle(path, label, on, hint) {
  return '<label class="toggle"><input type="checkbox" data-bool="' + path + '"' + (on ? " checked" : "") + ">" +
    "<span><b>" + esc(label) + "</b>" + (hint ? '<span class="hint">' + esc(hint) + "</span>" : "") + "</span></label>";
}
function wordList(path, words, placeholder) {
  return '<div class="words">' + words.map((w, i) => "<span>" + esc(w) + '<button title="Remove" data-drop="' + path +
    '" data-i="' + i + '">×</button></span>').join("") +
    '<input data-add="' + path + '" placeholder="' + esc(placeholder || "Add, then press Enter") + '"></div>';
}
const block = (title, help, inner) => '<section class="sec"><h2>' + esc(title) + "</h2>" +
  (help ? '<p class="quiet help">' + help + "</p>" : "") + inner + "</section>";

function searchForm(s) {
  return block("Terms", "Postings for a term you turn off are dropped.",
      '<div class="opts">' + Object.keys(s.seasons).map((t) => '<button class="opt' + (s.seasons[t] ? " on" : "") +
        '" data-flip="seasons.' + t + '">' + esc(t) + "</button>").join("") + "</div>") +
    block("Job levels", "",
      toggle("levels.internship", "Internships and co-ops", s.levels.internship) +
      toggle("levels.new_grad", "New grad and early career", s.levels.new_grad)) +
    block("Roles you want", "A title needs one of these words to count.", wordList("roles_wanted", s.roles_wanted)) +
    block("Roles you don't want", "A title with any of these words is dropped, even if it has one you want.",
      wordList("roles_excluded", s.roles_excluded)) +
    block("How recent", "Older postings go to Filtered out instead of your feed.",
      choice("window_hours", "Most companies", s.window_hours, WINDOWS) +
      choice("window_following_hours", "Companies you follow", s.window_following_hours, WINDOWS)) +
    block("Places", "",
      toggle("places.canada", "Canada", s.places.canada) +
      toggle("places.us", "United States", s.places.us) +
      toggle("places.remote", "Remote", s.places.remote) +
      '<div class="sub">Cities and regions you never want</div>' +
      wordList("places_excluded", s.places_excluded || [], "For example Austin, then press Enter")) +
    block("Sponsorship", "",
      toggle("hide_no_sponsor", "Hide US jobs that say they won't sponsor a visa", s.hide_no_sponsor,
        "Canadian seats are always kept."));
}

function profileForm(p) {
  const c = p.contact, e = p.education;
  return block("Contact", "Used on every resume header and application form.",
      '<div class="box">' + input("contact.name", "Name", c.name) + input("contact.email", "Email", c.email) +
      input("contact.phone", "Phone", c.phone) + input("contact.location", "City", c.location, "As it appears on your resume") +
      input("contact.linkedin", "LinkedIn", c.linkedin) + input("contact.github", "GitHub", c.github) +
      input("contact.website", "Website", c.website, "For portfolio questions. Blank uses GitHub") + "</div>") +
    block("Education", "",
      '<div class="box">' + input("education.school", "School", e.school) +
      input("education.degree", "Degree", e.degree, "As it appears on your resume") +
      input("education.degree_level", "Degree level", e.degree_level, "For forms, for example Bachelor's") +
      input("education.major", "Major", e.major) + input("education.gpa", "GPA", e.gpa) +
      input("education.start_month", "Started (month)", e.start_month) +
      input("education.start_year", "Started (year)", e.start_year) +
      input("education.coursework", "Coursework", e.coursework) +
      Object.keys(e.grad_by_term).map((t) => input("education.grad_by_term." + t, "Graduation for " + TERM_LABEL(t) + " roles",
        e.grad_by_term[t])).join("") + "</div>") +
    block("Notes for Claude", "Anything true about you that should shape every resume and answer.",
      area("notes", p.notes, 4, "For example: I want backend and infrastructure roles, so lead with systems work.")) +
    block("Experience and projects",
      "The facts Claude writes from. Every number on a resume must appear in a fact here, so edit these rather " +
      "than asking for a new figure.",
      p.entries.map((en, i) => '<details class="entry"' + (openEntry === en.id ? " open" : "") + ' data-entry="' + esc(en.id) + '">' +
        "<summary><span><b>" + esc(en.name) + "</b>" + (en.role ? " " + esc(en.role) : "") +
          (en.dates ? '<span class="hint">' + esc(en.dates) + "</span>" : "") + "</span>" +
          (en.use ? "" : '<span class="off">Not used</span>') + "</summary>" +
        toggle("entries." + i + ".use", "Use on resumes", en.use) +
        en.facts.map((f, j) => '<div class="fact">' +
          area("entries." + i + ".facts." + j + ".text", f.text, Math.min(12, Math.ceil((f.text || "").length / 85) + 1)) +
          '<div class="fact-meta"><label>Numbers you can use, one per line' +
            '<textarea data-lines="entries.' + i + ".facts." + j + '.metrics" rows="2">' + esc((f.metrics || []).join("\n")) +
            "</textarea></label>" +
          "<label>Tools, separated by commas<input data-csv=\"entries." + i + ".facts." + j + '.tech" value="' +
            esc((f.tech || []).join(", ")) + '"></label></div>' +
          '<button class="link danger" data-unfact="' + i + "." + j + '">Remove this fact</button></div>').join("") +
        '<button class="btn" data-fact="' + i + '">Add a fact</button></details>').join("")) +
    block("Skills", "The rows Claude picks from for the skills section.",
      Object.keys(p.skills).map((k) => '<div class="skill"><div class="skill-name">' + esc(k) + "</div>" +
        wordList("skills." + k, p.skills[k]) + "</div>").join(""));
}
let openEntry = null;

const MODELS = [["", "Whatever is current (recommended)"], ["claude-opus-5", "Opus 5 - the most careful"],
                ["claude-sonnet-5", "Sonnet 5 - balanced"], ["claude-haiku-4-5-20251001", "Haiku 4.5 - the fastest"]];

function resumeForm(r) {
  return block("Which Claude writes them",
      "Each resume is written by its own run, so a slower model costs you waiting, not money.",
      '<div class="box">' + choice("model", "Model", r.model || "", MODELS) + "</div>") +
    block("Your instructions", "Claude reads these on every resume, and they win over the rules below.",
      area("instructions", r.instructions, 6, "For example: Always lead with Python and cloud work. Never mention Helix Labs " +
        "for frontend roles. Keep projects to one unless the posting is AI.")) +
    block("Resume rules", "How every resume is written: voice, structure, what to emphasize. Started from your " +
      "PIPELINE.md. Claude still can't use a fact or number that isn't in your profile.",
      area("rules", r.rules, 18));
}

function answersForm(a) {
  return block("Standard answers", "Filled into every form without asking.",
      '<div class="box">' + input("form_location", "Location", a.form_location, "Full, for location fields") +
      input("current_employer", "Current employer", a.current_employer) +
      choice("relocate", "Willing to relocate", a.relocate, [["Yes", "Yes"], ["No", "No"]]) +
      choice("onsite", "Can work on site", a.onsite, [["Yes", "Yes"], ["No", "No"]]) +
      input("how_heard", "How you heard", a.how_heard) +
      choice("demographics", "Gender, race, veteran and disability questions", a.demographics,
        [["decline", "Decline to answer"], ["ask", "Ask me each time"]]) + "</div>") +
    block("Sponsorship", "The text used when a form asks whether you need a visa.",
      '<div class="box"><div class="field col"><label>US roles</label>' + area("sponsorship_us", a.sponsorship_us, 2) + "</div>" +
      '<div class="field col"><label>Canadian roles</label>' + area("sponsorship_canada", a.sponsorship_canada, 2) + "</div></div>") +
    block("Written answers", "How Claude drafts the questions a rule can't answer, like “Why do you want to work here?”",
      area("instructions", a.instructions, 8));
}

async function usageForm() {
  let d = { rows: [] };
  try { d = await api("/api/usage"); } catch (e) { /* shown as empty */ }
  if (!d.rows.length) return block("What you use", "", '<p class="quiet">Nothing counted yet. Each tap is ' +
    "counted from now on, so this fills in as you use the app.</p>");
  const top = d.rows[0].n;
  return block("What you use", "Taps in the last 30 days" + (d.first ? ", counted since " + esc(d.first) : "") +
      ". Names only, never what you type.",
    '<div class="usage">' + d.rows.map((r) => '<div class="use-row"><span class="use-name">' + esc(r.name) + "</span>" +
      '<span class="use-bar"><i style="width:' + Math.max(2, Math.round(100 * r.n / top)) + '%"></i></span>' +
      '<span class="use-n">' + r.n + "</span></div>").join("") + "</div>");
}

// Web push: the phone is told when a resume is ready, when an application needs
// him, and when one is sent. iOS only allows this for an app on the Home Screen.
const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const iphone = () => /iphone|ipad|ipod/i.test(navigator.userAgent);
let pushSub = null;
async function pushState() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "unsupported";
  if (iphone() && !standalone()) return "needs-home-screen";
  const reg = await navigator.serviceWorker.getRegistration();
  pushSub = reg ? await reg.pushManager.getSubscription() : null;
  if (Notification.permission === "denied") return "blocked";
  return pushSub ? "on" : "off";
}
function keyBytes(k) {
  const pad = "=".repeat((4 - (k.length % 4)) % 4);
  const raw = atob((k + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}
async function turnPushOn() {
  const d = await api("/api/push");
  if (!d.key) return toast("Notifications are not set up on the server yet");
  if ((await Notification.requestPermission()) !== "granted") return toast("Your phone refused notifications");
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(d.key) });
  const r = await send("/api/push", "POST", { subscription: sub.toJSON() });
  toast(r.said || "Notifications on");
  settingsPane(true);
}
async function turnPushOff() {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg && await reg.pushManager.getSubscription();
  if (sub) { await send("/api/push", "POST", { off: true, endpoint: sub.endpoint }); await sub.unsubscribe(); }
  toast("Notifications off on this device");
  settingsPane(true);
}
async function alertsForm() {
  const state = await pushState();
  const d = await api("/api/push").catch(() => ({ devices: 0 }));
  const says = {
    unsupported: "This browser cannot show notifications. Open the app in Safari or Chrome.",
    "needs-home-screen": "Add jobbot to your Home Screen first: tap Share, then Add to Home Screen, " +
      "and open it from there. iPhones only allow notifications for apps kept on the Home Screen.",
    blocked: "Your phone is blocking notifications for jobbot. Turn them back on in Settings, " +
      "Notifications, jobbot, then come back here.",
    off: "Off on this device.",
    on: "On for this device.",
  }[state];
  return block("Notifications", "You are told when a resume is ready, when an application needs you, and when " +
      "one is sent. Nothing else.",
    "<p>" + esc(says) + "</p>" +
    (state === "on" ? '<div class="row-btns"><button class="btn" id="push-test">Send a test</button>' +
      '<button class="btn danger" id="push-off">Turn off</button></div>'
      : state === "off" ? '<div class="row-btns"><button class="btn primary" id="push-on">Turn on notifications</button></div>' : "") +
    (d.devices ? '<p class="quiet" style="margin-top:12px">' + d.devices +
      (d.devices === 1 ? " device is" : " devices are") + " subscribed.</p>" : ""));
}

function lookForm() {
  const now = { theme: "system", accent: "graphite", ...look() };
  return block("Theme", "",
      '<div class="opts">' + THEMES.map(([v, label]) => '<button class="opt' + (now.theme === v ? " on" : "") +
        '" data-theme-pick="' + v + '">' + label + "</button>").join("") + "</div>") +
    block("Color", "Kept on this device.",
      '<div class="opts">' + ACCENTS.map(([v, label, hex]) => '<button class="opt' + (now.accent === v ? " on" : "") +
        '" data-accent-pick="' + v + '"><span class="swatch" style="background:' + hex + '"></span>' + label + "</button>").join("") +
      "</div>");
}

function followingForm() {
  const needle = key(followFind);
  const list = following.filter((f) => !needle || f.key.includes(needle) || key(f.name).includes(needle));
  return block("Companies you follow (" + following.length + ")",
      "Their postings come first, are checked every 15 minutes, and use the longer window from Job search.",
      '<div class="addrow"><input id="follow-add" placeholder="Add a company, for example Jane Street">' +
        '<button class="btn primary" id="follow-go">Follow</button></div>' +
      '<div class="addrow" style="margin-top:8px"><input id="follow-find" placeholder="Find in the list" value="' +
        esc(followFind) + '"></div>' +
      '<div class="follows" id="follow-list">' + (list.length ? list.map((f) =>
        "<span>" + esc(f.name) + '<button title="Stop following" data-unfollow="' + esc(f.name) + '">×</button></span>').join("")
        : '<p class="quiet">' + (following.length ? "No match." : "Nobody yet.") + "</p>") + "</div>");
}

async function settingsPane(keepScroll) {
  current = null; currentApp = null;
  const first = pane !== "settings";
  pane = "settings";
  if (first) { if (tab === "jobs") renderRail(); else renderApps(); }
  const box = document.getElementById("detail");
  const y = keepScroll ? box.scrollTop : 0;
  if (!setData) {
    box.innerHTML = '<div class="d"><h1 class="d-title">Settings</h1><p class="quiet">Loading</p></div>';
    try { await loadSettings(); } catch (e) { setData = {}; }
  }
  const s = drafts[setTab];
  const kept = ["search", "profile", "resume", "answers"].includes(setTab);
  let body;
  if (kept && !s) body = '<p class="quiet">jobbot sends its defaults on its next check, within 15 minutes. ' +
    "This section appears then.</p>";
  else if (setTab === "search") body = searchForm(s);
  else if (setTab === "profile") body = profileForm(s);
  else if (setTab === "resume") body = resumeForm(s);
  else if (setTab === "answers") body = answersForm(s);
  else if (setTab === "following") body = followingForm();
  else if (setTab === "usage") body = await usageForm();
  else if (setTab === "alerts") body = await alertsForm();
  else body = lookForm();
  const edited = kept && setData[setTab] && setData[setTab].edited;
  box.innerHTML = '<div class="d settings"><button class="btn back" id="back">‹ Back</button>' +
    '<h1 class="d-title">Settings</h1>' +
    '<div class="chips set-tabs">' + SECTIONS.map(([k, label]) => '<button class="' + (setTab === k ? "on" : "") +
      '" data-set-tab="' + k + '">' + label + (dirty(k) ? ' <i class="dot" title="Unsaved changes"></i>' : "") +
      "</button>").join("") + "</div>" +
    body +
    (edited ? '<p class="quiet reset-line">You have changed this section. <button class="link" id="set-reset">' +
      "Reset it to jobbot’s defaults</button></p>" : "") +
    '<div class="savebar" id="savebar"' + (dirty(setTab) ? "" : " hidden") + '><span>Unsaved changes</span>' +
      '<button class="btn" id="set-discard">Discard</button><button class="btn primary" id="set-save">Save</button></div>' +
    "</div>";
  box.scrollTop = y;
  if (phone() && !document.body.classList.contains("reading")) {
    document.body.classList.add("reading"); window.scrollTo(0, 0); history.pushState({ settings: 1 }, "");
  }
  bindSettings(box);
}

function bindSettings(box) {
  const redraw = () => settingsPane(true);
  const d = drafts[setTab];
  // Typing never redraws the form, so the cursor stays where it is.
  const changed = () => {
    const on = dirty(setTab);
    document.getElementById("savebar").hidden = !on;
    const chip = box.querySelector('[data-set-tab="' + setTab + '"]');
    const dot = chip && chip.querySelector(".dot");
    if (chip && on && !dot) chip.insertAdjacentHTML("beforeend", ' <i class="dot" title="Unsaved changes"></i>');
    if (dot && !on) dot.remove();
  };
  document.getElementById("back").onclick = () => history.back();
  box.querySelectorAll("[data-set-tab]").forEach((b) => b.onclick = () => { setTab = b.dataset.setTab; settingsPane(); });
  box.querySelectorAll("[data-path]").forEach((el) => el.oninput = () => {
    const was = getAt(d, el.dataset.path);
    setAt(d, el.dataset.path, typeof was === "number" ? Number(el.value) : el.value); changed();
  });
  box.querySelectorAll("[data-bool]").forEach((el) => el.onchange = () => { setAt(d, el.dataset.bool, el.checked); redraw(); });
  box.querySelectorAll("[data-flip]").forEach((el) => el.onclick = () => {
    setAt(d, el.dataset.flip, !getAt(d, el.dataset.flip)); redraw();
  });
  box.querySelectorAll("[data-lines]").forEach((el) => el.oninput = () => {
    setAt(d, el.dataset.lines, el.value.split("\n").map((x) => x.trim()).filter(Boolean)); changed();
  });
  box.querySelectorAll("[data-csv]").forEach((el) => el.oninput = () => {
    setAt(d, el.dataset.csv, el.value.split(",").map((x) => x.trim()).filter(Boolean)); changed();
  });
  box.querySelectorAll("[data-add]").forEach((el) => el.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !el.value.trim()) return;
    e.preventDefault();
    const list = getAt(d, el.dataset.add);
    const word = el.value.trim();
    if (!list.some((w) => w.toLowerCase() === word.toLowerCase())) list.push(word);
    redraw();
    const again = document.querySelector('[data-add="' + el.dataset.add + '"]');
    if (again) again.focus();
  }));
  box.querySelectorAll("[data-drop]").forEach((b) => b.onclick = () => {
    getAt(d, b.dataset.drop).splice(Number(b.dataset.i), 1); redraw();
  });
  box.querySelectorAll("details.entry").forEach((el) => el.ontoggle = () => {
    if (el.open) openEntry = el.dataset.entry; else if (openEntry === el.dataset.entry) openEntry = null;
  });
  box.querySelectorAll("[data-fact]").forEach((b) => b.onclick = () => {
    d.entries[Number(b.dataset.fact)].facts.push({ id: "", text: "", metrics: [], tech: [] }); redraw();
  });
  box.querySelectorAll("[data-unfact]").forEach((b) => b.onclick = () => {
    const [i, j] = b.dataset.unfact.split(".").map(Number);
    d.entries[i].facts.splice(j, 1); redraw();
  });
  const save = document.getElementById("set-save");
  if (save) save.onclick = async () => {
    const k = setTab;
    save.disabled = true;
    const r = await send("/api/settings", "POST", { key: k, value: drafts[k] });
    if (r.error) { save.disabled = false; return toast(r.error); }
    await loadSettings();
    drafts[k] = clone(setData[k].value);
    settingsPane(true);
    toast("Saved. Used from jobbot’s next check", async () => {
      await send("/api/settings", "POST", { key: k, undo: true });
      await loadSettings(); drafts[k] = clone(setData[k].value); if (pane === "settings") settingsPane(true);
    });
  };
  const discard = document.getElementById("set-discard");
  if (discard) discard.onclick = () => { drafts[setTab] = clone(setData[setTab].value); redraw(); };
  const reset = document.getElementById("set-reset");
  if (reset) reset.onclick = async () => {
    const k = setTab;
    await send("/api/settings", "POST", { key: k, reset: true });
    await loadSettings(); drafts[k] = clone(setData[k].value); settingsPane(true);
    toast("Back to the defaults", async () => {
      await send("/api/settings", "POST", { key: k, undo: true });
      await loadSettings(); drafts[k] = clone(setData[k].value); if (pane === "settings") settingsPane(true);
    });
  };
  const on = document.getElementById("push-on"), off = document.getElementById("push-off"),
        testIt = document.getElementById("push-test");
  if (on) on.onclick = () => turnPushOn().catch((e) => toast(String(e.message || e)));
  if (off) off.onclick = () => turnPushOff().catch((e) => toast(String(e.message || e)));
  if (testIt) testIt.onclick = async () => toast((await send("/api/push", "POST", { test: true })).said || "Sent");
  box.querySelectorAll("[data-theme-pick]").forEach((b) => b.onclick = () => { setLook({ theme: b.dataset.themePick }); redraw(); });
  box.querySelectorAll("[data-accent-pick]").forEach((b) => b.onclick = () => { setLook({ accent: b.dataset.accentPick }); redraw(); });
  const add = document.getElementById("follow-add");
  if (add) {
    const go = async () => {
      const name = add.value.trim();
      if (!name) return;
      if (following.some((f) => f.key === key(name))) { toast("Already following " + name); return; }
      await follow(name, true);
    };
    document.getElementById("follow-go").onclick = go;
    add.addEventListener("keydown", (e) => e.key === "Enter" && go());
    const findBox = document.getElementById("follow-find");
    findBox.oninput = debounce(() => {
      followFind = findBox.value; redraw();
      const again = document.getElementById("follow-find");
      again.focus(); again.setSelectionRange(again.value.length, again.value.length);
    }, 200);
    box.querySelectorAll("[data-unfollow]").forEach((b) => b.onclick = () => follow(b.dataset.unfollow, false));
  }
}
document.getElementById("settings").onclick = () => { setData = null; settingsPane(); };

/* ------------------------------------------------------------ answers -- */

let qa = { folder: null, list: [], editing: null, coined: [] };

async function loadAnswers(folder) {
  const d = await api("/api/answers?folder=" + enc(folder));
  qa = { folder, list: d.none ? null : (d.questions || []), editing: null, coined: d.coined || [] };
  renderAnswers();
  renderCoined();
}

// Numbers Claude put on the page that his facts did not carry. He reads these
// before anything is sent, which is the deal that lets it write them at all.
function renderCoined() {
  const box = document.getElementById("coined");
  if (!box) return;
  if (!qa.coined.length) { box.innerHTML = ""; return; }
  box.innerHTML = '<div class="coined"><b>Check these numbers</b>' +
    "<p>Claude wrote them from your work; your facts do not carry them.</p>" +
    qa.coined.map((c) => '<div class="cnum"><span class="num">' + esc(c.number || "") + "</span>" +
      "<span>" + esc(c.claim || "") + (c.why ? ' <i class="hint">' + esc(c.why) + "</i>" : "") +
      "</span></div>").join("") + "</div>";
}

function renderAnswers() {
  const box = document.querySelector("#qa .qa");
  if (!box) return;
  if (qa.list === null) { box.innerHTML = '<div class="quiet">This site’s form cannot be read automatically.</div>'; return; }
  if (!qa.list.length) { box.innerHTML = '<div class="quiet">Nothing beyond the usual details.</div>'; return; }
  box.innerHTML = qa.list.map((q, i) => {
    const head = '<div class="q"><span>' + esc(q.label) + (q.required ? " (required)" : "") +
      (q.how === "you" ? ' <span class="mine">Your answer</span>' : "") + "</span>" +
      (qa.editing === i ? "" : (q.how === "you" ? '<button class="link" data-revert="' + i + '">Use jobbot’s</button>' : "") +
        '<button class="link" data-edit="' + i + '">Edit</button>') + "</div>";
    if (qa.editing === i) return "<div>" + head + '<textarea data-box style="margin-top:6px">' + esc(q.answer ?? "") +
      '</textarea><div class="row-btns"><button class="btn primary" data-save="' + i + '">Save</button>' +
      '<button class="btn" data-cancel>Cancel</button></div></div>';
    return "<div>" + head + '<div class="a" title="Click to copy" data-copy="' + i + '">' +
      esc(q.answer ?? "Not answered") + "</div></div>";
  }).join("");
  box.querySelectorAll("[data-copy]").forEach((el) => el.onclick = () => {
    navigator.clipboard.writeText(qa.list[el.dataset.copy].answer ?? ""); toast("Copied"); });
  box.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => {
    qa.editing = Number(b.dataset.edit); renderAnswers();
    const area = box.querySelector("[data-box]");
    if (area) { area.focus(); area.setSelectionRange(area.value.length, area.value.length); }
  });
  box.querySelectorAll("[data-revert]").forEach((b) => b.onclick = async () => {
    const i = Number(b.dataset.revert), mine = qa.list[i].answer;
    const r = await send("/api/answer", "POST", { folder: qa.folder, label: qa.list[i].label, revert: true });
    if (!r.ok) { toast(r.failed || "Nothing to put back"); return; }
    qa.list[i] = { ...qa.list[i], answer: r.answer, how: "draft" }; renderAnswers();
    toast("Back to jobbot’s answer", async () => {
      await send("/api/answer", "POST", { folder: qa.folder, label: qa.list[i].label, text: mine });
      qa.list[i] = { ...qa.list[i], answer: mine, how: "you" }; renderAnswers();
    });
  });
  const cancel = box.querySelector("[data-cancel]");
  if (cancel) cancel.onclick = () => { qa.editing = null; renderAnswers(); };
  const save = box.querySelector("[data-save]");
  if (save) save.onclick = async () => {
    const i = Number(save.dataset.save), text = box.querySelector("[data-box]").value;
    save.disabled = true;
    const r = await send("/api/answer", "POST", { folder: qa.folder, label: qa.list[i].label, text });
    if (!r.ok) { save.disabled = false; toast(r.failed || "That did not save"); return; }
    qa.list[i] = { ...qa.list[i], answer: text, how: "you" }; qa.editing = null; renderAnswers(); toast("Saved");
  };
}

/* ------------------------------------------------------------ applied -- */

let currentApp = null;

function renderApps() {
  const rail = document.getElementById("rail");
  const s = apps.stats || {};
  const groups = [];
  for (const r of apps.rows) {
    const m = month(r.applied_at);
    if (!groups.length || groups[groups.length - 1].m !== m) groups.push({ m, rows: [] });
    groups[groups.length - 1].rows.push(r);
  }
  rail.innerHTML =
    '<div class="tools"><div class="search"><input id="aq" placeholder="Search applications" value="' + esc(appFind) +
      '"><button class="ghost" id="add">Add</button></div>' +
      '<div class="chips">' + ["", ...OUTCOMES].map((o) => '<button class="' + (appOutcome === o ? "on" : "") +
        '" data-outcome="' + esc(o) + '">' + (o || "All") + (s[o] ? " " + s[o] : "") + "</button>").join("") + "</div>" +
      '<div class="stats"><span><b>' + (s.total || 0) + "</b> sent</span><span><b>" + (s.live || 0) +
        "</b> waiting</span><span><b>" + ((s.interview || 0) + (s.OA || 0)) + "</b> interviews and OAs</span></div>" +
    "</div>" +
    (groups.length ? groups.map((g) => '<div class="group">' + esc(g.m) + ' <span class="n">' + g.rows.length + "</span></div>" +
      g.rows.map((r) => '<button class="row' + (currentApp === r.id ? " sel" : "") + '" data-id="' + r.id + '">' +
        logo(r.company, r.apply_url) + '<span class="main"><span class="line1"><span class="co">' + esc(r.company) +
        '</span><span class="out o-' + String(r.outcome).replace(/[^A-Za-z]/g, "") + '">' + esc(r.outcome) + "</span></span>" +
        '<span class="title">' + esc(r.title) + '</span><span class="line3"><span>' + esc(day(r.applied_at)) + "</span>" +
        (real(r.referral) ? "<span>Referred by " + esc(real(r.referral)) + "</span>" : "") + "</span></span></button>").join("")).join("")
      : '<div class="none"><b>Nothing here</b>Applications you send land here. Add older ones with Add.</div>') +
    '<div class="foot">' + (apps.rows.length < apps.total
      ? '<button class="link" id="older">Show ' + (apps.total - apps.rows.length) + " older</button>" : "") +
      '<a class="link" href="/api/export.csv">Download as a spreadsheet</a></div>';

  const q = document.getElementById("aq");
  q.oninput = debounce(() => { appFind = q.value; loadApps(0); }, 250);
  document.getElementById("add").onclick = () => openApp(null);
  rail.querySelectorAll("[data-outcome]").forEach((b) => b.onclick = () => { appOutcome = b.dataset.outcome; loadApps(0); });
  rail.querySelectorAll("[data-id]").forEach((b) => b.onclick = () =>
    openApp(apps.rows.find((r) => String(r.id) === b.dataset.id)));
  const older = document.getElementById("older");
  if (older) older.onclick = () => loadApps(apps.rows.length);
}

function openApp(r) {
  currentApp = r ? r.id : "new";
  pane = "app";
  if (tab === "apps") renderApps();
  const v = r || { company: "", title: "", applied_at: new Date().toISOString().slice(0, 10), outcome: "no response" };
  const field = (name, label, value, type) => '<div class="field"><label for="f-' + name + '">' + label +
    '</label><input id="f-' + name + '" name="' + name + '" type="' + (type || "text") + '" value="' + esc(value ?? "") + '"></div>';
  const box = document.getElementById("detail");
  box.innerHTML = '<div class="d"><button class="btn back" id="back">‹ Applied</button>' +
    '<div class="d-head">' + (r ? logo(r.company, r.apply_url, true) : "") + '<div><div class="d-co">' +
      (r ? esc(r.company) : "Add an application") + "</div>" + '<h1 class="d-title">' + (r ? esc(r.title) : "One you sent yourself") +
      "</h1></div></div>" +
    '<section class="sec"><div class="box">' +
      (r ? "" : field("company", "Company", "") + field("title", "Role", "")) +
      '<div class="field"><label for="f-outcome">Outcome</label><select id="f-outcome" name="outcome">' +
        OUTCOMES.map((o) => "<option" + (o === v.outcome ? " selected" : "") + ">" + esc(o) + "</option>").join("") + "</select></div>" +
      field("applied_at", "Applied on", v.applied_at, "date") +
      field("referral", "Referral", real(v.referral)) +
      '<div class="field"><label for="f-notes">Notes</label><textarea id="f-notes" name="notes">' + esc(real(v.notes)) + "</textarea></div>" +
    "</div>" +
    '<div class="row-btns"><button class="btn primary" id="save">Save</button>' +
      (r && r.apply_url ? '<a class="btn" href="' + esc(r.apply_url) + '" target="_blank" rel="noopener">Open posting</a>' : "") +
      (r && r.pdf ? '<a class="btn" href="/file?path=' + enc(r.pdf) + '" target="_blank">Resume you sent</a>' +
        '<button class="btn" data-pdf="' + esc(r.pdf) + '" data-co="' + esc(r.company) + '">Save PDF</button>' : "") +
      (r ? '<button class="btn danger" id="drop">Delete</button>' : "") + "</div></section>" +
    // Before an interview, this is what he needs: what the posting said, what he
    // sent, and what he answered.
    (r && r.preview ? '<section class="sec"><h2>The resume you sent</h2>' +
      '<img class="paper" alt="The resume you sent" src="/file?path=' + enc(r.preview) + '"></section>' : "") +
    (r && r.folder ? '<div id="qa">' + fold("answers", "What you answered",
      '<div class="box"><div class="qa"><div class="quiet">Loading</div></div></div>') + "</div>" +
      '<div id="coined"></div>' : "") +
    (r && r.jd ? fold("jd", "The posting", '<div class="jd">' + posting(r.jd) + "</div>") : "") +
    "</div>";
  if (phone()) { document.body.classList.add("reading"); window.scrollTo(0, 0); history.pushState({ app: 1 }, ""); }
  document.getElementById("back").onclick = () => history.back();
  bindPdf(document.getElementById("detail"));
  document.querySelectorAll("details.fold").forEach((el) => el.ontoggle = () => {
    folded[el.dataset.fold] = el.open;
    try { localStorage.setItem("jobbot-folded", JSON.stringify(folded)); } catch (e) { /* this visit only */ }
  });
  if (r && r.folder) loadAnswers(r.folder);
  const value = (n) => { const el = box.querySelector('[name="' + n + '"]'); return el ? el.value.trim() : ""; };
  document.getElementById("save").onclick = async () => {
    const body = { outcome: value("outcome"), applied_at: value("applied_at"), referral: value("referral"), notes: value("notes") };
    if (r) { body.id = r.id; await send("/api/applications", "PATCH", body); }
    else {
      body.company = value("company"); body.title = value("title");
      if (!body.company || !body.title) { toast("Add a company and a role first"); return; }
      await send("/api/applications", "POST", body);
    }
    toast("Saved"); loadApps(0);
  };
  const drop = document.getElementById("drop");
  if (drop) drop.onclick = async () => {
    await api("/api/applications?id=" + r.id, { method: "DELETE" });
    currentApp = null; closeJob();
    document.getElementById("detail").innerHTML = '<div class="empty-d">Pick an application to edit it.</div>';
    toast("Deleted", async () => { await send("/api/applications/restore", "POST", { id: r.id }); loadApps(0); });
    loadApps(0);
  };
}

/* -------------------------------------------------------------- shell -- */

function debounce(fn, ms) { let t = null; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function switchTab(next) {
  if (tab === next) return;
  tab = next; current = null; currentApp = null; closeJob();
  pane = next === "jobs" ? "job" : "app";
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === next));
  document.getElementById("rail").innerHTML = '<div class="none">Loading</div>';
  document.getElementById("detail").innerHTML = '<div class="empty-d">' +
    (next === "jobs" ? "Pick a job to read the posting." : "Pick an application to edit it.") + "</div>";
  load();
}
document.querySelectorAll("#tabs button").forEach((b) => b.onclick = () => switchTab(b.dataset.tab));
// The bottom bar is the app's navigation on a phone.
document.querySelectorAll("#tabbar button").forEach((b) => b.onclick = () => {
  const go = b.dataset.go;
  if (go === "settings") { setData = null; settingsPane(); }
  else { if (pane === "settings" || pane === "muted" || pane === "filtered") pane = go === "jobs" ? "job" : "app";
         document.body.classList.remove("reading"); switchTab(go); }
  markTabbar();
});
function markTabbar() {
  const on = pane === "settings" ? "settings" : tab === "jobs" ? "jobs" : "apps";
  document.querySelectorAll("#tabbar button").forEach((b) => b.classList.toggle("on", b.dataset.go === on));
}

let hintsLoaded = false;
async function loadJobs() {
  if (!hintsLoaded) { hintsLoaded = true; loadSuggestions(); }
  const q = [showArchived ? "skipped=1" : "", showSnoozed ? "snoozed=1" : ""].filter(Boolean).join("&");
  const d = await api("/api/jobs" + (q ? "?" + q : ""));
  jobs = d.jobs || []; checked = d.checked || null; snoozedCount = d.snoozed || 0; muted = d.muted || [];
  following = d.following || []; filteredCount = d.filtered || 0; owner = d.owner || "";
  const wasBusy = busyNow.length;
  busyNow = d.running || [];
  // He asked for a check: say what came of it once the run is done.
  if (waitingOn && wasBusy && !busyNow.length) {
    const fresh = jobs.filter((j) => j.state === "new" && !waitingOn.had.has(j.uid)).length;
    toast(fresh ? fresh + (fresh === 1 ? " new posting" : " new postings") : "Checked - nothing new");
    waitingOn = null;
  }
  if (tab !== "jobs") return;
  // On a laptop the first job is open from the start, so there is always a
  // posting to read - unless he has Settings or another page open there.
  if (pane === "job" && !current && !phone()) {
    const first = shown().find((j) => j.state !== "skipped");
    if (first) current = first.uid;
  }
  renderRail();
  if (pane === "job" && current && !document.querySelector("#detail textarea:focus") && !menuOpen) renderJob();
}

async function loadApps(offset) {
  const d = await api("/api/applications?q=" + enc(appFind) + "&outcome=" + enc(appOutcome) + "&offset=" + (offset || 0));
  apps = offset ? { ...d, rows: apps.rows.concat(d.rows || []) } : d;
  if (tab === "apps") renderApps();
}

const load = () => { markTabbar(); return (tab === "jobs" ? loadJobs() : loadApps(0)).catch(() => {}); };

// Swiping. A job swipes left to archive and right for whatever its button says;
// an open job swipes right to go back, the way iOS does it. Nothing moves until
// the gesture is clearly sideways, so scrolling still wins.
(() => {
  const RIGHT = { new: ["build", "Write it"], ready: ["approve", "Apply"], needs: ["applied", "Applied"],
                  skipped: ["reopen", "Put back"] };
  let row = null, job = null, x0 = 0, y0 = 0, dir = null, dx = 0;
  const rail = document.getElementById("rail");

  const wrap = (r) => {
    if (r.parentElement && r.parentElement.classList.contains("swipe")) return r.parentElement;
    const holder = document.createElement("div");
    holder.className = "swipe";
    r.replaceWith(holder);
    holder.append(r);
    return holder;
  };
  const clear = (r) => {
    r.style.transition = "transform .18s ease-out";
    r.style.transform = "";
    const holder = r.parentElement;
    if (holder && holder.classList.contains("swipe")) holder.dataset.side = "";
  };

  rail.addEventListener("touchstart", (e) => {
    const r = e.target.closest && e.target.closest(".row");
    row = r && !selecting ? r : null;
    job = row ? jobs.find((j) => j.uid === row.dataset.uid) : null;
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dir = null; dx = 0;
    if (row) row.style.transition = "";
  }, { passive: true });

  rail.addEventListener("touchmove", (e) => {
    if (!row || !job) return;
    const mx = e.touches[0].clientX - x0, my = e.touches[0].clientY - y0;
    if (!dir) {
      if (Math.abs(mx) < 12 && Math.abs(my) < 12) return;
      dir = Math.abs(mx) > Math.abs(my) * 1.6 ? "x" : "y";
      if (dir === "x") wrap(row);
    }
    if (dir !== "x") { row = null; return; }
    const right = RIGHT[job.state];
    dx = Math.max(-140, Math.min(140, mx));
    if (dx > 0 && !right) dx = Math.min(dx, 40) * 0.4;     // nothing to reveal that way
    if (dx < 0 && job.state === "skipped") dx = Math.max(dx, -40) * 0.4;
    e.preventDefault();
    row.style.transform = "translateX(" + dx + "px)";
    const holder = row.parentElement;
    holder.dataset.side = dx < -20 ? "left" : dx > 20 ? "right" : "";
    holder.dataset.label = dx < 0 ? "Archive" : right ? right[1] : "";
  }, { passive: false });

  rail.addEventListener("touchend", () => {
    if (!row || !job) { row = null; return; }
    const right = RIGHT[job.state];
    const go = Math.abs(dx) > 88;
    const r = row, j = job;
    row = null; job = null;
    clear(r);
    if (!go) return;
    if (dx < 0 && j.state !== "skipped") archive([j.uid]);
    else if (dx > 0 && right) run(j, right[0], "");
  });
})();

// Sideways on the list moves between tabs, so the whole app is thumb-driven.
(() => {
  const rail = document.getElementById("rail");
  let x0 = null, y0 = 0, onRow = false;
  const order = () => ZONES.map(([k]) => k);
  rail.addEventListener("touchstart", (e) => {
    onRow = !!(e.target.closest && e.target.closest(".row"));
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
  }, { passive: true });
  rail.addEventListener("touchend", (e) => {
    if (x0 === null || onRow || selecting) { x0 = null; return; }
    const mx = e.changedTouches[0].clientX - x0, my = Math.abs(e.changedTouches[0].clientY - y0);
    x0 = null;
    if (Math.abs(mx) < 70 || my > 50) return;
    const keys = order(), at = keys.indexOf(view.zone);
    const next = keys[Math.min(keys.length - 1, Math.max(0, at + (mx < 0 ? 1 : -1)))];
    if (next === view.zone) return;
    view.zone = next; saveView(); renderRail();
    const list = document.getElementById("rail");
    list.classList.remove("slide-l", "slide-r");
    void list.offsetWidth;
    list.classList.add(mx < 0 ? "slide-l" : "slide-r");
  });
})();

// An open job swipes back to the list, like every other phone app.
(() => {
  const box = document.getElementById("detail");
  let x0 = null, y0 = 0;
  box.addEventListener("touchstart", (e) => {
    const inSlider = e.target.closest && e.target.closest("textarea, input, .actions, .jd img");
    x0 = document.body.classList.contains("reading") && !inSlider ? e.touches[0].clientX : null;
    y0 = e.touches[0].clientY;
  }, { passive: true });
  box.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const t = e.changedTouches[0];
    const mx = t.clientX - x0, my = Math.abs(t.clientY - y0);
    x0 = null;
    if (mx > 90 && my < 60) history.back();
  });
})();

// Ask jobbot to sweep the boards now, and watch closely for a few minutes so
// what it finds appears without him reaching for anything.
let watching = null;
async function checkNow() {
  waitingOn = { had: new Set(jobs.map((j) => j.uid)), at: Date.now() };
  busyNow = [{ kind: "watch", says: "Checking the boards", since: new Date().toISOString() }];
  renderRail();
  const r = await send("/api/check", "POST", {});
  if (!r.ok) { busyNow = []; waitingOn = null; renderRail(); toast(r.said || "Could not start a check"); return; }
  clearTimeout(watching);
  const until = Date.now() + 5 * 60000;
  const peek = async () => {
    if (Date.now() > until) { busyNow = busyNow.filter((b) => b.kind !== "watch"); renderRail(); return; }
    await load();
    watching = setTimeout(peek, 6000);
  };
  watching = setTimeout(peek, 4000);
}

// Pull down at the top of the list to check the boards, as any phone app does.
(() => {
  const rail = document.getElementById("rail");
  let start = null, ready = false;
  const tip = document.createElement("div");
  tip.className = "pull";
  tip.textContent = "Pull to check for new postings";
  rail.style.position = "relative";
  rail.prepend(tip);
  rail.addEventListener("touchstart", (e) => {
    start = (window.scrollY <= 0 && rail.scrollTop <= 0) ? e.touches[0].clientY : null;
    ready = false;
  }, { passive: true });
  rail.addEventListener("touchmove", (e) => {
    if (start === null) return;
    const down = e.touches[0].clientY - start;
    ready = down > 70;
    tip.classList.toggle("on", down > 20);
    tip.textContent = ready ? "Release to check the boards" : "Pull to check for new postings";
  }, { passive: true });
  rail.addEventListener("touchend", async () => {
    if (ready) { tip.textContent = "Checking the boards"; await load(); await checkNow(); }
    tip.classList.remove("on");
    start = null; ready = false;
  });
})();
load();
// While a resume is being written or an application is being filled, the app
// checks every 10 seconds; otherwise every minute. It also checks the moment he
// comes back to it, so the board is never stale in front of him.
let beatTimer = null;
const busy = () => busyNow.length > 0 || jobs.some((j) => j.state === "building" || j.state === "working");
function keepUp() {
  clearTimeout(beatTimer);
  beatTimer = setTimeout(async () => {
    const quiet = !document.querySelector("#detail textarea:focus") && !menuOpen && pane !== "settings";
    if (tab === "jobs" && quiet && document.visibilityState === "visible") await load();
    keepUp();
  }, busy() ? 10000 : 60000);
}
keepUp();
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") { load(); keepUp(); } });
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => { /* no notifications */ });
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
</script></body></html>`;
