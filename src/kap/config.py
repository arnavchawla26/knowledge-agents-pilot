"""Settings for knowledge-agents-pilot. Everything comes from .env (gitignored) or the
environment; nothing here prints a secret."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", override=False)


def env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise KeyError(f"{key} is not set; copy .env.example to .env")
    return val


def sois_dir() -> Path:
    return Path(env("SOIS_DIR", str(REPO_ROOT.parent / "services-ops-intelligence"))).expanduser()


def pg_dsn(readonly: bool = True) -> str:
    """DSN for kap's own full-data Postgres (docker-compose.yml service sourcedb)."""
    host = env("KAP_PG_HOST", "localhost")
    port = env("KAP_PG_PORT", "5434")
    db = env("KAP_PG_DB", "sois")
    if readonly:
        user = env("KAP_PG_RO_USER", "kap_ro")
        pw = env("KAP_PG_RO_PASSWORD", "kap_ro_local_dev_only")
    else:
        user = env("KAP_PG_USER", "sois")
        pw = env("KAP_PG_PASSWORD", "kap_local_dev_only")
    return f"host={host} port={port} user={user} password={pw} dbname={db}"


def es_url() -> str:
    return env("KAP_ES_URL", "http://localhost:9201")


CACHE_DIR = REPO_ROOT / "cache"
AUDIT_DIR = REPO_ROOT / "audit"
REPORTS_DIR = REPO_ROOT / "reports"
QUESTIONS_DIR = REPO_ROOT / "questions"
AGENTS_DIR = REPO_ROOT / "agents"
