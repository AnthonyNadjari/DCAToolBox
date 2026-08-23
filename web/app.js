/* Le Signal — renders data.json into the instrument, the gate chart,
   the equity chart and the evidence tables. No dependencies. */

"use strict";

const SERIES = [
  { key: "strategy",   label: "70/30 CL2/LQQ + gate (the plan)", color: "#3987e5" },
  { key: "lev_nogate", label: "70/30 CL2/LQQ, no gate",          color: "#d95926" },
  { key: "mix7030",    label: "70/30 ESE/PUST, unlevered",       color: "#199e70" },
  { key: "ese",        label: "100% ESE",                        color: "#c98500" },
];
const ROLL_NAMES = {
  strategy: "70/30 CL2/LQQ + gate",
  lev_nogate: "70/30 CL2/LQQ, no gate",
  ese: "100% ESE",
};

const fmtEUR = (v) =>
  v >= 1e6 ? (v / 1e6).toFixed(2) + "M €"
           : Math.round(v / 1000) + "k €";
const fmtPct = (v, dp = 1) => (v >= 0 ? "+" : "") + (v * 100).toFixed(dp) + "%";

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
}

/* ---------- generic SVG line chart with crosshair tooltip ---------- */
function lineChart(host, opts) {
  const W = 960, H = opts.height || 300;
  const M = { t: 14, r: 14, b: 26, l: opts.left || 56 };
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const xs = opts.dates.map((d) => new Date(d).getTime());
  const x0 = xs[0], x1 = xs[xs.length - 1];
  const X = (t) => M.l + ((t - x0) / (x1 - x0)) * iw;

  const log = !!opts.log;
  const all = opts.series.flatMap((s) => s.values).filter((v) => v > 0);
  const lo = Math.min(...all), hi = Math.max(...all);
  const ty = log ? Math.log10 : (v) => v;
  const yl = ty(lo), yh = ty(hi), pad = (yh - yl) * 0.05;
  const Y = (v) => M.t + ih - ((ty(v) - yl + pad) / (yh - yl + 2 * pad)) * ih;

  const svg = [`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`];

  // off-period shading
  (opts.offPeriods || []).forEach(([a, b]) => {
    const ta = Math.max(new Date(a).getTime(), x0);
    const tb = Math.min(new Date(b).getTime(), x1);
    if (tb <= x0 || ta >= x1) return;
    svg.push(`<rect x="${X(ta).toFixed(1)}" y="${M.t}" width="${(X(tb) - X(ta)).toFixed(1)}" height="${ih}" fill="rgba(224,82,82,0.07)"/>`);
  });

  // y grid + labels
  const ticks = log
    ? [...Array(Math.ceil(yh) - Math.floor(yl) + 1)].map((_, i) => Math.pow(10, Math.floor(yl) + i)).filter((v) => v >= lo / 2 && v <= hi * 1.5)
    : [...Array(5)].map((_, i) => lo + ((hi - lo) * i) / 4);
  ticks.forEach((v) => {
    const y = Y(v).toFixed(1);
    if (y < M.t || y > M.t + ih) return;
    svg.push(`<line x1="${M.l}" x2="${W - M.r}" y1="${y}" y2="${y}" stroke="#26314a" stroke-width="1"/>`);
    svg.push(`<text x="${M.l - 8}" y="${+y + 4}" text-anchor="end" font-size="11" fill="#5d6778" font-family="IBM Plex Mono,monospace">${opts.fmtY(v)}</text>`);
  });
  // x labels: ~6 year marks
  const span = (x1 - x0) / 3.15e10;
  const step = Math.max(1, Math.round(span / 6));
  for (let yr = new Date(x0).getFullYear() + 1; yr <= new Date(x1).getFullYear(); yr += step) {
    const t = Date.UTC(yr, 0, 1);
    svg.push(`<text x="${X(t).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="#5d6778" font-family="IBM Plex Mono,monospace">${yr}</text>`);
  }

  // series paths
  opts.series.forEach((s) => {
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`).join("");
    svg.push(`<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round"/>`);
  });

  svg.push(`<line id="xhair" x1="0" x2="0" y1="${M.t}" y2="${M.t + ih}" stroke="#8a94a8" stroke-width="1" stroke-dasharray="2,3" visibility="hidden"/>`);
  svg.push("</svg>");
  host.innerHTML = svg.join("");

  const tip = el("div", "tooltip");
  host.appendChild(tip);
  const svgEl = host.querySelector("svg");
  const xh = host.querySelector("#xhair");

  svgEl.addEventListener("pointermove", (ev) => {
    const r = svgEl.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const t = x0 + ((px - M.l) / iw) * (x1 - x0);
    let i = xs.findIndex((v) => v >= t);
    if (i < 0) i = xs.length - 1;
    if (i > 0 && t - xs[i - 1] < xs[i] - t) i -= 1;
    xh.setAttribute("x1", X(xs[i]));
    xh.setAttribute("x2", X(xs[i]));
    xh.setAttribute("visibility", "visible");
    const rows = opts.series
      .filter((s) => !s.noTip)
      .map((s) => `<span class="sw" style="background:${s.color}"></span>${s.tipLabel || s.label}: <strong>${opts.fmtY(s.values[i])}</strong>`)
      .join("<br>");
    tip.innerHTML = `<span class="tt-date">${opts.dates[i]}</span><br>${rows}`;
    tip.style.display = "block";
    const hostR = host.getBoundingClientRect();
    let tx = ((X(xs[i]) / W) * hostR.width) + 14;
    if (tx + tip.offsetWidth > hostR.width - 8) tx -= tip.offsetWidth + 28;
    tip.style.left = tx + "px";
    tip.style.top = "14px";
  });
  svgEl.addEventListener("pointerleave", () => {
    tip.style.display = "none";
    xh.setAttribute("visibility", "hidden");
  });
}

