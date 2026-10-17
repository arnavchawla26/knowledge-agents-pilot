import json

import pytest

from kap import audit, tools


def test_audit_hashes_args_not_text(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path)
    e = audit.record(caller="t", agent="a", tool="sql_query", args={"sql": "SELECT 'secret case text'"}, rows=1, latency_s=0.01)
    line = json.loads((next(tmp_path.glob("*.jsonl"))).read_text().splitlines()[-1])
    assert line["args_hash"] == e["args_hash"] and len(line["args_hash"]) == 16
    assert "secret" not in json.dumps(line)


def test_server_side_permission_denied_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path)
    monkeypatch.setenv("KAP_ALLOWED_TOOLS", "fleet_risk")
    monkeypatch.setenv("KAP_AGENT", "case_triage")
    with pytest.raises(tools.ToolDenied):
        tools.sql_query("SELECT 1")
    line = json.loads((next(tmp_path.glob("*.jsonl"))).read_text().splitlines()[-1])
    assert line["ok"] is False and line["agent"] == "case_triage" and "ToolDenied" in line["error"]


def test_sql_tool_refuses_writes_before_touching_the_db(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path)
    monkeypatch.delenv("KAP_ALLOWED_TOOLS", raising=False)
    from kap.sqlguard import SQLRejected

    with pytest.raises(SQLRejected):
        tools.sql_query("DELETE FROM inventory")
