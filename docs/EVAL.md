# Evaluation design

## Text-to-SQL (questions/eval.yaml, 30 questions)
- 10 easy (one table), 10 medium (joins), 10 hard (a glossary definition decides the answer:
  two timestamp formats, repeat dispatch, deflectable case, fleet health, risky pod, warranty
  unknowns, service vs telemetry failure, parts lead time, serial prefixes).
- Ground-truth SQL is executed against the warehouse by `tests/test_tools_db.py`; every query
  returns rows.
- Arms: `control` (schema from information_schema, nothing else), `ontology` (same schema plus
  `questions/glossary.yaml`), and `auto_ontology` (NVIDIA Auto Ontology's own pipeline through
  its API; one model, reported as its own row).
- Each arm gives the model one repair turn if the SQL errors (same for both arms).
- Scoring: BIRD execution match as in NVIDIA ontology-sql-eval, `set(gold) == set(pred)` after
  value normalisation (`kap.eval.scoring`). A `lenient` column tolerates extra columns; the
  headline is strict.
- Determinism: temperature 0, responses cached; a rerun reproduces the CSV.
- Output: `reports/eval_results.csv` (per question), `reports/eval_summary.csv`,
  `reports/eval_summary.png`. The control-vs-ontology delta on the hard ten is the headline.

## Search (questions/search_queries.yaml, 15 queries)
- Hand-labelled expected runbook per query, written as an engineer would type it.
- BM25, dense (NeMo Retriever) and hybrid (RRF, k = 60) reported side by side; hit@1, hit@3, MRR.

## Agents (questions/agent_scenarios.yaml, 10 scenarios each)
- Case triage: expected decision and runbook from `truth/case_truth.csv` (5 deflectable with
  a named runbook, 5 that must escalate: hardware faults and predictive alerts).
- Dispatch readiness: first visits with `necessary` from `truth/dispatch_truth.csv`
  (5 necessary hardware faults, 5 unnecessary).
- Fleet reporter: five approval thresholds x two models; pass = flag matches the data, every
  number in the report appears in the data given to the model, and the top site is named.
- Output: `reports/agent_eval.csv`, `reports/agent_eval_summary.csv`.

## Cost (reports/cost.csv, reports/cost.png)
Built from `audit/*.jsonl`: per agent and model, mean tokens, dollars, model calls, tool calls,
model latency per task. NIM free tier is $0; Claude at list price.
