/* Le Signal — dashboard. Every number on this page is recomputed in the
   browser from monthly sleeve returns (data.json → sleeves): no server, no
   precomputed policy paths. Change a control, the backtest re-runs. */

"use strict";

/* ---------------------------------------------------------------- state -- */

const S = {
  budget: 1000,
  lev: 70, // % of the monthly flow going to the leveraged sleeve
  gate: 1, // 1 = leveraged sleeve follows the 200-day filter
  horizon: 3, // years
  era: "10y",
  range: null, // [lo, hi] month indices when the user drags a custom period
  compare: [], // up to 2 preset indices plotted alongside the policy
  sortCol: "median", // menu sort key
  sortDir: -1, // -1 = best first
};

const ERAS = {
  "10y": { label: "10 dernières années" },
  all: { label: "1989–2026", from: null },
  bear: { label: "débuts 1989–2008", from: null, maxStart: "2009-01-01" },
  bull: { label: "débuts 2009–", from: "2009-01-01" },
};

/** [lo, hi] month-index bounds for the selected era (hi inclusive). */
function eraRange() {
  const dates = D.sleeves.dates;
  const n = dates.length - 1;
  if (S.era === "10y") return [Math.max(0, n - 119), n];
  if (S.era === "bull") return [dates.findIndex((d) => d >= ERAS.bull.from), n];
  if (S.era === "bear") return [0, dates.findIndex((d) => d >= ERAS.bear.maxStart) - 1];
  return [0, n];
}

/** The period actually scored: custom drag range if set, else the era. */
function effRange() {
  return S.range || eraRange();
}

let D = null; // data.json
let R = null; // sleeve returns as typed arrays

/* ------------------------------------------------------------- helpers -- */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const eur = (v) =>
  v >= 1e6 ? (v / 1e6).toFixed(2) + " M€" : v >= 1e4 ? Math.round(v / 1000) + " k€" : Math.round(v) + " €";
const pct = (v, dp = 0) => (v * 100).toFixed(dp) + " %";
const mult = (v) => v.toFixed(2) + "×";
const median = (a) => {
  if (!a.length) return NaN;
  const s = Float64Array.from(a).sort();
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const quantile = (a, q) => {
  if (!a.length) return NaN;
  const s = Float64Array.from(a).sort();
  return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))];
};

/* -------------------------------------------------------------- engine -- */

/** Weights of the monthly flow across sleeves for the current controls. */
function currentWeights() {
  const share = S.lev / 100;
  const levSleeve = S.gate ? "strategy" : "lev_nogate";
  const w = {};
  if (share > 0) w[levSleeve] = share;
  if (share < 1) w.mix7030 = 1 - share;
  return w;
}

/** One DCA run over months [start, start+n). Returns wealth path + drawdown. */
function run(weights, start, n, budget) {
  const cash = budget * (1 - D.sleeves.fee);
  const acc = {};
  const path = new Float64Array(n);
  let peak = 0,
    mdd = 0;
  for (let k = 0; k < n; k++) {
    const i = start + k;
    let total = 0;
    for (const s in weights) acc[s] = (acc[s] || 0) + cash * weights[s];
    for (const s in acc) {
      acc[s] *= 1 + R[s][i];
      total += acc[s];
    }
    path[k] = total;
    if (total > peak) peak = total;
    const dd = total / peak - 1;
    if (dd < mdd) mdd = dd;
  }
  return { path, contributed: budget * n, final: path[n - 1], mdd };
}

/** Start indices allowed by the selected period for a window of `n` months. */
function starts(n) {
  const [lo, hi] = effRange();
  const out = [];
  for (let i = lo; i <= hi - n; i++) out.push(i);
  return out;
}

/** Score one policy over every allowed rolling window. */
function score(weights) {
  const n = S.horizon * 12;
  const idx = starts(n);
  const mults = new Float64Array(idx.length);
  const mdds = new Float64Array(idx.length);
  for (let j = 0; j < idx.length; j++) {
    const r = run(weights, idx[j], n, 1000);
    mults[j] = r.final / r.contributed;
    mdds[j] = r.mdd;
  }
  let sMult = 0,
    sIrr = 0,
    nIrr = 0;
  for (const m of mults) {
    sMult += m;
    const v = irr(m, S.horizon);
    if (Number.isFinite(v)) {
      sIrr += v;
      nIrr++;
    }
  }
  return {
    n: idx.length,
    mults,
    mdds,
    median: median(mults),
    mean: mults.length ? sMult / mults.length : NaN,
    meanIrr: nIrr ? sIrr / nIrr : NaN,
    p5: quantile(mults, 0.05),
    worst: mults.length ? Math.min(...mults) : NaN,
    best: mults.length ? Math.max(...mults) : NaN,
    pLoss: mults.reduce((a, v) => a + (v < 1 ? 1 : 0), 0) / (mults.length || 1),
    medMdd: median(mdds),
    worstMdd: mdds.length ? Math.min(...mdds) : NaN,
  };
}

