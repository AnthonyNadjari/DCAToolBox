"""Refresh the live blocks of ``web/data.json`` from public data — no Bloomberg.

The 37-year backtest in ``data.json`` is built from the Bloomberg caches by
``scripts/build_signal_page.py``, which only runs on the terminal machine. The
blocks a visitor reads first — the gate verdict, the pulse tiles, the 3-year
gate chart — go stale within days of that build, while the backtest behind them
does not: one more month on a 445-month curve changes nothing a reader can see.

So this script rebuilds exactly the live blocks from free sources, leaves every
Bloomberg-derived series untouched, and stamps both as-of dates so the page can
state which half is fresh. It deliberately does **not** splice new months onto
the Bloomberg history: mixing two data vendors inside one backtested curve is
how silent seams get in.

Sources: Yahoo Finance (``^GSPC``, ``^VIX``, ``ESE.PA``). Standard library only,
so CI needs no install step.

Before writing it replays the frozen Bloomberg numbers from public data. The
price replay is a hard gate — fail it and nothing is written. The fund-gate
replay is advisory: a disagreement there leaves ``off_periods`` exactly as the
terminal left it and is reported, rather than freezing the whole page over the
chart's shading. See :func:`check_prices` and :func:`check_gate`.

Usage::

    python scripts/refresh_public.py            # rewrite web/data.json
    python scripts/refresh_public.py --check    # report staleness, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "web" / "data.json"
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; DCAToolBox/1.0; +https://github.com/AnthonyNadjari/DCAToolBox)"
}
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"

MA_WINDOW = 200  # the gate's moving average, in trading days
GATE_BARS = 756  # ~3 years of daily bars on the gate chart
VIX_WINDOW = 252  # the VIX percentile's "1 year", in trading days
MAX_STALE_DAYS = 7  # a feed quieter than this is broken, not calm


def today() -> date:
    """Today in UTC — the one clock every date in this module is read against."""
    return datetime.now(UTC).date()


# --------------------------------------------------------------- sources ----
def fetch(url: str, params: dict[str, str | int]) -> bytes:
    """GET ``url`` with query ``params`` and return the raw body."""
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=UA)
    with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310 - fixed https hosts
        return resp.read()


def yahoo_closes(symbol: str, years: int) -> tuple[dict[str, float], dict]:
    """Daily closes for ``symbol`` over the last ``years``, plus the chart metadata.

    Yahoo stamps each daily bar in exchange time, so the exchange's UTC offset is
    added back before the date is taken — without it, European sessions land on
    the previous day. Bars with a null close are dropped; the gap that leaves is
    what ``build_signal_page.py`` sees too, since it drops Bloomberg's NaNs the
    same way.
    """
    now = int(datetime.now(UTC).timestamp())
    raw = fetch(
        YAHOO + urllib.parse.quote(symbol),
        {"period1": now - years * 366 * 86400, "period2": now + 86400, "interval": "1d"},
    )
    chart = json.loads(raw)["chart"]
    if chart.get("error"):
        raise RuntimeError(f"{symbol}: {chart['error']}")
    res = chart["result"][0]
    offset = res["meta"].get("gmtoffset") or 0
    out: dict[str, float] = {}
    for stamp, close in zip(res["timestamp"], res["indicators"]["quote"][0]["close"], strict=True):
        if close is not None:
            out[(date(1970, 1, 1) + timedelta(seconds=stamp + offset)).isoformat()] = float(close)
    if not out:
        raise RuntimeError(f"{symbol}: no closes returned")
    return dict(sorted(out.items())), res["meta"]


def drop_unsettled(closes: dict[str, float], meta: dict) -> dict[str, float]:
    """Drop the final bar while its own session can still move it.

    A mid-session call returns a live, partial bar, and the strategy only ever
    acts on settled closes. The cut-off is read from the symbol's own trading
    calendar rather than assumed, so Paris (15:30 UTC) and New York (20:00 UTC in
    summer, 21:00 in winter) are each judged against the right close.
    """
    end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    if not end or not closes:
        return closes
    offset = meta.get("gmtoffset") or 0
    session = (date(1970, 1, 1) + timedelta(seconds=end + offset)).isoformat()
    last = next(reversed(closes))
    if last == session and datetime.now(UTC).timestamp() < end:
        return {d: c for d, c in closes.items() if d != last}
    return closes


# ------------------------------------------------------------- primitives ----
def sma(values: list[float], window: int) -> list[float | None]:
    """Rolling mean of ``values``; ``None`` until ``window`` points are in hand."""
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def rank_pct(window: list[float], value: float) -> float:
    """Percentile of ``value`` within ``window``, matching pandas' average rank."""
    below = sum(1 for v in window if v < value)
    ties = sum(1 for v in window if v == value)
    return (below + (ties + 1) / 2) / len(window)


