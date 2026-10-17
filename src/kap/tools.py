"""The five data tools behind the MCP server. Plain functions so the MCP server, the agent
runtime and the tests all call the same code; every call is audited here."""
from __future__ import annotations

import os
import re
import time
from typing import Any

import psycopg

from kap import audit
from kap.config import pg_dsn
from kap.sqlguard import SQLRejected, validate_readonly, with_row_cap

ALL_TOOLS = ("sql_query", "search_runbooks", "asset_history", "parts_on_hand", "fleet_risk")
MAX_ROWS = 200
SERIAL_PREFIX = re.compile(r"^(SG-|HGST_|TOS-|WD-|HIT-|OEM-)", re.IGNORECASE)


class ToolDenied(PermissionError):
    pass


def _identity() -> tuple[str, str]:
    return os.environ.get("KAP_CALLER", "cli"), os.environ.get("KAP_AGENT", "none")


def _allowed(tool: str) -> None:
    allowed = os.environ.get("KAP_ALLOWED_TOOLS")
    if allowed is not None and tool not in [t.strip() for t in allowed.split(",") if t.strip()]:
        raise ToolDenied(f"tool '{tool}' is not in this agent's data permissions")


def _audited(tool: str, args: dict[str, Any], fn):
    caller, agent = _identity()
    t0 = time.perf_counter()
    try:
        _allowed(tool)
        out = fn()
        rows = out.get("row_count", len(out.get("rows", out.get("results", [])))) if isinstance(out, dict) else 0
        audit.record(caller=caller, agent=agent, tool=tool, args=args, rows=rows, latency_s=time.perf_counter() - t0, ok=True,
                     task_id=os.environ.get("KAP_TASK_ID"))
        return out
    except Exception as e:  # noqa: BLE001 - every failure is logged, then re-raised to the caller
        audit.record(caller=caller, agent=agent, tool=tool, args=args, rows=0, latency_s=time.perf_counter() - t0, ok=False,
                     error=f"{type(e).__name__}: {str(e)[:200]}", task_id=os.environ.get("KAP_TASK_ID"))
        raise


def _query(sql: str, params: tuple = (), cap: int = MAX_ROWS) -> tuple[list[str], list[tuple]]:
    with psycopg.connect(pg_dsn()) as pg:
        pg.read_only = True
        with pg.cursor() as cur:
            cur.execute(with_row_cap(sql, cap), params or None)
            cols = [d.name for d in cur.description] if cur.description else []
            return cols, cur.fetchall()


def _rows(cols: list[str], rows: list[tuple]) -> list[dict[str, Any]]:
    return [dict(zip(cols, (v if not hasattr(v, "isoformat") else v.isoformat() for v in r))) for r in rows]


# ---------------------------------------------------------------- sql_query
def sql_query(sql: str, max_rows: int = 100) -> dict[str, Any]:
    """Run one read-only SELECT against the warehouse. Rejects anything else; caps rows."""
    args = {"sql": sql, "max_rows": max_rows}

    def go():
        cap = max(1, min(int(max_rows), MAX_ROWS))
        cleaned = validate_readonly(sql)
        cols, rows = _query(cleaned, cap=cap)
        return {"columns": cols, "rows": _rows(cols, rows), "row_count": len(rows), "capped_at": cap}

    return _audited("sql_query", args, go)


# ---------------------------------------------------------------- search_runbooks
def search_runbooks(query: str, product_family: str | None = None, size: int = 5) -> dict[str, Any]:
    """Hybrid (BM25 + NeMo Retriever dense, RRF) search over runbooks."""
    args = {"query": query, "product_family": product_family, "size": size}

    def go():
        from kap.search import search

        hits = search(query, kind="runbook", size=max(1, min(int(size), 10)) * (3 if product_family else 1))
        if product_family:
            hits = [h for h in hits if h.get("product_family") == product_family] or hits
        hits = hits[: max(1, min(int(size), 10))]
        return {"results": [{"runbook_id": h["runbook_id"], "title": h["title"], "product_family": h["product_family"],
                             "category": h["category"], "score": h["score"], "body": h["body"]} for h in hits],
                "row_count": len(hits)}

    return _audited("search_runbooks", args, go)


# ---------------------------------------------------------------- asset_history
def normalize_serial(s: str) -> str:
    return SERIAL_PREFIX.sub("", s.strip()).upper()


