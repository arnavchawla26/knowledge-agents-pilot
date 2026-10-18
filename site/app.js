/* knowledge-agents-pilot results page. Reads data/site.json, data/memo.html and
   data/draft.html written by scripts/build_site.py from reports/ and program/. */
(async function () {
  "use strict";
  const S = window.Site;
  const { fmt, esc, table, tiles, setHTML, setText } = S;

  let D;
  try {
    D = await S.loadJSON("data/site.json");
  } catch (e) {
    setHTML("t2s-tiles", '<p class="note">Could not load data/site.json: ' + esc(e.message) + "</p>");
    return;
  }
  setText("commit", D.commit || "unknown");
  setText("generated", D.generated_at || "");
  if (D.intro) setText("intro", D.intro.replace(/^Project \d of \d:\s*/, "").replace(/^\w/, (c) => c.toUpperCase()));

  const MODELS = ["nemotron", "llama", "claude"];
  const MODEL_LABEL = { nemotron: "Nemotron (NIM)", llama: "Llama (NIM)", claude: "Claude" };
  const ARM_LABEL = { control: "schema only", ontology: "schema + glossary" };
  const AGENT_LABEL = { case_triage: "case triage", dispatch_readiness: "dispatch readiness", fleet_health_reporter: "fleet health reporter" };
  const modelKey = (s) => (s.includes("nemotron") ? "nemotron" : s.includes("llama") ? "llama" : s.includes("claude") ? "claude" : s);

  /* ---------------- Text-to-SQL ---------------- */
  const T = D.text_to_sql;
  const sum = {};
  for (const r of T.summary) sum[r.model + "/" + r.arm] = r;
  const hardDelta = {};
  for (const r of T.hard_delta) hardDelta[r.model] = r;
  setHTML("t2s-tiles", tiles(MODELS.map((m) => ({
    v: `${hardDelta[m].control}/${hardDelta[m].n} to ${hardDelta[m].ontology}/${hardDelta[m].n}`,
    l: `${MODEL_LABEL[m]} on the hard ten`,
    s: `+${hardDelta[m].delta} with the glossary`,
  }))));
  function armChart(el, key, label) {
    return new Chart(el, {
      type: "bar",
      data: {
        labels: MODELS.map((m) => MODEL_LABEL[m]),
        datasets: ["control", "ontology"].map((a, i) => S.barDataset(ARM_LABEL[a], MODELS.map((m) => sum[m + "/" + a][key]), i, { maxBarThickness: 56 })),
      },
      options: S.baseOptions({
        plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt.pct(c.parsed.y, 0)}` } } },
        scales: { y: { max: 1, ticks: { callback: (v) => fmt.pct(v, 0) }, title: { display: true, text: label, color: S.cssVar("--ink-2") } } },
      }),
    });
  }
  S.chart("c-t2s-all", (el) => armChart(el, "strict_accuracy", "execution match, 30 questions"));
  S.chart("c-t2s-hard", (el) => armChart(el, "hard", "execution match, hard ten"));
  const matrixRows = [];
  for (const m of MODELS) for (const a of ["control", "ontology"]) matrixRows.push(Object.assign({ model: MODEL_LABEL[m], arm: ARM_LABEL[a] }, sum[m + "/" + a]));
  setHTML("t2s-table", table([
    { key: "model", label: "Model" },
    { key: "arm", label: "Arm" },
    { key: "strict_accuracy", label: "All 30", fmt: (v) => fmt.pct(v, 1), cls: "n" },
    { key: "easy", label: "Easy", fmt: (v) => fmt.pct(v, 0), cls: "n" },
    { key: "medium", label: "Medium", fmt: (v) => fmt.pct(v, 0), cls: "n" },
    { key: "hard", label: "Hard 10", fmt: (v) => fmt.pct(v, 0), cls: "n" },
    { key: "sql_errors", label: "SQL errors", cls: "n" },
    { key: "mean_latency_s", label: "Mean model latency", fmt: (v) => fmt.num(v, 1) + " s", cls: "n" },
    { key: (r) => `${fmt.int(r.total_input_tokens)} / ${fmt.int(r.total_output_tokens)}`, label: "Tokens in / out", cls: "n" },
    { key: "total_cost_usd", label: "Cost", fmt: (v) => fmt.usd(v, 2), cls: "n" },
  ], matrixRows));
  const hardQ = {};
  for (const r of T.per_question) {
    if (r.difficulty !== "hard") continue;
    hardQ[r.question_id] = hardQ[r.question_id] || { question_id: r.question_id };
    hardQ[r.question_id][r.model + "/" + r.arm] = r;
  }
  const cell = (r) => (!r ? "" : Number(r.strict) ? '<span class="pass">pass</span>' : r.error ? '<span class="fail">error</span>' : '<span class="fail">wrong</span>');
  setHTML("t2s-hard-table", table([{ key: "question_id", label: "Question" }].concat(
    MODELS.flatMap((m) => ["control", "ontology"].map((a) => ({ key: (r) => cell(r[m + "/" + a]), label: `${MODEL_LABEL[m].replace(" (NIM)", "")} ${a === "control" ? "C" : "O"}`, raw: true })))
  ), Object.values(hardQ).sort((a, b) => a.question_id.localeCompare(b.question_id))));

  /* ---------------- Agents ---------------- */
  const A = D.agents;
  const agentKeys = ["case_triage", "dispatch_readiness", "fleet_health_reporter"];
  const asum = {};
  for (const r of A.summary) asum[r.agent + "/" + r.model] = r;
  S.chart("c-agents", (el) => new Chart(el, {
    type: "bar",
    data: {
      labels: agentKeys.map((a) => AGENT_LABEL[a]),
      datasets: MODELS.map((m, i) => S.barDataset(MODEL_LABEL[m], agentKeys.map((a) => (asum[a + "/" + m] ? asum[a + "/" + m].pass_rate : null)), i, { maxBarThickness: 44 })),
    },
    options: S.baseOptions({
      plugins: { tooltip: { callbacks: { label: (c) => { const r = asum[agentKeys[c.dataIndex] + "/" + MODELS[c.datasetIndex]]; return r ? `${c.dataset.label}: ${Math.round(r.pass_rate * r.n)}/${r.n}` : `${c.dataset.label}: not run`; } } } },
      scales: { y: { max: 1, ticks: { callback: (v) => fmt.pct(v, 0) } } },
    }),
  }));
  const agentRows = [];
  for (const a of agentKeys) for (const m of MODELS) {
    const r = asum[a + "/" + m];
    agentRows.push(r ? Object.assign({ agentLabel: AGENT_LABEL[a], modelName: MODEL_LABEL[m] }, r) : { agentLabel: AGENT_LABEL[a], modelName: MODEL_LABEL[m], n: "", pass_rate: null, mean_tokens: "", mean_cost_usd: "", mean_latency_s: "" });
  }
  setHTML("agents-table", table([
    { key: "agentLabel", label: "Agent" },
    { key: "modelName", label: "Model" },
    { key: (r) => (r.pass_rate == null ? "not run" : `${Math.round(r.pass_rate * r.n)}/${r.n}`), label: "Pass", cls: "n" },
    { key: "mean_tokens", label: "Tokens / task", fmt: (v) => (v === "" ? "" : fmt.int(v)), cls: "n" },
    { key: "mean_cost_usd", label: "$ / task", fmt: (v) => (v === "" ? "" : fmt.usd(v, 4)), cls: "n" },
    { key: "mean_latency_s", label: "Latency / task", fmt: (v) => (v === "" ? "" : fmt.num(v, 1) + " s"), cls: "n" },
  ], agentRows));
  setHTML("agents-detail-table", table([
    { key: "agent", label: "Agent", fmt: (v) => AGENT_LABEL[v] || v },
    { key: "scenario", label: "Scenario" },
    { key: "model", label: "Model", fmt: (v) => MODEL_LABEL[v] || v },
    { key: "expected", label: "Expected" },
    { key: "actual", label: "Actual" },
    { key: "pass", label: "Pass", raw: true, fmt: (v) => (Number(v) ? '<span class="pass">pass</span>' : '<span class="fail">fail</span>') },
    { key: "detail", label: "Detail", cls: "text" },
    { key: "tokens", label: "Tokens", fmt: fmt.int, cls: "n" },
    { key: "latency_s", label: "Latency", fmt: (v) => fmt.num(v, 1) + " s", cls: "n" },
  ], A.scenarios));

  /* ---------------- Cost ---------------- */
  const costBy = {};
  for (const r of D.cost) costBy[r.agent + "/" + modelKey(r.model)] = r;
  function costChart(el, key, fmtv, label) {
    return new Chart(el, {
      type: "bar",
      data: {
        labels: agentKeys.map((a) => AGENT_LABEL[a]),
        datasets: MODELS.map((m, i) => S.barDataset(MODEL_LABEL[m], agentKeys.map((a) => (costBy[a + "/" + m] ? costBy[a + "/" + m][key] : null)), i, { maxBarThickness: 44 })),
      },
      options: S.baseOptions({
        plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y == null ? "not run" : fmtv(c.parsed.y)}` } } },
        scales: { y: { ticks: { callback: (v) => fmtv(v) }, title: { display: true, text: label, color: S.cssVar("--ink-2") } } },
      }),
    });
  }
  S.chart("c-tokens", (el) => costChart(el, "mean_tokens", (v) => fmt.int(v), "mean tokens per task"));
  S.chart("c-dollars", (el) => costChart(el, "mean_cost_usd", (v) => fmt.usd(v, 3), "mean dollars per task"));
  setHTML("cost-table", table([
    { key: "agent", label: "Agent", fmt: (v) => AGENT_LABEL[v] || v },
    { key: "model", label: "Model id" },
    { key: "tasks", label: "Tasks", cls: "n" },
    { key: "mean_tokens_in", label: "Tokens in", fmt: fmt.int, cls: "n" },
    { key: "mean_tokens_out", label: "Tokens out", fmt: fmt.int, cls: "n" },
    { key: "mean_tokens", label: "Tokens", fmt: fmt.int, cls: "n" },
    { key: "mean_llm_calls", label: "Model calls", fmt: (v) => fmt.num(v, 2), cls: "n" },
    { key: "mean_tool_calls", label: "Tool calls", fmt: (v) => fmt.num(v, 2), cls: "n" },
    { key: "mean_cost_usd", label: "$ / task", fmt: (v) => fmt.usd(v, 4), cls: "n" },
    { key: "total_cost_usd", label: "$ total", fmt: (v) => fmt.usd(v, 4), cls: "n" },
    { key: "mean_llm_latency_s", label: "Model latency", fmt: (v) => fmt.num(v, 1) + " s", cls: "n" },
  ], D.cost));

  /* ---------------- Search ---------------- */
  const SE = D.search.summary;
  const modes = ["bm25", "dense", "hybrid"];
  const MODE_LABEL = { bm25: "BM25", dense: "dense (NeMo Retriever)", hybrid: "hybrid (RRF, k=60)" };
  S.chart("c-search", (el) => new Chart(el, {
    type: "bar",
    data: {
      labels: ["hit@1", "hit@3", "MRR"],
      datasets: modes.map((m, i) => S.barDataset(MODE_LABEL[m], [SE[m].hit_at_1, SE[m].hit_at_3, SE[m].mrr], i, { maxBarThickness: 44 })),
    },
    options: S.baseOptions({
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt.fixed(c.parsed.y, 3)}` } } },
      scales: { y: { max: 1, ticks: { callback: (v) => fmt.fixed(v, 1) } } },
    }),
  }));
  setHTML("search-table", table([
    { key: "mode", label: "Mode", fmt: (v) => MODE_LABEL[v] },
    { key: (r) => SE[r.mode].hit_at_1, label: "hit@1", fmt: (v) => fmt.fixed(v, 3), cls: "n" },
    { key: (r) => SE[r.mode].hit_at_3, label: "hit@3", fmt: (v) => fmt.fixed(v, 3), cls: "n" },
    { key: (r) => SE[r.mode].mrr, label: "MRR", fmt: (v) => fmt.fixed(v, 3), cls: "n" },
    { key: (r) => SE[r.mode].n, label: "Queries", cls: "n" },
  ], modes.map((m) => ({ mode: m }))));
  const rank = (v) => (v === "" || v == null ? '<span class="fail">miss</span>' : Number(v) === 1 ? '<span class="pass">1</span>' : String(v));
  setHTML("search-detail-table", table([
    { key: "query", label: "Query", cls: "text" },
    { key: "expected", label: "Expected" },
    { key: "bm25_rank", label: "BM25 rank", raw: true, fmt: rank, cls: "n" },
    { key: "dense_rank", label: "Dense rank", raw: true, fmt: rank, cls: "n" },
    { key: "hybrid_rank", label: "Hybrid rank", raw: true, fmt: rank, cls: "n" },
    { key: "hybrid_top3", label: "Hybrid top 3", fmt: (v) => v.replace(/;/g, ", ") },
  ], D.search.rows));

  /* ---------------- Auto Ontology ---------------- */
  const AO = D.auto_ontology;
  setHTML("ao-summary-table", table([
    { key: "layer", label: "Layer", fmt: (v) => (v === "v0" ? "v0 (as compiled)" : v) },
    { key: "variant", label: "Wording" },
    { key: (r) => `${r.strict}/${r.n}`, label: "Strict pass", cls: "n" },
    { key: (r) => `${fmt.num(r.latency_min, 0)} to ${fmt.num(r.latency_max, 0)} s, median ${fmt.num(r.latency_median, 0)} s`, label: "Latency on the free tier" },
  ], AO.summary));
  setHTML("ao-table", table([
    { key: "question_id", label: "Id" },
    { key: "variant", label: "Wording" },
    { key: "layer", label: "Layer" },
    { key: "strict", label: "Strict", raw: true, fmt: (v) => (Number(v) ? '<span class="pass">pass</span>' : '<span class="fail">fail</span>') },
    { key: (r) => `${r.pred_rows} / ${r.gold_rows}`, label: "Rows / gold", cls: "n" },
    { key: "latency_s", label: "Latency", fmt: (v) => fmt.num(v, 0) + " s", cls: "n" },
    { key: "question", label: "Question", cls: "text" },
  ], AO.rows));

  /* ---------------- Screenshots ---------------- */
  setHTML("screens-list", D.screenshots.map((s) => `<figure><img src="img/${esc(s.file)}" alt="Auto Ontology ${esc(s.caption)} screenshot"><figcaption>reports/screenshots/${esc(s.file)}</figcaption></figure>`).join(""));

  /* ---------------- Memo and draft ---------------- */
  try {
    setHTML("memo-doc", await S.loadText("data/memo.html"));
  } catch (e) {
    setHTML("memo-doc", '<p class="note">Could not load the memo: ' + esc(e.message) + "</p>");
  }
  setText("draft-sub", `${D.draft_file}, as the fleet health reporter agent wrote it. It was never published: publishing needs --approve --approver <name>, and this draft did not get one. The figures are the agent's reading of the sibling project's fleet-risk tables over telemetry that ends 2026-06-30.`);
  try {
    setHTML("draft-doc", '<span class="draft-label">DRAFT, NOT PUBLISHED</span>' + (await S.loadText("data/draft.html")));
  } catch (e) {
    setHTML("draft-doc", '<p class="note">Could not load the draft: ' + esc(e.message) + "</p>");
  }

  /* ---------------- Program folder ---------------- */
  setHTML("program-list", D.program.map((p) => `<li><a href="https://github.com/arnavchawla26/knowledge-agents-pilot/blob/main/program/${esc(p.file)}">program/${esc(p.file)}</a><span>${esc(p.what || "index of this folder")}</span></li>`).join(""));
})();
