# knowledge-agents-pilot

Project 3 of 3: three governed Knowledge Agents doing Services Operations work on top of NVIDIA
Auto Ontology, Elasticsearch and MCP, with the evaluations, cost tracking and program artifacts
a technical program manager needs to decide whether to scale them.

## Why this shape

The enterprise AI data platforms announced across the industry in 2026 describe **Knowledge
Agents**: agents built on a curated slice of a knowledge graph, with owner-set prompt guidance,
data access permissions, quality guardrails and token cost thresholds, model agnostic across open
and closed models. The operating model in one line: agents become the operator, and humans are
brought back in to review or approve when they need to. This repository is a small, measured
version of that idea, built on Project 1's warehouse (`services-ops-intelligence`) and its risk
model:

| Platform piece | Here |
|---|---|
| Unified Semantic Layer, extendable with NVIDIA Auto Ontology | NVIDIA Auto Ontology (pinned 2026-10-15) ingesting the warehouse: 26 tables, 221 columns, a compiled semantic layer of 26 terms, NL-to-SQL with provenance through its API; plus a 20-term glossary (`questions/glossary.yaml`) that is the agents' owner-set guidance and was pushed into Auto Ontology's term definitions through its management API (`kap.eval.ao_enrich`) |
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

NVIDIA Auto Ontology's own pipeline (Nemotron, its default flow) was run through its API twice,
because each question takes 1.5 to 9 minutes on the free NIM tier shared with the matrix above
(`reports/auto_ontology_smoke.md`, `reports/auto_ontology_rerun.csv`, `docs/AUTO_ONTOLOGY.md`).

