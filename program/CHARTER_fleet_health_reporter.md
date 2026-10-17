# Pilot charter: fleet health reporter

**Problem.** The daily fleet health note (which sites and vaults carry the most 30-day failure
risk, what moved in telemetry) is assembled by hand from Project 1's risk tables and the telemetry
summary.

**What the agent does.** On a schedule (`.github/workflows/fleet_report.yml`, 06:15 UTC, plus
`scripts/run_fleet_report_local.sh`): reads the top sites and vaults from the risk tables and a
7-day telemetry summary through the MCP tools, drafts the report in Markdown, and sets
`needs_human_approval` when any site's expected 30-day failures exceed the threshold (7.0 in the
config). It writes a draft under `reports/fleet/drafts/`; publishing is a separate human command
(`--approve --approver <name>`).

**Owner.** Services Operations analytics lead. Config: `agents/fleet_health_reporter.yaml`.

**Data permissions.** Tools `fleet_risk`, `sql_query` (read-only role, row cap 200).

**Success metric.** On 10 scenarios (five thresholds x two models): the approval flag is set
exactly when the data says so, every number in the report appears in the data the agent was given,
and the report names the top site. Target 100%: a report with an invented number is a failed report.

**Guardrails.** 1 model call, 8,000 tokens; publishes nothing; the audit log records the task.

**Stop criteria.** Any report with a number not in its source data stops the schedule until the
prompt or the model is changed.
