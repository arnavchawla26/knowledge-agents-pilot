# Weekly status: week 42, 2026 (written 2026-10-17, final update the same evening at tag v0.1)

**Overall: green on scope, yellow on model availability, closed at v0.1.** Everything in the
charters is built and measured; the numbers are in `reports/` and summarised in `README.md`, and
every design item is marked done or cut in the README's Scope table.

## Shipped
- Warehouse copy loaded from Project 1 (26 tables, 2.5M telemetry rows) in 18 s; read-only role.
- NVIDIA Auto Ontology (pinned 2026-10-15) up on Docker Compose, 26 tables / 221 columns ingested,
  semantic layer compiled (26 terms). Two passes through its API: as compiled, 1 of 3 evaluation
  questions correct at 92 to 218 s each; then with the pilot's glossary pushed into its term
  definitions and eight SQL attributes through its management API, the same three questions still fail in the
  same words, all three pass once rephrased in the layer's own nouns with the join path and
  the period spelled out, and ten questions on original wording score 5/10 at 74 to 521 s each
  (`reports/auto_ontology_smoke.md`, `docs/AUTO_ONTOLOGY.md`).
- Elasticsearch hybrid search over 22 runbooks and 500 case notes with NeMo Retriever
  embeddings; 15-query relevance check (`reports/search_eval.csv`).
- MCP server with five audited, permission-scoped, read-only tools; three agents as fixed
  workflows, registered as NeMo Agent Toolkit functions; five prompt-injection tests through
  the real server; 45 tests green.
- 30-question two-arm text-to-SQL evaluation across Nemotron, Llama and Claude (glossary arm
  moved the hard ten from 2-3/10 to 4-9/10); agent evaluation on 10 scenarios per agent (triage
  10/10, 8/10, 10/10; dispatch 10/10 x3; fleet reporter 0/10 first run, 10/10 after the
  truncation fix); cost dashboard from the audit log.
- Program folder: three charters, decision log (18 dated items), this note, runbook, three memos.

## Cut, with the reason (full list in `README.md`, Scope)
- NVIDIA ontology-sql-eval's benchmark: needs NeMo Gym, a second Auto Ontology install and a
  code-registered dataset; its scoring rule is reimplemented and the question set exported.
- NeMo Agent Toolkit's agent runtime: hands tool choice to the model; agents are NAT functions.
- Auto Ontology's MCP server as a tool source: read-only catalog tools without the audit and
  permission layer the agents need; the pilot's MCP server carries those.
- Project 2 graph scoping and risky communities: Project 2's Neo4j was not up; YAML slices and
  Project 1's fleet-risk tables instead.
- Llama via Ollama: hosted Llama on NIM covers the open-model arm; no GPU here.

## Risks and issues
- Hosted model churn: three model ids in the plan were retired before the build started
  (`program/DECISIONS.md` item 3). Any number in this repo is tied to the ids in `docs/VERSIONS.md`.
- The NIM free tier is rate limited (about 40 req/min) and not for production; evaluations are
  cached so reruns are free, but a first run of the full matrix takes about an hour, and one
  Auto Ontology question takes 1.5 to 4 minutes on it.
- Auto Ontology's backend is unauthenticated on localhost; acceptable for a laptop pilot only.
- The dispatch agent cannot see faults the telemetry never recorded (about 30% of background
  `drive_failure` cases in the generated data are true faults with clean SMART counters). Its
  `hold` on those is a policy choice, not a bug, and the eval shows the cost.
- 10 scenarios per agent and 30 questions are smoke tests; the intervals are wide.

## Next steps if the pilot were real
1. Host the warehouse and a paid or self-hosted NIM endpoint, then switch the fleet report cron
   on (`KAP_SCHEDULED=true`) with the truncation and grounding gates as hard stops.
2. Run case triage on Nemotron in shadow mode for two weeks with a human sending every draft;
   measure the human edit rate before any auto-send discussion.
3. Log the dispatcher's override on every `hold` so the hold-vs-go trade is measured on real
   tickets, then revisit the conservative-on-disagreement rule with the data.
4. Grow the text-to-SQL set past 30 and have someone other than the glossary's author write the
   questions; mint an Auto Ontology API token and move the scripts to the authenticated gateway.
5. Wire Auto Ontology's MCP server as a second, read-only tool source once its tools can be
   wrapped by the pilot's permission and audit layer.