- As compiled: 1 of 3 (E01 right; on M02 it declared that no join path existed and returned
  zeros; on H01 it mishandled the two timestamp formats and used today's date). Its own model
  export showed why: every one of its 26 Term descriptions was empty, so retrieval never put the
  `case` and `installed_asset` tables in front of the model even though the semantic foreign
  keys between them were in its graph.
- Then the glossary was pushed into its semantic layer through its management API (17 Term
  descriptions via `PATCH /api/terms`, eight SQL attributes via `POST /api/sql-attributes`;
  `kap.eval.ao_enrich`, no recompilation). After: the same three questions in the same words
  still fail, differently (M02 now invents a join through order lines; H03 applies the
  repeat-dispatch definition but drops the family join; H01 now parses both timestamp formats
  but still anchors "last month" on `current_date`); the same three rephrased in the layer's own
  nouns with the join path and the period spelled out pass, 3 of 3; six more questions from the
  set scored 4 of 6 (E02, M01, M05, H07 right; H04 used the deflectable-case definition but
  `current_date` again and dropped the family match; H06 ignored the risky-pod attribute and
  counted pods from the top-100 heuristic flag). Net: 5 of 10 on original wording, 1 of 4 before
  on the four questions that have a before; 74 to 521 s per question, median 144 s.

Reading: the definitions landed (the SQL after carries the glossary's timestamp parse and
category rules) but the pipeline's retrieval decides which tables the model sees, and a reference
date written into a Term description is not something it applies; a question phrased the way the
catalog is phrased gets through, which is what its query skill says to do. This is a finding about
an out-of-the-box deployment at this commit on this schema with one model, not a benchmark of
the product, and the per-model ontology numbers above remain the pilot's own harness.

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

- `uv run pytest -q`: 45 tests, including `tests/test_injection.py` (instructions inside case
  notes and runbook text do not change the tools an agent calls, verified through the real MCP
  server) and the server-side permission test (an agent whose client is patched to call a tool
  outside its YAML permissions is refused by the server and the refusal is logged).
- The SQL tool and the eval both run as a Postgres role with `default_transaction_read_only`
  and a 30 s statement timeout, behind an allow-list that rejects anything but one SELECT/WITH.

## Scope: every design item, done or cut

The design is sections 11 and 12 of the design notes that planned the three projects.
Each item is either done, with the file or report that proves it, or cut, with the reason.

| Design item | Status | Where, or why not |
|---|---|---|
| NVIDIA Auto Ontology over the warehouse: semantic layer, NL-to-SQL with provenance | done | `docs/AUTO_ONTOLOGY.md`, `reports/auto_ontology_smoke.md` (two passes: as compiled, then with the glossary pushed into its term definitions through its management API), `kap.auto_ontology`, `kap.eval.ao_enrich` |
| Auto Ontology's MCP server as the agents' tool source | cut | at this commit it is a separate `uvx` package (port 3003) whose tools only read the catalog; the pilot's MCP server is where the audit log and per-agent permissions live, so the agents use that and Auto Ontology is the catalog and an evaluation arm |
| Elasticsearch hybrid search over runbooks and case notes, NeMo Retriever embeddings via NIM | done | `kap.search` (BM25 + `nvidia/nemotron-3-embed-1b`, RRF), 22 runbooks + 500 case notes, `reports/search_eval.csv` |
| Three Knowledge Agents built with NeMo Agent Toolkit | done as NAT functions, runtime cut | `src/kap/agents/nat_workflow.py`, `docs/NAT.md`. NAT 1.9.0 installs on Python 3.13, but its ReAct runtime hands tool choice to the model, which the injection tests forbid; the agents are fixed workflows registered as NAT functions |
| Agents connected through MCP | done | `kap.mcp_server` (MCP SDK 2.x, five read-only tools), `kap.mcp_client`; every call audited |
| Each agent scoped to a slice of Project 2's graph | cut | Project 2's Neo4j was not up when the agents were built; each agent is scoped by a YAML slice (tools and tables, `agents/*.yaml`) enforced by the server |
| Per-agent data permissions, quality threshold, token budget | done | `agents/*.yaml`; server-side refusal test in `tests/test_audit_and_permissions.py`; budget and truncation checks in `kap.agents.base` |
| Model agnostic: Nemotron and Llama via NIM, Claude via API | done | `kap.llm` one adapter, `KAP_MODEL=`; every evaluation ran on all three |
| Llama locally via Ollama | cut | hosted Llama on NIM already covers the open-model arm, and this machine has no NVIDIA GPU; nothing in the numbers would change except latency |
| Case triage agent: classify, pull the runbook, draft, escalate when unsure | done | `kap.agents.case_triage`, `program/MEMO_case_triage.md`, 10/10, 8/10, 10/10 |
| Dispatch readiness agent: asset history, parts on hand, risk score; go / hold / ship-part-first | done | `kap.agents.dispatch_readiness`, `program/MEMO_dispatch_readiness.md`, 10/10 on all three with the conservative-on-disagreement rule |
| Fleet health reporter: scheduled, drafts the daily report, approval flag above a threshold | done | `kap.agents.fleet_health_reporter`, `program/MEMO_fleet_health_reporter.md` (0/10 first run, 10/10 after the truncation fix), `.github/workflows/fleet_report.yml` |
| Fleet reporter pulls risky communities from Project 2 | cut | same reason as the graph scoping; it uses Project 1's fleet-risk tables (sites, vaults, top-100 drives) instead |
| Governance: read-only SQL | done | Postgres role with `default_transaction_read_only` and a 30 s statement timeout, behind `kap.sqlguard`'s allow-list (`tests/test_sqlguard.py`) |
| Governance: audit log of every tool call | done | `kap.audit`, `audit/*.jsonl` (sample committed), feeds `reports/cost.csv` |
| Governance: prompt-injection tests | done | `tests/test_injection.py`, five tests through the real MCP server |
| Governance: approval gates on anything that writes | done | the only write is publishing a fleet report, which needs `--approve --approver <name>`; a truncated draft is forced to approval |
| Evaluation: question set with ground truth | done | `questions/eval.yaml`, 30 questions, every gold query executed by a test |
| Evaluation through NVIDIA's ontology-sql-eval harness | cut | its benchmark stage needs NeMo Gym with Ray resource servers, a second Auto Ontology install sharing the pgvector store and a code-registered dataset, and NVIDIA ran it with GPT 5.5 as the agent. Its scoring rule (BIRD execution match) is reimplemented in `kap.eval.scoring` and the question set is exported in its `evaluation.json` shape (`questions/ontology_sql_eval_dataset/`) |
| Execution accuracy, latency and cost per model, with and without the ontology | done | `reports/eval_results.csv`, `reports/eval_summary.csv`, the matrix above; Auto Ontology's own pipeline as a separate row |
| Program folder: a charter per agent (problem, owner, success metric, stop criteria) | done | `program/CHARTER_*.md` |
| Program folder: decision log | done | `program/DECISIONS.md`, dated, fallbacks included |
| Program folder: weekly status | done | `program/STATUS_2026-W42.md`; the pilot ran one week, so there is one note |
| Program folder: cost dashboard, tokens and dollars per task | done | `reports/cost.csv`, `reports/cost.png`, from the audit log (`make cost`) |
| Program folder: runbook | done | `program/RUNBOOK.md` |
| Program folder: a "what this pilot proved" memo per agent, including one that did not work | done | `program/MEMO_*.md`; the fleet reporter memo keeps its 0/10 first run |
| Docker Compose for the whole stack | done as two compose projects | `docker-compose.yml` (Elasticsearch, source Postgres) and Auto Ontology's own pinned compose under `vendor/` (`make ao-up`); merging them would mean editing a vendored file at every pin |
| GitHub Actions for the schedule | done, gated | `.github/workflows/fleet_report.yml` has the daily cron behind a repository variable and runs on manual dispatch until the warehouse is hosted somewhere a runner can reach |
| Neo4j in the stack | cut | belongs to Project 2; nothing here reads it |

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
