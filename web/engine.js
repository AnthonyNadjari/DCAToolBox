/**
 * DCAToolBox browser backtest engine.
 *
 * This is a faithful, dependency-free JavaScript mirror of the Python engine in
 * `dcatoolbox` (broker cost model, calendar logic, portfolio accounting and
 * metrics). It is validated against the Python implementation by a parity test
 * (`web/engine.test.mjs`) so the two never silently diverge.
 *
 * It runs unchanged in the browser and in Node (ES module).
 */

const PERIODS_PER_YEAR = 252;
const MIN_NOTIONAL = 1.0;
const EPS = 1e-12;

/* ----------------------------- calendar helpers ------------------------------ */

const ymKey = (d) => d.slice(0, 7);
const dayOf = (d) => parseInt(d.slice(8, 10), 10);

/** First bar index of each calendar month (deposit days). */
function monthStartFlags(dates) {
  const flags = new Array(dates.length).fill(false);
  let seen = null;
  for (let i = 0; i < dates.length; i++) {
    const k = ymKey(dates[i]);
    if (k !== seen) {
      flags[i] = true;
      seen = k;
    }
  }
  return flags;
}

/** Scheduled investment day: first trading day >= dayOfMonth, else month's last. */
function scheduledFlags(dates, dayOfMonth) {
  const flags = new Array(dates.length).fill(false);
  const byMonth = new Map();
  for (let i = 0; i < dates.length; i++) {
    const k = ymKey(dates[i]);
    if (!byMonth.has(k)) byMonth.set(k, []);
    byMonth.get(k).push(i);
  }
  for (const idxs of byMonth.values()) {
    let chosen = idxs.find((i) => dayOf(dates[i]) >= dayOfMonth);
    if (chosen === undefined) chosen = idxs[idxs.length - 1];
    flags[chosen] = true;
  }
  return flags;
}

/* -------------------------------- indicators -------------------------------- */

function sma(values, i, window) {
  if (i + 1 < window) return NaN;
  let s = 0;
  for (let k = i - window + 1; k <= i; k++) s += values[k];
  return s / window;
}

