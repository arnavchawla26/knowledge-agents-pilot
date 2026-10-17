import yaml

from conftest import needs_db

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


def test_auto_ontology_enrichment_is_built_from_the_glossary():
    """Every Auto Ontology term the enrichment targets gets a non-trivial description, and the SQL
    attributes it adds say nothing the glossary does not (each is keyed to a glossary term)."""
    from kap.eval.ao_enrich import SQL_ATTRIBUTES, TERM_MAP, build_descriptions

    g = yaml.safe_load((QUESTIONS_DIR / "glossary.yaml").read_text())["terms"]
    descs = build_descriptions()
    assert set(descs) == set(TERM_MAP)
    for name, d in descs.items():
        assert len(d) > 100, name
        if name in ("Case", "Dispatch", "Installed Asset", "Site", "Product", "Part"):
            assert "Relationships:" in d, name  # the join paths the compiled layer could not find
    for _term, attr_name, _desc, expr in SQL_ATTRIBUTES:
        assert expr.upper().startswith("SELECT")
        assert attr_name in g or attr_name in ("Opened At (parsed)", "Telemetry serial join"), attr_name


@needs_db
def test_auto_ontology_sql_attributes_execute():
    from kap import text2sql
    from kap.eval.ao_enrich import SQL_ATTRIBUTES

    for _term, name, _desc, expr in SQL_ATTRIBUTES:
        _, rows, _ = text2sql.run_sql(expr, cap=5)
        assert rows, name
