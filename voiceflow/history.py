"""Dictation history: history.jsonl, one JSON object per line."""
import json
from collections import deque
from datetime import datetime


def save(path, mode, raw, text, latency_ms):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), "mode": mode, "raw": raw,
                            "cleaned": text, "latency_ms": latency_ms}, ensure_ascii=False) + "\n")


def read(path, last=None):
    """Entries, oldest first (only the `last` lines if given, so the tray stays fast on a big file).
    Lines that aren't a complete dictation (a torn write after a power cut, a hand edit, a stray byte) are skipped:
    the tray menu and history window index these fields, so one bad line must not take them down."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", errors="replace") as f:
        lines = deque(f, maxlen=last) if last else f.read().splitlines()
    entries = []
    for line in lines:
        try:
            e = json.loads(line)
            datetime.fromisoformat(e["timestamp"])
            if isinstance(e["cleaned"], str) and isinstance(e.get("raw", ""), str):
                entries.append(e)
        except (ValueError, KeyError, TypeError):
            pass
    return entries
