"""Two-arm text-to-SQL evaluation over questions/eval.yaml.

arms:   control   schema only in the prompt
        ontology  schema plus the glossary (kap's semantic layer)
        auto_ontology  (optional) NVIDIA Auto Ontology's own text-to-SQL through its API; its
                       model is whatever its .env configures, so it is reported as its own row
models: nemotron, llama, claude (see kap.llm.MODELS)

    uv run python -m kap.eval.text2sql_eval --models nemotron llama claude --arms control ontology
    uv run python -m kap.eval.text2sql_eval --arms auto_ontology

Writes reports/eval_results.csv (one row per question x model x arm), reports/eval_summary.csv,
reports/eval_summary.png. Responses are cached, so a rerun is free and deterministic.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import yaml

from kap import llm, text2sql
from kap.config import QUESTIONS_DIR, REPORTS_DIR
from kap.eval.scoring import lenient_match, strict_match

FIELDS = ["question_id", "difficulty", "model", "arm", "strict", "lenient", "error", "attempts", "latency_s",
          "exec_latency_s", "input_tokens", "output_tokens", "cost_usd", "cached", "gold_rows", "pred_rows", "pred_sql"]


def load_questions() -> list[dict]:
    return yaml.safe_load((QUESTIONS_DIR / "eval.yaml").read_text())["questions"]


def gold_rows(sql: str) -> list[tuple]:
    _, rows, _ = text2sql.run_sql(sql, cap=10_000)
    return rows


def run_one(q: dict, model: str, arm: str, gold: list[tuple]) -> dict:
    if arm == "auto_ontology":
        from kap.auto_ontology import ask as ao_ask

        t0 = time.perf_counter()
        ao = ao_ask(q["question"])
        latency = time.perf_counter() - t0
        pred: list[tuple] = []
        err = ao.get("error")
        if ao.get("sql") and not err:
            try:
                _, pred, _ = text2sql.run_sql(ao["sql"], cap=10_000)
            except Exception as e:  # noqa: BLE001
                err = str(e).splitlines()[0][:200]
        return {"question_id": q["id"], "difficulty": q["difficulty"], "model": "auto_ontology:" + ao.get("model", "?"),
                "arm": arm, "strict": int(strict_match(gold, pred)) if not err else 0,
                "lenient": int(lenient_match(gold, pred)) if not err else 0, "error": err or "", "attempts": 1,
                "latency_s": round(ao.get("latency_s", latency), 3), "exec_latency_s": 0.0,
                "input_tokens": ao.get("input_tokens", 0), "output_tokens": ao.get("output_tokens", 0), "cost_usd": 0.0,
                "cached": int(ao.get("cached", False)), "gold_rows": len(gold), "pred_rows": len(pred),
                "pred_sql": (ao.get("sql") or "").replace("\n", " ")}
    ans = text2sql.ask(q["question"], model, arm, cap=10_000)
    ok = ans.error is None
    return {"question_id": q["id"], "difficulty": q["difficulty"], "model": model, "arm": arm,
            "strict": int(ok and strict_match(gold, ans.rows)), "lenient": int(ok and lenient_match(gold, ans.rows)),
            "error": ans.error or "", "attempts": ans.attempts,
            "latency_s": round(ans.llm.latency_s, 3) if ans.llm else 0.0, "exec_latency_s": round(ans.exec_latency_s, 4),
            "input_tokens": ans.llm.input_tokens if ans.llm else 0, "output_tokens": ans.llm.output_tokens if ans.llm else 0,
            "cost_usd": round(ans.llm.cost_usd, 6) if ans.llm else 0.0, "cached": int(ans.llm.cached) if ans.llm else 0,
            "gold_rows": len(gold), "pred_rows": len(ans.rows), "pred_sql": ans.sql.replace("\n", " ")}


def summarise(rows: list[dict]) -> list[dict]:
    out = []
    keys = sorted({(r["model"], r["arm"]) for r in rows})
    for model, arm in keys:
        sub = [r for r in rows if r["model"] == model and r["arm"] == arm]
        by_diff = {}
        for d in ("easy", "medium", "hard"):
            s = [r for r in sub if r["difficulty"] == d]
            by_diff[d] = sum(int(r["strict"]) for r in s) / len(s) if s else None
        out.append({
            "model": model, "arm": arm, "n": len(sub),
            "strict_accuracy": round(sum(int(r["strict"]) for r in sub) / len(sub), 4),
            "lenient_accuracy": round(sum(int(r["lenient"]) for r in sub) / len(sub), 4),
            "easy": by_diff["easy"], "medium": by_diff["medium"], "hard": by_diff["hard"],
            "sql_errors": sum(1 for r in sub if r["error"]),
            "mean_latency_s": round(sum(float(r["latency_s"]) for r in sub) / len(sub), 3),
            "total_input_tokens": sum(int(r["input_tokens"]) for r in sub),
            "total_output_tokens": sum(int(r["output_tokens"]) for r in sub),
            "total_cost_usd": round(sum(float(r["cost_usd"]) for r in sub), 4),
        })
    return out


def chart(summary: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted({s["model"] for s in summary if s["arm"] in ("control", "ontology")})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, metric, title in ((axes[0], "strict_accuracy", "Execution accuracy, all 30"), (axes[1], "hard", "Execution accuracy, hard 10")):
        x = range(len(models))
        for i, arm in enumerate(("control", "ontology")):
            vals = [next((s[metric] or 0 for s in summary if s["model"] == m and s["arm"] == arm), 0) for m in models]
            ax.bar([xi + (i - 0.5) * 0.36 for xi in x], vals, width=0.36, label={"control": "schema only", "ontology": "schema + glossary"}[arm],
                   color={"control": "#9aa5b1", "ontology": "#2f6f9f"}[arm])
            for xi, v in zip(x, vals):
                ax.text(xi + (i - 0.5) * 0.36, v + 0.01, f"{v:.0%}", ha="center", fontsize=8)
        ao = [s for s in summary if s["arm"] == "auto_ontology"]
        if ao and metric in ao[0]:
            ax.axhline(ao[0][metric] or 0, color="#76b900", linestyle="--", label=f"Auto Ontology ({ao[0]['model'].split(':', 1)[-1].split('/')[-1]})")
        ax.set_xticks(list(x)); ax.set_xticklabels(models); ax.set_ylim(0, 1.08); ax.set_title(title); ax.set_ylabel("accuracy")
    axes[0].legend(loc="lower right", fontsize=8)
    fig.suptitle("Text-to-SQL: control vs ontology-grounded, by model (questions/eval.yaml)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="*", default=["nemotron", "llama", "claude"])
    ap.add_argument("--arms", nargs="*", default=["control", "ontology"])
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--out", type=Path, default=REPORTS_DIR / "eval_results.csv")
    args = ap.parse_args(argv)
    qs = [q for q in load_questions() if not args.ids or q["id"] in args.ids]
    golds = {q["id"]: gold_rows(q["sql"]) for q in qs}
    existing: list[dict] = []
    if args.out.exists():
        with open(args.out, newline="") as f:
            existing = [r for r in csv.DictReader(f)]
    done = {(r["question_id"], r["model"], r["arm"]) for r in existing}
    rows = list(existing)
    for arm in args.arms:
        for model in (["auto_ontology"] if arm == "auto_ontology" else args.models):
            for q in qs:
                key = (q["id"], model if arm != "auto_ontology" else next((r["model"] for r in rows if r["arm"] == "auto_ontology"), "auto_ontology"), arm)
                if arm != "auto_ontology" and key in done:
                    continue
                if arm == "auto_ontology" and any(r["question_id"] == q["id"] and r["arm"] == arm for r in rows):
                    continue
                r = run_one(q, model, arm, golds[q["id"]])
                rows.append(r)
                print(f"{q['id']} {model:9s} {arm:13s} strict={r['strict']} lenient={r['lenient']} err={r['error'][:60]!r}", flush=True)
                with open(args.out, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=FIELDS)
                    w.writeheader(); w.writerows(rows)
    summary = summarise(rows)
    with open(REPORTS_DIR / "eval_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader(); w.writerows(summary)
    chart(summary, REPORTS_DIR / "eval_summary.png")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
