"""Client for NVIDIA Auto Ontology's backend (vendor/auto-ontology, docker compose, backend :3001).

Asks a natural-language question through POST /api/chat/completions (SSE) and returns the SQL the
agent validated, its answer text and the provenance it reports. Responses are cached on disk like
every other model call. The frontend (:3000) is the authenticated gateway; the backend port is only
reachable on localhost in this compose, which is how the pilot calls it."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
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


def cache_path(question: str, layer: str) -> Path:
    key_src: dict[str, Any] = {"ao": question, "v": 1}
    if layer != "v0":
        key_src["layer"] = layer
    key = hashlib.sha256(json.dumps(key_src).encode()).hexdigest()
    return CACHE_DIR / "auto_ontology" / f"{key}.json"


def ask(question: str, use_cache: bool = True, timeout: float = 600.0, layer: str | None = None) -> dict[str, Any]:
    """`layer` names the state of Auto Ontology's semantic layer the answer belongs to, so a before
    and an after answer to the same question are cached apart: "v0" is the compiled layer as
    shipped (empty term descriptions), "glossary" is after `kap.eval.ao_enrich`. Default from
    `AO_LAYER`, else v0 (whose cache key predates the tag)."""
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    layer = layer or env("AO_LAYER", "v0")
    path = cache_path(question, layer)
    if use_cache and path.exists():
        d = json.loads(path.read_text())
        d["cached"] = True
        return d
    out: dict[str, Any] = {"question": question, "sql": None, "sql_candidates": [], "steps": [], "answer": None,
                           "provenance": None, "error": None, "model": env("AO_MODEL_LABEL", "nemotron-3-super-120b-a12b"),
                           "layer": layer, "cached": False}
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


# --- semantic-layer writes (the documented management API, docs/openapi/backend.json) ---------
# These call the backend on localhost; a shared deployment would go through the Next.js gateway
# with an API token (vendor/auto-ontology/skills/nvidia-ontology-management).


def list_terms() -> list[dict[str, Any]]:
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    with httpx.Client(timeout=30) as c:
        return c.get(f"{base}/api/terms").json()["terms"]


def patch_term(term_id: str, description: str) -> dict[str, Any]:
    """PATCH /api/terms/{id} (TermUpdate.description). The backend refreshes the term's semantic
    embedding on a description change (server/terms/router.py), so no recompilation is needed."""
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    with httpx.Client(timeout=120) as c:
        r = c.patch(f"{base}/api/terms/{term_id}", json={"description": description})
        r.raise_for_status()
        return r.json()["data"]


def list_sql_attributes(term_id: str) -> list[dict[str, Any]]:
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    with httpx.Client(timeout=30) as c:
        d = c.get(f"{base}/api/terms/{term_id}/sql-attributes").json()
        return d.get("data", d) if isinstance(d, dict) else d


def create_sql_attribute(term_id: str, name: str, description: str, expression: str) -> dict[str, Any]:
    """POST /api/sql-attributes/validate then POST /api/sql-attributes (SqlAttributeCreate). The
    expression is a full SELECT over catalogued tables; 422 means it did not parse or resolve,
    409 means the term already has an equivalent expression."""
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    with httpx.Client(timeout=120) as c:
        v = c.post(f"{base}/api/sql-attributes/validate", json={"expression": expression, "term_id": term_id})
        if v.status_code == 409:
            return {"status": "exists", "name": name}
        if v.status_code != 200:
            return {"status": f"invalid HTTP {v.status_code}", "name": name, "detail": v.text[:300]}
        r = c.post(f"{base}/api/sql-attributes", json={"term_id": term_id, "name": name, "description": description,
                                                      "expression": expression, "source": "manual"})
        if r.status_code == 409:
            return {"status": "exists", "name": name}
        r.raise_for_status()
        return {"status": "created", "name": name, "id": r.json().get("data", {}).get("id")}


def coverage(question: str) -> dict[str, Any]:
    """POST /api/question-entity-coverage: the REST form of the MCP `check_answerable` step the
    query skill says to run before asking."""
    base = env("AO_BACKEND_URL", "http://localhost:3001")
    try:
        with httpx.Client(timeout=300) as c:
            r = c.post(f"{base}/api/question-entity-coverage", json={"question": question})
            return r.json().get("data", {"error": r.text[:300]}) if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
    except httpx.HTTPError as e:  # the free tier's model and embedding calls behind this endpoint time out at times
        return {"error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import sys

    print(json.dumps(status(), indent=1))
    if len(sys.argv) > 1:
        print(json.dumps(ask(" ".join(sys.argv[1:])), indent=1, default=str)[:4000])
