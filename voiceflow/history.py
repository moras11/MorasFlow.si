"""Dictation history: history.jsonl (one JSON object per line) and a readable page to search and copy from."""
import json
import os
from datetime import datetime


def save(path, mode, raw, text, latency_ms):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), "mode": mode, "raw": raw,
                            "cleaned": text, "latency_ms": latency_ms}, ensure_ascii=False) + "\n")


def read(path):
    """All entries, oldest first. Unreadable lines are skipped rather than hiding the rest."""
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    return entries


def open_page(path):
    """Write history.html next to history.jsonl and open it in the default browser."""
    page = path.with_suffix(".html")
    # Embedded as JSON and rendered with textContent, so dictated text can never become markup.
    data = json.dumps(read(path), ensure_ascii=False).replace("</", "<\\/")
    page.write_text(PAGE.replace("/*DATA*/[]", data), encoding="utf-8")
    os.startfile(page)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MorasFlow.si history</title>
<style>
  :root { --bg: #f6f7f9; --card: #fff; --text: #1f2328; --muted: #6b7280; --line: #e5e7eb;
          --accent: #16a34a; --accent-text: #fff; --badge: #eef2f7; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #111418; --card: #1b1f24; --text: #e6e8eb; --muted: #9aa3ad; --line: #2b3138;
            --accent: #22c55e; --accent-text: #0b1a10; --badge: #262c33; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 16px/1.55 "Segoe UI", system-ui, sans-serif; }
  header { position: sticky; top: 0; background: var(--bg); padding: 20px 0 12px;
           border-bottom: 1px solid var(--line); }
  .wrap { max-width: 760px; margin: 0 auto; padding-left: 16px; padding-right: 16px; }
  h1 { font-size: 20px; margin: 0 0 12px; }
  h1 span { color: var(--muted); font-weight: 400; font-size: 14px; margin-left: 8px; }
  input { width: 100%; padding: 10px 12px; font: inherit; color: var(--text); background: var(--card);
          border: 1px solid var(--line); border-radius: 8px; }
  main { padding-top: 8px; padding-bottom: 40px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
       margin: 24px 0 8px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
          padding: 12px 14px; margin-bottom: 10px; }
  .meta { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
  .badge { background: var(--badge); border-radius: 999px; padding: 1px 8px; }
  .meta > button:first-of-type { margin-left: auto; }
  .text { white-space: pre-wrap; overflow-wrap: anywhere; margin-top: 6px; }
  .raw { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--muted); font-size: 14px;
         border-left: 3px solid var(--line); padding-left: 10px; margin-top: 8px; }
  button { font: inherit; font-size: 13px; cursor: pointer; border-radius: 6px; padding: 4px 12px;
           border: 1px solid var(--line); background: var(--card); color: var(--text); }
  button.copy { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
  button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .empty { color: var(--muted); text-align: center; margin-top: 48px; }
</style>
</head>
<body>
<header><div class="wrap">
  <h1>MorasFlow.si history<span id="count"></span></h1>
  <input id="search" type="search" placeholder="Search your dictations" aria-label="Search" autofocus>
</div></header>
<main class="wrap" id="list"></main>
<script id="data" type="application/json">/*DATA*/[]</script>
<script>
const entries = JSON.parse(document.getElementById("data").textContent).reverse();  // newest first
const list = document.getElementById("list");
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls;
                                 if (text != null) e.textContent = text; return e; };

function dayLabel(d) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const diff = Math.round((today - day) / 864e5);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

async function copy(text, button) {
  try { await navigator.clipboard.writeText(text); }
  catch { const t = el("textarea"); t.value = text; document.body.append(t); t.select();
          document.execCommand("copy"); t.remove(); }
  const label = button.textContent; button.textContent = "Copied";
  setTimeout(() => button.textContent = label, 1200);
}

function render(query) {
  const q = query.trim().toLowerCase();
  const shown = entries.filter(e => !q || (e.cleaned + " " + e.raw).toLowerCase().includes(q));
  document.getElementById("count").textContent =
    q ? `${shown.length} of ${entries.length}` : `${entries.length} dictation${entries.length === 1 ? "" : "s"}`;
  list.replaceChildren();
  if (!shown.length) {
    list.append(el("p", "empty", entries.length ? "Nothing matches your search." : "No dictations yet."));
    return;
  }
  let lastDay = "";
  for (const e of shown) {
    const d = new Date(e.timestamp), day = dayLabel(d);
    if (day !== lastDay) { list.append(el("h2", null, day)); lastDay = day; }
    const card = el("article", "card"), meta = el("div", "meta");
    meta.append(el("span", null, d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })),
                el("span", "badge", e.mode));
    if (e.raw && e.raw !== e.cleaned) {
      const raw = el("div", "raw", e.raw); raw.hidden = true;
      const toggle = el("button", null, "Original");
      toggle.onclick = () => { raw.hidden = !raw.hidden; toggle.textContent = raw.hidden ? "Original" : "Hide original"; };
      const copyRaw = el("button", null, "Copy original"); copyRaw.onclick = () => copy(e.raw, copyRaw);
      raw.append(el("div"), copyRaw);
      meta.append(toggle);
      card.append(meta, el("div", "text", e.cleaned), raw);
    } else {
      card.append(meta, el("div", "text", e.cleaned));
    }
    const button = el("button", "copy", "Copy"); button.onclick = () => copy(e.cleaned, button);
    meta.append(button);
    list.append(card);
  }
}

const search = document.getElementById("search");
search.addEventListener("input", () => render(search.value));
render("");
</script>
</body>
</html>
"""
