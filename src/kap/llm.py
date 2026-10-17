"""One model adapter for every agent and eval arm.

Three providers behind one call shape:
  nemotron  nvidia/nemotron-3-super-120b-a12b      hosted NIM, OpenAI-compatible chat API
  llama     meta/llama-3.2-90b-vision-instruct     hosted NIM, text-only use
  claude    claude-opus-5-5                        Anthropic API via the anthropic SDK

Every response is cached on disk under cache/<sha256 of request>.json so an eval rerun costs
nothing and makes the same decisions. The free NIM tier is rate limited (about 40 requests a
minute), so NIM calls go through a token bucket and retry with backoff on 429/5xx.
Secrets never appear in the cache or in any log line.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from kap.config import CACHE_DIR, REPO_ROOT, env

NIM_BASE = "https://integrate.api.nvidia.com/v1"

MODELS: dict[str, dict[str, Any]] = {
    "nemotron": {"provider": "nim", "id": "nvidia/nemotron-3-super-120b-a12b"},
    "llama": {"provider": "nim", "id": "meta/llama-3.2-90b-vision-instruct"},
    "claude": {"provider": "anthropic", "id": "claude-opus-5-5"},
}

_pricing_path = REPO_ROOT / "questions" / "pricing.yaml"
PRICING: dict[str, dict[str, float]] = yaml.safe_load(_pricing_path.read_text())["models"] if _pricing_path.exists() else {}


@dataclass
class LLMResult:
    text: str
    model_key: str
    model_id: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    cached: bool
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def cost_for(model_key: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(model_key)
    if not p:
        return 0.0
    return input_tokens / 1e6 * p["input_per_mtok"] + output_tokens / 1e6 * p["output_per_mtok"]


class _Throttle:
    """Simple token bucket: at most `rate` calls per `per` seconds, process-wide."""

    def __init__(self, rate: int, per: float) -> None:
        self.rate, self.per = rate, per
        self.stamps: list[float] = []
        self.lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.stamps = [s for s in self.stamps if now - s < self.per]
                if len(self.stamps) < self.rate:
                    self.stamps.append(now)
                    return
                sleep_for = self.per - (now - self.stamps[0]) + 0.05
            time.sleep(max(sleep_for, 0.05))


_nim_throttle = _Throttle(rate=int(os.environ.get("KAP_NIM_RPM", "30")), per=60.0)


def _cache_key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    p = CACHE_DIR / "llm" / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def _cache_put(key: str, data: dict[str, Any]) -> None:
    p = CACHE_DIR / "llm" / f"{key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def _retry(fn, attempts: int = 6):
    delay = 2.0
    for i in range(attempts):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (429, 500, 502, 503, 504) and i < attempts - 1:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
        except (httpx.TimeoutException, httpx.TransportError):
            if i < attempts - 1:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise


def _nim_chat(model_id: str, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> dict[str, Any]:
    body = {"model": model_id, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    headers = {"Authorization": f"Bearer {env('NVIDIA_API_KEY')}", "Content-Type": "application/json"}

    def go():
        _nim_throttle.wait()
        with httpx.Client(timeout=180) as c:
            r = c.post(f"{NIM_BASE}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()

    return _retry(go)


def _anthropic_chat(model_id: str, system: str, user: str, max_tokens: int, effort: str) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"), max_retries=4)
    kwargs: dict[str, Any] = dict(
        model=model_id, max_tokens=max_tokens, messages=[{"role": "user", "content": user}],
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if system:
        kwargs["system"] = system
    with client.beta.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return {
        "text": text,
        "stop_reason": msg.stop_reason,
        "model": msg.model,
        "usage": {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens},
    }


def complete(model_key: str, system: str, user: str, *, max_tokens: int = 2048, temperature: float = 0.0,
             effort: str = "medium", use_cache: bool = True) -> LLMResult:
    """Single-turn completion. Deterministic settings so the cache is meaningful."""
    spec = MODELS[model_key]
    payload = {"model": spec["id"], "system": system, "user": user, "max_tokens": max_tokens,
               "temperature": temperature, "effort": effort if spec["provider"] == "anthropic" else None, "v": 1}
    key = _cache_key(payload)
    if use_cache and (hit := _cache_get(key)):
        return LLMResult(text=hit["text"], model_key=model_key, model_id=spec["id"], input_tokens=hit["input_tokens"],
                         output_tokens=hit["output_tokens"], latency_s=hit["latency_s"], cached=True,
                         cost_usd=cost_for(model_key, hit["input_tokens"], hit["output_tokens"]), raw=hit)
    t0 = time.perf_counter()
    if spec["provider"] == "nim":
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        data = _nim_chat(spec["id"], messages, max_tokens, temperature)
        choice = data["choices"][0]["message"]
        text = choice.get("content") or ""
        usage = data.get("usage") or {}
        in_tok, out_tok = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        stop = data["choices"][0].get("finish_reason")
    else:
        data = _anthropic_chat(spec["id"], system, user, max_tokens, effort)
        text = data["text"]
        in_tok, out_tok = data["usage"]["input_tokens"], data["usage"]["output_tokens"]
        stop = data["stop_reason"]
    latency = time.perf_counter() - t0
    record = {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "latency_s": latency,
              "stop_reason": stop, "model_id": spec["id"], "ts": time.time()}
    if use_cache:
        _cache_put(key, record)
    return LLMResult(text=text, model_key=model_key, model_id=spec["id"], input_tokens=in_tok, output_tokens=out_tok,
                     latency_s=latency, cached=False, cost_usd=cost_for(model_key, in_tok, out_tok), raw=record)


def strip_fences(text: str) -> str:
    """Pull the SQL (or JSON) out of a fenced block if the model used one."""
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        # take the first fenced block
        if len(parts) >= 3:
            block = parts[1]
            first_nl = block.find("\n")
            if first_nl != -1 and block[:first_nl].strip().isalpha():
                block = block[first_nl + 1:]
            return block.strip()
    return t


def embed(texts: list[str], input_type: str = "passage", model_id: str = "nvidia/nemotron-3-embed-1b") -> list[list[float]]:
    """NeMo Retriever embeddings through NIM. Cached per text."""
    out: list[list[float] | None] = [None] * len(texts)
    todo: list[int] = []
    for i, t in enumerate(texts):
        key = _cache_key({"embed": model_id, "input_type": input_type, "text": t})
        hit = _cache_get(key)
        if hit:
            out[i] = hit["embedding"]
        else:
            todo.append(i)
    headers = {"Authorization": f"Bearer {env('NVIDIA_API_KEY')}", "Content-Type": "application/json"}
    for start in range(0, len(todo), 16):
        idx = todo[start:start + 16]
        body = {"model": model_id, "input": [texts[i] for i in idx], "input_type": input_type,
                "encoding_format": "float", "truncate": "END"}

        def go():
            _nim_throttle.wait()
            with httpx.Client(timeout=120) as c:
                r = c.post(f"{NIM_BASE}/embeddings", headers=headers, json=body)
                r.raise_for_status()
                return r.json()

        data = _retry(go)
        for j, item in zip(idx, data["data"]):
            out[j] = item["embedding"]
            _cache_put(_cache_key({"embed": model_id, "input_type": input_type, "text": texts[j]}), {"embedding": item["embedding"]})
    return [o for o in out if o is not None]
