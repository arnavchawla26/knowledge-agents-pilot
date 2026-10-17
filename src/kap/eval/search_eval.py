"""15-query relevance check for the runbook search: BM25, dense and hybrid (RRF) side by side.
Writes reports/search_eval.csv (per query) and prints hit@1 / hit@3 / MRR per mode."""
from __future__ import annotations

import csv
import json

import yaml

from kap.config import QUESTIONS_DIR, REPORTS_DIR
from kap.search import search

MODES = ("bm25", "dense", "hybrid")


def main() -> int:
    qs = yaml.safe_load((QUESTIONS_DIR / "search_queries.yaml").read_text())["queries"]
    rows = []
    for q in qs:
        row = {"query": q["query"], "expected": ";".join(q["expected"])}
        for mode in MODES:
            hits = [h["runbook_id"] for h in search(q["query"], kind="runbook", size=5, mode=mode)]
            rank = next((i + 1 for i, h in enumerate(hits) if h in q["expected"]), 0)
            row[f"{mode}_top3"] = ";".join(hits[:3])
            row[f"{mode}_rank"] = rank
        rows.append(row)
    with open(REPORTS_DIR / "search_eval.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    summary = {}
    for mode in MODES:
        ranks = [r[f"{mode}_rank"] for r in rows]
        summary[mode] = {"hit_at_1": round(sum(r == 1 for r in ranks) / len(ranks), 3),
                         "hit_at_3": round(sum(1 <= r <= 3 for r in ranks) / len(ranks), 3),
                         "mrr": round(sum(1 / r for r in ranks if r) / len(ranks), 3), "n": len(ranks)}
    (REPORTS_DIR / "search_eval_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