/** The preset menu — the same policies the offline study scores. */
function presets() {
  const P = [{ label: "100 % 1× S&P (référence)", weights: { ese: 1 }, lev: -1 }];
  P.push({ label: "100 % 1× 70/30 (aucun levier)", weights: { mix7030: 1 }, lev: 0, gate: 0 });
  for (const gate of [0, 1])
    for (const s of [25, 50, 75, 100]) {
      const w = { [gate ? "strategy" : "lev_nogate"]: s / 100 };
      if (s < 100) w.mix7030 = 1 - s / 100;
      P.push({ label: `${s} % 2× ${gate ? "avec" : "sans"} filtre`, weights: w, lev: s, gate });
    }
  return P;
}

/**
 * Annualized money-weighted return (XIRR) of a DCA window: h monthly deposits
 * of 1 unit grow to mult × h. Bisection; monotone in the multiple, so all
 * rankings/medians/quantiles are preserved — this is a display transform.
 */
function irr(mult, years) {
  const h = years * 12;
  if (!Number.isFinite(mult) || mult <= 0) return NaN;
  const f = (r) => {
    let acc = 0;
    for (let k = 1; k <= h; k++) acc += Math.pow(1 + r, (h - k) / 12);
    return acc - mult * h;
  };
  let lo = -0.99,
    hi = 10;
  if (f(lo) > 0) return -0.99;
  if (f(hi) < 0) return 10;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (f(mid) > 0) hi = mid;
    else lo = mid;
  }
  return (lo + hi) / 2;
}

/** Annualized XIRR of a multiple at the current horizon, as a percent string. */
const ann = (m, dp = 1) => {
  const v = irr(m, S.horizon);
  return Number.isFinite(v) ? pct(v, dp) : "—";
};

/* -------------------------------------------------------------- charts -- */

function chart(host, opts) {
  const W = 960,
    H = opts.height || 260;
  const M = { t: 12, r: 14, b: 26, l: opts.left || 54 };
  const iw = W - M.l - M.r,
    ih = H - M.t - M.b;
  const xs = opts.x;
  const x0 = xs[0],
    x1 = xs[xs.length - 1];
  const X = (v) => M.l + ((v - x0) / (x1 - x0 || 1)) * iw;

  const vals = opts.series.flatMap((s) => s.y).filter((v) => Number.isFinite(v) && (!opts.log || v > 0));
  let lo = Math.min(...vals),
    hi = Math.max(...vals);
  if (opts.yMin !== undefined) lo = Math.min(lo, opts.yMin);
  if (opts.yMax !== undefined) hi = Math.max(hi, opts.yMax);
  const t = opts.log ? Math.log10 : (v) => v;
  const yl = t(lo),
    yh = t(hi),
    pad = (yh - yl) * 0.06 || 0.1;
  const Y = (v) => M.t + ih - ((t(v) - yl + pad) / (yh - yl + 2 * pad)) * ih;

  const g = [`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`];

  (opts.bands || []).forEach(([a, b]) => {
    const ta = Math.max(a, x0),
      tb = Math.min(b, x1);
    if (tb <= x0 || ta >= x1) return;
    g.push(
      `<rect x="${X(ta).toFixed(1)}" y="${M.t}" width="${Math.max(0.6, X(tb) - X(ta)).toFixed(1)}" height="${ih}" fill="rgba(224,82,82,0.10)"/>`,
    );
  });

  const ticks = opts.log
    ? Array.from({ length: Math.ceil(yh) - Math.floor(yl) + 1 }, (_, i) => Math.pow(10, Math.floor(yl) + i)).filter(
        (v) => v >= lo / 2 && v <= hi * 1.5,
      )
    : Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  ticks.forEach((v) => {
    const y = Y(v).toFixed(1);
    g.push(`<line x1="${M.l}" x2="${W - M.r}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="1"/>`);
    g.push(`<text class="ax" x="${M.l - 8}" y="${y}" text-anchor="end" dominant-baseline="middle">${opts.yFmt(v)}</text>`);
  });
  if (opts.hline !== undefined) {
    const y = Y(opts.hline).toFixed(1);
    g.push(`<line x1="${M.l}" x2="${W - M.r}" y1="${y}" y2="${y}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>`);
  }

  const nx = Math.min(6, xs.length);
  for (let i = 0; i < nx; i++) {
    const v = xs[Math.round((i * (xs.length - 1)) / (nx - 1))];
    g.push(`<text class="ax" x="${X(v).toFixed(1)}" y="${H - 8}" text-anchor="middle">${opts.xFmt(v)}</text>`);
  }

  opts.series.forEach((s) => {
    let d = "";
    for (let i = 0; i < s.y.length; i++) {
      const v = s.y[i];
      if (!Number.isFinite(v) || (opts.log && v <= 0)) continue;
      d += (d ? "L" : "M") + X(xs[i]).toFixed(1) + " " + Y(v).toFixed(1);
    }
    g.push(
      `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" stroke-linejoin="round" stroke-linecap="round"${s.dash ? ` stroke-dasharray="${s.dash}"` : ""}/>`,
    );
  });

  g.push(`<line id="cx" x1="0" x2="0" y1="${M.t}" y2="${M.t + ih}" stroke="var(--muted)" stroke-width="1" opacity="0"/>`);
  g.push("</svg>");
  host.innerHTML = g.join("") + `<div class="tip" hidden></div>`;

  // crosshair
  const svg = host.querySelector("svg"),
    line = host.querySelector("#cx"),
    tip = host.querySelector(".tip");
  const move = (ev) => {
    const box = host.getBoundingClientRect();
    const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - box.left) / box.width;
    const vx = x0 + px * (x1 - x0);
    let k = 0,
      best = Infinity;
    for (let i = 0; i < xs.length; i++) {
      const dd = Math.abs(xs[i] - vx);
      if (dd < best) (best = dd), (k = i);
    }
    const sx = X(xs[k]);
    line.setAttribute("x1", sx);
    line.setAttribute("x2", sx);
    line.setAttribute("opacity", "1");
    tip.hidden = false;
    tip.innerHTML =
      `<b>${opts.tipX(xs[k], k)}</b>` +
      opts.series.map((s) => `<span><i style="background:${s.color}"></i>${s.label} <b>${opts.tipY(s.y[k])}</b></span>`).join("");
    const left = Math.min(Math.max((sx / W) * box.width - 70, 4), box.width - 150);
    tip.style.left = left + "px";
  };
  const leave = () => {
    line.setAttribute("opacity", "0");
    tip.hidden = true;
  };
  svg.addEventListener("mousemove", move);
  svg.addEventListener("touchmove", move, { passive: true });
  svg.addEventListener("mouseleave", leave);
  svg.addEventListener("touchend", leave);
}

