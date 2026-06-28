/** DCAToolBox interactive backtester UI (browser). */
import { runBacktest } from "./engine.js";

const $ = (id) => document.getElementById(id);
const dataCache = new Map();
let manifest = null;

/* ------------------------------ formatting ------------------------------ */
const pct = (x) => (x === null || x === undefined || Number.isNaN(x) ? "n/a" : `${(x * 100).toFixed(2)}%`);
const num = (x) => (Number.isNaN(x) ? "n/a" : x.toFixed(3));
const cur = (x) => x.toLocaleString(undefined, { maximumFractionDigits: 0 });
const signed = (x) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;

const METRIC_ROWS = [
  ["total_return", "Total return", pct], ["cagr", "CAGR", pct],
  ["annual_return", "Annualised return", pct], ["annual_volatility", "Annualised volatility", pct],
  ["sharpe", "Sharpe", num], ["sortino", "Sortino", num], ["calmar", "Calmar", num],
  ["max_drawdown", "Max drawdown", pct], ["time_under_water", "Time under water", pct],
  ["xirr", "XIRR (annual)", pct], ["tracking_error", "Tracking error", pct],
  ["information_ratio", "Information ratio", num], ["n_orders", "Number of orders", (x) => `${x}`],
  ["avg_order_amount", "Avg order amount", cur], ["avg_buy_price", "Avg buy price", cur],
  ["avg_cash", "Avg cash", cur], ["cumulative_fees", "Cumulative fees", cur],
  ["invested_capital", "Invested capital", cur], ["final_value", "Final value", cur],
  ["excess_total_return", "Excess total return", pct], ["excess_cagr", "Excess CAGR", pct],
];

