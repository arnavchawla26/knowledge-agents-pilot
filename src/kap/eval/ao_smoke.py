"""Ask NVIDIA Auto Ontology three natural-language questions through its API and record the SQL,
answer and provenance it returns in reports/auto_ontology_smoke.md."""
from __future__ import annotations

import json

from kap.auto_ontology import ask, status
from kap.config import REPORTS_DIR

QUESTIONS = [
    "How many support cases have severity 1?",
    "How many dispatches were there per product family?",
    "What is the repeat-dispatch rate by product family?",
]


def main() -> int:
    st = status()
    lines = ["# NVIDIA Auto Ontology smoke test", "",
             f"Backend status: `{json.dumps(st)}`", "",
             "Three natural-language questions sent to `POST /api/chat/completions` (SSE) on the backend; the SQL,",
             "answer text and provenance fields are copied verbatim from the `sql` and `result` events.", ""]
    for q in QUESTIONS:
        r = ask(q)
        lines += [f"## {q}", "", f"- latency: {r.get('latency_s')} s, cached: {r.get('cached')}, error: `{r.get('error')}`",
                  f"- steps: {', '.join(str(s) for s in r.get('steps', []))}", "", "SQL:", "", "```sql", (r.get("sql") or "(none)").strip(), "```", "",
                  "Answer:", "", (r.get("answer") or "(none)").strip(), "", "Provenance / other answer fields:", "", "```json",
                  json.dumps(r.get("provenance"), indent=1, default=str)[:3000], "```", ""]
    (REPORTS_DIR / "auto_ontology_smoke.md").write_text("\n".join(lines))
    print("\n".join(lines)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