/* -------------------------------------------------------------- render -- */

const COL = { policy: "#3987e5", base: "#c98500", contrib: "#55617a", ref: "#199e70" };

function policyLabel() {
  if (S.lev === 0) return "100 % 1× 70/30 (aucun levier)";
  const g = S.gate ? "avec filtre de tendance" : "sans filtre";
  return `${S.lev} % du flux en 2× ${g}`;
}

function renderHero() {
  const sig = D.signal;
  const on = sig.state === "ON";
  document.body.classList.toggle("state-on", on);
  document.body.classList.toggle("state-off", !on);
  $("asof").textContent = "données Bloomberg au " + sig.asof;
  $("verdict").innerHTML = `<span class="flap ${on ? "on" : "off"}">${on ? "Tout investir" : "Défense"}</span>`;
  $("verdict-sub").textContent =
    `SPX ${sig.spx.toLocaleString("fr-FR")} · moyenne 200 j ${sig.sma200.toLocaleString("fr-FR")} · ` +
    `${sig.gap_pct > 0 ? "+" : ""}${String(sig.gap_pct).replace(".", ",")} % · dans cet état depuis ${sig.days_in_state} jours`;
}

/** The "today at a glance" strip — context for mid-day logins, no action attached. */
function renderPulse(live) {
  const sig = D.signal;
  const ind = D.indicators || {};
  const on = sig.state === "ON";
  const fr = (v, dp = 0) =>
    v === undefined || v === null ? "—" : v.toLocaleString("fr-FR", { maximumFractionDigits: dp });
  const spreadBad = ind.spread_bp_last > 25;
  const liveGap = live ? (live / sig.flip_level - 1) * 100 : null;
  const flipSub =
    liveGap !== null
      ? `SPX maintenant ${fr(Math.round(live))} · marge ${liveGap > 0 ? "+" : ""}${liveGap.toFixed(1).replace(".", ",")} % <span class="live-dot" title="cours en direct"></span>`
      : on
        ? `marge actuelle : +${String(sig.gap_pct).replace(".", ",")} % au-dessus`
        : `il manque ${String(-sig.gap_pct).replace(".", ",")} % pour recroiser`;
  const tiles = [
    {
      k: "Le signal bascule si…",
      v: on ? `SPX < ${fr(Math.round(sig.flip_level))}` : `SPX > ${fr(Math.round(sig.flip_level))}`,
      s: flipSub,
      tone: on ? "good" : "bad",
    },
    {
      k: "VIX (peur du marché)",
      v: fr(ind.vix, 1),
      s:
        `centile ${Math.round(ind.vix_pctl_1y)} sur 1 an — ` +
        (ind.vix_pctl_1y < 25 ? "marché calme" : ind.vix_pctl_1y > 75 ? "marché tendu" : "normal"),
      tone: ind.vix_pctl_1y > 75 ? "bad" : "",
    },
    {
      k: "Spread ESE (hier, clôture)",
      v: fr(ind.spread_bp_last, 1) + " pb",
      s: spreadBad
        ? "au-dessus de la garde 25 pb : on remet l'achat à demain"
        : `sous la garde de 25 pb (médiane 60 j : ${fr(ind.spread_bp_med_60d, 1)} pb)`,
      tone: spreadBad ? "warn" : "good",
    },
    {
      k: "Dans cet état depuis",
      v: `${sig.days_in_state} j`,
      s: `depuis le ${sig.since}`,
      tone: "",
    },
    {
      k: "SPX sur 1 mois",
      v: (ind.spx_chg_1m > 0 ? "+" : "") + String(ind.spx_chg_1m).replace(".", ",") + " %",
      s: "tendance courte — aucune action liée",
      tone: ind.spx_chg_1m >= 0 ? "good" : "bad",
    },
  ];
  const host = $("pulse");
  host.innerHTML = "";
  tiles.forEach((t) => {
    const n = el("div", "stat " + t.tone);
    n.appendChild(el("span", "stat-k", t.k));
    n.appendChild(el("span", "stat-v mono", t.v));
    n.appendChild(el("span", "stat-s", t.s));
    host.appendChild(n);
  });
}

