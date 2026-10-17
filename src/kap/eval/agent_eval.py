"""Evaluate the three agents on 10 scenarios each (questions/agent_scenarios.yaml) with expected
outcomes from Project 1's truth files. Writes reports/agent_eval.csv and reports/agent_eval_summary.csv.

    uv run python -m kap.eval.agent_eval --models nemotron            # one model
    uv run python -m kap.eval.agent_eval --models nemotron llama claude
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from typing import Any

import yaml

from kap import tools
from kap.agents import case_triage, dispatch_readiness, fleet_health_reporter
from kap.config import QUESTIONS_DIR, REPORTS_DIR

FIELDS = ["agent", "scenario", "model", "expected", "actual", "pass", "detail", "tool_calls", "llm_calls", "tokens", "cost_usd", "latency_s"]


def _case(case_id: str) -> dict[str, Any]:
    return tools.sql_query(f"SELECT case_id, asset_id, category, severity, description FROM \"case\" WHERE case_id = '{case_id}'")["rows"][0]


def numbers_in(text: str) -> set[str]:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)        # the draft header (task id etc.) is not a claim
    text = re.sub(r"^\s*\d+\.\s", " ", text, flags=re.MULTILINE)   # markdown list markers "1. "
    text = re.sub(r"[A-Za-z_-]+\d[\w-]*", " ", text)                # identifiers such as SITE-00432, sac2, p_fail_30d
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        out.add(m.replace(",", ""))
    return out


def grounded(report: str, data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Every number in the report must appear somewhere in the data the agent was given
    (single- and double-digit counts such as 'top 5' or '7 days' are not treated as claims)."""
    allowed = numbers_in(json.dumps(data, default=str)) | {"2026", "30"}
    allowed |= {a.rstrip("0").rstrip(".") for a in allowed if "." in a}
    stray = sorted(n for n in numbers_in(report) if n not in allowed and n.rstrip("0").rstrip(".") not in allowed
                   and not re.fullmatch(r"\d{1,2}", n))
    return not stray, stray


def run(models: list[str], agents: list[str]) -> list[dict[str, Any]]:
    sc = yaml.safe_load((QUESTIONS_DIR / "agent_scenarios.yaml").read_text())
    rows: list[dict[str, Any]] = []
    os.environ["KAP_CALLER"] = "agent-eval"
    for model in models:
        if "case_triage" in agents:
            for s in sc["case_triage"]:
                out = case_triage.run(_case(s["case_id"]), model=model, caller="agent-eval")
                ok = out["decision"] == s["expected_decision"]
                if ok and s["expected_decision"] == "respond_with_runbook":
                    ok = out["runbook_id"] == s["expected_runbook_id"]
                rows.append({"agent": "case_triage", "scenario": s["case_id"], "model": model,
                             "expected": f"{s['expected_decision']}/{s['expected_runbook_id'] or '-'}",
                             "actual": f"{out['decision']}/{out['runbook_id'] or '-'}", "pass": int(ok),
                             "detail": f"score={out['quality_score']} cls={out['classification'].get('category')}",
                             "tool_calls": ";".join(out["tool_calls"]), "llm_calls": out["llm_calls"], "tokens": out["tokens"],
                             "cost_usd": out["cost_usd"], "latency_s": out["latency_s"]})
                print(rows[-1], flush=True)
        if "dispatch_readiness" in agents:
            for s in sc["dispatch_readiness"]:
                out = dispatch_readiness.run(_case(s["case_id"]), model=model, caller="agent-eval")
                ok = out["recommendation"] in s["expected_recommendation"]
                rows.append({"agent": "dispatch_readiness", "scenario": s["case_id"], "model": model,
                             "expected": "|".join(s["expected_recommendation"]), "actual": out["recommendation"], "pass": int(ok),
                             "detail": f"llm={out['llm_recommendation']} rule={out['rule_recommendation']} truth={s['truth']['reason']}",
                             "tool_calls": ";".join(out["tool_calls"]), "llm_calls": out["llm_calls"], "tokens": out["tokens"],
                             "cost_usd": out["cost_usd"], "latency_s": out["latency_s"]})
                print(rows[-1], flush=True)
    if "fleet_health_reporter" in agents:
        for s in sc["fleet_health_reporter"]:
            os.environ["KAP_FLEET_THRESHOLD"] = str(s["threshold"])
            meta = fleet_health_reporter.run(model=s["model"], caller="agent-eval")
            del os.environ["KAP_FLEET_THRESHOLD"]
            worst = meta["worst_site_expected_failures_30d"]
            expected_flag = worst > s["threshold"]
            report = open(REPORTS_DIR.parent / meta["draft_path"]).read()
            is_grounded, stray = grounded(report, meta["data"])
            top_site = meta["data"]["top_sites"][0]["site_id"]
            mentions = top_site in report
            truncated = bool(meta.get("truncated"))
            ok = (meta["needs_human_approval"] == expected_flag or truncated) and is_grounded and mentions and not truncated
            rows.append({"agent": "fleet_health_reporter", "scenario": f"threshold={s['threshold']}", "model": s["model"],
                         "expected": f"flag={expected_flag} grounded top_site={top_site}",
                         "actual": f"flag={meta['needs_human_approval']} grounded={is_grounded} mentions_top_site={mentions} truncated={truncated}",
                         "pass": int(ok), "detail": f"stray_numbers={stray[:5]}", "tool_calls": ";".join(meta["tool_calls"]),
                         "llm_calls": meta["llm_calls"], "tokens": meta["tokens"], "cost_usd": meta["cost_usd"], "latency_s": meta["latency_s"]})
            print(rows[-1], flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="*", default=["nemotron"])
    ap.add_argument("--agents", nargs="*", default=["case_triage", "dispatch_readiness", "fleet_health_reporter"])
    args = ap.parse_args(argv)
    rows = run(args.models, args.agents)
    path = REPORTS_DIR / "agent_eval.csv"
    existing: list[dict[str, Any]] = []
    if path.exists():
        with open(path, newline="") as f:
            existing = [r for r in csv.DictReader(f)]
    keep = [r for r in existing if not any(r["agent"] == n["agent"] and r["scenario"] == n["scenario"] and r["model"] == n["model"] for n in rows)]
    rows = keep + rows
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    summary = []
    for agent in sorted({r["agent"] for r in rows}):
        for model in sorted({r["model"] for r in rows if r["agent"] == agent}):
            sub = [r for r in rows if r["agent"] == agent and r["model"] == model]
            summary.append({"agent": agent, "model": model, "n": len(sub), "pass_rate": round(sum(int(r["pass"]) for r in sub) / len(sub), 3),
                            "mean_tokens": round(sum(int(r["tokens"]) for r in sub) / len(sub)),
                            "mean_cost_usd": round(sum(float(r["cost_usd"]) for r in sub) / len(sub), 5),
                            "mean_latency_s": round(sum(float(r["latency_s"]) for r in sub) / len(sub), 2)})
    with open(REPORTS_DIR / "agent_eval_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader(); w.writerows(summary)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
