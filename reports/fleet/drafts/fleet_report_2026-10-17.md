<!-- DRAFT, not published. agent=fleet_health_reporter model=claude task=92b88e89a3d4 needs_human_approval=False truncated=False worst_site_expected_failures_30d=8.03 threshold=10.0 -->
# Daily Fleet Health Report: 2026-10-17

*Draft for human approval before publishing.*

## Summary
- **Approval threshold not exceeded.** The threshold is 10.0 expected 30-day failures. The highest site is 8.03 (Lighthouse Systems Boston), so the threshold-based approval flag is **not triggered**. Standard human review still applies.
- **Stale telemetry.** The telemetry window is 2026-06-24 to 2026-06-30, but the report date is 2026-10-17. Treat the telemetry figures as out of date until the feed is confirmed.

## Riskiest sites
| Site | Region | Drives | Exp. failures (30d) | Max p | Heuristic flagged |
|---|---|---|---|---|---|
| SITE-00432 Lighthouse Systems Boston | AMER-East | 3547 | 8.03 | 0.3184 | 99 |
| SITE-00492 Pinecrest Mutual Amsterdam | EMEA | 2436 | 7.17 | 0.6906 | 317 |
| SITE-00453 Harborview Logistics Austin | AMER-East | 2398 | 7.01 | 0.3184 | 55 |
| SITE-00017 Northwind Foods Tokyo | APJ | 2433 | 6.94 | 0.4026 | 226 |
| SITE-00656 Lakeshore Energy Phoenix | AMER-West | 1219 | 6.42 | 0.5718 | 92 |

## Riskiest vaults
| Datacenter / Vault | Drives | Exp. failures (30d) | Max p | Heuristic flagged |
|---|---|---|---|---|
| sac2 / 3013 | 1127 | 7.78 | 0.3184 | 18 |
| sac2 / 1124 | 1213 | 6.79 | 0.4026 | 204 |
| iad1 / 1028 | 1178 | 6.68 | 0.3184 | 28 |
| phx1 / 1063 | 1219 | 6.42 | 0.5718 | 92 |
| iad1 / 1034 | 1195 | 6.09 | 0.2647 | 31 |

## Last 7 days of telemetry
- **Window:** 2026-06-24 to 2026-06-30
- **Drives reporting:** 356012
- **Failures in window:** 77
- **Drives with SMART warnings:** 25205
- **Change from the prior period:** not available. The data has no comparison period.

## Recommended actions
1. **Fix the telemetry feed first.** Confirm why the latest window ends 2026-06-30 and refresh the data before relying on these figures.
2. **Prioritize Pinecrest Mutual Amsterdam.** It has the highest single-drive probability (max p 0.6906) and the most heuristic flags (317). Schedule proactive drive replacement review.
3. **Review Lighthouse Systems Boston.** It has the highest expected failures (8.03), the closest to the 10.0 threshold. Monitor daily.
4. **Check Lakeshore Energy Phoenix against vault phx1 / 1063.** Both show identical figures (1219 drives, 6.42, 0.5718, 92). This may be the same footprint, which would avoid double-counting.
5. **Investigate sac2 / 1124 and Northwind Foods Tokyo.** Both have high heuristic flag counts (204 and 226) alongside elevated risk.