function renderPolicy() {
  const w = currentWeights();
  const sc = score(w);
  const base = score({ ese: 1 });

  const dates = D.sleeves.dates;
  const [r0, r1] = effRange();
  $("policy-name").textContent = policyLabel();
  $("policy-sub").textContent =
    `${sc.n} fenêtres de ${S.horizon} an${S.horizon > 1 ? "s" : ""} · ` +
    `période ${dates[r0].slice(0, 7)} → ${dates[r1].slice(0, 7)}${S.range ? " (personnalisée)" : ""} · ` +
    `versements de ${S.budget.toLocaleString("fr-FR")} €/mois`;

  if (sc.n === 0) {
    $("stats").innerHTML = "";
    $("downside").textContent = `Période trop courte pour un horizon de ${S.horizon} an${S.horizon > 1 ? "s" : ""} — élargis la plage ou raccourcis l'horizon.`;
    $("dist-chart").innerHTML = "";
    $("dist-legend").textContent = "";
    return { sc, base };
  }

  const cells = [
    ["Rendement annuel médian", ann(sc.median), `1× : ${ann(base.median)}`, sc.median >= base.median ? "good" : "bad"],
    ["Rendement annuel moyen", pct(sc.meanIrr, 1), `1× : ${pct(base.meanIrr, 1)}`, sc.meanIrr >= base.meanIrr ? "good" : "bad"],
    ["Rendement annuel défavorable (p5)", ann(sc.p5), `1× : ${ann(base.p5)}`, sc.p5 >= base.p5 ? "good" : "bad"],
    ["Pire rendement annuel", ann(sc.worst), `1× : ${ann(base.worst)}`, sc.worst >= base.worst ? "good" : "bad"],
    ["Finir sous son argent", pct(sc.pLoss), `1× : ${pct(base.pLoss)}`, sc.pLoss <= base.pLoss ? "good" : "bad"],
    ["Pire baisse subie", pct(sc.worstMdd), `1× : ${pct(base.worstMdd)}`, sc.worstMdd >= base.worstMdd ? "good" : "bad"],
  ];
  const host = $("stats");
  host.innerHTML = "";
  cells.forEach(([k, v, sub, tone]) => {
    const n = el("div", "stat " + tone);
    n.appendChild(el("span", "stat-k", k));
    n.appendChild(el("span", "stat-v mono", v));
    n.appendChild(el("span", "stat-s mono", sub));
    host.appendChild(n);
  });

  const médEur = Math.round(sc.median * S.budget * S.horizon * 12);
  const pireEur = Math.round(sc.worst * S.budget * S.horizon * 12);
  const versé = (S.budget * S.horizon * 12).toLocaleString("fr-FR");
  $("downside").innerHTML =
    `Sur ${versé} € versés en ${S.horizon} an${S.horizon > 1 ? "s" : ""} : médiane <b>${eur(médEur)}</b> ` +
    `(soit <b>${ann(sc.median)}</b> annualisés), mais la pire fenêtre de cette période finit à <b>${eur(pireEur)}</b> ` +
    `(<b>${ann(sc.worst)}</b>/an), après une baisse de <b>${pct(sc.worstMdd)}</b> en cours de route.`;

  // distribution — same windows, expressed in annualized return
  const sortedP = Array.from(sc.mults).sort((a, b) => a - b).map((m) => irr(m, S.horizon));
  const sortedB = Array.from(base.mults).sort((a, b) => a - b).map((m) => irr(m, S.horizon));
  const x = sortedP.map((_, i) => (100 * i) / Math.max(1, sortedP.length - 1));
  chart($("dist-chart"), {
    x,
    height: 220,
    yFmt: (v) => Math.round(v * 100) + " %",
    xFmt: (v) => Math.round(v) + " %",
    hline: 0,
    series: [
      { label: policyLabel(), color: COL.policy, y: sortedP },
      { label: "100 % 1× S&P", color: COL.base, y: sortedB },
    ],
    tipX: (v) => "centile " + Math.round(v),
    tipY: (v) => (Number.isFinite(v) ? (v * 100).toFixed(1) + " %/an" : "—"),
  });
  $("dist-legend").innerHTML =
    `<span class="k" style="background:${COL.policy}"></span>${policyLabel()} &nbsp; ` +
    `<span class="k" style="background:${COL.base}"></span>100 % 1× S&P &nbsp; · ligne pointillée = 0 %/an`;

  return { sc, base };
}