function rsi(close, i, period) {
  if (i < period) return NaN;
  // Wilder's RSI via an EWM with alpha = 1/period, seeded from the first delta.
  let avgGain = 0;
  let avgLoss = 0;
  const alpha = 1 / period;
  for (let k = 1; k <= i; k++) {
    const delta = close[k] - close[k - 1];
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? -delta : 0;
    if (k === 1) {
      avgGain = gain;
      avgLoss = loss;
    } else {
      avgGain = alpha * gain + (1 - alpha) * avgGain;
      avgLoss = alpha * loss + (1 - alpha) * avgLoss;
    }
  }
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/* --------------------------------- signals ---------------------------------- */

const pct = (num, den) => (den > 0 ? num / den - 1 : 0);

/** Returns {fired, field} for the chosen signal method at bar i. */
function evaluateSignal(bars, i, s) {
  const { open, close } = bars;
  const w = s.signalWindow || 20;
  // Mirror the Python default (DipBuyingStrategy uses open_vs_open by default).
  switch (s.signalMethod || "open_vs_open") {
    case "open_vs_open":
      return { move: i >= 1 ? pct(open[i], open[i - 1]) : 0, field: "open" };
    case "close_vs_close":
      return { move: i >= 1 ? pct(close[i], close[i - 1]) : 0, field: "close" };
    case "open_vs_close":
      return { move: i >= 1 ? pct(open[i], close[i - 1]) : 0, field: "open" };
    case "close_vs_open":
      return { move: pct(close[i], open[i]), field: "close" };
    case "drawdown_n_days": {
      if (i < 1) return { move: 0, field: "close" };
      let mx = -Infinity;
      for (let k = Math.max(0, i - w + 1); k <= i; k++) mx = Math.max(mx, close[k]);
      return { move: pct(close[i], mx), field: "close" };
    }
    case "cumulative_return":
      // Mirror Python: fires at i >= window (history length i+1 > window).
      return { move: i >= w ? pct(close[i], close[i - w]) : 0, field: "close" };
    default:
      return { move: 0, field: "open" };
  }
}

/* -------------------------------- strategies -------------------------------- */

/** Returns a list of orders for bar i: [{notional, field, reason}]. */
function strategyOrders(name, s, bars, i, ctx) {
  const cash = ctx.cash;
  if (cash <= MIN_NOTIONAL) return [];
  const sweep = () => [{ notional: cash, field: "open", reason: "scheduled" }];

  if (name === "monthly_dca") {
    if (!ctx.isScheduled) return [];
    return [{ notional: cash, field: s.priceField || "open", reason: "scheduled" }];
  }

  // Budget-deploying strategies (dip_buying, rsi, moving_average).
  if (ctx.isScheduled && (s.budgetPolicy || "reset") === "reset") return sweep();

  let fired = false;
  let field = "close";
  if (name === "dip_buying") {
    const sig = evaluateSignal(bars, i, s);
    fired = sig.move <= -s.threshold;
    field = sig.field;
  } else if (name === "rsi") {
    const r = rsi(bars.close, i, s.period || 14);
    fired = !Number.isNaN(r) && r < (s.oversold || 30);
  } else if (name === "moving_average") {
    const avg = sma(bars.close, i, s.window || 50);
    fired = !Number.isNaN(avg) && bars.close[i] < avg * (1 - (s.margin || 0));
  }
  if (fired) {
    const notional = Math.min(s.allocation * cash, cash);
    if (notional >= MIN_NOTIONAL) return [{ notional, field, reason: "dip" }];
  }
  return [];
}

/* ---------------------------------- broker ---------------------------------- */

function executeBuy(notional, ref, cfg) {
  const price = ref * (1 + cfg.slippageRate);
  const fee = Math.max(notional * cfg.feeRate, cfg.minFee || 0);
  const investable = Math.max(notional - fee, 0);
  const quantity = investable / price;
  return { quantity, price, fee, cashFlow: -notional };
}

/* ------------------------------- core simulate ------------------------------ */

function sliceData(data, start, end) {
  const out = { dates: [], open: [], high: [], low: [], close: [], volume: [] };
  for (let i = 0; i < data.dates.length; i++) {
    const d = data.dates[i];
    if ((start && d < start) || (end && d > end)) continue;
    out.dates.push(d);
    out.open.push(data.open[i]);
    out.high.push(data.high[i]);
    out.low.push(data.low[i]);
    out.close.push(data.close[i]);
    out.volume.push(data.volume ? data.volume[i] : 0);
  }
  return out;
}

/** Run one strategy over `bars`; returns the raw run (history + trades). */
function simulate(name, strategyParams, bars, cfg) {
  const n = bars.dates.length;
  const deposits = monthStartFlags(bars.dates);
  const scheduled = scheduledFlags(bars.dates, cfg.dayOfMonth);
  const port = {
    cash: cfg.initialCash || 0,
    qty: 0,
    costBasis: 0,
    fees: 0,
    invested: cfg.initialCash || 0,
    trades: [],
  };
  const hist = { date: [], cash: [], positionsValue: [], total: [], invested: [], fees: [], qty: [] };

  for (let i = 0; i < n; i++) {
    if (deposits[i]) {
      port.cash += cfg.monthlyBudget;
      port.invested += cfg.monthlyBudget;
    }
    const ctx = { cash: port.cash, isScheduled: scheduled[i] };
    const orders = strategyOrders(name, strategyParams, bars, i, ctx);
    for (const o of orders) {
      const ref = bars[o.field][i];
      if (!(ref > 0) || !Number.isFinite(ref)) continue; // guard against bad prices
      const notional = Math.min(o.notional, port.cash);
      if (notional <= 0) continue;
      const t = executeBuy(notional, ref, cfg);
      port.qty += t.quantity;
      port.costBasis += t.quantity * t.price;
      port.cash += t.cashFlow;
      port.fees += t.fee;
      port.trades.push({ date: bars.dates[i], price: t.price, quantity: t.quantity, reason: o.reason });
    }
    const positionsValue = port.qty * bars.close[i];
    hist.date.push(bars.dates[i]);
    hist.cash.push(port.cash);
    hist.positionsValue.push(positionsValue);
    hist.total.push(port.cash + positionsValue);
    hist.invested.push(port.invested);
    hist.fees.push(port.fees);
    hist.qty.push(port.qty);
  }
  return { name, history: hist, trades: port.trades, costBasis: port.costBasis, qty: port.qty };
}

/* --------------------------------- metrics ---------------------------------- */

function std(arr) {
  if (arr.length < 2) return 0;
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  const v = arr.reduce((a, b) => a + (b - m) * (b - m), 0) / (arr.length - 1);
  return Math.sqrt(v);
}
const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);

