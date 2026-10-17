# knowledge-agents-pilot. Everything runs through uv; nothing here needs a GPU.
UV ?= $(HOME)/.local/bin/uv
COMPOSE = docker compose -p kap
AO_DIR = vendor/auto-ontology

.PHONY: up down load index search-eval eval agent-eval cost program-charts test ao-up ao-down ao-smoke fleet-report secrets-check

up:            ## Elasticsearch (9201) and the full-data source Postgres (5434)
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

load:          ## load Project 1's CSVs, parquet and fleet-risk reports into the source Postgres
	$(UV) run python -m kap.load_source --telemetry-days 7

index:         ## build the hybrid search index (runbooks + 500 case notes, NeMo Retriever embeddings)
	$(UV) run python -m kap.search index --cases 500

search-eval:
	$(UV) run python -m kap.eval.search_eval

eval:          ## 30 questions x 3 models x 2 arms, cached
	$(UV) run python -m kap.eval.text2sql_eval --models nemotron llama claude --arms control ontology

eval-ao:       ## the same 30 questions through NVIDIA Auto Ontology's API
	$(UV) run python -m kap.eval.text2sql_eval --arms auto_ontology

agent-eval:
	$(UV) run python -m kap.eval.agent_eval --models nemotron llama claude

fleet-report:  ## draft today's fleet report (never publishes)
	$(UV) run python -m kap.agents.fleet_health_reporter

cost:          ## cost dashboard from the audit log
	$(UV) run python -m kap.eval.cost_dashboard

test:
	$(UV) run pytest -q

ao-up:         ## NVIDIA Auto Ontology stack (needs vendor/auto-ontology/.env, see docs/AUTO_ONTOLOGY.md)
	cd $(AO_DIR) && docker compose up -d --build

ao-down:
	cd $(AO_DIR) && docker compose down

ao-smoke:
	$(UV) run python -m kap.eval.ao_smoke

# pattern assembled at run time so this file does not match itself
SECRET_PAT = $(shell printf 'nvapi%s|sk%s|AKIA[0-9A-Z]{16}|ghp%s|@gm%s|/Us%s' - -ant _ ail ers/)
secrets-check: ## must print nothing
	git ls-files | xargs grep -nEi "$(SECRET_PAT)" || true
