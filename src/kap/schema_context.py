"""Schema text for the two text-to-SQL arms.

control   : table and column names with types, straight from information_schema. Nothing else.
ontology  : the same schema plus the glossary definitions and relationships (questions/glossary.yaml),
            which is what an ontology-grounded agent gets from a semantic layer.
"""
from __future__ import annotations

from functools import lru_cache

import psycopg
import yaml

from kap.config import QUESTIONS_DIR, pg_dsn

TABLES_FOR_AGENTS = (
    "account", "site", "product", "installed_asset", "part", "supplier", "part_supplier", "inventory",
    "technician", "runbook", "case", "dispatch", "dispatch_part", "drive_model", "telemetry_drive_summary",
    "telemetry_daily_recent", "fleet_risk_sites", "fleet_risk_vaults", "fleet_risk_top100",
)


@lru_cache(maxsize=1)
def schema_text(tables: tuple[str, ...] = TABLES_FOR_AGENTS) -> str:
    with psycopg.connect(pg_dsn()) as pg, pg.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position")
        rows = cur.fetchall()
    by_table: dict[str, list[str]] = {}
    for t, c, d in rows:
        if t in tables:
            if t == "telemetry_daily_recent" and c.startswith("smart_") and c not in (
                    "smart_5_raw", "smart_9_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"):
                continue
            by_table.setdefault(t, []).append(f"{c} {d}")
    lines = []
    for t in tables:
        if t in by_table:
            name = f'"{t}"' if t in ("case", "order") else t
            lines.append(f"TABLE {name} ({', '.join(by_table[t])})")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def glossary() -> dict:
    return yaml.safe_load((QUESTIONS_DIR / "glossary.yaml").read_text())


def glossary_text() -> str:
    g = glossary()
    lines = ["BUSINESS GLOSSARY (one definition per term; follow these exactly):"]
    for term, body in g["terms"].items():
        lines.append(f"- {term}: {body['definition'].strip()}")
    lines.append("RELATIONSHIPS:")
    lines.extend(f"- {r}" for r in g["relationships"])
    return "\n".join(lines)


def context_for(arm: str) -> str:
    if arm == "control":
        return "POSTGRES SCHEMA:\n" + schema_text()
    if arm == "ontology":
        return "POSTGRES SCHEMA:\n" + schema_text() + "\n\n" + glossary_text()
    raise ValueError(arm)