function daysBetween(a, b) {
  return (Date.parse(b) - Date.parse(a)) / 86400000;
}

function xirr(amounts, dates) {
  const pos = amounts.some((a) => a > 0);
  const neg = amounts.some((a) => a < 0);
  if (!pos || !neg) return NaN;
  const t0 = dates.reduce((a, b) => (a < b ? a : b));
  const years = dates.map((d) => daysBetween(t0, d) / 365.0);
  const npv = (r) => amounts.reduce((s, a, i) => s + a / Math.pow(1 + r, years[i]), 0);
  let r = 0.1;
  for (let k = 0; k < 100; k++) {
    const f = npv(r);
    const df = (npv(r + 1e-6) - f) / 1e-6;
    if (Math.abs(df) < 1e-12) break;
    const next = r - f / df;
    if (!Number.isFinite(next)) break;
    if (Math.abs(next - r) < 1e-8) return next;
    r = next;
  }
  // Bisection fallback on a sane bracket.
  let lo = -0.9999;
  let hi = 10.0;
  let flo = npv(lo);
  for (let k = 0; k < 200; k++) {
    const mid = (lo + hi) / 2;
    const fm = npv(mid);
    if (Math.abs(fm) < 1e-7) return mid;
    if (flo * fm < 0) hi = mid;
    else {
      lo = mid;
      flo = fm;
    }
  }
  return NaN;
}