def align_to(dates: list[str], series: dict[str, float]) -> list[float | None]:
    """Reindex ``series`` onto ``dates``, carrying the last known value forward.

    The three feeds are fetched separately and do not share a calendar: Yahoo
    publishes a ``^VIX`` close on some US holidays where ``^GSPC`` has no bar at
    all. Pairing them by position would date a tile to a session the page says
    does not exist, so every cross-series read goes through here.
    """
    out: list[float | None] = []
    last: float | None = None
    for d in dates:
        if d in series:
            last = series[d]
        out.append(last)
    return out


def gate_states(dates: list[str], closes: list[float]) -> list[bool | None]:
    """Risk-on flags: close above its own moving average, ``None`` during warm-up."""
    avg = sma(closes, MA_WINDOW)
    return [None if m is None else c > m for c, m in zip(closes, avg, strict=True)]


def public_start(dates: list[str]) -> str:
    """First date a gate-off span can possibly start at.

    :func:`off_periods` needs a defined state on both sides of a flip, so the
    earliest span it can emit starts one bar after the moving average warms up.
    Anything earlier has to be kept from the published file rather than
    recomputed, or it would fall through the gap between the two halves.
    """
    return dates[MA_WINDOW]


def off_periods(dates: list[str], states: list[bool | None]) -> list[list[str]]:
    """``[[off_date, back_on_date], ...]`` spans where the gate was down."""
    spans: list[list[str]] = []
    start: str | None = None
    for i in range(1, len(states)):
        prev, cur = states[i - 1], states[i]
        if prev is None or cur is None:
            continue
        if prev and not cur:
            start = dates[i]
        elif cur and not prev and start:
            spans.append([start, dates[i]])
            start = None
    if start:
        spans.append([start, dates[-1]])
    return spans


def last_cross(dates: list[str], states: list[bool | None]) -> str:
    """Date of the most recent gate flip."""
    seen = [i for i in range(1, len(states)) if None not in (states[i], states[i - 1])]
    flips = [i for i in seen if states[i] != states[i - 1]]
    return dates[flips[-1]] if flips else dates[seen[0]]


# ------------------------------------------------------------------ build ----
def build_signal(dates: list[str], closes: list[float]) -> dict:
    """The gate block: SPX against its 200-day average, exactly as the terminal build."""
    avg = sma(closes, MA_WINDOW)
    states = gate_states(dates, closes)
    since = last_cross(dates, states)
    level = avg[-1]
    assert level is not None  # guaranteed: check_prices requires >= MA_WINDOW bars
    return {
        "asof": dates[-1],
        "spx": round(closes[-1], 2),
        "sma200": round(level, 2),
        "gap_pct": round((closes[-1] / level - 1) * 100, 2),
        "state": "ON" if closes[-1] > level else "OFF",
        "since": since,
        "days_in_state": (date.fromisoformat(dates[-1]) - date.fromisoformat(since)).days,
        "flip_level": round(level, 2),
    }


def build_indicators(old: dict, spx: list[float], vix: list[float], history_asof: str) -> dict:
    """The pulse tiles.

    ``vix`` arrives already aligned to the SPX sessions, so the published level
    and its percentile are both dated to the same day as the signal. The ESE
    bid/ask needs a terminal, so it is carried over untouched and dated.
    """
    new = dict(old)
    new["vix"] = round(vix[-1], 2)
    new["vix_pctl_1y"] = round(rank_pct(vix, vix[-1]) * 100, 0)
    new["spx_chg_1m"] = round((spx[-1] / spx[-22] - 1) * 100, 2)
    new["spread_asof"] = old.get("spread_asof") or history_asof
    return new


