"""Read-only SQL guard for the sql_query tool and the eval harness.

Defence in depth: the Postgres role is read-only with default_transaction_read_only on and a
30s statement timeout, and this module rejects anything that is not a single SELECT/WITH
statement before it reaches the database. Not a parser; a conservative allow-list.
"""
from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze|"
    r"call|do|execute|prepare|deallocate|listen|notify|lock|refresh|reindex|cluster|comment|"
    r"security|set|reset|begin|commit|rollback|savepoint|merge|import|export)\b",
    re.IGNORECASE,
)
FORBIDDEN_FUNCS = re.compile(r"\b(pg_sleep|pg_read_file|pg_ls_dir|lo_import|lo_export|dblink|pg_terminate_backend|pg_cancel_backend)\s*\(", re.IGNORECASE)


class SQLRejected(ValueError):
    pass


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def _strip_strings(sql: str) -> str:
    """Remove string literals so keywords inside quotes do not trip the allow-list."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate_readonly(sql: str) -> str:
    """Return the cleaned statement or raise SQLRejected."""
    if not isinstance(sql, str) or not sql.strip():
        raise SQLRejected("empty statement")
    cleaned = _strip_comments(sql).strip().rstrip(";").strip()
    if ";" in cleaned:
        raise SQLRejected("multiple statements are not allowed")
    head = cleaned.lstrip("(").split(None, 1)[0].lower() if cleaned else ""
    if head not in ("select", "with"):
        raise SQLRejected(f"only SELECT or WITH statements are allowed, got '{head}'")
    bare = _strip_strings(cleaned)
    if m := FORBIDDEN.search(bare):
        # 'set' appears legitimately in e.g. "offset" -- \b handles that; 'do' in "do_x" too.
        raise SQLRejected(f"forbidden keyword: {m.group(0)}")
    if m := FORBIDDEN_FUNCS.search(bare):
        raise SQLRejected(f"forbidden function: {m.group(0)}")
    return cleaned


def with_row_cap(sql: str, cap: int) -> str:
    """Wrap so the database never returns more than `cap` rows, whatever the model wrote."""
    return f"SELECT * FROM ({sql}) AS kap_capped LIMIT {int(cap)}"
