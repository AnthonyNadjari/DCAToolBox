/**
 * Parity test: assert the JS engine matches the Python `dcatoolbox` engine.
 *
 * Run `python scripts/gen_golden.py` first to produce web/.parity/*.json, then:
 *     node web/engine.test.mjs
 *
 * Exits non-zero on any metric mismatch beyond tolerance.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { runBacktest } from "./engine.js";

const here = dirname(fileURLToPath(import.meta.url));
const load = (f) => JSON.parse(readFileSync(join(here, ".parity", f), "utf-8"));

const cases = load("cases.json");
const golden = load("golden.json");
const datasets = {};
const dataFor = (name) => (datasets[name] ??= load(`data_${name}.json`));

// Per-metric absolute tolerances. Solver-based metrics (xirr/irr) are looser.
const TOL = {
  default: 1e-6,
  xirr: 2e-3,
  irr: 2e-3,
  sharpe: 1e-4,
  sortino: 1e-4,
  calmar: 1e-4,
  information_ratio: 1e-4,
  cagr: 1e-5,
};
// Metrics present in Python output but not mirrored in JS.
const SKIP = new Set(["max_time_under_water_days"]);

let failures = 0;
cases.forEach((cfg, i) => {
  const { strategy } = runBacktest(dataFor(cfg.dataset || "daily"), cfg);
  const got = strategy.metrics;
  const want = golden[i];
  const label = `${cfg.strategy.name} ${JSON.stringify(cfg.strategy)}`;
  for (const key of Object.keys(want)) {
    if (SKIP.has(key)) continue;
    const a = got[key];
    const b = want[key];
    if (typeof b !== "number") continue;
    if (Number.isNaN(a) && Number.isNaN(b)) continue;
    const tol = TOL[key] ?? TOL.default;
    const diff = Math.abs((a ?? NaN) - b);
    // Use a relative tolerance for large-magnitude values (prices, totals).
    const scale = Math.max(1, Math.abs(b));
    if (!(diff <= tol * scale)) {
      failures++;
      console.error(`MISMATCH case#${i} [${label}] ${key}: js=${a} py=${b} diff=${diff}`);
    }
  }
});

if (failures) {
  console.error(`\n❌ Parity FAILED: ${failures} mismatch(es).`);
  process.exit(1);
} else {
  console.log(`✅ Parity OK: ${cases.length} cases, all metrics within tolerance.`);
}
