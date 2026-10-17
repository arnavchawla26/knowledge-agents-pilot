#!/usr/bin/env bash
# Local runner for the scheduled fleet report (the cron file is .github/workflows/fleet_report.yml).
# Install on macOS with launchd or `crontab -e`:  15 6 * * * /path/to/scripts/run_fleet_report_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
"$HOME/.local/bin/uv" run python -m kap.agents.fleet_health_reporter "$@"
