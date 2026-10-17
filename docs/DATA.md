# Data: where the warehouse comes from

Project 1 (`services-ops-intelligence`, read-only input) ships the enterprise as CSV/Parquet plus
a Docker Postgres (`sois-postgres`, port 5432). At build time that container held a sample load
(6 installed assets, 9 cases, 11 telemetry rows), which is fine for its own tests but useless for
a 30-question evaluation. This project therefore runs its **own** Postgres (`kap-sourcedb`, port
5434, compose project `kap`) and loads the full data from Project 1's files with
`kap.load_source`, using Project 1's `sql/schema.sql` unchanged:

| Table | Rows | Source |
|---|---:|---|
| installed_asset, telemetry_drive_summary | 359,101 each | `data/enterprise/installed_asset.csv`, `data/parquet/drive_summary.parquet` |
| telemetry_daily_recent | 2,485,026 (last 7 days, 2026-06-24 to 06-30) | `data/parquet/telemetry_daily/` |
| case / dispatch / dispatch_part | 8,281 / 4,108 / 2,616 | CSV |
| account / site / contact | 335 / 701 / 471 | CSV |
| order / order_line | 8,204 / 43,624 | CSV |
| part / supplier / part_supplier / inventory | 30 / 8 / 61 / 180 | CSV |
| technician / runbook | 80 / 22 | CSV |
| fleet_risk_sites / fleet_risk_vaults / fleet_risk_top100 | 255 / 311 / 100 | `reports/*.csv` from Project 1's failure model |
| data_product / job / lineage / query_log | 3 / 4 / 10 / 300 | CSV |

Nothing in Project 1 is modified. `KAP_PG_*` in `.env` can point the pilot at any Postgres with
this schema, including Project 1's container once it carries a full load.

Two roles: `sois` (owner, used only by the loader) and `kap_ro` (`default_transaction_read_only`,
30 s statement timeout, SELECT only), which is the only role the MCP server, the agents, the
evaluation and NVIDIA Auto Ontology ever use.

What is real: the telemetry (Backblaze 2026 Q2) and everything derived from it. What is generated:
every CRM/ERP/support table, with documented mess (`docs/MESS_RULES.md` in Project 1) and ground
truth under Project 1's `truth/`. The agent scenarios' expected outcomes come from that truth.