/* ------------------------------ data loading ---------------------------- */
async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url} (HTTP ${res.status})`);
  return res.json();
}

const instrument = (t) => manifest.instruments.find((i) => i.ticker === t);
const currentFreq = () => instrument($("ticker").value).frequencies[$("frequency").value];

async function loadManifest() {
  manifest = await fetchJson("data/manifest.json");
  const sel = $("ticker");
  sel.innerHTML = "";
  for (const inst of manifest.instruments) {
    const o = document.createElement("option");
    o.value = inst.ticker;
    o.textContent = inst.label;
    sel.appendChild(o);
  }
  populateFrequencies();
}

function populateFrequencies() {
  const sel = $("frequency");
  const freqs = instrument($("ticker").value).frequencies;
  sel.innerHTML = "";
  for (const key of Object.keys(freqs)) {
    const o = document.createElement("option");
    o.value = key;
    o.textContent = key + (freqs[key].source === "synthetic" ? " (demo)" : "");
    sel.appendChild(o);
  }
}

async function loadData() {
  const f = currentFreq();
  const key = `${$("ticker").value}|${$("frequency").value}`;
  if (!dataCache.has(key)) dataCache.set(key, await fetchJson(`data/${f.file}`));
  return dataCache.get(key);
}

const fileFor = (ticker, freq) => {
  const freqs = instrument(ticker).frequencies;
  return (freqs[freq] || freqs.daily).file;
};
const basketSelection = () =>
  [...document.querySelectorAll("#basket input:checked")].map((c) => c.value);

function populateBasket() {
  const box = $("basket");
  box.innerHTML = "";
  for (const inst of manifest.instruments) {
    const checked = ["SPY", "QQQ"].includes(inst.ticker) ? "checked" : "";
    box.insertAdjacentHTML(
      "beforeend",
      `<label style="display:block;font-size:.85rem"><input type="checkbox" value="${inst.ticker}" ${checked}/> ${inst.ticker}</label>`,
    );
  }
}

/** Return the engine input: a single series, or a {primary, series} market. */
async function loadMarket(name) {
  name = name || $("strategy").value;
  if (name !== "momentum_rotation") return loadData();
  const freq = $("frequency").value;
  const primary = $("ticker").value;
  let tickers = basketSelection();
  if (!tickers.includes(primary)) tickers = [primary, ...tickers];
  const series = {};
  for (const t of tickers) {
    series[t] = { ...(await fetchJson(`data/${fileFor(t, freq)}`)), ticker: t };
  }
  return { primary, series };
}

/* ------------------------------ config build ---------------------------- */
function readConfig() {
  const name = $("strategy").value;
  const strategy = {
    name,
    threshold: parseFloat($("threshold").value),
    allocation: parseFloat($("allocation").value),
    signalMethod: $("signalMethod").value,
    signalWindow: parseInt($("signalWindow").value, 10),
    budgetPolicy: $("budgetPolicy").value,
    period: parseInt($("period").value, 10),
    oversold: parseFloat($("oversold").value),
    window: parseInt($("window").value, 10),
    margin: parseFloat($("margin").value),
    maWindow: parseInt($("maWindow").value, 10),
    lookback: parseInt($("lookback").value, 10),
    absolute: $("absolute").value === "true",
    basket: basketSelection(),
  };
  return {
    start: $("start").value || null,
    end: $("end").value || null,
    periodsPerYear: currentFreq().periodsPerYear,
    monthlyBudget: parseFloat($("budget").value),
    dayOfMonth: parseInt($("day").value, 10),
    initialCash: 0,
    riskFreeRate: 0.02,
    feeRate: parseFloat($("fee").value),
    slippageRate: parseFloat($("slippage").value),
    minFee: 0,
    strategy,
    benchmark: { name: "monthly_dca" },
  };
}

/* ------------------------------ UI helpers ------------------------------ */
function syncRangeLabels() {
  $("thresholdVal").textContent = `${(parseFloat($("threshold").value) * 100).toFixed(1)}%`;
  $("allocationVal").textContent = `${Math.round(parseFloat($("allocation").value) * 100)}%`;
  $("feeVal").textContent = `${(parseFloat($("fee").value) * 100).toFixed(2)}%`;
  $("slippageVal").textContent = `${(parseFloat($("slippage").value) * 100).toFixed(2)}%`;
  $("marginVal").textContent = `${(parseFloat($("margin").value) * 100).toFixed(1)}%`;
}

function syncStrategyFields() {
  const strat = $("strategy").value;
  document.querySelectorAll("[data-strat]").forEach((el) => {
    el.style.display = el.dataset.strat.split(" ").includes(strat) ? "" : "none";
  });
  const windowed = ["drawdown_n_days", "cumulative_return"].includes($("signalMethod").value);
  $("windowField").style.display = strat === "dip_buying" && windowed ? "" : "none";
}

/* ------------------------------ rendering ------------------------------- */
function renderCards(result) {
  const m = result.strategy.metrics;
  const bm = result.benchmark.metrics;
  const trades = result.strategy.trades;
  const dipNotional = trades.filter((t) => t.reason === "dip").reduce((a, t) => a + t.price * t.quantity, 0);
  const allNotional = trades.reduce((a, t) => a + t.price * t.quantity, 0) || 1;
  const dipPct = dipNotional / allNotional;
  const pxDelta = m.avg_buy_price - bm.avg_buy_price; // negative = bought cheaper than DCA
  const cls = (x) => (x >= 0 ? "pos" : "neg");
  $("cards").innerHTML = `
    <div class="card"><div class="v">${pct(m.cagr)}</div><div class="k">CAGR</div></div>
    <div class="card"><div class="v">${pct(m.total_return)}</div><div class="delta ${cls(m.excess_total_return)}">${signed(m.excess_total_return)} vs benchmark</div></div>
    <div class="card"><div class="v">${num(m.sharpe)}</div><div class="k">Sharpe ratio</div></div>
    <div class="card"><div class="v">${pct(m.max_drawdown)}</div><div class="k">Max drawdown</div></div>
    <div class="card"><div class="v">${cur(m.final_value)}</div><div class="k">Final value (invested ${cur(m.invested_capital)})</div></div>
    <div class="card"><div class="v">${pct(dipPct)}</div><div class="k">Capital deployed on dips (rest swept on DCA day)</div></div>
    <div class="card"><div class="v">${pxDelta.toFixed(2)}</div><div class="delta ${cls(-pxDelta)}">avg buy price vs benchmark</div></div>
    <div class="card"><div class="v">${m.n_orders}</div><div class="k">Orders · fees ${cur(m.cumulative_fees)}</div></div>`;
}

function renderMetrics(name, sm, bm) {
  const rows = METRIC_ROWS.map(([k, label, fmt]) =>
    `<tr><td>${label}</td><td>${fmt(sm[k])}</td><td>${fmt(bm[k])}</td></tr>`
  ).join("");
  $("metrics").innerHTML =
    `<thead><tr><th>Metric</th><th>${name}</th><th>monthly_dca</th></tr></thead><tbody>${rows}</tbody>`;
}

const LAYOUT = (title, extra = {}) => ({
  title: { text: title, font: { size: 14 } }, template: "plotly_white",
  margin: { t: 40, r: 16, b: 36, l: 56 }, hovermode: "x unified",
  legend: { orientation: "h", y: 1.12 }, ...extra,
});
const draw = (id, traces, layout) =>
  Plotly.react(id, traces, layout, { displayModeBar: false, responsive: true });

function renderCharts(result) {
  const s = result.strategy;
  const b = result.benchmark;
  const bars = result.bars;
  const dd = s.metrics._series;
  if (!dd || !dd.date.length) return;
  const ddDates = dd.date.slice(1);

  draw("chart-equity", [
    { x: s.history.date, y: s.history.total, name: s.name, mode: "lines" },
    { x: b.history.date, y: b.history.total, name: "monthly_dca", mode: "lines" },
  ], LAYOUT("Portfolio value: strategy vs benchmark", { yaxis: { title: "Value" } }));

  draw("chart-drawdown", [
    { x: ddDates, y: dd.drawdown, name: "drawdown", fill: "tozeroy", line: { color: "#ef4444" } },
  ], LAYOUT("Drawdown", { yaxis: { tickformat: ".0%" } }));

  draw("chart-cash", [
    { x: s.history.date, y: s.history.cash, name: "cash", fill: "tozeroy", line: { color: "#10b981" } },
  ], LAYOUT("Remaining cash"));

  const reasons = [...new Set(s.trades.map((t) => t.reason))];
  const signalTraces = [{ x: bars.dates, y: bars.close, name: "close", mode: "lines", line: { color: "#94a3b8" } }];
  for (const r of reasons) {
    const pts = s.trades.filter((t) => t.reason === r);
    signalTraces.push({ x: pts.map((t) => t.date), y: pts.map((t) => t.price), name: `buy: ${r}`, mode: "markers", marker: { size: 7 } });
  }
  draw("chart-signals", signalTraces, LAYOUT(`${bars.ticker || "Price"} & buy signals`, { yaxis: { title: "Price" } }));

  draw("chart-invested", [
    { x: s.history.date, y: s.history.invested, name: "invested", mode: "lines" },
    { x: s.history.date, y: s.history.total, name: "value", mode: "lines" },
  ], LAYOUT("Invested capital vs value"));

  draw("chart-fees", [
    { x: s.history.date, y: s.history.fees, name: "fees", fill: "tozeroy", line: { color: "#f59e0b" } },
  ], LAYOUT("Cumulative fees"));

  draw("chart-returns", [
    { x: dd.returns, type: "histogram", name: "daily returns", marker: { color: "#2563eb" } },
  ], LAYOUT("Distribution of daily returns", { xaxis: { tickformat: ".1%" } }));

  const purchaseTraces = reasons.map((r) => ({
    x: s.trades.filter((t) => t.reason === r).map((t) => t.price * t.quantity),
    type: "histogram", name: r, opacity: 0.7,
  }));
  draw("chart-purchases", purchaseTraces, LAYOUT("Purchase amounts", { barmode: "overlay" }));
}

/* -------------------------------- run ----------------------------------- */
async function run() {
  syncRangeLabels();
  syncStrategyFields();
  const cfg = readConfig();
  const input = await loadMarket();
  const result = runBacktest(input, cfg);
  if (result.bars.dates.length < 2) {
    $("status").textContent = "Not enough trading days in the selected range — widen Start/End.";
    return;
  }
  renderCards(result);
  renderMetrics(result.strategy.name, result.strategy.metrics, result.benchmark.metrics);
  renderCharts(result);
  const f = currentFreq();
  $("status").innerHTML =
    `<span class="badge">${f.source} · ${$("frequency").value}</span> ${cfg.strategy.name} ` +
    `on ${$("ticker").value}, ${cfg.start} → ${cfg.end} · benchmark: monthly_dca`;
}

async function compareAll() {
  await run(); // keep cards, metrics table and the other charts consistent first
  const cfg = readConfig();
  const names = [
    "momentum_rotation", "dip_buying", "trend_filter", "absolute_momentum",
    "rsi", "moving_average", "monthly_dca",
  ];
  const traces = [];
  for (const name of names) {
    const c = { ...cfg, strategy: { ...cfg.strategy, name } };
    const r = runBacktest(await loadMarket(name), c);
    traces.push({ x: r.strategy.history.date, y: r.strategy.history.total, name, mode: "lines" });
  }
  draw("chart-equity", traces, LAYOUT("All strategies — portfolio value", { yaxis: { title: "Value" } }));
  $("status").textContent = `Comparing ${names.length} strategies on ${$("ticker").value}.`;
}

/* ------------------------------ bootstrap ------------------------------- */
function setDateBounds() {
  const f = currentFreq();
  for (const id of ["start", "end"]) {
    $(id).min = f.start;
    $(id).max = f.end;
  }
  $("start").value = f.start;
  $("end").value = f.end;
}

function debounce(fn, ms) {
  let t;
  return () => { clearTimeout(t); t = setTimeout(fn, ms); };
}

async function main() {
  await loadManifest();
  populateBasket();
  setDateBounds();
  syncStrategyFields();
  const debounced = debounce(run, 150);
  document.querySelector(".panel").addEventListener("input", (e) => {
    if (e.target.id === "ticker") {
      populateFrequencies();
      setDateBounds();
    }
    if (e.target.id === "frequency") setDateBounds();
    if (["strategy", "signalMethod"].includes(e.target.id)) syncStrategyFields();
    debounced();
  });
  $("compareBtn").addEventListener("click", compareAll);
  await run();
}

main().catch((e) => {
  $("status").textContent = `Error: ${e.message}`;
  console.error(e);
});
