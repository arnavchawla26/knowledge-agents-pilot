"""Ask NVIDIA Auto Ontology evaluation questions through its API, score the SQL it returns by
execution match against questions/eval.yaml, and write reports/auto_ontology_smoke.md.

Two states of its semantic layer are compared:
- v0: the layer as compiled on 2026-10-17 (every Term description empty); answers are read from
  the cache only, because that state no longer exists on the running install;
- glossary: after `kap.eval.ao_enrich` pushed the pilot's glossary into the Term descriptions and
  added eight SQL attributes. Answers are fetched live once and cached under `cache/auto_ontology`.

Rephrased variants follow the query skill in vendor/auto-ontology/skills/nvidia-ontology-query:
discover the nouns the layer knows (`GET /api/terms`), confirm coverage
(`POST /api/question-entity-coverage`), then ask in those nouns, naming the join path and the
reference period explicitly. Latency is wall time of the SSE call, free NIM tier included.

    uv run python -m kap.eval.ao_smoke            # all questions, live for the glossary layer
    uv run python -m kap.eval.ao_smoke --ids E01 M02
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics

from kap import text2sql
from kap.auto_ontology import ask, cache_path, coverage, status
from kap.config import REPORTS_DIR
from kap.eval.scoring import lenient_match, strict_match
from kap.eval.text2sql_eval import load_questions

# (question id, variant, text). "original" is the eval.yaml wording; "rephrased" names the layer's
# own terms, the join path and the period, as the query skill recommends.
QUESTIONS: list[tuple[str, str, str]] = [
    ("E01", "original", "How many support cases have severity 1?"),
    ("M02", "original", "How many dispatches were there per product family?"),
    ("M02", "rephrased", "For each Product family, count the Dispatch records whose Case is about an Installed Asset of that Product (dispatch -> case -> installed asset -> product)."),
    ("H03", "original", "What is the repeat-dispatch rate by product family?"),
    ("H03", "rephrased", "For each Product family, what fraction of Dispatch records (dispatch -> case -> installed asset -> product) are repeat dispatches, i.e. have visit_number greater than 1?"),
    ("H01", "original", "How many cases were opened last month?"),
    ("H01", "rephrased", "How many Case records have an opened_at timestamp in June 2026 (2026-06-01 to 2026-06-30), parsing both the ISO and the MM/DD/YYYY formats?"),
    ("E02", "original", "How many cases are there in each case category?"),
    ("M01", "original", "How many cases were opened against assets in each site region?"),
    ("M05", "original", "How many installed assets are there per product family?"),
    ("H04", "original", "How many deflectable cases were opened last quarter?"),
    ("H06", "original", "How many risky pods are there?"),
    ("H07", "original", "How many installed assets are in warranty, out of warranty, and of unknown warranty status?"),
]
LAYERS = ("v0", "glossary")


def score(gold: list[tuple], sql: str | None, err: str | None) -> tuple[int, int, str, int]:
    if err or not sql:
        return 0, 0, err or "no SQL", 0
    try:
        _, pred, _ = text2sql.run_sql(sql, cap=10_000)
    except Exception as e:  # noqa: BLE001
        return 0, 0, str(e).splitlines()[0][:200], 0
    return int(strict_match(gold, pred)), int(lenient_match(gold, pred)), "", len(pred)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", help="question ids to run (default all)")
    args = ap.parse_args()
    by_id = {q["id"]: q for q in load_questions()}
    st = status()
    rows: list[dict] = []
    for qid, variant, text in QUESTIONS:
        if args.ids and qid not in args.ids:
            continue
        gold = gold_rows(by_id[qid]["sql"])
        for layer in LAYERS:
            if layer == "v0" and not cache_path(text, layer).exists():
                continue  # the empty-description layer no longer exists; only cached answers count
            r = ask(text, layer=layer)
            strict, lenient, err, n_pred = score(gold, r.get("sql"), r.get("error"))
            rows.append({"question_id": qid, "variant": variant, "layer": layer, "strict": strict, "lenient": lenient,
                         "error": err, "latency_s": r.get("latency_s"), "cached": int(bool(r.get("cached"))),
                         "gold_rows": len(gold), "pred_rows": n_pred, "question": text, "sql": r.get("sql"),
                         "answer": r.get("answer"), "provenance": r.get("provenance"), "steps": r.get("steps", [])})
            print(f"{qid:4} {variant:9} {layer:8} strict={strict} lenient={lenient} {r.get('latency_s')} s cached={r.get('cached')} {err[:80]}", flush=True)
    cov = {text: coverage(text) for qid, variant, text in QUESTIONS if variant == "rephrased" and (not args.ids or qid in args.ids)}
    write_report(st, rows, cov)
    return 0


def gold_rows(sql: str) -> list[tuple]:
    _, rows, _ = text2sql.run_sql(sql, cap=10_000)
    return rows


def write_report(st: dict, rows: list[dict], cov: dict[str, dict]) -> None:
    with (REPORTS_DIR / "auto_ontology_rerun.csv").open("w", newline="") as f:
        cols = ["question_id", "variant", "layer", "strict", "lenient", "error", "latency_s", "cached", "gold_rows", "pred_rows", "question", "sql"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    L = ["# NVIDIA Auto Ontology: before and after the glossary", "",
         f"Backend status at the time of the last run: `{json.dumps(st)}`", "",
         "Every row is one `POST /api/chat/completions` call; SQL, answer and provenance are copied verbatim from",
         "the `sql` and `result` events; `strict` is BIRD execution match against the ground-truth SQL in",
         "`questions/eval.yaml`. Layer `v0` is the semantic layer as compiled (empty Term descriptions),",
         "read from the cache; `glossary` is after `kap.eval.ao_enrich` (Term descriptions from",
         "`questions/glossary.yaml` plus eight SQL attributes). Latency is wall time on the free NIM tier.", ""]
    L += ["| id | variant | layer | strict | lenient | latency s | error |", "|---|---|---|---:|---:|---:|---|"]
    for r in rows:
        L.append(f"| {r['question_id']} | {r['variant']} | {r['layer']} | {r['strict']} | {r['lenient']} | {r['latency_s']} | {r['error'][:60]} |")
    for layer in LAYERS:
        sub = [r for r in rows if r["layer"] == layer and r["variant"] == "original"]
        if sub:
            lat = [r["latency_s"] for r in sub if r["latency_s"]]
            L.append(f"\n{layer}, original wording: {sum(r['strict'] for r in sub)}/{len(sub)} strict; latency "
                     f"{min(lat):.0f} to {max(lat):.0f} s, median {statistics.median(lat):.0f} s.")
        sub = [r for r in rows if r["layer"] == layer and r["variant"] == "rephrased"]
        if sub:
            L.append(f"{layer}, rephrased: {sum(r['strict'] for r in sub)}/{len(sub)} strict.")
    if cov:
        L += ["", "## Entity coverage of the rephrased questions (`POST /api/question-entity-coverage`)", ""]
        for text, c in cov.items():
            cands = [f"{x.get('term')}.{x.get('attribute') or x.get('name')}" for x in c.get("candidates", [])]
            L.append(f"- coverage {c.get('coverage')}: {text}  \n  candidates: {', '.join(cands) or 'none'}; uncovered: {c.get('uncovered_entities')}")
    L += ["", "## Verbatim answers", ""]
    for r in rows:
        L += [f"### {r['question_id']} ({r['variant']}, layer {r['layer']}): {r['question']}", "",
              f"- strict {r['strict']}, lenient {r['lenient']}, latency {r['latency_s']} s, cached {bool(r['cached'])}, error `{r['error'] or None}`",
              f"- steps: {', '.join(dict.fromkeys(str(s) for s in r['steps']))}", "", "SQL:", "", "```sql",
              (r["sql"] or "(none)").strip(), "```", "", "Answer:", "", (r["answer"] or "(none)").strip(), "",
              "Provenance / other answer fields:", "", "```json", json.dumps(r["provenance"], indent=1, default=str)[:3000], "```", ""]
    (REPORTS_DIR / "auto_ontology_smoke.md").write_text("\n".join(L))


if __name__ == "__main__":
    raise SystemExit(main())