function renderMenu() {
  const list = presets();
  const exact = list.some((p) => p.lev === S.lev && (S.lev === 0 || p.gate === S.gate));
  const rows = exact
    ? list
    : [{ label: "votre réglage — " + policyLabel(), weights: currentWeights(), lev: S.lev, gate: S.gate }, ...list];

  const scored = rows.map((p) => ({ p, s: score(p.weights) }));
  scored.sort((a, b) => {
    if (a.s.n === 0) return 1;
    if (b.s.n === 0) return -1;
    if (S.sortCol === "label") return S.sortDir * a.p.label.localeCompare(b.p.label);
    return S.sortDir * (a.s[S.sortCol] - b.s[S.sortCol]);
  });

  document.querySelectorAll("#menu th").forEach((th) => {
    const c = th.dataset.col;
    th.classList.toggle("sorted", c === S.sortCol);
    th.textContent = (th.dataset.label || th.textContent) + (c === S.sortCol ? (S.sortDir < 0 ? " ▼" : " ▲") : "");
  });

  const tb = $("menu").querySelector("tbody");
  tb.innerHTML = "";
  scored.forEach(({ p, s }) => {
    const tr = el("tr");
    if (p.lev === S.lev && (S.lev === 0 ? p.lev === 0 : p.gate === S.gate)) tr.className = "cur";
    tr.innerHTML =
      `<td>${p.label}</td>` +
      (s.n === 0
        ? '<td colspan="6" class="mono">période trop courte</td>'
        : `<td class="mono">${ann(s.median)}</td><td class="mono">${pct(s.meanIrr, 1)}</td>` +
          `<td class="mono">${ann(s.p5)}</td><td class="mono">${ann(s.worst)}</td>` +
          `<td class="mono">${pct(s.pLoss)}</td><td class="mono">${pct(s.worstMdd)}</td>`);
    tr.tabIndex = 0;
    const load = () => {
      if (p.lev < 0) return; // the 1x reference row is not a selectable setting
      S.lev = p.lev;
      if (p.lev > 0) S.gate = p.gate;
      syncControls();
      renderAll();
    };
    tr.addEventListener("click", load);
    tr.addEventListener("keydown", (e) => e.key === "Enter" && load());
    tb.appendChild(tr);
  });
}

