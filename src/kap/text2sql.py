"""kap's own text-to-SQL layer (the fallback when NVIDIA Auto Ontology is not the live path, and
the schema-only control arm either way): one OpenAI-compatible NIM call or one Anthropic call with
the schema in the prompt, read-only execution through sqlguard, result validation."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import psycopg

from kap import llm
from kap.config import pg_dsn
from kap.schema_context import context_for
from kap.sqlguard import SQLRejected, validate_readonly, with_row_cap

SYSTEM = (
    "You write one PostgreSQL SELECT statement that answers the user's question over the schema given. "
    "Rules: output only the SQL, no prose, no markdown fence; one statement; never modify data; "
    "quote the reserved table names \"case\" and \"order\"; prefer explicit joins; return the columns "
    "the question asks for and nothing else; round nothing unless asked."
)


@dataclass
class SQLAnswer:
    sql: str
    rows: list[tuple]
    columns: list[str]
    error: str | None
    llm: llm.LLMResult | None
    exec_latency_s: float = 0.0
    attempts: int = 1
    meta: dict[str, Any] = field(default_factory=dict)


def run_sql(sql: str, cap: int = 200, dsn: str | None = None) -> tuple[list[str], list[tuple], float]:
    cleaned = validate_readonly(sql)
    t0 = time.perf_counter()
    with psycopg.connect(dsn or pg_dsn()) as pg:
        pg.read_only = True
        with pg.cursor() as cur:
            cur.execute(with_row_cap(cleaned, cap))
            cols = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall()
    return cols, rows, time.perf_counter() - t0


def ask(question: str, model_key: str, arm: str, *, retry_on_error: bool = True, cap: int = 200) -> SQLAnswer:
    """Generate SQL, execute it, and on a database error give the model one repair turn."""
    user = f"{context_for(arm)}\n\nQUESTION: {question}\nSQL:"
    res = llm.complete(model_key, SYSTEM, user, max_tokens=1500)
    sql = llm.strip_fences(res.text)
    attempts = 1
    total = res
    try:
        cols, rows, lat = run_sql(sql, cap=cap)
        return SQLAnswer(sql=sql, rows=rows, columns=cols, error=None, llm=total, exec_latency_s=lat, attempts=attempts)
    except (SQLRejected, psycopg.Error) as e:
        err = str(e).strip().splitlines()[0][:300]
        if not retry_on_error:
            return SQLAnswer(sql=sql, rows=[], columns=[], error=err, llm=total, attempts=attempts)
    repair = f"{user}\n{sql}\n\nThat SQL failed with: {err}\nWrite a corrected single SELECT statement. SQL:"
    res2 = llm.complete(model_key, SYSTEM, repair, max_tokens=1500)
    attempts = 2
    sql2 = llm.strip_fences(res2.text)
    merged = llm.LLMResult(text=res2.text, model_key=model_key, model_id=res.model_id,
                           input_tokens=res.input_tokens + res2.input_tokens,
                           output_tokens=res.output_tokens + res2.output_tokens,
                           latency_s=res.latency_s + res2.latency_s, cached=res.cached and res2.cached,
                           cost_usd=res.cost_usd + res2.cost_usd)
    try:
        cols, rows, lat = run_sql(sql2, cap=cap)
        return SQLAnswer(sql=sql2, rows=rows, columns=cols, error=None, llm=merged, exec_latency_s=lat, attempts=attempts)
    except (SQLRejected, psycopg.Error) as e:
        return SQLAnswer(sql=sql2, rows=[], columns=[], error=str(e).strip().splitlines()[0][:300], llm=merged, attempts=attempts)
