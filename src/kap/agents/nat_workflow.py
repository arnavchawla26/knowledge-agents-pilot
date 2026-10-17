"""NeMo Agent Toolkit registration: exposes the three Knowledge Agents as NAT functions so they can
be referenced from a NAT workflow config. Import this module (or list it as a NAT plugin entry
point) in a NAT environment; it is not imported by the pilot itself. See docs/NAT.md."""
from __future__ import annotations

import json

try:
    from nat.plugin_api import Builder, FunctionBaseConfig, FunctionInfo, register_function
except ImportError as e:  # pragma: no cover - NAT is optional
    raise ImportError("install nvidia-nat[mcp]==1.9.0 to use kap.agents.nat_workflow") from e

from pydantic import Field


class KapCaseTriageConfig(FunctionBaseConfig, name="kap_case_triage"):
    """Case triage Knowledge Agent (classify, runbook, draft, escalate below threshold)."""
    model: str | None = Field(default=None, description="nemotron | llama | claude; None = agents/case_triage.yaml")


class KapDispatchReadinessConfig(FunctionBaseConfig, name="kap_dispatch_readiness"):
    """Dispatch readiness Knowledge Agent (go / hold / ship-part-first)."""
    model: str | None = Field(default=None)


class KapFleetHealthConfig(FunctionBaseConfig, name="kap_fleet_health_report"):
    """Fleet health reporter: drafts the daily report, sets the approval flag, publishes nothing."""
    model: str | None = Field(default=None)


@register_function(config_type=KapCaseTriageConfig)
async def kap_case_triage(config: KapCaseTriageConfig, _builder: Builder):
    from kap import tools
    from kap.agents import case_triage

    async def _run(case_id: str) -> str:
        row = tools.sql_query(f"SELECT case_id, asset_id, category, severity, description FROM \"case\" WHERE case_id = '{case_id}'")["rows"][0]
        return json.dumps(case_triage.run(row, model=config.model, caller="nat"), default=str)

    yield FunctionInfo.from_fn(_run, description="Triage a support case by case id; returns the decision, runbook and draft as JSON.")


@register_function(config_type=KapDispatchReadinessConfig)
async def kap_dispatch_readiness(config: KapDispatchReadinessConfig, _builder: Builder):
    from kap import tools
    from kap.agents import dispatch_readiness

    async def _run(case_id: str) -> str:
        row = tools.sql_query(f"SELECT case_id, asset_id, category, severity, description FROM \"case\" WHERE case_id = '{case_id}'")["rows"][0]
        return json.dumps(dispatch_readiness.run(row, model=config.model, caller="nat"), default=str)

    yield FunctionInfo.from_fn(_run, description="Dispatch readiness check for a case id; returns go/hold/ship-part-first with reasons.")


@register_function(config_type=KapFleetHealthConfig)
async def kap_fleet_health_report(config: KapFleetHealthConfig, _builder: Builder):
    from kap.agents import fleet_health_reporter

    async def _run(_unused: str = "") -> str:
        meta = fleet_health_reporter.run(model=config.model, caller="nat")
        return json.dumps({k: v for k, v in meta.items() if k != "data"}, default=str)

    yield FunctionInfo.from_fn(_run, description="Draft today's fleet health report; sets needs_human_approval above the threshold.")
