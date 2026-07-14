/** DCAToolBox interactive backtester UI (browser). */
import { runBacktest, currentSignal } from "./engine.js";

const $ = (id) => document.getElementById(id);
const dataCache = new Map();
let manifest = null;

// Categorical series palette (validated: worst adjacent CVD ΔE 25, all slots in
// the lightness band; the sub-3:1 slots get relief from the legend, the unified
// hover and the exact-value ranking chips). Colors are assigned to instruments
// in manifest order and follow the ticker, never its rank, so a basket change
// never repaints the survivors.
const PALETTE = ["#2563eb", "#1baf7a", "#eb6834", "#4a3aa7", "#eda100", "#e34948", "#e87ba4", "#008300"];
const tickerColors = {};
const colorOf = (t) => tickerColors[t] || "#64748b";

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
  manifest.instruments.forEach((inst, i) => (tickerColors[inst.ticker] = PALETTE[i % PALETTE.length]));
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

async function fetchData(file) {
  // Cache by filename (unique per ticker+frequency) so the rotation basket and
  // single-series paths share one cache and never refetch on every keystroke.
  if (!dataCache.has(file)) dataCache.set(file, await fetchJson(`data/${file}`));
  return dataCache.get(file);
}

async function loadData() {
  return { ...(await fetchData(currentFreq().file)), ticker: $("ticker").value };
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
  if (!["momentum_rotation", "adaptive_momentum"].includes(name)) return loadData();
  const freq = $("frequency").value;
  const primary = $("ticker").value;
  let tickers = basketSelection();
  if (!tickers.includes(primary)) tickers = [primary, ...tickers];
  const series = {};
  for (const t of tickers) {
    series[t] = { ...(await fetchData(fileFor(t, freq))), ticker: t };
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
    rotate: $("rotate").value === "true",
    basket: basketSelection(),
    // Champion parameters for adaptive_momentum (validated out-of-sample).
    checkEvery: 21,
    horizons: [21, 63, 126, 252],
    recalibrateEvery: 21,
    trainWindow: 756,
    hiThreshold: 0.05,
    loThreshold: 0,
    dipBoost: 0,
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
const niceDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("fr-FR", { year: "numeric", month: "long", day: "numeric" });
};

// Le héros : l'instruction complète du mois (quoi / combien / quand),
// composée en français depuis le signal STRUCTURÉ du moteur backtesté.
function renderSignal(sig, cfg, preset) {
  const el = $("signal");
  if (!sig.asOf) {
    el.innerHTML = `<div class="sig-action">Pas de données</div>`;
    return;
  }
  // Prochain jour d'action : le jour DCA à venir, décalé au jour ouvré.
  const day = cfg.dayOfMonth;
  const now = new Date();
  let next = new Date(now.getFullYear(), now.getMonth(), day);
  if (next <= now) next = new Date(now.getFullYear(), now.getMonth() + 1, day);
  while ([0, 6].includes(next.getDay())) next.setDate(next.getDate() + 1);
  const nextTxt = next.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

  const budget = `${cur(cfg.monthlyBudget)} ${preset.currency}`;
  const leader = sig.rows.length && sig.fired ? sig.rows[0].label : null;
  let action;
  let amount;
  let detail;
  if (!sig.rows.length) {
    action = `Achetez ${cfg.strategy.basket[0]}`;
    amount = budget;
    detail = "Pas encore assez d'historique pour départager — on investit comme un DCA classique.";
  } else if (!sig.fired) {
    action = "N'achetez rien ce mois-ci";
    amount = `gardez vos ${budget} de côté`;
    detail = `Tout baisse en ce moment (le meilleur fait ${sig.rows[0].value}). Le signal préfère attendre : ce cash sera investi d'un coup quand ça repartira.`;
  } else if (sig.tier === "high") {
    action = `Achetez ${leader}`;
    amount = `${budget} + tout le cash mis de côté les mois précédents`;
    detail = `${leader} (${preset.names[leader] || leader}) est en forte tendance (${sig.rows[0].value}). Signal fort : on investit tout ce qui est disponible.`;
  } else {
    action = `Achetez ${leader}`;
    amount = budget;
    detail = `${leader} (${preset.names[leader] || leader}) est le plus fort du moment (${sig.rows[0].value}).`;
  }
  const cls = sig.fired === false ? "wait" : "go";
  const ranking = sig.rows.length
    ? `<div class="sig-rank">${sig.rows
        .map((r) => `<span class="sig-chip ${r.picked ? "picked" : ""}">${r.label} : ${r.value}</span>`)
        .join("")}</div>`
    : "";
  el.innerHTML = `
    <div class="sig-head">
      <span class="sig-dot ${cls}"></span>
      <div>
        <div class="sig-label">Ce mois-ci · données au ${niceDate(sig.asOf)}</div>
        <div class="sig-action ${cls}">${action}</div>
      </div>
    </div>
    <ul class="sig-plan">
      <li>💶 <b>Montant :</b> ${amount}</li>
      <li>📅 <b>Quand :</b> ${sig.fired === false ? "rien à faire ce mois-ci" : `le <b>${nextTxt}</b> — ou n'importe quel jour où tu as du cash (rouvre cette page ce jour-là)`}</li>
    </ul>
    <p class="sig-detail">${detail}</p>
    ${ranking}`;
}

function renderCards(result) {
  const m = result.strategy.metrics;
  const bm = result.benchmark.metrics;
  const trades = result.strategy.trades.filter((t) => t.side !== "sell");
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
  legend: { orientation: "h", y: 1.12 },
  // dragmode:false lets the page scroll over charts on touch devices (iOS)
  // instead of the chart capturing the gesture as a pan/zoom.
  dragmode: false, ...extra,
});
// Size charts explicitly from their container and disable Plotly's built-in
// responsive listener. On iOS, scrolling shows/hides the address bar, firing a
// stream of height-only `resize` events; Plotly's responsive mode would re-lay
// out all eight charts on each one, causing jank and transient overlaps
// ("frames slipping under each other"). We instead relayout only on real width
// changes (see the resize handler in main()).
const PLOT_CONFIG = { displayModeBar: false, responsive: false, scrollZoom: false };
const draw = (id, traces, layout) => {
  const el = $(id);
  const r = el.getBoundingClientRect();
  // A chart inside a hidden tab measures 0×0; draw at a sane fallback size and
  // let the tab-switch resizeCharts() refit it once it becomes visible.
  const width = Math.round(r.width) || Math.min(window.innerWidth - 40, 720);
  const sized = { ...layout, autosize: false, width, height: Math.round(r.height) || 300 };
  Plotly.react(el, traces, sized, PLOT_CONFIG);
};

// Re-fit every already-plotted VISIBLE chart to its container's current box.
function resizeCharts() {
  for (const el of document.querySelectorAll(".chart")) {
    if (!el.data) continue; // not yet plotted
    const r = el.getBoundingClientRect();
    if (r.width < 10) continue; // hidden tab — refit when it becomes visible
    Plotly.relayout(el, { width: Math.round(r.width), height: Math.round(r.height) || 300 });
  }
}

function showTab(name) {
  for (const b of document.querySelectorAll(".tab")) {
    b.classList.toggle("active", b.dataset.tab === name);
    b.setAttribute("aria-selected", String(b.dataset.tab === name));
  }
  $("tab-signal").hidden = name !== "signal";
  $("tab-backtest").hidden = name !== "backtest";
  resizeCharts(); // charts drawn while their tab was hidden need a real size
}

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

  // Group buy markers by (ticker, reason) so multi-asset rotation buys are
  // labelled with the asset that was actually bought, not lumped on the primary.
  const buysOnly = s.trades.filter((t) => t.side !== "sell");
  const sellsOnly = s.trades.filter((t) => t.side === "sell");
  const groups = [...new Set(buysOnly.map((t) => `${t.ticker}|${t.reason}`))];
  const signalTraces = [
    { x: bars.dates, y: bars.close, name: `${bars.ticker} close`, mode: "lines", line: { color: "#94a3b8" } },
  ];
  for (const g of groups) {
    const [tk, reason] = g.split("|");
    const pts = buysOnly.filter((t) => t.ticker === tk && t.reason === reason);
    const label = tk === bars.ticker ? `buy: ${reason}` : `buy ${tk}: ${reason}`;
    signalTraces.push({ x: pts.map((t) => t.date), y: pts.map((t) => t.price), name: label, mode: "markers", marker: { size: 7 } });
  }
  if (sellsOnly.length) {
    signalTraces.push({
      x: sellsOnly.map((t) => t.date), y: sellsOnly.map((t) => t.price), name: "sell (rotation)",
      mode: "markers", marker: { size: 8, symbol: "triangle-down", color: "#ef4444" },
    });
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

  const reasons = [...new Set(buysOnly.map((t) => t.reason))];
  const purchaseTraces = reasons.map((r) => ({
    x: buysOnly.filter((t) => t.reason === r).map((t) => t.price * t.quantity),
    type: "histogram", name: r, opacity: 0.7,
  }));
  draw("chart-purchases", purchaseTraces, LAYOUT("Purchase amounts", { barmode: "overlay" }));
}

/* ---------------------------- signal tab -------------------------------- */

/** Tickers the current signal actually looks at. */
function signalTickers(cfg, aligned) {
  if (!["momentum_rotation", "adaptive_momentum"].includes(cfg.strategy.name))
    return [aligned.primary];
  const basket = cfg.strategy.basket && cfg.strategy.basket.length ? cfg.strategy.basket : Object.keys(aligned.bars);
  return basket.filter((t) => aligned.bars[t]);
}

/** The race the signal ranks: each candidate over the look-back, indexed to 0%. */
function renderRace(result, cfg, sig) {
  const aligned = result.aligned;
  const dates = aligned.dates;
  const n = dates.length;
  const momentum = ["momentum_rotation", "absolute_momentum", "adaptive_momentum"].includes(
    cfg.strategy.name,
  );
  const lb = momentum ? cfg.strategy.lookback || 126 : 126;
  const i0 = Math.max(0, n - 1 - lb);
  const tickers = signalTickers(cfg, aligned);
  const picked = sig.rows.find((r) => r.picked)?.label;

  const traces = [];
  const annotations = [];
  for (const t of tickers) {
    const close = aligned.bars[t].close;
    const base = close[i0];
    if (!(base > 0)) continue; // not enough history to race yet
    const y = [];
    for (let i = i0; i < n; i++) y.push(close[i] / base - 1);
    const isPick = t === picked;
    traces.push({
      x: dates.slice(i0), y, name: t, mode: "lines",
      line: { color: colorOf(t), width: isPick ? 3 : 2 },
    });
    if (isPick || tickers.length === 1) {
      annotations.push({
        x: dates[n - 1], y: y[y.length - 1], xanchor: "left", showarrow: false,
        text: `<b>${t} ${signed(y[y.length - 1])}</b>`, font: { size: 12, color: "#0f172a" },
      });
    }
  }
  const title = momentum
    ? `La course sur ${Math.round(lb / 21)} mois`
    : `${aligned.primary} — ${lb} derniers jours de bourse (base 0 %)`;
  draw("chart-race", traces, LAYOUT(title, {
    yaxis: { tickformat: ".0%" }, margin: { t: 40, r: 90, b: 56, l: 48 }, annotations,
  }));
}

/** Ce que le signal a décidé chacun des 12 derniers mois. */
function renderHistory(result, cfg, preset) {
  const months = [...new Set(result.bars.dates.map((d) => d.slice(0, 7)))].slice(-12).reverse();
  const byMonth = new Map(months.map((m) => [m, []]));
  for (const t of result.strategy.trades) {
    const m = t.date.slice(0, 7);
    if (byMonth.has(m)) byMonth.get(m).push(t);
  }
  const label = (m) =>
    new Date(m + "-01T00:00:00").toLocaleDateString("fr-FR", { year: "numeric", month: "short" });
  const rows = months.map((m) => {
    const trades = byMonth.get(m);
    const buys = trades.filter((t) => t.side !== "sell");
    const sells = trades.filter((t) => t.side === "sell");
    const amount = buys.reduce((a, t) => a + t.price * t.quantity, 0);
    let what;
    if (!trades.length) what = "Rien acheté — tout baissait, resté en cash";
    else if (!buys.length && sells.length) what = "Tout vendu — passé en cash";
    else {
      const tk = [...new Set(buys.map((t) => t.ticker))].join(", ");
      const rotated = sells.length
        ? ` (vendu ${[...new Set(sells.map((t) => t.ticker))].join(", ")})`
        : "";
      what = `Acheté <b style="color:${colorOf(buys[0]?.ticker)}">${tk}</b>${rotated}`;
    }
    const amt = amount ? `${cur(amount)} ${preset.currency}` : "—";
    return `<tr><td>${label(m)}</td><td style="text-align:left">${what}</td><td>${amt}</td></tr>`;
  }).join("");
  $("history").innerHTML =
    `<thead><tr><th>Mois</th><th style="text-align:left">Décision</th><th>Montant</th></tr></thead><tbody>${rows}</tbody>`;
}

/* --------------------- signal tab: presets & cards ---------------------- */

// The home tab is deliberately a PRODUCT, not a lab: one strategy (momentum
// rotation, accumulation mode -- never sells), one choice (the market), one
// decision a month. Everything tweakable lives in the Backtest tab.
const SIGNAL_PRESETS = {
  us: {
    key: "us", label: "\u{1F1FA}\u{1F1F8} USA ($)", currency: "$",
    primary: "SPY", basket: ["SPY", "QQQ"],
    names: { SPY: "l'ETF S&P 500", QQQ: "l'ETF Nasdaq-100" },
    broker: "un compte-titres (ou un courtier type IBKR/Trade Republic)",
  },
  fr: {
    key: "fr", label: "\u{1F1EB}\u{1F1F7} France (\u20AC / PEA)", currency: "\u20AC",
    primary: "ESE.PA", basket: ["ESE.PA", "PUST.PA"],
    names: { "ESE.PA": "l'ETF S&P 500 de BNP, \u00e9ligible PEA", "PUST.PA": "l'ETF Nasdaq-100 d'Amundi, \u00e9ligible PEA" },
    broker: "un PEA (Bourse Direct, Fortuneo, BoursoBank\u2026)",
  },
};
let signalMarket = "fr";
// ⚡ ON = the research champion (walk-forward multi-horizon momentum with
// conviction sizing, validated out-of-sample with fees). OFF = the simple
// fixed 6-month rotation. Both accumulate — never sell (selling lost 16-30%
// vs DCA out-of-sample in every tested market).
const signalTurbo = true; // the validated champion is the only home strategy

function signalConfig(preset) {
  const f = instrument(preset.primary).frequencies.daily;
  const strategy = signalTurbo
    ? {
        name: "adaptive_momentum", checkEvery: 21, horizons: [21, 63, 126, 252],
        recalibrateEvery: 21, trainWindow: 756, hiThreshold: 0.05, loThreshold: 0,
        dipBoost: 0, rotate: false, basket: preset.basket,
      }
    : { name: "momentum_rotation", lookback: 126, absolute: true, rotate: false, basket: preset.basket };
  return {
    start: f.start, end: f.end, periodsPerYear: f.periodsPerYear || 252,
    monthlyBudget: parseFloat($("sbudget").value) || 1000,
    dayOfMonth: 26, initialCash: 0, riskFreeRate: 0.02,
    feeRate: 0.005, slippageRate: 0.0005, minFee: 0,
    strategy,
    benchmark: { name: "monthly_dca" },
  };
}

function renderMarketSeg() {
  $("market").innerHTML = Object.values(SIGNAL_PRESETS)
    .filter((p) => instrument(p.primary)) // hide a preset whose data is absent
    .map((p) => `<button class="seg-btn ${p.key === signalMarket ? "active" : ""}" data-mkt="${p.key}">${p.label}</button>`)
    .join("");
  for (const b of document.querySelectorAll("#market .seg-btn"))
    b.addEventListener("click", () => { signalMarket = b.dataset.mkt; runSignal(); });
  
}

/** « Comment ça marche » + « quand j'investis » — une seule explication. */
function renderSteps(preset) {
  const [a, b] = preset.basket;
  const names = `<b style="color:${colorOf(a)}">${a}</b> et <b style="color:${colorOf(b)}">${b}</b>`;
  $("steps").innerHTML = `
    <ol class="plan-steps">
      <li>📊 Le signal compare ${names} : leur force de hausse sur 1, 3, 6 et 12 mois
        (pondération recalibrée automatiquement — jamais sur le futur).</li>
      <li>🏆 Ton argent du mois va sur <b>le plus fort des deux</b>. S'il est en très forte
        tendance (score ≥ +5 %), le signal te dit d'investir aussi le cash mis de côté.</li>
      <li>🛑 Si les deux baissent : tu n'achètes <b>rien</b>, tu gardes le cash. Il sera
        investi d'un coup quand la tendance repartira.</li>
      <li>🔁 On ne vend <b>jamais</b> — testé : vendre coûte 16 à 30 % de patrimoine.</li>
    </ol>
    <p class="note"><b>Et « quand » j'investis ?</b> Le signal se recalcule à chaque clôture ;
    ce qui est mensuel c'est ton argent, pas le signal. Le jour où tu as du cash (ton virement,
    une prime…), ouvre cette page et fais ce qu'elle dit — c'est tout. Investir plus souvent a
    été testé (quotidien, hebdo) : ça fait <b>moins bien</b> après frais de courtage.</p>`;
}

/** Le r\u00e9sultat long terme en une phrase, calcul\u00e9 du backtest complet. */
function renderStat(result, preset) {
  const m = result.strategy.metrics;
  const b = result.benchmark.metrics;
  const y0 = result.bars.dates[0].slice(0, 4);
  const y1 = result.bars.dates[result.bars.dates.length - 1].slice(0, 4);
  const c = preset.currency;
  $("stat").innerHTML =
    `\u{1F4C8} Backtest ${y0}\u2192${y1} : en investissant ${cur(m.invested_capital)} ${c} au total, ` +
    `ce signal aurait donn\u00e9 <b>${cur(m.final_value)} ${c}</b>, contre ` +
    `${cur(b.final_value)} ${c} pour un DCA classique sur ${preset.primary} ` +
    `(soit <b>${signed(m.excess_total_return)}</b>). Les performances pass\u00e9es ne pr\u00e9jugent pas du futur.`;
}

/** La check-list une-fois-pour-toutes pour d\u00e9marrer en vrai. */
function renderStart(preset) {
  const [a, b] = preset.basket;
  $("start").innerHTML = `
    <h3>Comment d\u00e9marrer en vrai (une seule fois)</h3>
    <ol class="plan-steps">
      <li>Ouvre ${preset.broker}.</li>
      <li>Rep\u00e8re les deux ETFs : <b>${a}</b> (${preset.names[a]}) et <b>${b}</b> (${preset.names[b]}).</li>
      <li>Mets un rappel r\u00e9current le <b>26 de chaque mois</b> sur ton t\u00e9l\u00e9phone.</li>
      <li>Chaque mois : ouvre cette page, ach\u00e8te ce que dit le signal (ou rien), ferme. C'est tout.</li>
    </ol>`;
}

/** Recompute and render the whole signal tab from the market preset. */
async function runSignal() {
  const preset = SIGNAL_PRESETS[signalMarket];
  if (!instrument(preset.primary)) return; // data missing for this preset
  renderMarketSeg();
  const cfg = signalConfig(preset);
  const series = {};
  for (const t of preset.basket) series[t] = { ...(await fetchData(fileFor(t, "daily"))), ticker: t };
  const input = { primary: preset.primary, series };
  const result = runBacktest(input, cfg);
  const sig = currentSignal(input, cfg);
  renderSignal(sig, cfg, preset);
  renderSteps(preset);
  renderRace(result, cfg, sig);
  renderStat(result, preset);
  renderHistory(result, cfg, preset);
  renderStart(preset);
}

/* -------------------------------- run ----------------------------------- */
async function run() {
  syncRangeLabels();
  syncStrategyFields();
  const cfg = readConfig();
  const bad = Object.entries({
    "monthly budget": cfg.monthlyBudget, "DCA day": cfg.dayOfMonth,
    "fee": cfg.feeRate, "slippage": cfg.slippageRate,
  }).find(([, v]) => !Number.isFinite(v));
  if (bad) {
    $("status").textContent = `Please enter a valid number for ${bad[0]}.`;
    return;
  }
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
  const entries = [
    { name: "adaptive_momentum", label: "adaptive (champion)", extra: { rotate: false } },
    { name: "momentum_rotation", label: "rotation (keep holdings)", extra: { rotate: false } },
    { name: "momentum_rotation", label: "rotation (switch all)", extra: { rotate: true } },
    { name: "dip_buying", label: "dip_buying" },
    { name: "trend_filter", label: "trend_filter" },
    { name: "absolute_momentum", label: "absolute_momentum" },
    { name: "rsi", label: "rsi" },
    { name: "moving_average", label: "moving_average" },
    { name: "monthly_dca", label: "monthly_dca" },
  ];
  const traces = [];
  for (const e of entries) {
    const c = { ...cfg, strategy: { ...cfg.strategy, name: e.name, ...(e.extra || {}) } };
    const r = runBacktest(await loadMarket(e.name), c);
    traces.push({ x: r.strategy.history.date, y: r.strategy.history.total, name: e.label, mode: "lines" });
  }
  draw("chart-equity", traces, LAYOUT("All strategies — portfolio value", { yaxis: { title: "Value" } }));
  $("status").textContent = `Comparing ${entries.length} strategy variants on ${$("ticker").value}.`;
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
  // The FR preset needs its data present; fall back to US otherwise.
  if (!instrument(SIGNAL_PRESETS.fr.primary)) signalMarket = "us";
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
  $("sbudget").addEventListener("input", debounce(runSignal, 200));
  for (const b of document.querySelectorAll(".tab"))
    b.addEventListener("click", () => showTab(b.dataset.tab));
  for (const d of document.querySelectorAll("details.acc"))
    d.addEventListener("toggle", () => resizeCharts());
  for (const a of document.querySelectorAll(".goto-backtest"))
    a.addEventListener("click", (e) => { e.preventDefault(); showTab("backtest"); window.scrollTo(0, 0); });

  // Only re-fit charts when the viewport WIDTH changes. iOS fires `resize` on
  // every address-bar show/hide (height-only) while scrolling — ignoring those
  // keeps scrolling smooth and stops charts from jumping around.
  let lastWidth = window.innerWidth;
  const onResize = debounce(() => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    resizeCharts();
  }, 200);
  window.addEventListener("resize", onResize);
  window.addEventListener("orientationchange", () => setTimeout(resizeCharts, 350));

  await runSignal(); // home tab first: it is what the user sees
  await run();
}

main().catch((e) => {
  $("status").textContent = `Erreur : ${e.message}`;
  console.error(e);
});
