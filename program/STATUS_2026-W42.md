# Weekly status: week 42, 2026 (written 2026-10-17)

**Overall: green on scope, yellow on model availability.** Everything in the charter is built and
measured; the numbers are in `reports/` and summarised in `README.md`.

## Done this week
- Warehouse copy loaded from Project 1 (26 tables, 2.5M telemetry rows) in 18 s; read-only role.
- NVIDIA Auto Ontology (pinned 2026-10-15) up on Docker Compose, ingested 26 tables / 221
  columns, semantic layer compiled (24 terms); three questions answered through its API with SQL
  and provenance (`reports/auto_ontology_smoke.md`).
- Elasticsearch hybrid search over 22 runbooks and 500 case notes with NeMo Retriever
  embeddings; 15-query relevance check (`reports/search_eval.csv`).
- MCP server with five audited, permission-scoped, read-only tools; three agents; injection tests.
- 30-question two-arm text-to-SQL evaluation across Nemotron, Llama and Claude; agent evaluation
  on 10 scenarios per agent; cost dashboard from the audit log.

## Risks and issues
- Hosted model churn: three model ids in the plan were retired before the build started
  (`program/DECISIONS.md` item 3). Any number in this repo is tied to the ids in `docs/VERSIONS.md`.
- The NIM free tier is rate limited (about 40 req/min) and not for production; evaluations are
  cached so reruns are free, but a first run of the full matrix takes about an hour.
- Auto Ontology's backend is unauthenticated on localhost; acceptable for a laptop pilot only.
- The dispatch agent cannot see faults the telemetry never recorded (about 30% of background
  `drive_failure` cases in the generated data are true faults with clean SMART counters). Its
  `hold` on those is a policy choice, not a bug, and the eval shows the cost.

## Next week (if the pilot continued)
- Wire Auto Ontology's MCP server (`mcp/`, port 3003) as a second tool source for the agents.
- Add a human-feedback loop: approved drafts and overridden recommendations back into the
  glossary and the quality score.
- Replace the free NIM tier with a self-hosted NIM or a paid endpoint before any schedule runs
  unattended.
