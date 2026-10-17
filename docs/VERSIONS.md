# Pinned versions

| Component | Version / revision | Where |
|---|---|---|
| Python | 3.13.0 (Homebrew), `uv` 0.12.21 | `pyproject.toml` requires `>=3.13,<3.14` |
| NVIDIA Auto Ontology | commit `5c72bf860d95909c61a0c81fb41e5a17bea89d99` (2026-10-15, "Merge pull request #365 from NVIDIA/feature/add-owners") | `vendor/auto-ontology` (gitignored clone; `make ao-up` builds its compose) |
| NVIDIA ontology-sql-eval | commit `d78656ad2f66164313c3a3f50990ceb8e3fcda74` (2026-10-14, "Merge pull request #44 from NVIDIA/gym/count-auto-ontology-tokens"); it pins auto-ontology `2deaca7814f5530d8be9f1847681d95a56b8f420` | `vendor/ontology-sql-eval` (gitignored clone) |
| NVIDIA NeMo Agent Toolkit | `nvidia-nat[mcp]==1.9.0` | installs on Python 3.13; see `docs/NAT.md` |
| MCP Python SDK | `mcp==2.3.0` (`MCPServer`, formerly FastMCP) | `pyproject.toml` |
| Anthropic SDK | `anthropic==1.3.0` | `pyproject.toml` |
| Elasticsearch | server `8.17.4` (Docker), client `elasticsearch==8.17.2` | `docker-compose.yml` |
| Postgres (kap source copy) | `postgres:16` on host port 5434 | `docker-compose.yml` |
| Postgres (Auto Ontology catalog) | `pgvector/pgvector:pg17` on host port 5433 | `vendor/auto-ontology/docker-compose.yml` with `POSTGRES_PORT=5433` in its `.env` |
| Project 1 input | `services-ops-intelligence` tag `v0.1` (read only) | `SOIS_DIR` in `.env` |

Models (all hosted; no GPU in this project):

| Key | Model id | Endpoint | Note |
|---|---|---|---|
| nemotron | `nvidia/nemotron-3-super-120b-a12b` | integrate.api.nvidia.com (NIM, free developer tier) | Auto Ontology's default `nvidia/nemotron-3-nano-30b-a3b` reached end of life on 2026-09-01 and the API refuses it; this is the replacement used everywhere, including inside Auto Ontology |
| llama | `meta/llama-3.2-90b-vision-instruct` | NIM | the only Meta Llama chat models still served on the free tier on 2026-10-17 were the 3.2 vision models (3.1 and 3.3 text models and Llama 4 Maverick returned "end of life"); used text-only |
| claude | `claude-opus-5-5` | api.anthropic.com | adaptive thinking, `effort: medium`, server-side refusal fallbacks on |
| embeddings | `nvidia/nemotron-3-embed-1b` (2048 dims) | NIM | NeMo Retriever family; `nvidia/nv-embedqa-e5-v5` returned end of life (2026-08-25) |
