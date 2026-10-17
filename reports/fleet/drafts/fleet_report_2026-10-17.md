<!-- DRAFT, not published. agent=fleet_health_reporter model=nemotron task=575edaca2ec9 needs_human_approval=True worst_site_expected_failures_30d=8.03 threshold=7.0 -->
# Daily Fleet Health Report  
**Report Date:** 2026-10-17  

## Summary  
The fleet health report identifies sites and vaults with the highest expected 30-day failures. The approval threshold for expected 30-day failures is 7.0. Any site exceeding this threshold requires human approval before publication.  

## Riskiest Sites  
Ranked by expected_failures_30d (highest to lowest):  
1. **SITE-00432** (Lighthouse Systems Boston): expected_failures_30d = 8.03, drives = 3547, max_p = 0.3184, heuristic_flagged = 99  
2. **SITE-00492** (Pinecrest Mutual Amsterdam): expected_failures_30d = 7.17, drives = 2436, max_p = 0.6906, heuristic_flagged = 317  
3. **SITE-00453** (Harborview Logistics Austin): expected_failures_30d = 7.01, drives = 2398, max_p = 0.3184, heuristic_flagged = 55  
4. **SITE-00017** (Northwind Foods Tokyo): expected_failures_30d = 6.94, drives = 2433, max_p = 0.4026, heuristic_flagged = 226  
5. **SITE-00656** (Lakeshore Energy Phoenix): expected_failures_30d = 6.42, drives = 1219, max_p = 0.5718, heuristic_flagged = 92  

## Riskiest Vaults  
Ranked by expected_failures_30d (highest to lowest):  
1. **sac2, vault_id 3013**: expected_failures_30d = 7.78, drives = 1127, max_p = 0.3184, heuristic_flagged = 18  
2. **sac2, vault_id 1124**: expected_failures_30d = 6.79, drives = 1213, max_p = 0.4026, heuristic_flagged = 204  
3. **iad1, vault_id 1028**: expected_failures_30d = 6.68, drives = 1178, max_p = 0.3184, heuristic_flagged = 28  
4. **phx1, vault_id 1063**: expected_failures_30d = 6.42, drives = 1219, max_p = 0.5718, heuristic_flagged = 92  
5. **iad1, vault_id 1034**: expected_failures_30d = 6.09, drives = 1195, max_p = 0.2647, heuristic_flagged = 31  

## Last 7 Days of Telemetry  
- First day: 2026-06-24  
- Last day: 2026-06-30  
- Drives reporting: 356012  
- Failures in window: 77  
- Drives with SMART warnings: 25205  

## Recommended Actions  
- Prioritize inspection and preventive maintenance at **SITE-00432**, **SITE-00492**, and **SITE-00453** due to expected 30-day failures exceeding the approval threshold of 7.0.  
- Focus diagnostic efforts on **vault sac2/3013** and **sac2/1124**, which show the highest vault
