import os

import psycopg
import pytest

from kap.config import pg_dsn


def _db_up() -> bool:
    try:
        with psycopg.connect(pg_dsn(), connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001
        return False


def _es_up() -> bool:
    try:
        import httpx

        from kap.config import es_url

        return httpx.get(f"{es_url()}/_cluster/health", timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        return False


needs_db = pytest.mark.skipif(not _db_up(), reason="kap source Postgres (port 5434) is not running")
needs_es = pytest.mark.skipif(not _es_up(), reason="Elasticsearch (port 9201) is not running")
needs_keys = pytest.mark.skipif(not os.environ.get("NVIDIA_API_KEY"), reason="NVIDIA_API_KEY not set")
