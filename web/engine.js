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

/** Trailing return over `lookback` bars at index i, or null when undefined. */
function trailingReturn(close, i, lookback) {
  if (i < lookback) return null;
  const a = close[i];
  const b = close[i - lookback];
  if (!(a > 0) || !(b > 0)) return null;
  return a / b - 1;
}

/**
 * Orders for bar i: a list of {ticker, notional, field, reason}.
 * `aligned` = {dates, primary, bars:{ticker:{open,high,low,close}}}.
 */
function strategyOrders(name, s, aligned, i, ctx) {
  const cash = ctx.cash;
  const primary = aligned.primary;
  const p = aligned.bars[primary];
  const buy = (ticker, notional, field, reason) => [{ ticker, notional, field, reason }];

  if (name === "momentum_rotation") {
    // Handled before the low-cash guard: in `rotate` mode the strategy may need
    // to SELL holdings even when no cash is waiting to be deployed.
    if (!ctx.isScheduled) return [];
    const lb = s.lookback || 126;
    const basket = s.basket && s.basket.length ? s.basket : Object.keys(aligned.bars);
    const ranked = basket
      .map((t) => [t, aligned.bars[t] ? trailingReturn(aligned.bars[t].close, i, lb) : null])
      .filter((r) => r[1] !== null);
    const sells = (keep) =>
      Object.entries(ctx.positions || {})
        .filter(([t, pos]) => t !== keep && pos.qty > 1e-9)
        .map(([t, pos]) => ({ ticker: t, side: "sell", quantity: pos.qty, field: "open", reason: "rotate" }));
    if (!ranked.length)
      return cash > MIN_NOTIONAL ? buy(primary, cash, "open", "momentum") : [];
    let best = ranked[0];
    for (const r of ranked) if (r[1] > best[1]) best = r;
    if (s.absolute !== false && best[1] <= 0)
      return s.rotate ? sells(null) : []; // dual momentum: all falling -> cash
    const orders = s.rotate ? sells(best[0]) : [];
    // The buy is capped to available cash AT EXECUTION TIME, so after the sells
    // settle it deploys cash + proceeds in one order (mirrors the Python engine).
    if (cash > MIN_NOTIONAL || orders.length)
      orders.push({ ticker: best[0], notional: Infinity, field: "open", reason: "momentum" });
    return orders;
  }

  if (cash <= MIN_NOTIONAL) return [];

  if (name === "monthly_dca")
    return ctx.isScheduled ? buy(primary, cash, s.priceField || "open", "scheduled") : [];

  if (name === "trend_filter") {
    if (!ctx.isScheduled) return [];
    const w = s.maWindow || s.ma_window || 200;
    const above = i + 1 < w || p.close[i] > sma(p.close, i, w);
    return above ? buy(primary, cash, "open", "trend") : [];
  }

  if (name === "absolute_momentum") {
    if (!ctx.isScheduled) return [];
    const tr = trailingReturn(p.close, i, s.lookback || 126);
    return tr !== null && tr <= 0 ? [] : buy(primary, cash, "open", "momentum");
  }

  // Budget-deploying signal strategies (dip_buying, rsi, moving_average).
  if (ctx.isScheduled && (s.budgetPolicy || "reset") === "reset")
    return buy(primary, cash, "open", "scheduled");
  let fired = false;
  let field = "close";
  if (name === "dip_buying") {
    const sig = evaluateSignal(p, i, s);
    fired = sig.move <= -s.threshold;
    field = sig.field;
  } else if (name === "rsi") {
    const r = rsi(p.close, i, s.period || 14);
    fired = !Number.isNaN(r) && r < (s.oversold || 30);
  } else if (name === "moving_average") {
    const avg = sma(p.close, i, s.window || 50);
    fired = !Number.isNaN(avg) && p.close[i] < avg * (1 - (s.margin || 0));
  }
  if (fired) {
    const notional = Math.min(s.allocation * cash, cash);
    if (notional >= MIN_NOTIONAL) return buy(primary, notional, field, "dip");
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

function executeSell(quantity, ref, cfg) {
  const price = ref * (1 - cfg.slippageRate);
  const gross = quantity * price;
  const fee = Math.max(gross * cfg.feeRate, cfg.minFee || 0);
  return { quantity, price, fee, cashFlow: gross - fee };
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

/** Forward-fill one OHLC series onto a target date axis (two-pointer). */
function ffillOnto(ds, dates) {
  const out = { open: [], high: [], low: [], close: [] };
  let j = -1;
  let k = 0;
  for (const d of dates) {
    while (k < ds.dates.length && ds.dates[k] <= d) j = k++;
    for (const f of ["open", "high", "low", "close"]) out[f].push(j < 0 ? NaN : ds[f][j]);
  }
  return out;
}

/** Align a {ticker:series} map onto the primary ticker's sliced calendar. */
function alignSeries(series, primary, start, end) {
  const p = sliceData(series[primary], start, end);
  const bars = {};
  for (const [t, ds] of Object.entries(series)) {
    bars[t] =
      t === primary
        ? { open: p.open, high: p.high, low: p.low, close: p.close }
        : ffillOnto(ds, p.dates);
  }
  return { dates: p.dates, primary, bars };
}

/** Run one strategy over an aligned multi-asset market; returns history + trades. */
function simulate(name, params, aligned, cfg) {
  const dates = aligned.dates;
  const n = dates.length;
  const deposits = monthStartFlags(dates);
  const scheduled = scheduledFlags(dates, cfg.dayOfMonth);
  const positions = {}; // ticker -> {qty, costBasis}
  const port = { cash: cfg.initialCash || 0, fees: 0, invested: cfg.initialCash || 0, trades: [] };
  const hist = { date: [], cash: [], positionsValue: [], total: [], invested: [], fees: [], qty: [] };

  for (let i = 0; i < n; i++) {
    if (deposits[i]) {
      port.cash += cfg.monthlyBudget;
      port.invested += cfg.monthlyBudget;
    }
    const orders = strategyOrders(name, params, aligned, i, {
      cash: port.cash, isScheduled: scheduled[i], positions,
    });
    for (const o of orders) {
      const ref = aligned.bars[o.ticker]?.[o.field]?.[i];
      if (!(ref > 0) || !Number.isFinite(ref)) continue; // guard against bad/missing prices
      if (o.side === "sell") {
        const pos = positions[o.ticker];
        const qty = Math.min(o.quantity, pos ? pos.qty : 0);
        if (qty <= 1e-9) continue;
        const t = executeSell(qty, ref, cfg);
        // Average-cost reduction, mirroring the Python Position._reduce.
        const avg = pos.qty > 0 ? pos.costBasis / pos.qty : 0;
        pos.qty -= qty;
        pos.costBasis -= avg * qty;
        port.cash += t.cashFlow;
        port.fees += t.fee;
        port.trades.push({ date: dates[i], ticker: o.ticker, price: t.price, quantity: qty, reason: o.reason, side: "sell" });
        continue;
      }
      const notional = Math.min(o.notional, port.cash);
      if (notional <= 0) continue;
      const t = executeBuy(notional, ref, cfg);
      const pos = (positions[o.ticker] ??= { qty: 0, costBasis: 0 });
      pos.qty += t.quantity;
      pos.costBasis += t.quantity * t.price;
      port.cash += t.cashFlow;
      port.fees += t.fee;
      port.trades.push({ date: dates[i], ticker: o.ticker, price: t.price, quantity: t.quantity, reason: o.reason, side: "buy" });
    }
    let positionsValue = 0;
    let totalQty = 0;
    for (const [t, pos] of Object.entries(positions)) {
      positionsValue += pos.qty * aligned.bars[t].close[i];
      totalQty += pos.qty;
    }
    hist.date.push(dates[i]);
    hist.cash.push(port.cash);
    hist.positionsValue.push(positionsValue);
    hist.total.push(port.cash + positionsValue);
    hist.invested.push(port.invested);
    hist.fees.push(port.fees);
    hist.qty.push(totalQty);
  }
  return { name, history: hist, trades: port.trades };
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
  // Whole days only, matching pandas Timedelta.days (drops any partial intraday
  // day) so annualisation is identical to the Python engine at every frequency.
  return Math.floor((Date.parse(b) - Date.parse(a)) / 86400000);
}

function xirr(amounts, dates) {
  const pos = amounts.some((a) => a > 0);
  const neg = amounts.some((a) => a < 0);
  if (!pos || !neg) return NaN;
  const t0 = dates.reduce((a, b) => (a < b ? a : b));
  const years = dates.map((d) => daysBetween(t0, d) / 365.0);
  const npv = (r) => amounts.reduce((s, a, i) => s + a / Math.pow(1 + r, years[i]), 0);
  // Prefer a deterministic bracketed solve (matches the Python brentq path).
  let lo = -0.9999;
  let hi = 10.0;
  let flo = npv(lo);
  if (flo * npv(hi) < 0) {
    for (let k = 0; k < 200; k++) {
      const mid = (lo + hi) / 2;
      const fm = npv(mid);
      if (Math.abs(fm) < 1e-9) return mid;
      if (flo * fm < 0) hi = mid;
      else {
        lo = mid;
        flo = fm;
      }
    }
    return (lo + hi) / 2;
  }
  // Fallback: Newton from a default guess.
  let r = 0.1;
  for (let k = 0; k < 100; k++) {
    const f = npv(r);
    const df = (npv(r + 1e-6) - f) / 1e-6;
    if (Math.abs(df) < 1e-12) break;
    const next = r - f / df;
    if (!Number.isFinite(next)) break;
    if (Math.abs(next - r) < 1e-9) return next;
    r = next;
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
  const ppy = (cfg && cfg.periodsPerYear) || PERIODS_PER_YEAR;
  out.annual_return = mean(twr) * ppy;
  out.annual_volatility = std(twr) * Math.sqrt(ppy);
  const excess = out.annual_return - cfg.riskFreeRate;
  out.sharpe = out.annual_volatility > EPS ? excess / out.annual_volatility : 0;
  const downVol = std(twr.filter((r) => r < 0)) * Math.sqrt(ppy);
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
  const buys = run.trades.filter((t) => t.side !== "sell");
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
    out.tracking_error = std(active) * Math.sqrt(ppy);
    out.information_ratio = out.tracking_error > EPS ? (mean(active) * ppy) / out.tracking_error : 0;
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

/* ------------------------------ live signal --------------------------------- */

const sgnPct = (x) => (x >= 0 ? "+" : "") + (x * 100).toFixed(2) + "%";

/**
 * What the selected strategy says to do RIGHT NOW, on the most recent bar.
 *
 * Reuses the exact same indicators and rules as the backtest (`strategyOrders`,
 * `trailingReturn`, `sma`, `rsi`, `evaluateSignal`) so the live signal can never
 * disagree with what was backtested. Returns a plain-language recommendation
 * plus the numbers that drive it.
 *
 * @returns {{asOf, action, detail, fired, rows}} where `rows` is an optional
 *   ranking ([{label, value, picked}]) for multi-asset strategies.
 */
export function currentSignal(input, cfg) {
  const market = input.dates
    ? { primary: input.ticker || "asset", series: { [input.ticker || "asset"]: input } }
    : input;
  const aligned = alignSeries(market.series, market.primary, cfg.start, cfg.end);
  const dates = aligned.dates;
  const i = dates.length - 1;
  if (i < 0) return { asOf: null, action: "No data in range", detail: "", fired: false, rows: [] };

  const s = cfg.strategy;
  const name = s.name;
  const primary = aligned.primary;
  const p = aligned.bars[primary];
  const asOf = dates[i];
  const px = p.close[i];

  if (name === "momentum_rotation") {
    const lb = s.lookback || 126;
    const basket = s.basket && s.basket.length ? s.basket : Object.keys(aligned.bars);
    const ranked = basket
      .map((t) => ({ ticker: t, ret: aligned.bars[t] ? trailingReturn(aligned.bars[t].close, i, lb) : null }))
      .filter((r) => r.ret !== null)
      .sort((a, b) => b.ret - a.ret);
    if (!ranked.length)
      return { asOf, action: `Buy ${primary}`, detail: `Not enough history to rank the basket yet; default to ${primary}.`, fired: true, rows: [] };
    const best = ranked[0];
    const cash = s.absolute !== false && best.ret <= 0;
    const rotate = !!s.rotate;
    let action;
    let detail;
    if (cash) {
      action = rotate ? "Go to cash — sell everything" : "Hold cash this month";
      detail = `Dual-momentum guard: even the strongest asset's ${lb}-day return is ${sgnPct(best.ret)} (≤ 0). ` +
        (rotate
          ? "In switch mode the rule liquidates all holdings and waits in cash."
          : "The rule skips this month's purchase and keeps the cash.");
    } else {
      action = rotate ? `Hold 100% ${best.ticker}` : `Buy ${best.ticker}`;
      detail = `${best.ticker} has the strongest trailing ${lb}-day return (${sgnPct(best.ret)}). ` +
        (rotate
          ? `In switch mode: sell anything that is not ${best.ticker} and route all capital plus this month's budget into ${best.ticker} on your DCA day (day ${cfg.dayOfMonth}).`
          : `Invest this month's whole budget in ${best.ticker} on your DCA day (day ${cfg.dayOfMonth}).`);
    }
    return {
      asOf, fired: !cash, action, detail,
      rows: ranked.map((r, idx) => ({ label: r.ticker, value: sgnPct(r.ret), picked: !cash && idx === 0 })),
    };
  }

  if (name === "absolute_momentum") {
    const lb = s.lookback || 126;
    const tr = trailingReturn(p.close, i, lb);
    const invest = !(tr !== null && tr <= 0);
    return {
      asOf, fired: invest,
      action: invest ? `Buy ${primary}` : "Hold cash this month",
      detail: tr === null
        ? `Not enough history for a ${lb}-day look-back yet.`
        : `${primary}'s trailing ${lb}-day return is ${sgnPct(tr)} → ${invest ? "positive, so invest the budget on your DCA day." : "negative, so stay in cash this month."}`,
      rows: [],
    };
  }

  if (name === "trend_filter") {
    const w = s.maWindow || s.ma_window || 200;
    const ma = sma(p.close, i, w);
    const above = Number.isNaN(ma) || px > ma;
    return {
      asOf, fired: above,
      action: above ? `Buy ${primary}` : "Skip this month",
      detail: Number.isNaN(ma)
        ? `Not enough history for a ${w}-day average yet; invest by default.`
        : `Price ${px.toFixed(2)} is ${above ? "above" : "below"} the ${w}-day moving average ${ma.toFixed(2)} → ${above ? "invest the budget on your DCA day." : "stay out until the trend turns up."}`,
      rows: [],
    };
  }

  // Per-day signal strategies: dip_buying / rsi / moving_average.
  let fired = false;
  let detail = "";
  if (name === "dip_buying") {
    const sig = evaluateSignal(p, i, s);
    fired = sig.move <= -s.threshold;
    detail = `Signal "${s.signalMethod}" today is ${sgnPct(sig.move)} vs a trigger of −${(s.threshold * 100).toFixed(2)}%. ${fired ? `Dip triggered → buy ${(s.allocation * 100).toFixed(0)}% of the remaining monthly budget now.` : `No dip → the leftover budget auto-invests on day ${cfg.dayOfMonth}.`}`;
  } else if (name === "rsi") {
    const r = rsi(p.close, i, s.period || 14);
    fired = !Number.isNaN(r) && r < (s.oversold || 30);
    detail = `RSI(${s.period || 14}) is ${Number.isNaN(r) ? "n/a" : r.toFixed(1)} vs an oversold level of ${s.oversold || 30}. ${fired ? `Oversold → buy ${(s.allocation * 100).toFixed(0)}% of the remaining budget now.` : `Not oversold → leftover budget auto-invests on day ${cfg.dayOfMonth}.`}`;
  } else if (name === "moving_average") {
    const w = s.window || 50;
    const ma = sma(p.close, i, w);
    fired = !Number.isNaN(ma) && px < ma * (1 - (s.margin || 0));
    detail = `Price ${px.toFixed(2)} vs ${w}-day MA ${Number.isNaN(ma) ? "n/a" : ma.toFixed(2)} (−${((s.margin || 0) * 100).toFixed(1)}% band). ${fired ? `Below the band → buy ${(s.allocation * 100).toFixed(0)}% of the remaining budget now.` : `Not below → leftover budget auto-invests on day ${cfg.dayOfMonth}.`}`;
  } else {
    // monthly_dca
    return { asOf, fired: true, action: `Buy ${primary} on day ${cfg.dayOfMonth}`, detail: `Plain DCA: invest the full monthly budget in ${primary} on your DCA day, regardless of price.`, rows: [] };
  }
  return {
    asOf, fired,
    action: fired ? "Buy now" : `Wait — no signal today`,
    detail,
    rows: [],
  };
}

/* ------------------------------- public API --------------------------------- */

/**
 * Run a strategy and its benchmark.
 * @param {object} input  Either a single OHLC series {ticker,dates,open,...} or a
 *   multi-asset market {primary, series:{ticker: series}}.
 * @param {object} cfg    Full configuration (see web/app.js for the shape).
 * @returns {{bars, strategy, benchmark}} runs with `.metrics` attached.
 */
export function runBacktest(input, cfg) {
  const market = input.dates
    ? { primary: input.ticker || "asset", series: { [input.ticker || "asset"]: input } }
    : input;
  const aligned = alignSeries(market.series, market.primary, cfg.start, cfg.end);
  const stratRun = simulate(cfg.strategy.name, cfg.strategy, aligned, cfg);
  const benchRun = simulate(cfg.benchmark.name, cfg.benchmark, aligned, cfg);
  stratRun.metrics = metrics(stratRun, cfg, benchRun.history);
  benchRun.metrics = metrics(benchRun, cfg, null);
  const pbars = { ...aligned.bars[aligned.primary], dates: aligned.dates, ticker: aligned.primary };
  return { bars: pbars, aligned, strategy: stratRun, benchmark: benchRun };
}

export const _internals = { monthStartFlags, scheduledFlags, evaluateSignal, executeBuy, xirr, simulate, metrics };
