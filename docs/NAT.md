# NVIDIA NeMo Agent Toolkit: what was used and what was not

`nvidia-nat[mcp]==1.9.0` installs cleanly on Python 3.13.0 (checked 2026-10-17; the core package
plus `nvidia-nat-mcp`). Its `nat` CLI, `register_function`, NIM/OpenAI/LiteLLM LLM configs and
MCP client/server runtimes are all present.

Decision (program/DECISIONS.md, 2026-10-17): the three agents are **fixed workflows** whose tool
calls are chosen by code, in a fixed order, through the MCP client, with the model limited to
producing a classification, a recommendation or a draft. NAT's bundled `react_agent` workflow hands
tool selection to the model, which is exactly what the governance rule here forbids (prompt
injection through runbook or case text must not be able to change a tool call), and it needs a
framework plugin (`nvidia-nat-langchain`) for the LLM clients. So:

- used: the install itself, `register_function` to expose each agent as a NAT function with a
  typed config (`src/kap/agents/nat_workflow.py`), so a NAT user can call the agents from a NAT
  workflow YAML or `nat` serve front end;
- not used: NAT's ReAct/tool-calling agents, its evaluation harness (the agent evaluation here is
  scenario-based against ground truth, `kap.eval.agent_eval`), and its profiler (token and latency
  numbers come from the audit log, which records every model and tool call per task).

Honest reading for the resume: "agents registered as NeMo Agent Toolkit functions over an MCP
server" is defensible; "built with the NeMo Agent Toolkit agent runtime" is not.
