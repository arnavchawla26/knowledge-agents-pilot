import yaml

from kap.config import AGENTS_DIR, QUESTIONS_DIR
from kap.agents.base import AgentConfig
from kap.tools import ALL_TOOLS


def test_glossary_covers_the_13c_terms():
    g = yaml.safe_load((QUESTIONS_DIR / "glossary.yaml").read_text())
    for term in ["Account", "Site", "Installed Asset", "Product", "Part", "Supplier", "Case", "Dispatch", "Technician",
                 "Runbook", "Failure", "Service Failure", "Repeat Dispatch", "Deflectable Case", "Fleet Health", "Risky Pod",
                 "Warranty Status", "Parts Lead Time"]:
        assert term in g["terms"], term
        assert len(g["terms"][term]["definition"]) > 40
    assert len(g["relationships"]) >= 10


def test_every_agent_config_is_scoped():
    for path in AGENTS_DIR.glob("*.yaml"):
        cfg = AgentConfig.load(path.stem)
        assert set(cfg.tools) <= set(ALL_TOOLS)
        assert set(cfg.tools) != set(ALL_TOOLS), "an agent with every tool is not scoped"
        assert 0 < cfg.quality_threshold < 1
        assert cfg.token_budget_per_task > 0 and cfg.max_llm_calls_per_task >= 1
        assert cfg.model in ("nemotron", "llama", "claude")


def test_eval_set_shape():
    qs = yaml.safe_load((QUESTIONS_DIR / "eval.yaml").read_text())["questions"]
    assert len(qs) == 30
    by = {}
    for q in qs:
        by[q["difficulty"]] = by.get(q["difficulty"], 0) + 1
        assert q["sql"].strip().upper().startswith(("SELECT", "WITH"))
    assert by == {"easy": 10, "medium": 10, "hard": 10}
    assert len({q["id"] for q in qs}) == 30
