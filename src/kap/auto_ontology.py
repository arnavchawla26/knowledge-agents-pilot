"""Client for NVIDIA Auto Ontology's backend (vendor/auto-ontology, docker compose, backend :3001).

Asks a natural-language question through POST /api/chat/completions (SSE) and returns the SQL the
agent validated, its answer text and the provenance it reports. Responses are cached on disk like
every other model call. The frontend (:3000) is the authenticated gateway; the backend port is only
reachable on localhost in this compose, which is how the pilot calls it."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx

from kap.config import CACHE_DIR, env


def status() -> dict[str, Any]:
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    with httpx.Client(timeout=10) as c:
        return {"health": c.get(f"{base}/api/health/live").json(),
                "semantic": c.get(f"{base}/api/semantic-compilation/status").json(),
                "dbs": c.get(f"{base}/api/datasources/dbs").json().get("count"),
                "terms": c.get(f"{base}/api/terms").json().get("total")}


def ask(question: str, use_cache: bool = True, timeout: float = 600.0) -> dict[str, Any]:
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    key = hashlib.sha256(json.dumps({"ao": question, "v": 1}).encode()).hexdigest()
    path = CACHE_DIR / "auto_ontology" / f"{key}.json"
    if use_cache and path.exists():
        d = json.loads(path.read_text())
        d["cached"] = True
        return d
    out: dict[str, Any] = {"question": question, "sql": None, "sql_candidates": [], "steps": [], "answer": None,
                           "provenance": None, "error": None, "model": env("AO_MODEL_LABEL", "nemotron-3-super-120b-a12b"),
                           "cached": False}
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as c, c.stream("POST", f"{base}/api/chat/completions",
                                                          json={"question": question}, headers={"Accept": "text/event-stream"}) as r:
            if r.status_code != 200:
                out["error"] = f"HTTP {r.status_code}: {r.read().decode()[:300]}"
            else:
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        ev = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    t = ev.get("type")
                    if t == "step":
                        out["steps"].append(ev.get("label") or ev.get("node"))
                    elif t == "sql":
                        out["sql_candidates"].append(ev.get("sql"))
                    elif t == "result":
                        ans = ev.get("answer") or {}
                        out["answer"] = ans.get("response")
                        out["sql"] = ans.get("sql_code") or (out["sql_candidates"][-1] if out["sql_candidates"] else None)
                        out["provenance"] = {k: v for k, v in ans.items() if k not in ("response", "sql_code")}
                    elif t == "error":
                        out["error"] = ev.get("message")
    except httpx.HTTPError as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["latency_s"] = round(time.perf_counter() - t0, 3)
    if use_cache and not out["error"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, default=str))
    return out


if __name__ == "__main__":
    import sys

    print(json.dumps(status(), indent=1))
    if len(sys.argv) > 1:
        print(json.dumps(ask(" ".join(sys.argv[1:])), indent=1, default=str)[:4000])
