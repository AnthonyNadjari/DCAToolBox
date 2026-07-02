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
  if (name !== "momentum_rotation") return loadData();
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
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

// The actionable "what do I do now" panel, derived from the latest bar.
function renderSignal(sig, cfg) {
  const el = $("signal");
  if (!sig.asOf) {
    el.innerHTML = `<div class="sig-action">No data in the selected range</div>`;
    return;
  }
  const cls = sig.fired ? "go" : "wait";
  const ranking = sig.rows.length
    ? `<div class="sig-rank">${sig.rows
        .map((r) => `<span class="sig-chip ${r.picked ? "picked" : ""}">${r.label}: ${r.value}</span>`)
        .join("")}</div>`
    : "";
  el.innerHTML = `
    <div class="sig-head">
      <span class="sig-dot ${cls}"></span>
      <div>
        <div class="sig-label">Signal for ${$("strategy").options[$("strategy").selectedIndex].text} · as of ${niceDate(sig.asOf)}</div>
        <div class="sig-action ${cls}">${sig.action}</div>
      </div>
    </div>
    <p class="sig-detail">${sig.detail}</p>
    ${ranking}
    <p class="sig-foot">Based on the latest available end-of-day data. Act on your DCA day (currently day ${cfg.dayOfMonth}); change any parameter on the left and this updates instantly. Educational tool — not investment advice.</p>`;
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
  if (cfg.strategy.name !== "momentum_rotation") return [aligned.primary];
  const basket = cfg.strategy.basket && cfg.strategy.basket.length ? cfg.strategy.basket : Object.keys(aligned.bars);
  return basket.filter((t) => aligned.bars[t]);
}

/** The race the signal ranks: each candidate over the look-back, indexed to 0%. */
function renderRace(result, cfg, sig) {
  const aligned = result.aligned;
  const dates = aligned.dates;
  const n = dates.length;
  const momentum = ["momentum_rotation", "absolute_momentum"].includes(cfg.strategy.name);
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
    ? `The ${lb}-day race the signal ranks (indexed to 0%)`
    : `${aligned.primary} — last ${lb} trading days (indexed to 0%)`;
  draw("chart-race", traces, LAYOUT(title, {
    yaxis: { tickformat: ".0%" }, margin: { t: 40, r: 90, b: 56, l: 48 }, annotations,
  }));
}