function renderPaths() {
  const dates = D.sleeves.dates;
  const [r0, r1] = effRange();
  const from = r0;
  const len = Math.max(24, r1 - r0 + 1);

  const w = currentWeights();
  const pol = run(w, from, len, S.budget);
  const bas = run({ ese: 1 }, from, len, S.budget);
  const xs = Array.from({ length: len }, (_, i) => new Date(dates[from + i]).getTime());
  const contrib = Array.from({ length: len }, (_, i) => (i + 1) * S.budget);

  const bands = (D.off_periods || [])
    .map(([a, b]) => [new Date(a).getTime(), new Date(b).getTime()])
    .filter(() => S.gate && S.lev > 0);

  // main policy + 1x reference by default; ONLY the ticked ones when comparing
  const plist = presets();
  const series = [];
  const finals = [];
  if (S.compare.length) {
    S.compare.forEach((pi, k) => {
      const p = plist[pi];
      if (!p) return;
      const r = run(p.weights, from, len, S.budget);
      series.push({ label: p.label, color: COMP_COLORS[k], y: Array.from(r.path), width: 2.4 });
      finals.push([p.label, COMP_COLORS[k], r.final]);
    });
  } else {
    series.push({ label: policyLabel(), color: COL.policy, y: Array.from(pol.path), width: 2.4 });
    series.push({ label: "100 % 1× S&P", color: COL.base, y: Array.from(bas.path), width: 1.4 });
    finals.push([policyLabel(), COL.policy, pol.final], ["100 % 1× S&P", COL.base, bas.final]);
  }
  series.push({ label: "versé", color: COL.contrib, y: contrib, width: 1.5, dash: "4 4" });

  chart($("equity-chart"), {
    x: xs,
    height: 250,
    log: true,
    bands,
    yFmt: eur,
    xFmt: (v) => new Date(v).getFullYear(),
    series,
    tipX: (v) => new Date(v).toLocaleDateString("fr-FR", { month: "short", year: "numeric" }),
    tipY: (v) => eur(v),
  });
  attachTimeBrush($("equity-chart"), xs[0], xs[len - 1]);
  syncBrushUI();
  $("equity-legend").innerHTML =
    finals.map(([lb, c, f]) => `<span class="k" style="background:${c}"></span>${lb} → <b>${eur(f)}</b>`).join(" &nbsp; ") +
    ` &nbsp; <span class="k" style="background:${COL.contrib}"></span>versé → <b>${eur(contrib[len - 1])}</b>`;

  const dd = (p) => {
    let peak = 0;
    return Array.from(p, (v) => {
      peak = Math.max(peak, v);
      return v / peak - 1;
    });
  };
  chart($("dd-chart"), {
    x: xs,
    height: 140,
    bands,
    yFmt: (v) => Math.round(v * 100) + " %",
    xFmt: (v) => new Date(v).getFullYear(),
    yMax: 0,
    series: [
      { label: policyLabel(), color: COL.policy, y: dd(pol.path) },
      { label: "1× S&P", color: COL.base, y: dd(bas.path) },
    ],
    tipX: (v) => new Date(v).toLocaleDateString("fr-FR", { month: "short", year: "numeric" }),
    tipY: (v) => (v * 100).toFixed(1) + " %",
  });
  attachTimeBrush($("dd-chart"), xs[0], xs[len - 1]);
}

function renderGate() {
  const g = D.gate_series;
  const xs = g.dates.map((d) => new Date(d).getTime());
  chart($("gate-chart"), {
    x: xs,
    height: 170,
    bands: (D.off_periods || []).map(([a, b]) => [new Date(a).getTime(), new Date(b).getTime()]),
    yFmt: (v) => Math.round(v).toLocaleString("fr-FR"),
    xFmt: (v) => new Date(v).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" }),
    series: [
      { label: "SPX", color: COL.policy, y: g.spx },
      { label: "200 j", color: COL.ref, y: g.sma, width: 1.6 },
    ],
    tipX: (v) => new Date(v).toLocaleDateString("fr-FR"),
    tipY: (v) => Math.round(v).toLocaleString("fr-FR"),
  });
  attachTimeBrush($("gate-chart"), xs[0], xs[xs.length - 1]);
}

function renderAll() {
  renderHero();
  renderPolicy();
  renderMenu();
  renderPaths();
}

/* ------------------------------------------------------- period brush -- */

const CH = { ML: 54, MR: 14, W: 960 }; // must match chart() margins

function hostTime(host, clientX, t0, t1) {
  const rect = host.getBoundingClientRect();
  const fx = ((clientX - rect.left) / rect.width) * CH.W;
  const f = Math.max(0, Math.min(1, (fx - CH.ML) / (CH.W - CH.ML - CH.MR)));
  return { f, t: t0 + f * (t1 - t0) };
}

/** First sleeve month ending at/after timestamp t. */
function monthIdxAt(t) {
  const dates = D.sleeves.dates;
  let lo = 0,
    hi = dates.length - 1;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (new Date(dates[m]).getTime() < t) lo = m + 1;
    else hi = m;
  }
  return lo;
}

function setRangeTimes(ta, tb) {
  const [elo, ehi] = eraRange();
  let lo = monthIdxAt(Math.min(ta, tb));
  let hi = Math.max(lo, monthIdxAt(Math.max(ta, tb)));
  if (hi - lo < 24) {
    const mid = (lo + hi) >> 1;
    lo = Math.max(elo, Math.min(ehi - 24, mid - 12));
    hi = lo + 24;
  }
  S.range = lo === elo && hi === ehi ? null : [lo, hi];
  syncControls();
  renderAll();
}

