# Pilot charter: dispatch readiness agent

**Problem.** Trucks roll on cases that did not need one. In Project 1's data 1,902 of 4,108
dispatches (46%) were unnecessary by the truth file (`truth/dispatch_truth.csv`): no hardware
fault, a deflectable case, or a repeat without a new fault; 177 visits ended `parts_not_available`.

**What the agent does.** Before a dispatch is scheduled: pulls the asset's history (prior cases
and visits, telemetry failure flag, last-7-day SMART counters, 30-day risk from Project 1's model),
checks the drive sled for that drive's capacity at the regional depot, and recommends
`go`, `hold` (ask for diagnostics or deflect) or `ship-part-first`, with reasons. A rule-based
recommendation is computed alongside the model's so disagreement is visible.

**Owner.** Field Services dispatch manager. Config: `agents/dispatch_readiness.yaml`.

**Data permissions.** Tools `asset_history`, `parts_on_hand` only.

**Success metric.** On 10 scenarios with truth: `go` or `ship-part-first` on necessary dispatches,
`hold` on unnecessary ones. Target >= 80%.

**Guardrails.** 1 model call, 6,000 tokens per task; the recommendation is advisory, the dispatcher
decides; case text is data, not instructions.

**Stop criteria.** Stop if the agent recommends `hold` on a telemetry-confirmed failed drive, or
if the pass rate is below 60% on the best model.
