# NVIDIA Auto Ontology: bring-up notes

Status on 2026-10-17: **live**, glossary pushed into its semantic layer the same evening (below). Pinned commit `5c72bf86` (2026-10-15), see `docs/VERSIONS.md`.

## Steps that worked
1. `git clone https://github.com/NVIDIA/auto-ontology vendor/auto-ontology && git -C vendor/auto-ontology checkout 5c72bf860d95909c61a0c81fb41e5a17bea89d99`
2. `vendor/auto-ontology/.env` from its `.env.example` with: `POSTGRES_PORT=5433` (host mapping;
   5432 is Project 1), `CONNECTION_STRINGS=postgresql://kap_ro:<pw>@host.docker.internal:5434/sois`
   (the pilot's read-only role on its full-data Postgres), the NIM key in `DEFAULT_MODELS_API_KEY`,
   `EMBED_API_KEY`, `RERANK_API_KEY`, and every chat model set to
   `nvidia/nemotron-3-super-120b-a12b` because the default `nemotron-3-nano-30b-a3b` is end of life
   on the API. `AUTH_SECRET`, `APP_URL`, admin email/password as the README requires.
3. `docker compose build` (about 12 minutes on this machine, mostly dependency downloads) then
   `docker compose up -d`. Containers: `postgres` (pgvector pg17, 5433), `pgadmin` (5050),
   `auto-ontology` (backend, 3001), `auto-ontology-ingestion-service` (3002),
   `auto-ontology-frontend` (3000); the two migrate jobs exit 0. The MCP server (3003) is a
   separate package (`mcp/`) run with `uvx`, not part of the compose file at this commit.
4. Ingestion ran at startup from `CONNECTION_STRINGS`: "26 table(s), 221 column(s), 247 embedding
   row(s) in 7.9s" (ingestion-service log). Semantic compilation is **off by default** ("compilation
   disabled in settings"); the switch is a row the UI writes:
   `docker exec postgres psql -U postgres -d auto_ontology -c "insert into frontend.configurations(key,value,updated_at) values ('semantic_compilation_enabled','true',now()) on conflict (key) do update set value='true'"`
   then `curl -X POST localhost:3001/api/semantic-compilation/trigger`. Compilation took about
   15 minutes (terms and descriptions per table, FK detection, semantic FK edges) and finished
   `last_success_at 2026-10-17T09:07:58Z` with 24 terms.
5. Questions: `POST /api/chat/completions` on :3001 with `{"question": ...}`, SSE events
   `step`, `sql`, `result`. Chat returns 409 until the semantic layer is compiled. `kap.auto_ontology`
   wraps this; `reports/auto_ontology_smoke.md` has three questions with the SQL and provenance.

## Rough edges met
- The README's default model ids are already retired on the hosted catalog; nothing warns at
  startup, the ingestion embed probe logs a 400 and continues.
- `/api/chat/completions` without a `conversation_id` runs statelessly, which is right for an
  evaluation but means nothing shows in the UI's history.
- The backend port is unauthenticated inside the compose network and on localhost; the Next.js
  frontend is the gateway. Fine for a laptop pilot, not for anything shared.
- The ingestion service re-ingests every 24 h by default (`INGEST_INTERVAL_HOURS`).

## Second pass: the glossary in the semantic layer (2026-10-17, evening)

The first three questions through the API scored 1 of 3 at 92 to 218 s each
(`reports/auto_ontology_smoke.md`, layer `v0`). The two misses had the same cause: on "dispatches
per product family" the pipeline retrieved Product and Dispatch columns, never the Case and
Installed Asset tables that connect them, and its "Constructing SQL" step wrote `LEFT JOIN ... ON
1 = 0` and reported zeros; "cases opened last month" used `current_date` on a warehouse that ends
2026-06-30. Its own export (`POST /api/model/export`) showed why retrieval had so little to go on:
every one of the 26 Terms had an empty `description`; only the column attributes carried text.
The semantic foreign keys were all there (dispatch.case_id -> case, case.asset_id ->
installed_asset, installed_asset.product_id -> product), so the join path existed in the graph
and was never put in front of the model.

What was tried, exactly (`kap.eval.ao_enrich`, the management skill's documented write path):
1. `PATCH /api/terms/{term_id}` with `description` for 17 Terms, built from
   `questions/glossary.yaml`: the term's definition, the related definitions (Repeat Dispatch
   under Dispatch, Service Failure and Deflectable Case under Case, Warranty Status under
   Installed Asset, Reference date under the time-bearing terms) and the glossary relationships
   that name the term, join columns included. The backend refreshes the term embedding on a
   description change (`server/terms/router.py`); no recompilation and no destructive
   `semantic-compilation/reset`.
2. `POST /api/sql-attributes/validate` then `POST /api/sql-attributes` for eight derived
   definitions as full SELECTs (parsed `opened_at`, repeat dispatch, service failure, deflectable
   case, risky pod, warranty status, parts lead time, the prefix-stripped serial join). These
   are the glossary's own SQL hints; no join-path query that answers an evaluation question was
   added (`program/DECISIONS.md` item 14).
3. `POST /api/question-entity-coverage` (the REST form of the MCP `check_answerable` step the
   query skill prescribes) on the rephrased questions, then the rephrased questions themselves,
   which name the layer's terms, the join path and the period.
4. The 13 question rows (4 originals with a cached "before", 3 rephrasings, 6 more from the
   evaluation set) through `POST /api/chat/completions`, scored by execution match.

Result, per row, `reports/auto_ontology_smoke.md` and `reports/auto_ontology_rerun.csv`.

| Question | before (v0) | after (glossary) | after, rephrased |
|---|---|---|---|
| E01 severity-1 count | right, 92 s | right, 111 s | |
| M02 dispatches per product family | wrong: "no join path", zeros, 218 s | wrong: joins dispatch_part to order_line on part_id = product_id, 228 s | right, 286 s |
| H03 repeat-dispatch rate by family | wrong: same "no join path", NULLs, 126 s | wrong: applies visit_number > 1 but drops the family join (one NULL row), 387 s | right, 272 s |
| H01 cases opened last month | wrong: `current_date`, 123 s | wrong: now parses both timestamp formats, still `current_date`, 126 s | right (June 2026 named), 151 s |
| E02, M01, M05, H07 | not run | right: 74, 216, 109, 154 s | |
| H04 deflectable cases last quarter | not run | wrong: the category and severity rule and the parse are the glossary's, but `current_date` again and no family match on the runbook, 521 s | |
| H06 risky pods | not run | wrong: ignores the Risky Pod SQL attribute, counts pods of top-100 heuristic drives, 133 s | |

Totals: original wording 1/4 before and 1/4 after on the questions that have a before, 5/10
after over all ten; rephrased 3/3; latency after 74 to 521 s, median 144 s (before: 92 to 218 s,
median 124 s on four questions, so no latency claim either way).

What changed: the SQL after the enrichment carries the glossary's content (the two-format
timestamp parse, the deflectable-case rule, visit_number > 1), which it did not before, so the
Term descriptions and SQL attributes are being retrieved. Entity coverage on the rephrased
questions lists the new `Dispatch.Repeat Dispatch` and `Case.Opened At (parsed)` attributes as
candidates.

What did not change: which tables the model gets to see. Candidate retrieval is by embedding
distance to column attributes; a question that names only "dispatches" and "product family"
retrieves Product and Dispatch columns and the bridge tables stay out of the prompt, so the
model either declares no path (before) or invents one (after). A reference date written into
the Case and Dispatch descriptions was not applied; "last month" and "last quarter" resolve to
`current_date` every time. Spelling the join path and the period out in the question is what
fixed each miss, which is what the query skill prescribes (discover terms, check coverage, then
ask), and it is also what an operator will not do.

Not tried, and why: `POST /api/semantic-compilation/reset` (documented as destructive, would
regenerate the same empty descriptions), custom analyses (reusable full queries that would hand
the pipeline the gold SQL), and a second model (the pipeline runs one configured model).


Calls went to the backend on localhost without a token (decision 5); on a shared install they
go through the Next.js gateway with an API token minted in the UI.

## What this project does with it
Auto Ontology is the semantic catalog over the warehouse and an independent text-to-SQL arm in the
evaluation. The three agents use the pilot's own MCP tools (`kap.mcp_server`) and glossary rather
than Auto Ontology's MCP server, because the agents need governed tools (read-only SQL, scoped
permissions, audit) that the catalog does not provide.