/**
 * Plotly-style period manipulation on a chart: drag = select, wheel = zoom
 * around the cursor, double-click = full period. Attached once per host
 * (listeners persist; chart() wipes innerHTML but not host listeners).
 */
function attachTimeBrush(host, t0, t1) {
  let st = host.__brush;
  if (!st) {
    st = host.__brush = { t0, t1, drag: null, sel: document.createElement("div") };
    st.sel.className = "sel";
    st.sel.hidden = true;
    const toPct = (t) => ((CH.ML + ((t - st.t0) / (st.t1 - st.t0)) * (CH.W - CH.ML - CH.MR)) / CH.W) * 100;
    const paint = (cur) => {
      const a = Math.min(st.drag, cur),
        b = Math.max(st.drag, cur);
      st.sel.hidden = false;
      st.sel.style.left = toPct(a) + "%";
      st.sel.style.width = Math.max(0.3, toPct(b) - toPct(a)) + "%";
    };
    const finish = (cur) => {
      const a = st.drag;
      st.drag = null;
      st.sel.hidden = true;
      if (Math.abs(cur - a) > 45 * 864e5) setRangeTimes(a, cur);
    };

    host.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "touch" || e.button !== 0) return;
      st.drag = hostTime(host, e.clientX, st.t0, st.t1).t;
    });
    // move/up on window: no pointer capture (it ate pointerup in some setups)
    window.addEventListener("pointermove", (e) => {
      if (st.drag !== null) paint(hostTime(host, e.clientX, st.t0, st.t1).t);
    });
    window.addEventListener("pointerup", (e) => {
      if (st.drag !== null) finish(hostTime(host, e.clientX, st.t0, st.t1).t);
    });
    host.addEventListener("dblclick", () => {
      S.range = null;
      syncControls();
      renderAll();
    });
    host.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const { f } = hostTime(host, e.clientX, st.t0, st.t1);
        const [elo, ehi] = eraRange();
        const [r0, r1] = effRange();
        let span = r1 - r0 + 1;
        span = Math.max(24, Math.min(ehi - elo + 1, Math.round(span * (e.deltaY > 0 ? 1.3 : 0.77))));
        const center = r0 + f * (r1 - r0);
        let lo = Math.round(center - f * span);
        lo = Math.max(elo, Math.min(ehi - span + 1, lo));
        const hi = lo + span - 1;
        S.range = lo === elo && hi === ehi ? null : [lo, hi];
        syncControls();
        renderAll();
      },
      { passive: false },
    );
  }
  st.t0 = t0;
  st.t1 = t1;
  host.appendChild(st.sel); // chart() wiped the host — put the overlay back
}

/** Reflect the effective period into the date fields and reset button. */
function syncBrushUI() {
  const dates = D.sleeves.dates;
  const [r0, r1] = effRange();
  const bf = $("brush-from"),
    bt = $("brush-to");
  const min = dates[0].slice(0, 7),
    max = dates[dates.length - 1].slice(0, 7);
  if (bf.min !== min) {
    bf.min = min;
    bf.max = max;
    bt.min = min;
    bt.max = max;
  }
  if (document.activeElement !== bf) bf.value = dates[r0].slice(0, 7);
  if (document.activeElement !== bt) bt.value = dates[r1].slice(0, 7);
  $("brush-reset").style.visibility = S.range ? "visible" : "hidden";
}

/* ------------------------------------------------------------ live quote -- */

/** Live SPX quote from stooq (free, no key). null on any failure — the page
 *  silently falls back to the last Bloomberg close. */
