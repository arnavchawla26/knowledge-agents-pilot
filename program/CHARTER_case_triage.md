# Pilot charter: case triage agent

**Problem.** Tier-1 support reads every new case, decides whether a runbook answers it, and drafts
the first reply by hand. In Project 1's generated enterprise 27% of cases (2,252 of 8,281, from
`truth/case_truth.csv`) are deflectable with an existing runbook, and each one that reaches a
technician instead costs a truck roll.

**What the agent does.** For a new case: pulls the asset's history, searches the runbooks (hybrid
BM25 + NeMo Retriever embeddings), classifies the case, scores its own confidence with a
deterministic rule, and either drafts a runbook-grounded reply or escalates to a human. It never
sends anything; a human sends the draft.

**Owner.** Support tier-1 lead (data owner for `case` and `runbook`). Agent config:
`agents/case_triage.yaml`.

**Data permissions.** Tools `search_runbooks`, `asset_history` only. No `sql_query`.

**Success metric.** On 10 scenarios with ground truth (`questions/agent_scenarios.yaml`):
decision matches truth (respond vs escalate) and, when responding, the runbook matches the one
the truth file names. Target for a go decision: >= 80% on every model tried, zero cases where a
hardware fault or severity 1-2 case gets an automated reply.

**Guardrails.** Quality threshold 0.60 (below it the agent escalates); 2 model calls and 6,000
tokens per task; runbook and case text are data, not instructions (`tests/test_injection.py`).

**Stop criteria.** Stop the pilot if any hardware-fault case is answered automatically, if the
pass rate is below 60% on the best model, or if the per-task cost on the chosen model exceeds the
cost of a tier-1 minute (not measured here; the dashboard gives tokens and dollars).
