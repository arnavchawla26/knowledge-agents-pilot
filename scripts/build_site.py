"""Regenerate site/data/*.json and site/img/* from reports/ and docs/.

The static site under site/ is published on Vercel. Every number it shows comes
from the files this script reads; nothing is typed into the page by hand.
Run from the repository root:  python3 scripts/build_site.py
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
SITE = ROOT / "site"
DATA = SITE / "data"
IMG = SITE / "img"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def num(s: str) -> float | int | str:
    if s is None or s == "":
        return ""
    try:
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        return float(s)
    except ValueError:
        return s


def typed(rows: list[dict[str, str]]) -> list[dict]:
    return [{k: num(v) for k, v in r.items()} for r in rows]


# ----------------------------------------------------------------------------
# A small Markdown-to-HTML converter: headings, paragraphs, lists, tables,
# fenced code, inline code, bold, italics, links. Enough for the docs.
# ----------------------------------------------------------------------------

def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def md_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        if para:
            if len(para) > 1 and all(re.match(r"^[A-Z][a-z]+: ", s) for s in para):
                out.append("<p>" + "<br>".join(inline(s.strip()) for s in para) + "</p>")
            else:
                out.append("<p>" + inline(" ".join(s.strip() for s in para)) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_para()
            j = i + 1
            code: list[str] = []
            while j < len(lines) and not lines[j].startswith("```"):
                code.append(lines[j])
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1]):
            flush_para()
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            j = i + 2
            body: list[list[str]] = []
            while j < len(lines) and lines[j].startswith("|"):
                body.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append('<div class="tablewrap"><table><thead><tr>' + "".join(f"<th>{inline(h)}</th>" for h in header) + "</tr></thead><tbody>")
            for r in body:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table></div>")
            i = j
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            flush_para()
            ordered = m.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            j = i
            while j < len(lines):
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[j])
                if mm:
                    items.append(mm.group(3))
                    j += 1
                elif lines[j].startswith("  ") and items:
                    items[-1] += " " + lines[j].strip()
                    j += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>")
            i = j
            continue
        if line.startswith("!["):
            i += 1
            continue
        if not line.strip():
            flush_para()
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para()
    return "\n".join(out)


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def readme_intro() -> str:
    text = (ROOT / "README.md").read_text()
    body = text.split("\n", 1)[1].strip()
    first = body.split("\n\n", 1)[0]
    return " ".join(s.strip() for s in first.splitlines())


PROGRAM = ROOT / "program"
SCREENSHOTS = ("auto_ontology_data_catalog.png", "auto_ontology_terms.png", "auto_ontology_chat.png")


def program_index() -> list[dict]:
    """The file table from program/README.md plus every file in program/."""
    text = (PROGRAM / "README.md").read_text()
    described: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("|") and "`" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2:
                for name in re.findall(r"`([^`]+)`", cells[0]):
                    described[Path(name).name] = cells[1]
    out = []
    for path in sorted(PROGRAM.glob("*.md")):
        out.append({"file": path.name, "what": described.get(path.name, ""), "bytes": path.stat().st_size})
    return out


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)

    eval_summary = typed(read_csv(REPORTS / "eval_summary.csv"))
    eval_results = read_csv(REPORTS / "eval_results.csv")
    agent_summary = typed(read_csv(REPORTS / "agent_eval_summary.csv"))
    agent_eval = read_csv(REPORTS / "agent_eval.csv")
    cost = typed(read_csv(REPORTS / "cost.csv"))
    search_eval = read_csv(REPORTS / "search_eval.csv")
    search_summary = json.loads((REPORTS / "search_eval_summary.json").read_text())
    ao_rerun = read_csv(REPORTS / "auto_ontology_rerun.csv")

    # Per question x model x arm: strict score, so the page can show the hard ten.
    per_question = []
    for r in eval_results:
        per_question.append({
            "question_id": r["question_id"],
            "difficulty": r["difficulty"],
            "model": r["model"],
            "arm": r["arm"],
            "strict": num(r["strict"]),
            "lenient": num(r["lenient"]),
            "error": r.get("error", ""),
            "attempts": num(r["attempts"]),
            "latency_s": num(r["latency_s"]),
        })

    # Hard-ten delta per model: ontology arm minus control arm, strict.
    hard = {}
    for r in per_question:
        if r["difficulty"] != "hard":
            continue
        h = hard.setdefault(r["model"], {"control": 0, "ontology": 0, "n": set()})
        h[r["arm"]] += int(r["strict"] or 0)
        h["n"].add(r["question_id"])
    hard_delta = [{"model": m, "control": v["control"], "ontology": v["ontology"], "n": len(v["n"]), "delta": v["ontology"] - v["control"]} for m, v in sorted(hard.items())]

    agents = []
    for r in agent_eval:
        agents.append({
            "agent": r["agent"], "scenario": r["scenario"], "model": r["model"], "expected": r["expected"], "actual": r["actual"],
            "pass": num(r["pass"]), "detail": r["detail"], "tool_calls": r["tool_calls"], "llm_calls": num(r["llm_calls"]),
            "tokens": num(r["tokens"]), "cost_usd": num(r["cost_usd"]), "latency_s": num(r["latency_s"]),
        })

    search_rows = [{"query": r["query"], "expected": r["expected"], "bm25_rank": num(r["bm25_rank"]), "dense_rank": num(r["dense_rank"]), "hybrid_rank": num(r["hybrid_rank"]), "bm25_top3": r["bm25_top3"], "dense_top3": r["dense_top3"], "hybrid_top3": r["hybrid_top3"]} for r in search_eval]

    ao_rows = [{"question_id": r["question_id"], "variant": r["variant"], "layer": r["layer"], "strict": num(r["strict"]), "lenient": num(r["lenient"]), "latency_s": num(r["latency_s"]), "question": r["question"], "gold_rows": num(r["gold_rows"]), "pred_rows": num(r["pred_rows"])} for r in ao_rerun]
    ao_counts = {}
    for r in ao_rows:
        key = f"{r['layer']}, {r['variant']}"
        c = ao_counts.setdefault(key, {"layer": r["layer"], "variant": r["variant"], "n": 0, "strict": 0, "latencies": []})
        c["n"] += 1
        c["strict"] += int(r["strict"] or 0)
        c["latencies"].append(float(r["latency_s"]))
    ao_summary = []
    for c in ao_counts.values():
        lat = sorted(c["latencies"])
        ao_summary.append({"layer": c["layer"], "variant": c["variant"], "n": c["n"], "strict": c["strict"], "latency_min": lat[0], "latency_max": lat[-1], "latency_median": lat[len(lat) // 2]})

    drafts = sorted((REPORTS / "fleet" / "drafts").glob("fleet_report_*.md"))
    latest_draft = drafts[-1]
    draft_md = latest_draft.read_text()
    draft_md = re.sub(r"<!--.*?-->\s*", "", draft_md, count=1, flags=re.S)

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "intro": readme_intro(),
        "text_to_sql": {"summary": eval_summary, "per_question": per_question, "hard_delta": hard_delta},
        "agents": {"summary": agent_summary, "scenarios": agents},
        "cost": cost,
        "search": {"summary": search_summary, "rows": search_rows},
        "auto_ontology": {"rows": ao_rows, "summary": ao_summary},
        "screenshots": [{"file": s, "caption": s.replace("auto_ontology_", "").replace(".png", "").replace("_", " ")} for s in SCREENSHOTS],
        "memo_file": "program/MEMO_case_triage.md",
        "draft_file": str(latest_draft.relative_to(ROOT)),
        "program": program_index(),
    }
    (DATA / "site.json").write_text(json.dumps(out, separators=(",", ":")))
    (DATA / "memo.html").write_text(md_to_html((PROGRAM / "MEMO_case_triage.md").read_text()))
    (DATA / "draft.html").write_text(md_to_html(draft_md))

    for stale in IMG.glob("*.png"):
        stale.unlink()
    for s in SCREENSHOTS:
        shutil.copyfile(REPORTS / "screenshots" / s, IMG / s)
    print(f"wrote {DATA / 'site.json'} ({(DATA / 'site.json').stat().st_size} bytes), memo.html, draft.html, {len(list(IMG.iterdir()))} images")


if __name__ == "__main__":
    main()
