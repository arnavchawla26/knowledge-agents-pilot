"""Cost dashboard from the audit log: tokens and dollars per task per model per agent.
Writes reports/cost.csv and reports/cost.png. Dollars use questions/pricing.yaml rates (NIM free
tier = 0; Claude at list price), so the Claude bars are real money and the NIM bars are tokens."""
from __future__ import annotations

import csv
from collections import defaultdict

from kap import audit
from kap.config import REPORTS_DIR


def main() -> int:
    entries = [e for e in audit.read_all() if e["tool"] == "llm.complete" and e.get("task_id") and e.get("model") != "stub"]
    tasks: dict[tuple[str, str, str], dict] = {}
    for e in entries:
        key = (e["agent"], e["model"] or "?", e["task_id"])
        t = tasks.setdefault(key, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "llm_calls": 0, "latency_ms": 0.0})
        t["tokens_in"] += e["tokens_in"]; t["tokens_out"] += e["tokens_out"]; t["cost_usd"] += e["cost_usd"]
        t["llm_calls"] += 1; t["latency_ms"] += e["latency_ms"]
    tool_calls: dict[tuple[str, str], int] = defaultdict(int)
    for e in audit.read_all():
        if e.get("task_id") and e["tool"] != "llm.complete":
            tool_calls[(e["agent"], e["task_id"])] += 1
    agg: dict[tuple[str, str], dict] = {}
    for (agent, model, task_id), t in tasks.items():
        a = agg.setdefault((agent, model), {"tasks": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "llm_calls": 0, "tool_calls": 0, "latency_ms": 0.0})
        a["tasks"] += 1
        for k in ("tokens_in", "tokens_out", "cost_usd", "llm_calls", "latency_ms"):
            a[k] += t[k]
        a["tool_calls"] += tool_calls.get((agent, task_id), 0)
    rows = []
    for (agent, model), a in sorted(agg.items()):
        n = a["tasks"]
        rows.append({"agent": agent, "model": model, "tasks": n,
                     "mean_tokens_in": round(a["tokens_in"] / n), "mean_tokens_out": round(a["tokens_out"] / n),
                     "mean_tokens": round((a["tokens_in"] + a["tokens_out"]) / n),
                     "mean_cost_usd": round(a["cost_usd"] / n, 5), "total_cost_usd": round(a["cost_usd"], 4),
                     "mean_llm_calls": round(a["llm_calls"] / n, 2), "mean_tool_calls": round(a["tool_calls"] / n, 2),
                     "mean_llm_latency_s": round(a["latency_ms"] / n / 1000, 2)})
    if not rows:
        print("no agent tasks in the audit log yet")
        return 0
    with open(REPORTS_DIR / "cost.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    agents = sorted({r["agent"] for r in rows})
    models = sorted({r["model"] for r in rows})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, metric, title in ((axes[0], "mean_tokens", "Tokens per task"), (axes[1], "mean_cost_usd", "Dollars per task (list price; NIM free tier = 0)")):
        for i, m in enumerate(models):
            vals = [next((r[metric] for r in rows if r["agent"] == a and r["model"] == m), 0) for a in agents]
            ax.bar([x + (i - (len(models) - 1) / 2) * 0.8 / len(models) for x in range(len(agents))], vals, width=0.8 / len(models), label=m.split("/")[-1])
        ax.set_xticks(range(len(agents))); ax.set_xticklabels(agents, fontsize=8); ax.set_title(title)
    axes[0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(REPORTS_DIR / "cost.png", dpi=130)
    for r in rows:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
