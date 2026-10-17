# knowledge-agents-pilot

Project 3 of 3: three governed Knowledge Agents doing Services Operations work on top of NVIDIA
Auto Ontology, Elasticsearch and MCP, with the evaluations, cost tracking and program artifacts
a technical program manager needs to decide whether to scale them.

## Why this shape

On October 6, 2026 Dell announced the next release of the Dell AI Data Platform with an
Enterprise Knowledge Graph and **Knowledge Agents**: agents built on a curated slice of the graph,
with owner-set prompt guidance, data access permissions, quality guardrails and token cost
thresholds, model agnostic across open and closed models. The announcement puts the operating model in one line: agents become the operator, and humans are brought
back in to review or approve "when they need them". This repository is a small, measured
version of that idea, built on Project 1's warehouse (`services-ops-intelligence`) and its risk
model:

| Dell AI Data Platform piece | Here |
|---|---|
| Unified Semantic Layer, extendable with NVIDIA Auto Ontology | NVIDIA Auto Ontology (pinned 2026-10-15) ingesting the warehouse: 26 tables, 221 columns, a compiled semantic layer of 26 terms, NL-to-SQL with provenance through its API; plus a 20-term glossary (`questions/glossary.yaml`) that is the agents' owner-set guidance |
| Data Search Engine (hybrid keyword + vector) | Elasticsearch 8 with BM25 + NeMo Retriever embeddings (`nvidia/nemotron-3-embed-1b` via NIM), reciprocal rank fusion, over 22 runbooks and 500 case notes |
| Context handed to models through MCP | `kap.mcp_server` (MCP Python SDK 2.x): `sql_query` (read-only, allow-listed, row-capped), `search_runbooks`, `asset_history`, `parts_on_hand`, `fleet_risk`; every call audited |
| Knowledge Agents with permissions, guardrails, cost thresholds | three agents, each a YAML config: model, tools it may call, tables it may see, quality threshold, token budget, model-call cap; one adapter across Nemotron and Llama (NIM) and Claude (Anthropic) |
| Humans review or approve | the triage agent escalates below its threshold; dispatch readiness is advisory and conservative on disagreement; the fleet reporter drafts and publishes nothing without a named approver |
| Evaluation and governance | 30-question text-to-SQL set with ground truth, two arms, BIRD execution match; 10 scenarios per agent against Project 1's truth files; prompt-injection tests; audit log; cost dashboard |

## What is real and what is generated