def asset_history(serial_or_asset_id: str) -> dict[str, Any]:
    """Asset, its cases, dispatches, telemetry summary and risk score for one serial or asset id."""
    args = {"serial_or_asset_id": serial_or_asset_id}

    def go():
        key = serial_or_asset_id.strip()
        cols, rows = _query(
            "SELECT a.asset_id, a.serial_number, a.site_id, a.product_id, a.install_date, a.warranty_end, a.status, "
            "p.product_name, p.family, s.site_name, s.region, s.account_id "
            "FROM installed_asset a JOIN product p ON p.product_id = a.product_id JOIN site s ON s.site_id = a.site_id "
            "WHERE a.asset_id = %s OR upper(regexp_replace(a.serial_number, '^(SG-|HGST_|TOS-|WD-|HIT-|OEM-)', '', 'i')) = %s",
            (key, normalize_serial(key)), cap=1)
        if not rows:
            return {"found": False, "row_count": 0}
        asset = _rows(cols, rows)[0]
        tserial = normalize_serial(asset["serial_number"])
        c_cols, c_rows = _query(
            "SELECT case_id, opened_at, closed_at, category, severity, resolution_code, failure_reported, left(description, 200) AS description "
            "FROM \"case\" WHERE asset_id = %s ORDER BY case_id", (asset["asset_id"],), cap=50)
        d_cols, d_rows = _query(
            "SELECT d.dispatch_id, d.case_id, d.visit_number, d.scheduled_at, d.outcome, d.parts_used, t.region AS technician_region "
            "FROM dispatch d JOIN \"case\" c ON c.case_id = d.case_id JOIN technician t ON t.technician_id = d.technician_id "
            "WHERE c.asset_id = %s ORDER BY d.scheduled_at", (asset["asset_id"],), cap=50)
        t_cols, t_rows = _query(
            "SELECT serial_number, model, capacity_bytes, datacenter, vault_id, pod_id, first_seen, last_seen, days_observed, failed, failure_date, max_power_on_hours "
            "FROM telemetry_drive_summary WHERE upper(serial_number) = %s", (tserial,), cap=1)
        r_cols, r_rows = _query(
            "SELECT p_fail_30d, heuristic_flag, smart_5_raw, smart_187_raw, smart_197_raw, smart_198_raw "
            "FROM fleet_risk_top100 WHERE upper(serial_number) = %s", (tserial,), cap=1)
        h_cols, h_rows = _query(
            "SELECT max(smart_5_raw) AS smart_5_raw, max(smart_187_raw) AS smart_187_raw, max(smart_188_raw) AS smart_188_raw, "
            "max(smart_197_raw) AS smart_197_raw, max(smart_198_raw) AS smart_198_raw, max(date) AS last_date "
            "FROM telemetry_daily_recent WHERE upper(serial_number) = %s", (tserial,), cap=1)
        telem = _rows(t_cols, t_rows)[0] if t_rows else None
        recent = _rows(h_cols, h_rows)[0] if h_rows and h_rows[0][5] is not None else None
        risk: dict[str, Any]
        if r_rows:
            risk = {"source": "fleet_risk_top100 (Project 1 LightGBM, 30-day)", **_rows(r_cols, r_rows)[0]}
        else:
            flag = bool(recent and any((recent.get(k) or 0) > 0 for k in ("smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw")))
            risk = {"source": "not in top-100 risk table; Backblaze heuristic on last 7 days", "p_fail_30d": None, "heuristic_flag": int(flag)}
        return {"found": True, "asset": asset, "telemetry": telem, "recent_smart": recent, "risk": risk,
                "cases": _rows(c_cols, c_rows), "dispatches": _rows(d_cols, d_rows),
                "row_count": 1 + len(c_rows) + len(d_rows)}

    return _audited("asset_history", args, go)


# ---------------------------------------------------------------- parts_on_hand
def parts_on_hand(depot_id: str | None = None, part_id: str | None = None, region: str | None = None) -> dict[str, Any]:
    """Inventory by depot. A region maps to its depot (DEPOT-<region>); Central is the fallback."""
    args = {"depot_id": depot_id, "part_id": part_id, "region": region}

    def go():
        depot = depot_id or (f"DEPOT-{region}" if region else None)
        sql = ("SELECT i.depot_id, i.part_id, p.part_number, p.description, p.category, i.on_hand, i.reorder_point, "
               "(i.on_hand < i.reorder_point) AS below_reorder FROM inventory i JOIN part p ON p.part_id = i.part_id WHERE 1=1")
        params: list[Any] = []
        if depot:
            sql += " AND i.depot_id = %s"
            params.append(depot)
        if part_id:
            sql += " AND (i.part_id = %s OR p.part_number = %s)"
            params += [part_id, part_id]
        sql += " ORDER BY i.depot_id, i.part_id"
        cols, rows = _query(sql, tuple(params))
        return {"depot_id": depot, "rows": _rows(cols, rows), "row_count": len(rows)}

    return _audited("parts_on_hand", args, go)


# ---------------------------------------------------------------- fleet_risk
def fleet_risk(level: str = "sites", top_n: int = 10) -> dict[str, Any]:
    """Top-N from Project 1's fleet risk tables: sites, vaults, or drives."""
    args = {"level": level, "top_n": top_n}

    def go():
        table = {"sites": "fleet_risk_sites", "vaults": "fleet_risk_vaults", "drives": "fleet_risk_top100"}.get(level)
        if table is None:
            raise ValueError("level must be sites, vaults or drives")
        order = "p_fail_30d DESC" if level == "drives" else "expected_failures_30d DESC"
        n = max(1, min(int(top_n), 100))
        cols, rows = _query(f"SELECT * FROM {table} ORDER BY {order}", cap=n)
        return {"level": level, "rows": _rows(cols, rows), "row_count": len(rows)}

    return _audited("fleet_risk", args, go)


TOOL_FUNCS = {"sql_query": sql_query, "search_runbooks": search_runbooks, "asset_history": asset_history,
              "parts_on_hand": parts_on_hand, "fleet_risk": fleet_risk}
