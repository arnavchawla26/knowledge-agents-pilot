"""Shared runtime for the three Knowledge Agents.

Design, deliberately: each agent is a fixed workflow (tool calls decided by code, in a fixed order,
through the MCP client with the agent's data permissions) plus one or two model calls that only
produce structured text (a classification, a draft, a recommendation with reasons). The model never
chooses tools, so text inside runbooks or case notes cannot change what the agent touches; that is
what tests/test_injection.py checks. Per-task token budget and LLM-call cap are enforced here.

NeMo Agent Toolkit (nvidia-nat 1.9.0) installs on Python 3.13; its react_agent workflow needs a
framework plugin (langchain) and hands tool choice to the model, which is the opposite of the
governance rule above, so the agents are built on the MCP client directly and registered as NAT
functions in kap.agents.nat_workflow for `nat` users. See docs/NAT.md.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from kap import audit, llm
from kap.config import AGENTS_DIR
from kap.mcp_client import MCPToolClient


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class AgentConfig:
    name: str
    owner: str
    model: str
    tools: list[str]
    tables: list[str]
    quality_threshold: float
    token_budget_per_task: int
    max_llm_calls_per_task: int
    prompt_guidance: str
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, name: str, model_override: str | None = None) -> "AgentConfig":
        raw = yaml.safe_load((AGENTS_DIR / f"{name}.yaml").read_text())
        known = {"name", "owner", "model", "data_permissions", "quality_threshold", "token_budget_per_task",
                 "max_llm_calls_per_task", "prompt_guidance"}
        return cls(name=raw["name"], owner=raw["owner"], model=model_override or os.environ.get("KAP_MODEL") or raw["model"],
                   tools=list(raw["data_permissions"]["tools"]), tables=list(raw["data_permissions"]["tables"]),
                   quality_threshold=float(raw["quality_threshold"]), token_budget_per_task=int(raw["token_budget_per_task"]),
                   max_llm_calls_per_task=int(raw["max_llm_calls_per_task"]), prompt_guidance=raw["prompt_guidance"].strip(),
                   extra={k: v for k, v in raw.items() if k not in known})


@dataclass
class TaskTrace:
    agent: str
    task_id: str
    model: str
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    budget_exceeded: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# A stub model for offline tests: KAP_LLM_STUB=1 makes every model call return canned JSON chosen by
# the caller (see kap.agents.base.StubLLM). Tests set it; nothing else does.
class StubLLM:
    def __init__(self, responder: Callable[[str, str], str]) -> None:
        self.responder = responder

    def complete(self, model_key: str, system: str, user: str, **kw) -> llm.LLMResult:
        return llm.LLMResult(text=self.responder(system, user), model_key=model_key, model_id="stub", input_tokens=len(user) // 4,
                             output_tokens=50, latency_s=0.0, cached=True)


_stub: StubLLM | None = None


def set_stub(stub: StubLLM | None) -> None:
    global _stub
    _stub = stub


class AgentRuntime:
    """One task = one MCP session (so the audit log carries agent + task id) + budgeted model calls."""

    def __init__(self, cfg: AgentConfig, caller: str = "agent-runtime", task_id: str | None = None) -> None:
        self.cfg = cfg
        self.trace = TaskTrace(agent=cfg.name, task_id=task_id or uuid.uuid4().hex[:12], model=cfg.model)
        self.client = MCPToolClient(cfg.name, cfg.tools, caller=caller, task_id=self.trace.task_id)
        self._t0 = 0.0

    def __enter__(self) -> "AgentRuntime":
        self._t0 = time.perf_counter()
        self.client.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self.trace.latency_s = time.perf_counter() - self._t0
        self.client.__exit__(*exc)

    def tool(self, name: str, **args: Any) -> dict[str, Any]:
        out = self.client.call(name, **args)
        self.trace.tool_calls.append((name, args))
        return out

    def llm(self, system: str, user: str, *, max_tokens: int = 1200) -> str:
        if self.trace.llm_calls >= self.cfg.max_llm_calls_per_task:
            self.trace.budget_exceeded = True
            raise BudgetExceeded(f"{self.cfg.name}: max_llm_calls_per_task={self.cfg.max_llm_calls_per_task} reached")
        if self.trace.total_tokens >= self.cfg.token_budget_per_task:
            self.trace.budget_exceeded = True
            raise BudgetExceeded(f"{self.cfg.name}: token budget {self.cfg.token_budget_per_task} exhausted")
        guidance = f"OWNER GUIDANCE ({self.cfg.owner}): {self.cfg.prompt_guidance}\n\n{system}"
        t0 = time.perf_counter()
        res = (_stub.complete if _stub else llm.complete)(self.cfg.model, guidance, user, max_tokens=max_tokens, thinking=False)
        self.trace.llm_calls += 1
        self.trace.input_tokens += res.input_tokens
        self.trace.output_tokens += res.output_tokens
        self.trace.cost_usd += res.cost_usd
        audit.record(caller="agent-runtime", agent=self.cfg.name, tool="llm.complete", args={"system": guidance, "user": user},
                     rows=0, latency_s=time.perf_counter() - t0, tokens_in=res.input_tokens, tokens_out=res.output_tokens,
                     model=res.model_id, cost_usd=res.cost_usd, task_id=self.trace.task_id)
        if self.trace.total_tokens > self.cfg.token_budget_per_task:
            self.trace.budget_exceeded = True
        return res.text


def parse_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (fences, prose, or reasoning around it)."""
    t = llm.strip_fences(text)
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model reply")
    return json.loads(m.group(0))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=str))