- Real: the drive telemetry under everything (Backblaze 2026 Q2 via Project 1), the risk scores
  (Project 1's LightGBM, 30-day), NVIDIA Auto Ontology, the models, the latencies and token counts.
- Generated (Project 1, seeded, with documented mess and ground truth): accounts, sites, assets,
  cases, dispatches, parts, inventory, technicians, runbooks. Case text is templated. The agent
  scenarios' expected outcomes come from Project 1's `truth/` files, which is what makes the agent
  numbers checkable at all. Details: `docs/DATA.md`.
- Not real: dollar costs on NIM. The free developer tier bills nothing, so NIM rows say $0 and
  report tokens; Claude rows use Anthropic list price (`questions/pricing.yaml`).

## Measured results (2026-10-17)

Every number below is printed by code in this repository and lives in `reports/`. Model ids and
pins are in `docs/VERSIONS.md`; three of the planned model ids were end-of-life on the hosted
catalog before the build started and were replaced (`program/DECISIONS.md`, item 3).

### Text-to-SQL: schema-only control vs ontology-grounded (`reports/eval_results.csv`)

30 questions (10 easy, 10 medium, 10 hard where a business definition decides the answer), one
repair turn per arm, scored by execution match (`set(gold) == set(pred)`, the BIRD rule NVIDIA's
ontology-sql-eval uses). The ontology arm is the same prompt plus the glossary, so the delta is
the semantic layer's.

| Model | Arm | All 30 | Easy | Medium | Hard 10 | SQL errors | Mean model latency | Tokens in / out | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| nemotron (nvidia/nemotron-3-super-120b-a12b, reasoning on) | schema only | 66.7% | 80% | 90% | 30% | 0 | 13.8 s | 30,510 / 12,476 | $0 |
| nemotron | schema + glossary | 80.0% | 90% | 90% | 60% | 0 | 13.3 s | 77,113 / 15,542 | $0 |
| llama (meta/llama-3.2-90b-vision-instruct) | schema only | 56.7% | 90% | 60% | 20% | 2 | 33.5 s | 32,705 / 1,800 | $0 |
| llama | schema + glossary | 73.3% | 100% | 80% | 40% | 1 | 17.0 s | 85,380 / 2,387 | $0 |
| claude (claude-opus-5-5, effort medium) | schema only | 66.7% | 90% | 90% | 20% | 0 | 2.8 s | 45,643 / 5,556 | $0.29 |
| claude | schema + glossary | 93.3% | 100% | 90% | 90% | 0 | 2.7 s | 117,553 / 5,516 | $0.58 |

**Headline: on the hard ten, the glossary moved Claude from 2/10 to 9/10, Nemotron from 3/10 to
6/10 and Llama from 2/10 to 4/10.** Without the semantic layer every model is at 20 to 30% on
questions where a definition decides the answer (two timestamp formats, repeat dispatch,
deflectable case, warranty unknowns, serial prefixes, service vs telemetry failure); the schema
alone does not carry those meanings. The cost of the context is about 2.6x the input tokens.
Easy and medium questions barely move, which is what a semantic layer should do. Latency for the
NIM models includes free-tier throttling and retries (`KAP_NIM_RPM`), so it is not a model
benchmark; Claude's is a clean API latency. Caveats: 30 questions, one author's glossary written
against the same schema (a glossary tuned to the question set is the obvious confound: it was
written from Project 1's schema and mess rules before any question was run, with one correction
before the ontology arm ran, the case-insensitive serial join in `program/DECISIONS.md` item 11,
but it was written by the same person who wrote the questions), and generated data.

![text-to-SQL summary](reports/eval_summary.png)

NVIDIA Auto Ontology's own pipeline (Nemotron, its default flow) was run through its API on
three questions only, because each took 92 to 218 s and the free NIM tier was shared with the
matrix above (`reports/auto_ontology_smoke.md`, `reports/eval_results_ao.csv`). It answered the
single-table count correctly (E01: 1,046 severity-1 cases, SQL and provenance returned) and
missed the two others: on the dispatch-per-product-family question it declared that no join path
existed and returned zeros, and on "cases opened last month" it did not handle the two timestamp
formats. 1 of 3 by execution match. That is a finding about an out-of-the-box deployment at this
commit on this schema, not a benchmark of the product.

### Runbook search (`reports/search_eval.csv`, 15 hand-labelled queries)

| Mode | hit@1 | hit@3 | MRR |
|---|---:|---:|---:|
| BM25 | 0.867 | 1.000 | 0.933 |
| dense (NeMo Retriever) | 1.000 | 1.000 | 1.000 |
| hybrid (RRF, k=60) | 0.933 | 1.000 | 0.967 |

On 22 short runbooks the dense ranking alone is best; equal-weight RRF lets one BM25 miss drag
the fusion. Hybrid is kept because case notes (500 indexed) have exact identifiers BM25 handles;
with this little data the comparison proves the plumbing, not a retrieval claim.

### Agents (`reports/agent_eval.csv`, 10 scenarios each, truth from Project 1)

| Agent | nemotron | llama | claude | Tokens / task (nemotron, claude) | $ / task (claude) |
|---|---:|---:|---:|---:|---:|
| case triage (decision + runbook) | 10/10 | 8/10 | 10/10 | 500, 864 | $0.0087 |
| dispatch readiness (go / hold / ship-part-first) | 10/10 | 10/10 | 10/10 | 1,055, 1,518 | $0.0122 |
| fleet health reporter (flag, grounding, not truncated) | 5/5 | not run | 5/5 | 2,146, 2,752 | $0.0333 |

What each proves and does not prove is in `program/MEMO_*.md`. Short version: the fixed
workflow plus deterministic guardrails did the governing (no hardware fault was ever auto-replied;
the approval flag was right on every run; the dispatch agent returned the conservative answer on
the one model-vs-rule disagreement); model choice moved the deflectable cases (Llama misread two
categories) and the report quality; the fleet reporter's first run failed 0/10 on both models
because every report silently hit a 900-token budget, which is now a hard check; 10 scenarios is
a smoke test, not a measurement.

### Cost (`reports/cost.csv`, from the audit log)

![cost](reports/cost.png)

Per task, mean over every run in `audit/*.jsonl` (including the fleet reporter's truncated
first run): triage 437 to 864 tokens and 1.4 to 1.5 model calls; dispatch 854 to 1,518 tokens
and 1 model call; fleet report 2,078 to 2,382 tokens, 3 tool calls, 1 model call. Claude at
list price: $0.0087, $0.0122 and $0.0259 per task respectively. NIM: $0 on the free tier (rate
limited, not for production).

### Governance checks

- `uv run pytest -q`: 43 tests, including `tests/test_injection.py` (instructions inside case
  notes and runbook text do not change the tools an agent calls, verified through the real MCP
  server) and the server-side permission test (an agent whose client is patched to call a tool
  outside its YAML permissions is refused by the server and the refusal is logged).
- The SQL tool and the eval both run as a Postgres role with `default_transaction_read_only`
  and a 30 s statement timeout, behind an allow-list that rejects anything but one SELECT/WITH.

## What was not achievable, and why

- **NVIDIA ontology-sql-eval's benchmark was not run.** It installs, but its two-arm benchmark
  needs NeMo Gym with Ray resource servers, a second Auto Ontology install sharing the pgvector
  store and a code-registered dataset, and NVIDIA tested it with GPT 5.5 as the agent. This
  repository reimplements its scoring rule and exports the question set in its format
  (`questions/ontology_sql_eval_dataset/`). The numbers above are from this harness.
- **NeMo Agent Toolkit's agent runtime was not used.** It installs on Python 3.13; its ReAct
  workflow hands tool choice to the model, which the governance design here forbids. The agents
  are registered as NAT functions (`src/kap/agents/nat_workflow.py`, `docs/NAT.md`).
- **Auto Ontology's MCP server (port 3003) is not wired to the agents.** It is a separate
  `uvx` package at this commit; the agents use this project's MCP server because they need
  permission scoping and audit. Auto Ontology is the semantic catalog and an evaluation arm.
- **Project 2's graph was not used for scoping.** The sibling repository's Neo4j was not up when
  the agents were built; the agents are scoped by a YAML slice (tools and tables) instead.
- **Llama via Ollama** was dropped: the hosted Llama on NIM covers the model-agnostic claim and
  this machine has no NVIDIA GPU.

## Resume-defensible claims

- Built three Knowledge Agents (case triage, dispatch readiness, daily fleet-health report) on
  NVIDIA Auto Ontology, Elasticsearch hybrid search and an MCP server, each with YAML data
  permissions, a quality threshold and a token budget; model-agnostic across Nemotron and Llama
  (NIM) and Claude.
- Evaluated text-to-SQL on 30 ground-truth questions, schema-only vs ontology-grounded, across
  three models with BIRD execution-match scoring; evaluated each agent on 10 truth-backed
  scenarios; prompt-injection tests through the real MCP server.
- Ran it as a pilot program: charters, decision log, cost dashboard from the audit log, memos.

Not defensible: "ran NVIDIA's ontology-sql-eval harness", "built with the NeMo Agent Toolkit
runtime", or any production claim.

## How to run

```
cp .env.example .env            # NVIDIA_API_KEY, ANTHROPIC_API_KEY, SOIS_DIR (Project 1 checkout)
make up && make load && make index
uv run pytest -q
uv run python -m kap.agents.case_triage CS-0000066
uv run python -m kap.agents.dispatch_readiness CS-0000050
uv run python -m kap.agents.fleet_health_reporter      # draft only; --approve publishes
make eval && make agent-eval && make search-eval && make cost
```

Ports: Elasticsearch 9201, source Postgres 5434 (compose project `kap`); NVIDIA Auto Ontology
3000/3001/3002 with its Postgres on 5433 (`make ao-up`, `docs/AUTO_ONTOLOGY.md`). Python 3.13,
`uv`, everything pinned in `pyproject.toml`; no GPU. Model responses are cached under `cache/`
so every evaluation reruns for free and deterministically.

Layout: `src/kap/` (tools, MCP server and client, agents, eval), `agents/` (configs),
`questions/` (eval set, glossary, scenarios, pricing), `reports/` (every number and chart),
`program/` (charters, decisions, status, runbook, memos), `docs/`, `tests/`, `audit/` (sample).
Screenshots of the Auto Ontology catalog, terms and chat are in `reports/screenshots/`.