/** Concrete action plan: what, how much, when. */
function renderPlan(sig, cfg) {
  const day = cfg.dayOfMonth;
  const now = new Date();
  let next = new Date(now.getFullYear(), now.getMonth(), day);
  if (next <= now) next = new Date(now.getFullYear(), now.getMonth() + 1, day);
  while ([0, 6].includes(next.getDay())) next.setDate(next.getDate() + 1); // roll to a weekday
  const nextTxt = next.toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" });
  const budget = cur(cfg.monthlyBudget);
  const perDip = ["dip_buying", "rsi", "moving_average"].includes(cfg.strategy.name);
  $("plan").innerHTML = `
    <h3>Your action plan</h3>
    <ol class="plan-steps">
      <li><b>${sig.action}</b> — ${sig.fired ? "the rule gives a green light." : "the rule says to hold off for now."}</li>
      <li><b>Amount:</b> ${perDip
        ? `${Math.round(cfg.strategy.allocation * 100)}% of the month's remaining budget per signal (budget ${budget}/month; anything left auto-invests on day ${day}).`
        : cfg.strategy.name === "momentum_rotation" && cfg.strategy.rotate
          ? `this month's budget (${budget}) plus the proceeds of anything you rotate out of.`
          : `this month's full budget, ${budget}.`}</li>
      <li><b>When:</b> ${perDip
        ? "the day the signal fires (check this page after the close)."
        : `on your DCA day — next: <b>${nextTxt}</b> (first trading day on/after day ${day}).`}</li>
    </ol>
    <p class="note">Signals use the latest end-of-day close. Re-check this page on the day you plan to invest.</p>`;
}

/** What the rule decided in each of the last 12 months of the backtest. */
function renderHistory(result, cfg) {
  const name = cfg.strategy.name;
  const months = [...new Set(result.bars.dates.map((d) => d.slice(0, 7)))].slice(-12).reverse();
  const byMonth = new Map(months.map((m) => [m, []]));
  for (const t of result.strategy.trades) {
    const m = t.date.slice(0, 7);
    if (byMonth.has(m)) byMonth.get(m).push(t);
  }
  const noBuyText = {
    momentum_rotation: "Held cash (dual-momentum guard: everything falling)",
    absolute_momentum: "Held cash (negative momentum)",
    trend_filter: "Skipped (price below the trend MA)",
  }[name] || "No purchase";
  const label = (m) =>
    new Date(m + "-01T00:00:00").toLocaleDateString(undefined, { year: "numeric", month: "short" });
  const rows = months.map((m) => {
    const trades = byMonth.get(m);
    const buys = trades.filter((t) => t.side !== "sell");
    const sells = trades.filter((t) => t.side === "sell");
    const amount = buys.reduce((a, t) => a + t.price * t.quantity, 0);
    let what;
    if (!trades.length) what = noBuyText;
    else if (["dip_buying", "rsi", "moving_average"].includes(name)) {
      const dips = buys.filter((t) => t.reason === "dip").length;
      what = dips ? `${dips} signal buy${dips > 1 ? "s" : ""} + sweep on day ${cfg.dayOfMonth}` : `No signal — swept on day ${cfg.dayOfMonth}`;
    } else if (!buys.length && sells.length) {
      what = `Sold everything — went to cash`;
    } else {
      const tk = [...new Set(buys.map((t) => t.ticker))].join(", ");
      const rotated = sells.length ? ` (sold ${[...new Set(sells.map((t) => t.ticker))].join(", ")})` : "";
      what = `Bought <b style="color:${colorOf(buys[0]?.ticker)}">${tk}</b>${rotated}`;
    }
    return `<tr><td>${label(m)}</td><td style="text-align:left">${what}</td><td>${amount ? cur(amount) : "—"}</td></tr>`;
  }).join("");
  $("history").innerHTML =
    `<thead><tr><th>Month</th><th style="text-align:left">Decision</th><th>Amount</th></tr></thead><tbody>${rows}</tbody>`;
}

/** Plain-language explanation of the selected strategy. */
const EXPLAINERS = {
  momentum_rotation: `
    <h3>How Momentum Rotation works</h3>
    <p><b>It is not a blend.</b> The strategy never splits your money across the indices —
    each month it holds <b>exactly one</b> of them (or cash). The "mix" you see in the
    portfolio builds up over time from whichever index won each month.</p>
    <ol>
      <li><b>Rank.</b> On your DCA day, compute each candidate's trailing return over the
      look-back (default 126 trading days ≈ 6 months). That is the race in the chart above —
      the ranking chips are simply where each line ends.</li>
      <li><b>Pick the leader.</b> Invest the whole month's budget in the index with the
      highest trailing return (<i>relative momentum</i>).</li>
      <li><b>Crash guard.</b> If even the leader's trailing return is negative — everything
      is falling — skip the purchase and keep the cash (<i>absolute momentum</i>, the
      "dual momentum" switch). This is what kept the strategy out of 2008-style slides.</li>
    </ol>
    <p><b>Two rotation modes</b> (see the Backtest tab): <i>new contributions only</i>
    routes each month's budget to the leader and never sells — past holdings ride through
    crashes; <i>switch entire portfolio</i> also sells whatever is not the leader (and
    liquidates everything to cash when the guard fires) — stronger crash protection for
    ALL your capital, at the cost of more trades, fees and (outside tax wrappers) taxable
    sales. Use ⚖️ Compare to see both curves.</p>
    <p><b>Why it has historically worked:</b> trends persist over 3–12-month horizons
    (the momentum premium), so the recent leader tends to keep leading for a while; and the
    cash guard avoids averaging down through long bear markets.</p>
    <p><b>Honest limits:</b> in choppy, trendless markets the ranking flips often
    (whipsaw, extra fees); much of the historical edge comes from having QQQ in the basket;
    and a monthly signal reacts with up to a month of delay to sudden crashes.</p>`,
  absolute_momentum: `
    <h3>How Absolute Momentum works</h3>
    <p>Plain DCA with a bear-market filter: on your DCA day, invest only if the asset's own
    trailing look-back return is positive; otherwise hold the cash. You give up some
    upside in recoveries to avoid buying into long slides.</p>`,
  trend_filter: `
    <h3>How the Trend Filter works</h3>
    <p>Invest the monthly budget only when the price is above its long moving average
    (default 200 days) — the classic "only buy in an uptrend" rule. Below the average, cash
    accumulates and deploys once the trend turns back up.</p>`,
  dip_buying: `
    <h3>How Dip Buying works</h3>
    <p>Each month's budget is split: whenever the chosen dip signal fires (e.g. price drops
    2% vs yesterday), a slice of the remaining budget buys immediately; whatever is left
    auto-invests on your DCA day. With the <i>reset</i> policy the whole budget is always
    deployed monthly, so results stay close to plain DCA by construction.</p>`,
  rsi: `
    <h3>How the RSI strategy works</h3>
    <p>Buys a slice of the remaining monthly budget whenever the RSI (a 0–100 oscillator
    of recent gains vs losses) drops below the oversold level — i.e. after sharp selling.
    The leftover budget auto-invests on your DCA day.</p>`,
  moving_average: `
    <h3>How the Moving-Average strategy works</h3>
    <p>Buys a slice of the remaining budget whenever the price trades below its moving
    average by the chosen margin ("buy weakness"), sweeping the rest on your DCA day.</p>`,
  monthly_dca: `
    <h3>How Monthly DCA works</h3>
    <p>The benchmark everything is measured against: invest the full budget on the same
    day every month, no matter the price. Simple, disciplined, and famously hard to beat.</p>`,
};
function renderExplainer(cfg) {
  $("explainer").innerHTML = EXPLAINERS[cfg.strategy.name] || "";
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
  const sig = currentSignal(input, cfg);
  renderSignal(sig, cfg);
  renderRace(result, cfg, sig);
  renderPlan(sig, cfg);
  renderHistory(result, cfg);
  renderExplainer(cfg);
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
  for (const b of document.querySelectorAll(".tab"))
    b.addEventListener("click", () => showTab(b.dataset.tab));
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

  await run();
}

main().catch((e) => {
  $("status").textContent = `Error: ${e.message}`;
  console.error(e);
});
