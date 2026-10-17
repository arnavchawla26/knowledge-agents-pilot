"""Append-only audit log: one JSON line per tool call (audit/YYYY-MM-DD.jsonl, gitignored;
audit/sample.jsonl is a committed excerpt). Arguments are hashed, not stored, so case text
never lands in the log; the hash still lets two calls be matched."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from kap.config import AUDIT_DIR

_lock = threading.Lock()


def args_hash(args: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]


def record(*, caller: str, agent: str, tool: str, args: dict[str, Any], rows: int, latency_s: float,
           tokens_in: int = 0, tokens_out: int = 0, ok: bool = True, error: str | None = None,
           model: str | None = None, cost_usd: float = 0.0, task_id: str | None = None) -> dict[str, Any]:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "caller": caller, "agent": agent, "tool": tool, "args_hash": args_hash(args),
        "rows": rows, "latency_ms": round(latency_s * 1000, 1), "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": round(cost_usd, 6), "model": model, "ok": ok, "error": error, "task_id": task_id,
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIT_DIR / f"{time.strftime('%Y-%m-%d')}.jsonl"
    with _lock, open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_all() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not AUDIT_DIR.exists():
        return out
    for p in sorted(AUDIT_DIR.glob("*.jsonl")):
        if p.name == "sample.jsonl":
            continue
        for line in p.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out
