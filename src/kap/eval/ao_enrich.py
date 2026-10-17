"""Push the pilot's glossary (questions/glossary.yaml) into NVIDIA Auto Ontology's semantic layer.

Why: the compiled layer (24-26 terms) had an empty `description` on every Term; only the
column attributes carried LLM-written text. The chat pipeline retrieves candidate terms and
columns by embedding similarity, so a question such as "dispatches per product family" pulled
Product and Dispatch but never the Case and Installed Asset tables that connect them, and the
model concluded no join path existed (reports/auto_ontology_smoke.md, before).

Mechanism (both are the documented management API in vendor/auto-ontology/docs/openapi):
1. PATCH /api/terms/{term_id} with a description built from the glossary definition(s) that map
   to the term plus the glossary relationships naming it. The backend re-embeds the term.
2. POST /api/sql-attributes (after /validate) for the glossary's derived definitions that are a
   SQL expression and not a sentence: parsed case timestamps, repeat dispatch, service failure,
   deflectable case, risky pod, warranty status, parts lead time, the serial join. These are the
   same SQL hints the per-model "schema + glossary" arm receives in its prompt, so the arms stay
   comparable. No join-path query that answers an evaluation question is added.

Idempotent: PATCH overwrites; an existing equivalent SQL attribute is reported as "exists".

    uv run python -m kap.eval.ao_enrich [--dry-run]
"""
from __future__ import annotations

import argparse
import json

import yaml

from kap.auto_ontology import create_sql_attribute, list_terms, patch_term
from kap.config import QUESTIONS_DIR

# Auto Ontology term name -> glossary terms whose definitions describe it (in order).
TERM_MAP: dict[str, list[str]] = {
    "Account": ["Account", "Region"],
    "Site": ["Site", "Region"],
    "Installed Asset": ["Installed Asset", "Warranty Status"],
    "Product": ["Product"],
    "Part": ["Part", "Parts Lead Time"],
    "Dispatch Part": ["Part"],
    "Supplier": ["Supplier", "Region"],
    "Part Supplier": ["Supplier", "Parts Lead Time"],
    "Case": ["Case", "Service Failure", "Deflectable Case", "Reference date"],
    "Dispatch": ["Dispatch", "Repeat Dispatch", "Reference date"],
    "Technician": ["Technician", "Region"],
    "Runbook": ["Runbook", "Deflectable Case"],
    "Drive Summary": ["Failure", "Risky Pod", "Reference date"],
    "Drive Telemetry": ["Failure", "Reference date"],
    "Fleet Risk Site": ["Fleet Health"],
    "Fleet Risk Vault": ["Fleet Health"],
    "Inventory": ["Depot"],
}