def build_gate_series(dates: list[str], closes: list[float]) -> dict:
    """The 3-year daily gate chart."""
    avg = sma(closes, MA_WINDOW)
    tail = slice(-GATE_BARS, None)
    return {
        "dates": dates[tail],
        "spx": [round(c, 2) for c in closes[tail]],
        "sma": [round(m, 2) if m is not None else None for m in avg[tail]],
    }


def merge_off_periods(
    published: list[list[str]], public: list[list[str]], first: str
) -> list[list[str]]:
    """Keep the spans that predate the public window, take the public ones after.

    ``first`` must be :func:`public_start`: a span starting on an earlier date
    cannot be re-emitted by the public half, so keeping only ``p[0] < first``
    would delete it from both halves — and, since the next run reads this output
    back as ``published``, delete it for good.

    Safe to apply repeatedly to its own output: ``first`` only moves forward, so
    a span is recomputed from public data until it leaves the window, then frozen.
    """
    return [p for p in published if p[0] < first] + public


# ------------------------------------------------------------ validation ----
BASELINE_YEARS = 3  # how far back the frozen Bloomberg spans are kept for the replay


def baseline(payload: dict) -> dict:
    """The frozen Bloomberg half this run validates against.

    A terminal rebuild leaves pure Bloomberg blocks in the file, so the first
    refresh after one captures them; later refreshes reuse that capture. Without
    it the replay would end up checking public data against public data — a test
    that passes by construction and catches nothing.

    Spans ending on the build date itself are left out: ``build_signal_page.py``
    closes a still-open gate-off span at its last bar, so such a span is not a
    recross and the public replay will rightly end it somewhere later.
    """
    src = payload.get("sources") or {}
    asof = src.get("history_asof") or payload["generated"]
    frozen = src.get("baseline")
    if frozen and frozen.get("asof") == asof:
        return frozen
    cut = (date.fromisoformat(asof) - timedelta(days=365 * BASELINE_YEARS)).isoformat()
    return {
        "asof": asof,
        "from": cut,
        "sma200": payload["signal"]["sma200"],
        "off_periods": [p for p in payload["off_periods"] if cut <= p[0] and p[1] < asof],
    }


def check_feed(symbol: str, closes: dict[str, float], need: int) -> list[str]:
    """Reject a feed that came back short or stopped updating."""
    fails = []
    if len(closes) < need:
        fails.append(f"{symbol}: {len(closes)} bars, need {need}")
    if closes:
        stale = (today() - date.fromisoformat(next(reversed(closes)))).days
        if stale > MAX_STALE_DAYS:
            fails.append(f"{symbol}: last bar {next(reversed(closes))} is {stale} days old")
    return fails


def check_prices(base: dict, spx: dict[str, float], vix: dict[str, float]) -> list[str]:
    """Hard gate: the price feeds behind the verdict and the pulse tiles.

    The 200-day average on the day Bloomberg last published must match to a tenth
    of a percent. The closes themselves may differ — a terminal build run
    mid-session quotes a live price — but an average over 200 settled closes may
    not.
    """
    fails = check_feed("^GSPC", spx, MA_WINDOW + GATE_BARS) + check_feed("^VIX", vix, VIX_WINDOW)
    if fails:
        return fails

    sdates, scloses = list(spx), list(spx.values())
    if align_to(sdates[-VIX_WINDOW:], vix)[0] is None:
        fails.append(f"^VIX does not reach back {VIX_WINDOW} SPX sessions to {sdates[-VIX_WINDOW]}")

    # The terminal build can land on a day Yahoo has no session for (a US holiday
    # that Euronext trades, a Bloomberg stamp a day ahead). Replay on the nearest
    # earlier session instead of wedging the page as permanently stale; a 200-day
    # mean moves far less than the tolerance over a day or two.
    prior = [d for d in sdates if d <= base["asof"]]
    if not prior:
        fails.append(f"Bloomberg as-of {base['asof']} predates the public window")
    elif (date.fromisoformat(base["asof"]) - date.fromisoformat(prior[-1])).days > 5:
        fails.append(f"no public session within 5 days of the Bloomberg as-of {base['asof']}")
    else:
        got = sma(scloses, MA_WINDOW)[sdates.index(prior[-1])]
        if got is None or abs(got / base["sma200"] - 1) > 0.001:
            want = base["sma200"]
            fails.append(f"sma200 replay at {prior[-1]}: public {got} vs Bloomberg {want}")
    return fails


