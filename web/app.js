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
  era: "all",
};

const ERAS = {
  all: { label: "1989–2026", from: null },
  bear: { label: "débuts 1989–2008", from: null, maxStart: "2009-01-01" },
  bull: { label: "débuts 2009–", from: "2009-01-01" },
};

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
  const s = Float64Array.from(a).sort();
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const quantile = (a, q) => {
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

/** Start indices allowed by the selected era for a window of `n` months. */
function starts(n) {
  const dates = D.sleeves.dates;
  const last = dates.length - n;
  const out = [];
  for (let i = 0; i <= last; i++) {
    if (S.era === "bull" && dates[i] < ERAS.bull.from) continue;
    if (S.era === "bear" && dates[i] >= ERAS.bear.maxStart) continue;
    out.push(i);
  }
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
  return {
    n: idx.length,
    mults,
    mdds,
    median: median(mults),
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
  $("asof").textContent = "au " + sig.asof;
  $("verdict").innerHTML = `<span class="flap ${on ? "on" : "off"}">${on ? "RISK ON" : "RISK OFF"}</span>`;
  $("verdict-sub").textContent = `SPX ${sig.spx.toLocaleString("fr-FR")} · 200 j ${sig.sma200.toLocaleString("fr-FR")} · écart ${sig.gap_pct > 0 ? "+" : ""}${sig.gap_pct} % · depuis le ${sig.since}`;
  const levEur = Math.round((S.budget * S.lev) / 100);
  const oneEur = S.budget - levEur;
  const parts = [];
  if (levEur > 0)
    parts.push(
      on || !S.gate
        ? `<b>${levEur.toLocaleString("fr-FR")} €</b> en CL2/LQQ (70/30)`
        : `<b>${levEur.toLocaleString("fr-FR")} €</b> au monétaire — et la poche 2× déjà investie y reste`,
    );
  if (oneEur > 0) parts.push(`<b>${oneEur.toLocaleString("fr-FR")} €</b> en ESE (1×)`);
  $("verdict-action").innerHTML = "Ce mois-ci : " + parts.join(" · ") + ".";
}

function renderPolicy() {
  const w = currentWeights();
  const sc = score(w);
  const base = score({ ese: 1 });

  $("policy-name").textContent = policyLabel();
  $("policy-sub").textContent = `${sc.n} fenêtres de ${S.horizon} an${S.horizon > 1 ? "s" : ""} · ${ERAS[S.era].label} · versements de ${S.budget.toLocaleString("fr-FR")} €/mois`;

  const cells = [
    ["Médiane", mult(sc.median), `1× : ${mult(base.median)}`, sc.median >= base.median ? "good" : "bad"],
    ["Cas défavorable (p5)", mult(sc.p5), `1× : ${mult(base.p5)}`, sc.p5 >= base.p5 ? "good" : "bad"],
    ["Pire fenêtre", mult(sc.worst), `1× : ${mult(base.worst)}`, sc.worst >= base.worst ? "good" : "bad"],
    ["Finir sous son argent", pct(sc.pLoss), `1× : ${pct(base.pLoss)}`, sc.pLoss <= base.pLoss ? "good" : "bad"],
    ["Baisse médiane subie", pct(sc.medMdd), `1× : ${pct(base.medMdd)}`, sc.medMdd >= base.medMdd ? "good" : "bad"],
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
    `Sur ${versé} € versés en ${S.horizon} an${S.horizon > 1 ? "s" : ""} : médiane <b>${eur(médEur)}</b>, ` +
    `mais la pire fenêtre de cette époque finit à <b>${eur(pireEur)}</b> — ` +
    `soit <b>${pct(sc.worst - 1, 0)}</b> sur l'argent versé, après une baisse de <b>${pct(sc.worstMdd)}</b> en cours de route.`;

  // distribution
  const sortedP = Float64Array.from(sc.mults).sort();
  const sortedB = Float64Array.from(base.mults).sort();
  const x = Array.from(sortedP, (_, i) => (100 * i) / Math.max(1, sortedP.length - 1));
  chart($("dist-chart"), {
    x,
    height: 280,
    yFmt: (v) => v.toFixed(2) + "×",
    xFmt: (v) => Math.round(v) + " %",
    hline: 1,
    yMin: Math.min(1, sortedP[0]) * 0.98,
    series: [
      { label: policyLabel(), color: COL.policy, y: Array.from(sortedP) },
      { label: "100 % 1× S&P", color: COL.base, y: Array.from(sortedB) },
    ],
    tipX: (v) => "centile " + Math.round(v),
    tipY: (v) => (Number.isFinite(v) ? v.toFixed(2) + "×" : "—"),
  });
  $("dist-legend").innerHTML =
    `<span class="k" style="background:${COL.policy}"></span>${policyLabel()} &nbsp; ` +
    `<span class="k" style="background:${COL.base}"></span>100 % 1× S&P &nbsp; · ligne pointillée = seuil de perte`;

  return { sc, base };
}

function renderMenu() {
  const list = presets();
  const exact = list.some((p) => p.lev === S.lev && (S.lev === 0 || p.gate === S.gate));
  const rows = exact
    ? list
    : [{ label: "votre réglage — " + policyLabel(), weights: currentWeights(), lev: S.lev, gate: S.gate }, ...list];

  const tb = $("menu").querySelector("tbody");
  tb.innerHTML = "";
  rows.forEach((p) => {
    const s = score(p.weights);
    const tr = el("tr");
    if (p.lev === S.lev && (S.lev === 0 ? p.lev === 0 : p.gate === S.gate)) tr.className = "cur";
    tr.innerHTML =
      `<td>${p.label}</td><td class="mono">${mult(s.median)}</td><td class="mono">${mult(s.p5)}</td>` +
      `<td class="mono">${mult(s.worst)}</td><td class="mono">${pct(s.pLoss)}</td><td class="mono">${pct(s.worstMdd)}</td>`;
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
  let from = 0;
  if (S.era === "bull") from = dates.findIndex((d) => d >= ERAS.bull.from);
  const n = dates.length - from;
  const nEnd = S.era === "bear" ? dates.findIndex((d) => d >= "2009-01-01") - from : n;
  const len = Math.max(24, nEnd);

  const w = currentWeights();
  const pol = run(w, from, len, S.budget);
  const bas = run({ ese: 1 }, from, len, S.budget);
  const xs = Array.from({ length: len }, (_, i) => new Date(dates[from + i]).getTime());
  const contrib = Array.from({ length: len }, (_, i) => (i + 1) * S.budget);

  const bands = (D.off_periods || [])
    .map(([a, b]) => [new Date(a).getTime(), new Date(b).getTime()])
    .filter(() => S.gate && S.lev > 0);

  chart($("equity-chart"), {
    x: xs,
    height: 300,
    log: true,
    bands,
    yFmt: eur,
    xFmt: (v) => new Date(v).getFullYear(),
    series: [
      { label: policyLabel(), color: COL.policy, y: Array.from(pol.path) },
      { label: "100 % 1× S&P", color: COL.base, y: Array.from(bas.path) },
      { label: "versé", color: COL.contrib, y: contrib, width: 1.5, dash: "4 4" },
    ],
    tipX: (v) => new Date(v).toLocaleDateString("fr-FR", { month: "short", year: "numeric" }),
    tipY: (v) => eur(v),
  });
  $("equity-legend").innerHTML =
    `<span class="k" style="background:${COL.policy}"></span>${policyLabel()} → <b>${eur(pol.final)}</b> &nbsp; ` +
    `<span class="k" style="background:${COL.base}"></span>1× S&P → <b>${eur(bas.final)}</b> &nbsp; ` +
    `<span class="k" style="background:${COL.contrib}"></span>versé → <b>${eur(contrib[len - 1])}</b>`;

  const dd = (p) => {
    let peak = 0;
    return Array.from(p, (v) => {
      peak = Math.max(peak, v);
      return v / peak - 1;
    });
  };
  chart($("dd-chart"), {
    x: xs,
    height: 190,
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
}

function renderGate() {
  const g = D.gate_series;
  const xs = g.dates.map((d) => new Date(d).getTime());
  chart($("gate-chart"), {
    x: xs,
    height: 220,
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
}

function renderAll() {
  renderHero();
  renderPolicy();
  renderMenu();
  renderPaths();
}

/* ------------------------------------------------------------ controls -- */

function syncControls() {
  $("budget").value = S.budget;
  $("budget-out").textContent = S.budget.toLocaleString("fr-FR") + " €";
  $("lev").value = S.lev;
  $("lev-out").textContent = S.lev + " %";
  document.querySelectorAll("#gate-seg button").forEach((b) => b.classList.toggle("on", +b.dataset.gate === S.gate));
  document.querySelectorAll("#hz-seg button").forEach((b) => b.classList.toggle("on", +b.dataset.h === S.horizon));
  document.querySelectorAll("#era-seg button").forEach((b) => b.classList.toggle("on", b.dataset.era === S.era));
  $("gate-seg").classList.toggle("muted", S.lev === 0);
}

function wire() {
  let t = null;
  const debounce = (fn) => {
    clearTimeout(t);
    t = setTimeout(fn, 90);
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
    syncControls();
    renderAll();
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
    $("foot").textContent =
      `données Bloomberg au ${d.generated} · ${d.sleeves.dates.length} mois (${d.sleeves.dates[0]} → ${d.sleeves.dates.at(-1)}) · ` +
      `frais ${(d.sleeves.fee * 100).toFixed(2)} % par ordre · tout est recalculé dans le navigateur`;
    syncControls();
    wire();
    renderAll();
    renderGate();
  })
  .catch((e) => {
    $("verdict-sub").textContent = "données indisponibles : " + e.message;
  });