/* ---------- page assembly ---------- */
fetch("data.json").then((r) => r.json()).then((D) => {
  const S = D.signal;
  const on = S.state === "ON";
  document.getElementById("hero").classList.add(on ? "state-on" : "state-off");
  document.getElementById("asof").textContent = `data through ${S.asof} · built ${D.generated}`;
  document.getElementById("verdict").innerHTML = `<span class="flap">RISK ${S.state}</span>`;
  document.getElementById("verdict-sub").innerHTML =
    `SPX <strong>${S.spx.toLocaleString("en-US")}</strong> · 200-DMA <strong>${Math.round(S.sma200).toLocaleString("en-US")}</strong> · ` +
    `<strong>${S.gap_pct >= 0 ? "+" : ""}${S.gap_pct}%</strong> ${S.gap_pct >= 0 ? "above" : "below"} · since ${S.since}`;
  document.getElementById("verdict-action").innerHTML = on
    ? `This month&rsquo;s cash: <em>buy 70% CL2 &middot; 30% LQQ</em> the day it arrives. Hold everything.`
    : `This month&rsquo;s cash and all holdings: <em>move to the money-market ETF</em>. Wait for the recross.`;

  /* gate chart */
  lineChart(document.getElementById("gate-chart"), {
    dates: D.gate_series.dates,
    height: 240,
    fmtY: (v) => Math.round(v).toLocaleString("en-US"),
    offPeriods: offFromSeries(D.gate_series),
    series: [
      { label: "SPX", tipLabel: "SPX", values: D.gate_series.spx, color: "#e8edf5", width: 2 },
      { label: "200-DMA", tipLabel: "200-DMA", values: D.gate_series.sma, color: "#c98500", width: 2 },
    ],
  });

  /* equity chart */
  lineChart(document.getElementById("equity-chart"), {
    dates: D.equity.dates,
    height: 380,
    log: true,
    left: 64,
    fmtY: fmtEUR,
    offPeriods: D.off_periods,
    series: SERIES.map((s) => ({
      label: s.label, tipLabel: s.label.split(" (")[0], values: D.equity[s.key], color: s.color,
    })).concat([{
      label: "contributions", tipLabel: "paid in", values: D.equity.invested,
      color: "#55617a", width: 1.5, dash: "4,4",
    }]),
  });
  const leg = document.getElementById("equity-legend");
  SERIES.forEach((s) => leg.appendChild(el("span", null, `<span class="sw" style="background:${s.color}"></span>${s.label}`)));
  leg.appendChild(el("span", null, `<span class="sw" style="background:#55617a"></span>contributions paid in`));

  /* equity table view */
  const et = document.getElementById("equity-table");
  const step = 24; // every 2 years
  let rows = `<table><thead><tr><th>date</th><th>paid in</th>${SERIES.map((s) => `<th>${s.label.split(" (")[0]}</th>`).join("")}</tr></thead><tbody>`;
  for (let i = D.equity.dates.length - 1; i >= 0; i -= step) {
    rows += `<tr><td>${D.equity.dates[i]}</td><td>${fmtEUR(D.equity.invested[i])}</td>` +
      SERIES.map((s) => `<td>${fmtEUR(D.equity[s.key][i])}</td>`).join("") + "</tr>";
  }
  et.innerHTML = rows + "</tbody></table>";

  /* rolling table */
  const rt = document.getElementById("roll-table");
  let h = `<thead><tr><th>policy</th><th>5y win</th><th>5y median</th><th>5y worst-5%</th><th>10y win</th><th>10y median</th><th>10y worst-5%</th></tr></thead><tbody>`;
  D.rolling.forEach((r) => {
    const c = (v) => `<td class="${v >= 0 ? "pos" : "neg"}">${fmtPct(v)}</td>`;
    h += `<tr${r.name === "strategy" ? ' class="hl"' : ""}><td>${ROLL_NAMES[r.name] || r.name}</td>` +
      `<td>${Math.round(r.y5.win_rate * 100)}%</td>${c(r.y5.median)}${c(r.y5.p5)}` +
      `<td>${Math.round(r.y10.win_rate * 100)}%</td>${c(r.y10.median)}${c(r.y10.p5)}</tr>`;
  });
  rt.innerHTML = h + "</tbody>";
});

function offFromSeries(g) {
  const out = [];
  let start = null;
  for (let i = 0; i < g.dates.length; i++) {
    const off = g.spx[i] < g.sma[i];
    if (off && start === null) start = g.dates[i];
    if (!off && start !== null) { out.push([start, g.dates[i]]); start = null; }
  }
  if (start !== null) out.push([start, g.dates[g.dates.length - 1]]);
  return out;
}
