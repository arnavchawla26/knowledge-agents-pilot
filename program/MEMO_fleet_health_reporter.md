# What the pilot proved: fleet health reporter (2026-10-17)

**Verdict: failed its first run on both models, passed 10/10 after one fix. Schedule it only
with the truncation and grounding checks as a gate.**

**Setup.** Five approval thresholds (6 to 10 expected 30-day failures at a site) on two models.
Pass = the approval flag matches the data (worst site 8.03, so thresholds 6-8 flag and 9-10 do
not), every number in the Markdown report appears in the data the agent was given, the report
names the worst site (SITE-00432), and the model reply was not cut off by the token budget.

| Run | Model | Pass | Mean tokens / task | Mean cost / task |
|---|---|---:|---:|---:|
| first (900-token answer budget) | nemotron | 0/5 | 2,057 | $0 |
| first (900-token answer budget) | claude | 0/5 | 2,258 | $0.0234 |
| final (2,500-token answer budget, truncation check) | nemotron | 5/5 | 2,146 | $0 |
| final | claude | 5/5 | 2,752 | $0.0333 |

**What it proved.**
- The approval gate is deterministic and correct on all 10 runs: the flag is code, not the model,
  and nothing is published without `--approve --approver <name>` (`reports/fleet/drafts/` vs
  `reports/fleet/`).
- The first run is the useful lesson. Both models ignored the "under 350 words" instruction and
  every one of the ten reports hit the 900-token answer limit (`stop_reason: length`), most of
  them cleanly at a table boundary, so they looked finished. The number check caught only one
  (a Nemotron report cut mid-number: `Max p: 0.2` where the data says `0.2647`). A truncated
  report that looks complete is the dangerous kind, so the agent now records the stop reason,
  any truncated draft is forced to human approval, and the eval fails it. With a 2,500-token
  budget every report completed and every number traced to its source.
- Grounding can be checked mechanically, and the check is cheap: strip identifiers, list markers
  and the draft header, then every remaining number must appear in the tool results.
- Three tool calls, one model call, 2,100 to 2,800 tokens per report: the only agent that runs
  unattended, which is exactly why it needs the gate.

**What it did not prove.**
- The telemetry window is the last 7 days of 2026 Q2 (the warehouse ends 2026-06-30), so "what
  changed" is one fixed window; a daily schedule on live data was not observed.
- Report usefulness was not rated by an operations leader; the eval checks truthfulness, not
  insight.
- The GitHub Actions cron is present but runs only on manual dispatch until the stack is hosted
  (`.github/workflows/fleet_report.yml`); the local runner was used.

**Recommendation.** Keep the truncation and grounding checks as hard gates (re-draft once, then
escalate); keep the human approval even for unflagged reports until a month of drafts has been
read.
