from kap import tools
from kap.eval import text2sql_eval
from conftest import needs_db, needs_es


@needs_db
def test_every_ground_truth_query_runs_and_returns_rows():
    for q in text2sql_eval.load_questions():
        rows = text2sql_eval.gold_rows(q["sql"])
        assert rows, q["id"]


@needs_db
def test_asset_history_normalises_serial_prefixes(monkeypatch):
    monkeypatch.delenv("KAP_ALLOWED_TOOLS", raising=False)
    row = tools.sql_query("SELECT asset_id, serial_number FROM installed_asset WHERE serial_number LIKE 'SG-%' LIMIT 1")["rows"][0]
    h = tools.asset_history(row["serial_number"])
    assert h["found"] and h["asset"]["asset_id"] == row["asset_id"]
    assert h["telemetry"] is not None, "prefix stripped serial must join to telemetry"


@needs_db
def test_sql_tool_caps_rows(monkeypatch):
    monkeypatch.delenv("KAP_ALLOWED_TOOLS", raising=False)
    out = tools.sql_query("SELECT * FROM installed_asset", max_rows=5)
    assert out["row_count"] == 5


@needs_db
def test_fleet_risk_levels(monkeypatch):
    monkeypatch.delenv("KAP_ALLOWED_TOOLS", raising=False)
    for level in ("sites", "vaults", "drives"):
        assert tools.fleet_risk(level, 3)["row_count"] == 3


@needs_db
@needs_es
def test_search_runbooks_returns_runbooks(monkeypatch):
    monkeypatch.delenv("KAP_ALLOWED_TOOLS", raising=False)
    out = tools.search_runbooks("RAID degraded after a change", size=3)
    assert out["results"][0]["runbook_id"].startswith("RB-")
