"""MCP server exposing the five warehouse tools (Python MCP SDK 2.x, MCPServer, stdio).

    uv run python -m kap.mcp_server                 # stdio, for an MCP client
    KAP_AGENT=case_triage KAP_ALLOWED_TOOLS=search_runbooks,asset_history uv run python -m kap.mcp_server

Identity and permissions come from the environment the client spawns the server with
(KAP_CALLER, KAP_AGENT, KAP_ALLOWED_TOOLS, KAP_TASK_ID); every call is appended to audit/*.jsonl.
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from kap import tools
from kap.sqlguard import SQLRejected

mcp = MCPServer("knowledge-agents-pilot")


def _safe(fn, *args):
    """Return a structured error for expected failures (rejected SQL, denied tool, bad argument)
    so the calling agent can read why; anything else propagates as a tool error."""
    try:
        return fn(*args)
    except (SQLRejected, tools.ToolDenied, ValueError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "row_count": 0}


@mcp.tool()
def sql_query(sql: str, max_rows: int = 100) -> dict[str, Any]:
    """Run ONE read-only SELECT/WITH statement against the Services Operations warehouse.
    Writes, DDL, multiple statements and dangerous functions are refused; rows are capped at 200."""
    return _safe(tools.sql_query, sql, max_rows)


@mcp.tool()
def search_runbooks(query: str, product_family: str | None = None, size: int = 5) -> dict[str, Any]:
    """Hybrid search (BM25 + NeMo Retriever embeddings, reciprocal rank fusion) over the runbooks."""
    return _safe(tools.search_runbooks, query, product_family, size)


@mcp.tool()
def asset_history(serial_or_asset_id: str) -> dict[str, Any]:
    """Asset record, its cases and dispatches, telemetry summary and 30-day risk for one serial or asset id."""
    return _safe(tools.asset_history, serial_or_asset_id)


@mcp.tool()
def parts_on_hand(depot_id: str | None = None, part_id: str | None = None, region: str | None = None) -> dict[str, Any]:
    """Inventory on hand and reorder points by depot (or by region's depot) and optionally one part."""
    return _safe(tools.parts_on_hand, depot_id, part_id, region)


@mcp.tool()
def fleet_risk(level: str = "sites", top_n: int = 10) -> dict[str, Any]:
    """Top-N riskiest sites, vaults or drives from Project 1's 30-day failure risk tables."""
    return _safe(tools.fleet_risk, level, top_n)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
