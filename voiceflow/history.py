"""Dictation history: history.jsonl, one JSON object per line."""
import json
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
