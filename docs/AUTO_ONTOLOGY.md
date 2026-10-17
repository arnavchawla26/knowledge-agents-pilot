# NVIDIA Auto Ontology: bring-up notes

Status on 2026-10-17: **live**. Pinned commit `5c72bf86` (2026-10-15), see `docs/VERSIONS.md`.

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

## What this project does with it
Auto Ontology is the semantic catalog over the warehouse and an independent text-to-SQL arm in the
evaluation. The three agents use the pilot's own MCP tools (`kap.mcp_server`) and glossary rather
than Auto Ontology's MCP server, because the agents need governed tools (read-only SQL, scoped
permissions, audit) that the catalog does not provide.
