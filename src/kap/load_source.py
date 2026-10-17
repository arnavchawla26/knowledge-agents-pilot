"""Load Project 1's enterprise data into kap's own Postgres (port 5434).

Reads, never writes, the Project 1 checkout (SOIS_DIR): sql/schema.sql, data/enterprise/*.csv,
data/parquet/drive_model.parquet and drive_summary.parquet, and the last N days of
data/parquet/telemetry_daily. Then creates the read-only role the MCP server uses.

    uv run python -m kap.load_source --telemetry-days 7
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import duckdb
import psycopg
import pyarrow.csv as pacsv
from psycopg import sql

from kap.config import env, pg_dsn, sois_dir

ENTERPRISE_ORDER = (
    "account", "site", "contact", "product", "order", "installed_asset", "order_line",
    "part", "supplier", "part_supplier", "inventory", "technician", "runbook", "case",
    "dispatch", "dispatch_part", "data_product", "job", "lineage", "query_log",
)


# Project 1's fleet risk outputs (reports/*.csv), loaded as tables so the fleet_risk tool and the
# Fleet Health glossary term can be answered in SQL. Column types are inferred by DuckDB.
FLEET_RISK_TABLES = ("fleet_risk_sites", "fleet_risk_vaults", "fleet_risk_top100")


def _load_report_csv(cur: psycopg.Cursor, con: duckdb.DuckDBPyConnection, name: str, path: Path) -> int:
    desc = con.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{path}')").fetchall()
    type_map = {"BIGINT": "BIGINT", "INTEGER": "INTEGER", "DOUBLE": "DOUBLE PRECISION", "VARCHAR": "VARCHAR",
                "DATE": "DATE", "BOOLEAN": "BOOLEAN", "HUGEINT": "NUMERIC", "TIMESTAMP": "TIMESTAMP"}
    cols = ", ".join(f"{_q(c)} {type_map.get(t, 'VARCHAR')}" for c, t, *_ in desc)
    cur.execute(f"DROP TABLE IF EXISTS {_q(name)}")
    cur.execute(f"CREATE TABLE {_q(name)} ({cols})")
    return _copy_duck(cur, con, name, f"SELECT * FROM read_csv_auto('{path}')")


def _q(name: str) -> str:
    return f'"{name}"'


def _copy_csv(cur: psycopg.Cursor, table: str, path: Path) -> int:
    with cur.copy(f"COPY {_q(table)} FROM STDIN WITH (FORMAT csv, HEADER true)") as cp, open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            cp.write(chunk)
    cur.execute(f"SELECT count(*) FROM {_q(table)}")
    return int(cur.fetchone()[0])


def _copy_duck(cur: psycopg.Cursor, con: duckdb.DuckDBPyConnection, table: str, sql: str) -> int:
    reader = con.execute(sql).fetch_record_batch(200_000)
    with cur.copy(f"COPY {_q(table)} FROM STDIN WITH (FORMAT csv, HEADER false)") as cp:
        for batch in reader:
            buf = io.BytesIO()
            pacsv.write_csv(batch, buf, write_options=pacsv.WriteOptions(include_header=False))
            cp.write(buf.getvalue())
    cur.execute(f"SELECT count(*) FROM {_q(table)}")
    return int(cur.fetchone()[0])


def telemetry_columns(schema_sql: str) -> list[str]:
    """Column list of telemetry_daily_recent, parsed from Project 1's schema.sql."""
    block = schema_sql.split("CREATE TABLE telemetry_daily_recent (")[1].split("PRIMARY KEY")[0]
    cols = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith('"'):
            cols.append(line.split('"')[1])
    return cols


def ensure_readonly_role(cur: psycopg.Cursor) -> None:
    ro_user = env("KAP_PG_RO_USER", "kap_ro")
    ro_pw = env("KAP_PG_RO_PASSWORD", "kap_ro_local_dev_only")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ro_user,))
    if cur.fetchone() is None:
        cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(ro_user), sql.Literal(ro_pw)))
    cur.execute(f"ALTER ROLE {_q(ro_user)} SET default_transaction_read_only = on")
    cur.execute(f"ALTER ROLE {_q(ro_user)} SET statement_timeout = '30s'")
    cur.execute(f"GRANT CONNECT ON DATABASE {_q(env('KAP_PG_DB', 'sois'))} TO {_q(ro_user)}")
    cur.execute(f"GRANT USAGE ON SCHEMA public TO {_q(ro_user)}")
    cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {_q(ro_user)}")
    cur.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {_q(ro_user)}")


def load(dsn: str, sois: Path, telemetry_days: int) -> dict[str, int]:
    schema_sql = (sois / "sql" / "schema.sql").read_text()
    parquet = sois / "data" / "parquet"
    enterprise = sois / "data" / "enterprise"
    counts: dict[str, int] = {}
    con = duckdb.connect()
    with psycopg.connect(dsn) as pg, pg.cursor() as cur:
        cur.execute(schema_sql)
        pg.commit()
        counts["drive_model"] = _copy_duck(
            cur, con, "drive_model",
            f"SELECT model, vendor, capacity_bytes, drive_count, failure_count FROM read_parquet('{parquet / 'drive_model.parquet'}')")
        counts["telemetry_drive_summary"] = _copy_duck(
            cur, con, "telemetry_drive_summary",
            "SELECT serial_number, model, capacity_bytes, datacenter, cluster_id, vault_id, pod_id, first_seen, last_seen, "
            f"days_observed, failed, failure_date, max_power_on_hours FROM read_parquet('{parquet / 'drive_summary.parquet'}')")
        glob = str(parquet / "telemetry_daily" / "*" / "*.parquet")
        cols = ", ".join(_q(c) for c in telemetry_columns(schema_sql))
        counts["telemetry_daily_recent"] = _copy_duck(
            cur, con, "telemetry_daily_recent",
            f"SELECT {cols} FROM read_parquet('{glob}', hive_partitioning=true) "
            f"WHERE date > (SELECT max(date) FROM read_parquet('{glob}')) - INTERVAL {int(telemetry_days)} DAY "
            "ORDER BY date, serial_number")
        pg.commit()
        for table in ENTERPRISE_ORDER:
            counts[table] = _copy_csv(cur, table, enterprise / f"{table}.csv")
        pg.commit()
        for name in FLEET_RISK_TABLES:
            counts[name] = _load_report_csv(cur, con, name, sois / "reports" / f"{name}.csv")
        pg.commit()
        ensure_readonly_role(cur)
        pg.commit()
    con.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--telemetry-days", type=int, default=7)
    args = ap.parse_args(argv)
    t0 = time.time()
    counts = load(pg_dsn(readonly=False), sois_dir(), args.telemetry_days)
    for k, v in counts.items():
        print(f"{k:24s} {v:>10,}")
    print(f"loaded {len(counts)} tables in {time.time() - t0:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
