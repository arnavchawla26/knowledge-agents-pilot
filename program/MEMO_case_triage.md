# What the pilot proved: case triage agent (2026-10-17)

**Verdict: cleared its threshold on two of three models; promote to a supervised trial.**

**Setup.** 10 scenarios from `questions/agent_scenarios.yaml` with expected outcomes from Project 1's
`truth/case_truth.csv`: 5 deflectable cases whose truth names the runbook, 5 that must go to a
human (3 telemetry-confirmed drive failures, 2 predictive alerts on drives that then failed).
Pass = right decision and, when responding, the right runbook. Numbers: `reports/agent_eval.csv`,
`reports/agent_eval_summary.csv` (latency is mean wall time per task, tools and model included).

| Model | Pass rate | Mean tokens / task | Mean cost / task | Mean latency |
|---|---:|---:|---:|---:|
| nemotron (nvidia/nemotron-3-super-120b-a12b, reasoning off) | 10/10 | 500 | $0 (free tier) | 4.8 s |
| llama (meta/llama-3.2-90b-vision-instruct) | 8/10 | 414 | $0 (free tier) | 47.4 s (free-tier throttling and retries) |
| claude (claude-opus-5-5) | 10/10 | 864 | $0.0087 | 6.1 s |

**What it proved.**
- The fixed workflow plus a deterministic quality score keeps every hardware fault and severity
  1-2 case on the human path on all three models: zero automated replies on the five escalation
  scenarios, which was the stop criterion.
- Model choice matters less than the retrieval and the score: Nemotron and Claude were identical
  on this set; Llama's two misses were misclassifications (`config` read as `performance`,
  `firmware` read as `config`) that the score then correctly turned into escalations, so the cost
  of the weaker model was two deflectable cases sent to a human, not a wrong reply.
- Prompt injection through case notes or runbook text does not change the tools called
  (`tests/test_injection.py`, 5 tests), because the model never chooses tools.

**What it did not prove.**
- 10 scenarios is a smoke test, not a measurement; the 95% interval on 10/10 still allows a
  true pass rate in the 70s.
- The draft replies were not graded for quality by a human; the eval checks decision and runbook.
- The case text is templated (Project 1 generator); real tickets are messier, and the hybrid
  search was tuned on 15 hand-written queries only (`reports/search_eval.csv`).

**Recommendation.** Run Nemotron (free tier, 500 tokens a task) in shadow mode on live cases for
two weeks with a human sending every draft; promote only if the human edit rate on drafts is
below an agreed bar.
