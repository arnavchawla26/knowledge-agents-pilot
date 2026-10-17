# Decision log

Dated the day each decision was made. Fallbacks are decisions too.

## 2026-10-17

1. **Run the pilot against a full-data copy of the warehouse on port 5434, not Project 1's
   container on 5432.** Project 1's `sois-postgres` held a 6-asset test fixture when this build
   started (its live test suite had overwritten it; the orchestrator reloaded it later). The
   pilot loads Project 1's CSV/Parquet files with Project 1's own `schema.sql` into its own
   Postgres (`kap.load_source`, 18 s) and points everything, including NVIDIA Auto Ontology,
   at that copy. Consequence: nothing here depends on the state of another project's container,
   and Auto Ontology's ingest cannot touch Project 1's database. `KAP_PG_*` still lets the pilot
   target any Postgres with the schema.
2. **Load only the last 7 days of daily telemetry (2.49M rows), not 30.** The agents need
   recent SMART counters, not the quarter; the summary table has the per-drive history. Keeps the
   load under 20 s and the read-only queries under the 30 s statement timeout.
3. **Replace the end-of-life model ids.** On 2026-10-17 the NIM catalog refused Auto Ontology's
   default `nvidia/nemotron-3-nano-30b-a3b` (EOL 2026-09-01), every Meta Llama 3.x text model
   and Llama 4 Maverick (EOL), and `nvidia/nv-embedqa-e5-v5` (EOL 2026-08-25). Chosen:
   `nvidia/nemotron-3-super-120b-a12b` (also set inside Auto Ontology's `.env`),
   `meta/llama-3.2-90b-vision-instruct` used text-only (the only Meta Llama chat model left on
   the free tier), `nvidia/nemotron-3-embed-1b` for embeddings. Recorded in `docs/VERSIONS.md`.
4. **Auto Ontology is live; the pilot's own glossary is the per-model ontology arm.** Auto
   Ontology's chat runs one configured model (Nemotron) through its own multi-step pipeline, so
   it cannot give a per-model control-vs-ontology comparison. The evaluation therefore reports
   three things: schema-only control per model, schema + glossary per model (same prompt shape,
   only the context differs, so the delta is the ontology's), and Auto Ontology's own answers as
   a separate row. Agents call the pilot's MCP tools; the glossary is the owner-set guidance.
5. **Enable Auto Ontology's semantic compilation by flipping its settings flag in its database**
   (`frontend.configurations.semantic_compilation_enabled = true`) and triggering
   `/api/semantic-compilation/trigger`. The compose stack has no admin API token minted and the
   backend on :3001 is unauthenticated on localhost, which is how scripts here call it. Not
   production practice; documented in `docs/AUTO_ONTOLOGY.md`.
6. **Do not run NVIDIA ontology-sql-eval's NeMo Gym benchmark.** `uv sync` in the vendored
   checkout succeeded (it downloads CPython 3.13.15 and nemo-gym 0.7.0), but the benchmark stage
   needs Ray resource servers, a second Auto Ontology install sharing the pgvector store, a
   registered `DatasetSpec` in its code, and was tested by NVIDIA with GPT 5.5 as the agent.
   The pilot reimplements its scoring rule (BIRD execution match, `set(gold) == set(pred)`,
   `ontology_sql_eval/gym/exec_match.py`) in `kap.eval.scoring` and exports the question set in
   its `evaluation.json` shape (`questions/ontology_sql_eval_dataset/`). Numbers here are from
   the pilot's harness, not NVIDIA's.
7. **Agents are fixed workflows, not model-driven tool loops.** Tool calls are chosen by code in
   a fixed order through the MCP client; the model produces a classification, a recommendation or
   a draft. This is what makes the prompt-injection tests meaningful and keeps every task at one
   or two model calls. NeMo Agent Toolkit installs on 3.13 but its ReAct runtime hands tool
   choice to the model, so the agents are registered as NAT functions instead (`docs/NAT.md`).
8. **Nemotron reasoning off inside the agents, on for text-to-SQL.** With reasoning on, a
   500-token answer budget was consumed by reasoning and the JSON was cut off. Agents send
   `chat_template_kwargs.enable_thinking=false`; the text-to-SQL arms keep each vendor's default
   (Nemotron reasoning on, Claude adaptive thinking at medium effort, Llama 3.2 none).
9. **Dispatch readiness treats a `drive_failure` case category as a claim, not evidence.** First
   version counted the category as fault evidence and recommended `go` on a case whose drive had
   zero SMART counters, no telemetry failure and no risk score; the truth said no fault. The rule
   now needs telemetry, SMART or the risk model to corroborate; otherwise `hold` and ask for
   diagnostics. Project 1's generator makes about 70% of background `drive_failure` cases true
   faults that telemetry never recorded, so this rule will hold some real faults; that is the
   cost of not rolling trucks on uncorroborated claims, and it is visible in the eval.
10. **Case triage searches runbooks without a product-family filter** and re-ranks by category
    agreement, then family, then search order: Project 1's generator matches a case's runbook by
    category first, and a family filter dropped the right runbook (HCI Node has no `config`
    runbook; the truth names the Storage Array one).
11. **Serial joins are case-insensitive on both sides.** Telemetry serials mix cases natively
    (WD hex serials are lowercase); `upper()` on the ERP side only lost those joins. Fixed in the
    glossary, the `asset_history` tool and ground-truth H08 (913 -> 914).
12. **NIM cost is reported as zero dollars with tokens shown.** The free developer tier bills
    nothing; inventing a per-token price would be a made-up number. Claude is at Anthropic list
    price (`questions/pricing.yaml`).

## 2026-10-17, evening (closing the pilot at v0.1)

13. **Push the glossary into Auto Ontology through its management API instead of recompiling.**
    The compiled semantic layer had an empty `description` on all 26 Terms (only the column
    attributes carried LLM-written text), which is why retrieval never surfaced the `case` and
    `installed_asset` tables that join dispatches to products. `kap.eval.ao_enrich` does what
    NVIDIA's management skill documents: `PATCH /api/terms/{id}` with a description built from
    `questions/glossary.yaml` (17 terms; the backend re-embeds each one, no compile needed) and
    `POST /api/sql-attributes` after `/validate` for eight derived definitions (parsed case
    timestamps, repeat dispatch, service failure, deflectable case, risky pod, warranty status,
    parts lead time, the serial join). A `semantic-compilation/reset` would have regenerated the
    same empty descriptions and is documented as destructive. Calls went to the backend on
    localhost, as in item 5.
14. **No SQL attribute may be a join-path query that answers an evaluation question.** The eight
    attributes are the glossary's own SQL hints, the same text the per-model "schema + glossary"
    arm gets in its prompt; adding "dispatches per product family" as a reusable query would have
    handed Auto Ontology the gold SQL for M02 and the comparison would mean nothing.
15. **Before and after are compared on cached "before" answers only.** The as-compiled state no
    longer exists on the install once the terms are patched, so the "before" column is the four
    questions answered on 2026-10-17 morning (`cache/auto_ontology`, keyed without a layer tag);
    the extra questions in the second pass have an "after" number and no "before", and the report
    says so rather than inventing one. Cache keys now carry an `AO_LAYER` tag so the two states
    never collide.
16. **Rephrased questions are extra rows, not replacements.** The query skill says to discover
    the layer's nouns and check coverage before asking; the rephrased variants name the term, the
    join path and the period. They are reported next to the original wording so the reader can
    see what the phrasing bought, and the headline stays on the original wording, which is what
    an operator would type.
17. **The fleet reporter's first run is reported as 0/10.** By the grounding check in force when
    it ran it was 1/10 (one Claude report happened to contain no stray number); the audit log
    shows every one of the ten calls stopped at exactly the 900-token budget, and once truncation
    counts, which it now does, the run is 0/10. The memo states both.
18. **Tag v0.1 and stop.** Everything in the design is either shipped or cut with a reason in
    `README.md`'s Scope table. Nothing is scheduled to run unattended.