def check_gate(base: dict, ese: dict[str, float]) -> list[str]:
    """Advisory: every gate-off span Bloomberg recorded must come back to the day.

    Only the chart's shading rides on this, so a disagreement is reported and the
    published spans are kept rather than failing the whole refresh — a stale
    verdict is a worse outcome than stale shading.
    """
    fails = check_feed("ESE.PA", ese, MA_WINDOW + 2)
    if fails:
        return fails
    edates, ecloses = list(ese), list(ese.values())
    public = off_periods(edates, gate_states(edates, ecloses))
    # Compare over the overlap only: the public window starts after the fund's
    # own moving-average warm-up, the frozen baseline reaches back BASELINE_YEARS.
    lo = max(public_start(edates), base["from"])
    got = [p for p in public if p[0] >= lo and p[1] < base["asof"]]
    want = [p for p in base["off_periods"] if p[0] >= lo]
    if got != want:
        fails.append(f"gate-off spans disagree: public {got} vs Bloomberg {want}")
    return fails


# ------------------------------------------------------------------- main ----
def refresh(payload: dict) -> tuple[dict, list[str], list[str]]:
    """Return the refreshed payload, the fatal failures, and the warnings."""
    spx, spx_meta = yahoo_closes("^GSPC", 10)
    vix, vix_meta = yahoo_closes("^VIX", 2)
    ese, ese_meta = yahoo_closes("ESE.PA", 5)
    spx = drop_unsettled(spx, spx_meta)
    vix = drop_unsettled(vix, vix_meta)
    ese = drop_unsettled(ese, ese_meta)

    base = baseline(payload)
    fatal = check_prices(base, spx, vix)
    if fatal:
        return payload, fatal, []
    warnings = check_gate(base, ese)

    sdates, scloses = list(spx), list(spx.values())
    out = dict(payload)
    out["signal"] = build_signal(sdates, scloses)
    out["indicators"] = build_indicators(
        payload["indicators"], scloses, align_to(sdates[-VIX_WINDOW:], vix), base["asof"]
    )
    out["gate_series"] = build_gate_series(sdates, scloses)
    if warnings:
        out["off_periods"] = payload["off_periods"]
    else:
        edates = list(ese)
        public = off_periods(edates, gate_states(edates, list(ese.values())))
        out["off_periods"] = merge_off_periods(payload["off_periods"], public, public_start(edates))
    out["generated"] = out["signal"]["asof"]
    out["sources"] = {
        "live": "Yahoo Finance (^GSPC, ^VIX, ESE.PA)",
        "live_asof": out["signal"]["asof"],
        "history": "Bloomberg",
        "history_asof": base["asof"],
        "baseline": base,
    }
    if warnings:
        out["sources"]["warnings"] = warnings
    return out, [], warnings


def main() -> int:
    """Refresh ``web/data.json`` in place, or report staleness under ``--check``."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    before = payload["signal"]["asof"]
    out, fatal, warnings = refresh(payload)
    for w in warnings:
        print(f"WARN  {w} — keeping the published gate-off spans", file=sys.stderr)
    if fatal:
        for f in fatal:
            print(f"FAIL  {f}", file=sys.stderr)
        return 1

    sig = out["signal"]
    print(
        f"signal {before} -> {sig['asof']}: {sig['state']} "
        f"(SPX {sig['spx']:,.0f} vs 200d {sig['sma200']:,.0f}, {sig['gap_pct']:+.2f}%, "
        f"{sig['days_in_state']} days) · VIX {out['indicators']['vix']} "
        f"(p{out['indicators']['vix_pctl_1y']:.0f}) · history au {out['sources']['history_asof']}"
    )
    if args.check:
        print("--check: nothing written")
        return 0 if before == sig["asof"] else 1

    DATA.write_text(json.dumps(out), encoding="utf-8")
    print(f"wrote {DATA} ({DATA.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
