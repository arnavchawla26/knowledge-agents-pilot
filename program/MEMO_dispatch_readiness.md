# What the pilot proved: dispatch readiness agent (2026-10-17)

**Verdict: cleared its threshold on all three models (10/10 each) with the conservative-on-
disagreement rule; without that rule Nemotron alone would have scored 9/10, and the miss is a
policy choice the owner has to make, not a model error.**

**Setup.** 10 first-visit dispatches with `necessary` from `truth/dispatch_truth.csv`: 5 hardware
faults (expected `go` or `ship-part-first`), 5 unnecessary (expected `hold`). The agent sees the
asset's telemetry failure flag, last-7-day SMART counters, Project 1's 30-day risk score, prior
visits and the drive sled stock at the regional depot; the model's recommendation and a rule's
are both computed and the more conservative wins on disagreement.

| Model | Pass rate | Mean tokens / task | Mean cost / task | Mean latency / task |
|---|---:|---:|---:|---:|
| nemotron | 10/10 (9/10 on the model's own answer) | 1,055 | $0 | 5.6 s |
| llama | 10/10 | 854 | $0 | 24.5 s (free-tier throttling) |
| claude | 10/10 | 1,518 | $0.0122 | 5.3 s |

**What it proved.**
- With corroborating evidence in front of it, every model agreed with the truth on the five real
  faults and on the four unnecessary visits that had no fault evidence.
- The disagreement (CS-0000050, Nemotron) is the case the design is about: the ticket says
  `drive_failure`, the drive's SMART counters are zero, it never failed in telemetry and has no
  risk score. The truth says no fault. Nemotron said `go`, the rule said `hold`, the agent
  returned `hold` and reported the disagreement (`reports/agent_eval.csv`, detail column). The
  owner has to decide whether an uncorroborated ticket rolls a truck: Project 1's generator makes
  70% of such tickets real faults the telemetry never saw, so `hold` will delay some real
  repairs. That trade is now visible instead of implicit.
- Parts awareness works: `ship-part-first` fires when the regional depot has no sled of the
  drive's capacity; on the 2026-06 inventory it never had to, because those sleds were in stock.

**What it did not prove.**
- No `ship-part-first` scenario occurred in the sample, so that branch is exercised only by the
  rule's unit path, not by the truth file.
- Risk scores exist only for the top-100 drives in Project 1's report; for every other drive the
  agent falls back to the Backblaze SMART heuristic, which Project 1 showed catches 7% of
  failures at the top-0.1% budget. A full-fleet score table would change this agent's quality.

**Recommendation.** Keep the conservative-on-disagreement rule; add the dispatcher's override
as a logged event so the hold-vs-go trade can be measured on real data.