# Derived definitions as full SELECTs (what /api/sql-attributes/validate accepts); each is the
# glossary's own SQL hint, no more.
SQL_ATTRIBUTES: list[tuple[str, str, str, str]] = [
    ("Case", "Opened At (parsed)",
     "opened_at is VARCHAR in two formats (ISO 8601 from svc_cloud, MM/DD/YYYY HH:MM from legacy_crm); this parses both to a timestamp. Use it for any date filter on case open time.",
     "SELECT c.case_id, CASE WHEN c.opened_at LIKE '__/__/____%' THEN to_timestamp(c.opened_at, 'MM/DD/YYYY HH24:MI')::timestamp ELSE c.opened_at::timestamp END AS opened_ts FROM \"case\" c"),
    ("Case", "Service Failure",
     "Support failure: a case with failure_reported = 1 (closed with resolution_code hardware_replaced). Not the same as telemetry failure.",
     "SELECT c.case_id FROM \"case\" c WHERE c.failure_reported = 1"),
    ("Case", "Deflectable Case",
     "A case a runbook could have resolved without a dispatch: category in (how_to, config, firmware) with severity >= 3, or false_alarm, where a runbook exists for the asset's product family and the case category.",
     "SELECT c.case_id FROM \"case\" c JOIN installed_asset a ON a.asset_id = c.asset_id JOIN product p ON p.product_id = a.product_id WHERE ((c.category IN ('how_to', 'config', 'firmware') AND c.severity >= 3) OR c.category = 'false_alarm') AND EXISTS (SELECT 1 FROM runbook r WHERE r.product_family = p.family AND r.category = c.category)"),
    ("Dispatch", "Repeat Dispatch",
     "A dispatch with visit_number > 1 on the same case. Repeat-dispatch rate = repeat dispatches / all dispatches.",
     "SELECT d.dispatch_id, CASE WHEN d.visit_number > 1 THEN 1 ELSE 0 END AS is_repeat_dispatch FROM dispatch d"),
    ("Drive Summary", "Risky Pod",
     "A (datacenter, vault_id, pod_id) group with at least 2 telemetry failures in the quarter.",
     "SELECT t.datacenter, t.vault_id, t.pod_id FROM telemetry_drive_summary t WHERE t.failed = 1 GROUP BY t.datacenter, t.vault_id, t.pod_id HAVING count(*) >= 2"),
    ("Installed Asset", "Warranty Status",
     "in_warranty when warranty_end >= 2026-06-30 (the warehouse reference date), out_of_warranty when earlier, unknown when NULL (10% by design; never report unknown as expired).",
     "SELECT a.asset_id, CASE WHEN a.warranty_end IS NULL THEN 'unknown' WHEN a.warranty_end >= DATE '2026-06-30' THEN 'in_warranty' ELSE 'out_of_warranty' END AS warranty_status FROM installed_asset a"),
    ("Installed Asset", "Telemetry serial join",
     "Join an installed asset to its drive telemetry: strip the vendor prefix (SG-, HGST_, TOS-, WD-, HIT-, OEM-) from installed_asset.serial_number and compare case-insensitively with telemetry_drive_summary.serial_number.",
     "SELECT a.asset_id, t.serial_number FROM installed_asset a JOIN telemetry_drive_summary t ON upper(t.serial_number) = upper(regexp_replace(a.serial_number, '^(SG-|HGST_|TOS-|WD-|HIT-|OEM-)', ''))"),
    ("Part Supplier", "Parts Lead Time",
     "Lead time per part: the preferred supplier's lead_time_days, else the minimum across its suppliers.",
     "SELECT p.part_id, coalesce(min(ps.lead_time_days) FILTER (WHERE ps.preferred), min(ps.lead_time_days)) AS lead_time_days FROM part p JOIN part_supplier ps ON ps.part_id = p.part_id GROUP BY p.part_id"),
]


def build_descriptions() -> dict[str, str]:
    g = yaml.safe_load((QUESTIONS_DIR / "glossary.yaml").read_text())
    defs = {k: " ".join(v["definition"].split()) for k, v in g["terms"].items()}
    rels = g["relationships"]
    out = {}
    for ao_name, gloss_terms in TERM_MAP.items():
        parts = []
        for t in gloss_terms:
            parts.append(defs[t] if t == gloss_terms[0] else f"{t}: {defs[t]}")
        related = [r for r in rels if any(t.lower() in r.lower() for t in (ao_name, gloss_terms[0]))]
        if related:
            parts.append("Relationships: " + "; ".join(related) + ".")
        out[ao_name] = " ".join(parts)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    terms = {t["name"]: t for t in list_terms()}
    descs = build_descriptions()
    report = {"terms_patched": [], "terms_missing": [], "sql_attributes": []}
    for name, desc in descs.items():
        if name not in terms:
            report["terms_missing"].append(name)
            continue
        if not args.dry_run:
            patch_term(terms[name]["id"], desc)
        report["terms_patched"].append({"term": name, "chars": len(desc), "was_empty": not (terms[name].get("description") or "").strip()})
    for term_name, attr_name, attr_desc, expr in SQL_ATTRIBUTES:
        if term_name not in terms:
            report["sql_attributes"].append({"status": "term missing", "name": attr_name})
            continue
        if args.dry_run:
            report["sql_attributes"].append({"status": "dry-run", "name": attr_name, "term": term_name})
            continue
        r = create_sql_attribute(terms[term_name]["id"], attr_name, attr_desc, expr)
        r["term"] = term_name
        report["sql_attributes"].append(r)
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