async function liveQuote() {
  try {
    const r = await fetch("https://stooq.com/q/l/?s=%5Espx&f=sd2t2c&h&e=csv", { cache: "no-store" });
    const rows = (await r.text()).trim().split("\n");
    const close = parseFloat(rows[1].split(",")[3]);
    return Number.isFinite(close) && close > 1000 ? close : null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------ controls -- */

const COMP_COLORS = ["#d95926", "#199e70"]; // tick 1, tick 2

/** The comparison chips under the trajectory chart: tick up to 2 strategies. */
function renderCompare() {
  const host = $("compare-chips");
  host.innerHTML = "";
  presets().forEach((p, i) => {
    if (p.lev < 0) return; // the 1x reference is always plotted already
    const k = S.compare.indexOf(i);
    const b = el("button", "chip" + (k >= 0 ? ` on c${k}` : ""), p.label);
    b.type = "button";
    b.addEventListener("click", () => {
      if (k >= 0) S.compare.splice(k, 1);
      else {
        S.compare.push(i);
        if (S.compare.length > 2) S.compare.shift();
      }
      renderCompare();
      renderPaths();
    });
    host.appendChild(b);
  });
}

function syncControls() {
  $("budget").value = S.budget;
  $("budget-out").textContent = S.budget.toLocaleString("fr-FR") + " €";
  $("lev").value = S.lev;
  $("lev-out").textContent = S.lev + " %";
  document.querySelectorAll("#gate-seg button").forEach((b) => b.classList.toggle("on", +b.dataset.gate === S.gate));
  document.querySelectorAll("#hz-seg button").forEach((b) => b.classList.toggle("on", +b.dataset.h === S.horizon));
  document
    .querySelectorAll("#era-seg button")
    .forEach((b) => b.classList.toggle("on", !S.range && b.dataset.era === S.era));
  $("gate-seg").classList.toggle("muted", S.lev === 0);
}

function wire() {
  let t = null;
  const debounce = (fn) => {
    clearTimeout(t);
    t = setTimeout(fn, 60);
  };
  $("budget").addEventListener("input", (e) => {
    S.budget = +e.target.value;
    syncControls();
    debounce(renderAll);
  });
  $("lev").addEventListener("input", (e) => {
    S.lev = +e.target.value;
    syncControls();
    debounce(renderAll);
  });
  $("gate-seg").addEventListener("click", (e) => {
    if (!e.target.dataset.gate) return;
    S.gate = +e.target.dataset.gate;
    syncControls();
    renderAll();
  });
  $("hz-seg").addEventListener("click", (e) => {
    if (!e.target.dataset.h) return;
    S.horizon = +e.target.dataset.h;
    syncControls();
    renderAll();
  });
  $("era-seg").addEventListener("click", (e) => {
    if (!e.target.dataset.era) return;
    S.era = e.target.dataset.era;
    S.range = null; // an era preset clears any custom drag range
    syncControls();
    renderAll();
  });

  // period brush: date fields (drag on the chart also sets these)
  const monthToIdx = (val, fallback) => {
    const i = D.sleeves.dates.findIndex((d) => d.slice(0, 7) === val);
    return i < 0 ? fallback : i;
  };
  const brushInput = (e) => {
    const [elo, ehi] = eraRange();
    let lo = monthToIdx($("brush-from").value, elo);
    let hi = monthToIdx($("brush-to").value, ehi);
    const minSpan = Math.min(S.horizon * 12, ehi - elo);
    if (hi - lo < minSpan) {
      if (e.target.id === "brush-from") hi = Math.min(ehi, lo + minSpan);
      else lo = Math.max(elo, hi - minSpan);
    }
    S.range = lo === elo && hi === ehi ? null : [lo, hi];
    syncControls();
    syncBrushUI();
    debounce(renderAll);
  };
  $("brush-from").addEventListener("change", brushInput);
  $("brush-to").addEventListener("change", brushInput);
  $("brush-reset").addEventListener("click", () => {
    S.range = null;
    syncControls();
    renderAll();
  });

  // sortable menu columns
  document.querySelectorAll("#menu th").forEach((th) => {
    th.dataset.label = th.textContent;
    th.addEventListener("click", () => {
      if (S.sortCol === th.dataset.col) S.sortDir *= -1;
      else {
        S.sortCol = th.dataset.col;
        S.sortDir = th.dataset.col === "label" || th.dataset.col === "pLoss" ? 1 : -1;
      }
      renderMenu();
    });
  });

  addEventListener("resize", () => debounce(renderAll));
}

/* ---------------------------------------------------------------- boot -- */

fetch("data.json")
  .then((r) => r.json())
  .then((d) => {
    D = d;
    R = {};
    for (const k in d.sleeves.r) R[k] = Float64Array.from(d.sleeves.r[k]);
    // theme toggle (the head inline script already applied the stored theme)
    const tg = $("theme-toggle");
    const setTheme = (t) => {
      document.documentElement.dataset.theme = t;
      localStorage.setItem("theme", t);
      tg.textContent = t === "light" ? "☾" : "☀";
      tg.title = t === "light" ? "passer en mode sombre" : "passer en mode clair";
    };
    setTheme(document.documentElement.dataset.theme || "dark");
    tg.addEventListener("click", () =>
      setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"),
    );
    $("foot").textContent =
      `données Bloomberg au ${d.generated} · ${d.sleeves.dates.length} mois (${d.sleeves.dates[0]} → ${d.sleeves.dates.at(-1)}) · ` +
      `frais ${(d.sleeves.fee * 100).toFixed(2)} % par ordre · tout est recalculé dans le navigateur`;
    syncControls();
    wire();
    renderAll();
    renderPulse();
    renderGate();
    renderCompare();
    liveQuote().then((q) => {
      if (q) renderPulse(q);
    });
  })
  .catch((e) => {
    $("verdict-sub").textContent = "données indisponibles : " + e.message;
  });
