"""Execution-match scoring, the BIRD rule used by NVIDIA ontology-sql-eval
(vendor/ontology-sql-eval/ontology_sql_eval/gym/exec_match.py): set(gold rows) == set(pred rows),
order ignored, duplicate rows collapsed. Values are normalised first so Decimal('1.50') and 1.5
compare equal and floats agree to 6 decimals; strings are stripped. A looser 'lenient' flag is also
reported: every gold row appears in the prediction when the prediction is projected onto the gold
column count (extra columns tolerated). The headline number is the strict one."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from itertools import combinations
from typing import Any, Iterable


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, int):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        try:
            return round(float(s), 6)
        except ValueError:
            return s
    return v


def norm_rows(rows: Iterable[tuple]) -> set[tuple]:
    return {tuple(_norm(v) for v in r) for r in rows}


def strict_match(gold: list[tuple], pred: list[tuple]) -> bool:
    return norm_rows(gold) == norm_rows(pred)


def lenient_match(gold: list[tuple], pred: list[tuple]) -> bool:
    """Gold rows found among the predicted rows after projecting pred onto any column subset of the
    same width (handles an extra label column the question did not ask for). Bounded search."""
    g = norm_rows(gold)
    if not g or not pred:
        return False
    width = len(next(iter(g)))
    pw = len(pred[0])
    if pw < width:
        return False
    if pw == width:
        return g == norm_rows(pred)
    if pw - width > 3:
        return False
    for cols in combinations(range(pw), width):
        if g == norm_rows(tuple(r[i] for i in cols) for r in pred):
            return True
    return False
