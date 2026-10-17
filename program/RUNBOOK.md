# Operating runbook: knowledge-agents-pilot

## Start
1. `cp .env.example .env`, fill `NVIDIA_API_KEY` and `ANTHROPIC_API_KEY`, set `SOIS_DIR` to the
   Project 1 checkout. Never commit `.env`.
2. `make up` (Elasticsearch on 9201, source Postgres on 5434), then `make load` (about 20 s),
   then `make index` (22 runbooks + 500 case notes, about 1 min of NIM embedding calls).
3. Optional, NVIDIA Auto Ontology: `docs/AUTO_ONTOLOGY.md` steps 1-4, then `make ao-smoke`.

## Run an agent
- `uv run python -m kap.agents.case_triage CS-0000066`
- `uv run python -m kap.agents.dispatch_readiness CS-0000050`
- `uv run python -m kap.agents.fleet_health_reporter` (draft only) then, after reading it,
  `uv run python -m kap.agents.fleet_health_reporter --approve reports/fleet/drafts/<file>.md --approver "<name>"`
- Switch model per run with `KAP_MODEL=claude` or per agent in `agents/<agent>.yaml`.

## Governance checks
- `audit/<date>.jsonl`: one line per tool and model call with caller, agent, task id, args hash,
  rows, latency, tokens, cost. Review daily; `make cost` rebuilds the dashboard from it.
- Permissions live in `agents/*.yaml` (`data_permissions.tools`); the MCP server enforces them
  from `KAP_ALLOWED_TOOLS`, so a code change in an agent cannot widen them silently.
- `uv run pytest -q` runs the SQL guard, permission, injection and ground-truth tests.

## Rate limits and cost
- The NIM free tier allows about 40 requests a minute. `KAP_NIM_RPM` (default 30) throttles each
  process; run one evaluation at a time or lower it.
- Every model response is cached under `cache/`; delete a file to force a fresh call.
- Claude is real money (list price in `questions/pricing.yaml`); the dashboard shows it per task.

## Rotate a key
Replace the value in `.env` and in `vendor/auto-ontology/.env`, `make ao-down && make ao-up`.
Cached responses stay valid. Run `make secrets-check` before any push (must print nothing).

## Recover
- Postgres gone: `make up && make load`.
- Index gone: `make index`.
- Auto Ontology chat returns 409: the semantic layer is not compiled; see docs/AUTO_ONTOLOGY.md step 4.
- A model id returns "end of life": change `kap.llm.MODELS` and `docs/VERSIONS.md`; the cache key
  includes the model id so old answers are not reused.