function metrics(run, cfg, benchHistory) {
  const h = run.history;
  const n = h.total.length;
  const out = emptyMetrics();
  if (n === 0) return out;

  const flows = h.invested.map((v, i) => (i === 0 ? v : v - h.invested[i - 1]));
  const twr = [];
  for (let i = 1; i < n; i++) {
    const prior = h.total[i - 1] + flows[i];
    twr.push(prior > 0 ? h.total[i] / prior - 1 : 0);
  }
  const wi = [];
  let acc = 1;
  for (const r of twr) {
    acc *= 1 + r;
    wi.push(acc);
  }
  const dd = drawdown(wi);

  out.invested_capital = h.invested[n - 1];
  out.final_value = h.total[n - 1];
  out.total_return = out.invested_capital ? out.final_value / out.invested_capital - 1 : 0;
  const years = Math.max(daysBetween(h.date[0], h.date[n - 1]) / 365.25, EPS);
  out.cagr = wi.length ? Math.pow(wi[wi.length - 1], 1 / years) - 1 : 0;
  out.twr_total_return = wi.length ? wi[wi.length - 1] - 1 : 0;
  out.annual_return = mean(twr) * PERIODS_PER_YEAR;
  out.annual_volatility = std(twr) * Math.sqrt(PERIODS_PER_YEAR);
  const excess = out.annual_return - cfg.riskFreeRate;
  out.sharpe = out.annual_volatility > EPS ? excess / out.annual_volatility : 0;
  const downVol = std(twr.filter((r) => r < 0)) * Math.sqrt(PERIODS_PER_YEAR);
  out.sortino = downVol > EPS ? excess / downVol : 0;
  out.max_drawdown = dd.length ? Math.min(...dd) : 0;
  out.calmar = Math.abs(out.max_drawdown) > EPS ? out.cagr / Math.abs(out.max_drawdown) : 0;
  out.time_under_water = dd.length ? dd.filter((x) => x < -EPS).length / dd.length : 0;

  const amounts = flows.map((f) => -f);
  const xdates = h.date.slice();
  amounts.push(out.final_value);
  xdates.push(h.date[n - 1]);
  out.xirr = xirr(amounts, xdates);
  out.irr = Number.isFinite(out.xirr) ? Math.pow(1 + out.xirr, 1 / 12) - 1 : NaN;

  out.avg_cash = mean(h.cash);
  out.cumulative_fees = h.fees[n - 1];
  out.n_orders = run.trades.length;
  const buys = run.trades;
  if (buys.length) {
    out.avg_order_amount = mean(buys.map((t) => t.price * t.quantity));
    const totalQty = buys.reduce((a, t) => a + t.quantity, 0);
    out.avg_buy_price = totalQty ? buys.reduce((a, t) => a + t.price * t.quantity, 0) / totalQty : 0;
  }

  if (benchHistory) {
    const bn = benchHistory.total.length;
    const bflows = benchHistory.invested.map((v, i) => (i === 0 ? v : v - benchHistory.invested[i - 1]));
    const btwr = [];
    for (let i = 1; i < bn; i++) {
      const prior = benchHistory.total[i - 1] + bflows[i];
      btwr.push(prior > 0 ? benchHistory.total[i] / prior - 1 : 0);
    }
    const active = twr.map((r, i) => r - (btwr[i] ?? 0));
    out.tracking_error = std(active) * Math.sqrt(PERIODS_PER_YEAR);
    out.information_ratio = out.tracking_error > EPS ? (mean(active) * PERIODS_PER_YEAR) / out.tracking_error : 0;
    const bInvested = benchHistory.invested[bn - 1];
    const bTotal = benchHistory.total[bn - 1] / bInvested - 1;
    out.excess_total_return = out.total_return - bTotal;
    const bwi = [];
    let bacc = 1;
    for (const r of btwr) {
      bacc *= 1 + r;
      bwi.push(bacc);
    }
    const byears = Math.max(daysBetween(benchHistory.date[0], benchHistory.date[bn - 1]) / 365.25, EPS);
    const bcagr = bwi.length ? Math.pow(bwi[bwi.length - 1], 1 / byears) - 1 : 0;
    out.excess_cagr = out.cagr - bcagr;
  }
  out._series = { date: h.date, wealthIndex: wi, drawdown: dd, returns: twr };
  return out;
}

function drawdown(wi) {
  const dd = [];
  let peak = -Infinity;
  for (const v of wi) {
    peak = Math.max(peak, v);
    dd.push(peak > 0 ? v / peak - 1 : 0);
  }
  return dd;
}

function emptyMetrics() {
  return {
    total_return: 0, twr_total_return: 0, cagr: 0, annual_return: 0, annual_volatility: 0,
    sharpe: 0, sortino: 0, calmar: 0, max_drawdown: 0, time_under_water: 0, irr: 0, xirr: 0,
    tracking_error: 0, information_ratio: 0, n_orders: 0, avg_order_amount: 0, avg_buy_price: 0,
    avg_cash: 0, cumulative_fees: 0, invested_capital: 0, final_value: 0, excess_total_return: 0,
    excess_cagr: 0,
    _series: { date: [], wealthIndex: [], drawdown: [], returns: [] },
  };
}

/* ------------------------------- public API --------------------------------- */

/**
 * Run a strategy and its benchmark over `data`.
 * @param {object} data  OHLCV series {dates, open, high, low, close, volume}.
 * @param {object} cfg   Full configuration (see web/app.js for the shape).
 * @returns {{strategy, benchmark}} runs with `.metrics` attached.
 */
export function runBacktest(data, cfg) {
  const bars = sliceData(data, cfg.start, cfg.end);
  bars.ticker = data.ticker;
  const stratRun = simulate(cfg.strategy.name, cfg.strategy, bars, cfg);
  const benchRun = simulate(cfg.benchmark.name, cfg.benchmark, bars, cfg);
  stratRun.metrics = metrics(stratRun, cfg, benchRun.history);
  benchRun.metrics = metrics(benchRun, cfg, null);
  return { bars, strategy: stratRun, benchmark: benchRun };
}

export const _internals = { monthStartFlags, scheduledFlags, evaluateSignal, executeBuy, xirr, simulate, metrics };
