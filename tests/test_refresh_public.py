"""Unit tests for the Bloomberg-free refresh of the signal page.

Only the pure functions are exercised — the fetch layer is deliberately left to
the live ``--check`` run, which is what CI schedules.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "refresh_public", Path(__file__).resolve().parents[1] / "scripts" / "refresh_public.py"
)
rp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rp)


def test_sma_warms_up_then_averages():
    out = rp.sma([1.0, 2.0, 3.0, 4.0], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)


def test_rank_pct_matches_pandas_average_rank():
    # pandas: Series([1,2,3,4]).rank(pct=True) -> last element 1.0
    assert rp.rank_pct([1.0, 2.0, 3.0, 4.0], 4.0) == pytest.approx(1.0)
    assert rp.rank_pct([1.0, 2.0, 3.0, 4.0], 1.0) == pytest.approx(0.25)
    # ties average: [1,2,2,3] ranking 2 -> (1 + (2+1)/2)/4
    assert rp.rank_pct([1.0, 2.0, 2.0, 3.0], 2.0) == pytest.approx(0.625)


def _series(values, window=3):
    dates = [(date(2020, 1, 6) + timedelta(days=i)).isoformat() for i in range(len(values))]
    saved = rp.MA_WINDOW
    rp.MA_WINDOW = window
    try:
        return dates, rp.gate_states(dates, values)
    finally:
        rp.MA_WINDOW = saved


def test_gate_states_none_during_warmup():
    dates, states = _series([1.0, 2.0, 3.0, 4.0])
    assert states[:2] == [None, None]
    assert states[2] is True  # 3 > mean(1,2,3)


def test_off_periods_pairs_each_fall_with_its_recross():
    values = [10, 11, 12, 13, 14, 9, 8, 7, 20, 21, 22]
    dates, states = _series([float(v) for v in values])
    spans = rp.off_periods(dates, states)
    assert len(spans) == 1
    lo, hi = spans[0]
    assert lo < hi
    assert states[dates.index(lo)] is False
    assert states[dates.index(hi)] is True


def test_off_periods_leaves_an_open_span_open_ended():
    values = [10, 11, 12, 13, 14, 9, 8, 7, 6]
    dates, states = _series([float(v) for v in values])
    spans = rp.off_periods(dates, states)
    assert spans[-1][1] == dates[-1]


def test_last_cross_is_the_most_recent_flip():
    values = [10, 11, 12, 13, 14, 9, 8, 7, 20, 21, 22]
    dates, states = _series([float(v) for v in values])
    flip = rp.last_cross(dates, states)
    i = dates.index(flip)
    assert states[i] != states[i - 1]
    assert all(states[j] == states[i] for j in range(i, len(states)))


def test_merge_off_periods_keeps_history_and_replaces_the_tail():
    published = [["1990-07-05", "1990-07-06"], ["2025-03-05", "2025-03-06"]]
    public = [["2025-03-05", "2025-03-07"], ["2026-04-07", "2026-04-08"]]
    out = rp.merge_off_periods(published, public, "2024-01-01")
    assert out == [["1990-07-05", "1990-07-06"], *public]


def test_drop_unsettled_uses_the_symbols_own_close():
    now = datetime.now(UTC)
    d = now.date().isoformat()
    older = (now.date() - timedelta(days=5)).isoformat()
    open_meta = {
        "gmtoffset": 0,
        "currentTradingPeriod": {"regular": {"end": int(now.timestamp()) + 3600}},
    }
    shut_meta = {
        "gmtoffset": 0,
        "currentTradingPeriod": {"regular": {"end": int(now.timestamp()) - 60}},
    }
    assert rp.drop_unsettled({older: 1.0, d: 2.0}, open_meta) == {older: 1.0}
    assert rp.drop_unsettled({older: 1.0, d: 2.0}, shut_meta) == {older: 1.0, d: 2.0}
    assert rp.drop_unsettled({older: 1.0}, {}) == {older: 1.0}


def test_baseline_is_captured_once_then_reused():
    payload = {
        "generated": "2026-09-03",
        "signal": {"asof": "2026-09-03", "sma200": 7136.49},
        "off_periods": [
            ["1990-07-05", "1990-07-06"],
            ["2026-04-07", "2026-04-08"],
            ["2026-08-20", "2026-09-03"],
        ],
    }
    first = rp.baseline(payload)
    assert first["asof"] == "2026-09-03"
    assert first["sma200"] == 7136.49
    # 1990 is outside BASELINE_YEARS; the span closed at the build date is still open
    assert first["off_periods"] == [["2026-04-07", "2026-04-08"]]

    # a later refresh must reuse the capture, not re-derive it from its own output
    refreshed = {
        "generated": "2026-10-15",
        "signal": {"asof": "2026-10-15", "sma200": 7268.0},
        "off_periods": payload["off_periods"],
        "sources": {"history_asof": "2026-09-03", "baseline": first},
    }
    assert rp.baseline(refreshed) == first


def test_baseline_is_recaptured_after_a_terminal_rebuild():
    stale = {"asof": "2026-09-03", "from": "2023-09-04", "sma200": 1.0, "off_periods": []}
    rebuilt = {
        "generated": "2026-11-02",
        "signal": {"asof": "2026-11-02", "sma200": 7400.0},
        "off_periods": [],
        "sources": {"history_asof": "2026-11-02", "baseline": stale},
    }
    assert rp.baseline(rebuilt)["asof"] == "2026-11-02"
    assert rp.baseline(rebuilt)["sma200"] == 7400.0


def test_self_check_flags_a_replica_that_disagrees():
    # a flat synthetic series ending today: the replayed average can never match 7136.49
    end = datetime.now(UTC).date()
    dates = [(end - timedelta(days=1199 - i)).isoformat() for i in range(1200)]
    spx = dict.fromkeys(dates, 100.0)
    base = {"asof": dates[-1], "from": dates[0], "sma200": 7136.49, "off_periods": []}
    fails = rp.check_prices(base, spx, spx)
    assert any("sma200 replay" in f for f in fails)
    assert fails


def test_self_check_replays_on_the_nearest_earlier_session():
    # business days only, so a Bloomberg as-of landing on a Sunday has no session
    days = [date(2020, 1, 6) + timedelta(days=i) for i in range(1600)]
    sessions = [d.isoformat() for d in days if d.weekday() < 5]
    spx = {d: 100.0 + i * 0.01 for i, d in enumerate(sessions)}
    avg = rp.sma(list(spx.values()), rp.MA_WINDOW)
    anchor = sessions[-300]
    sunday = (date.fromisoformat(anchor) + timedelta(days=1)).isoformat()
    assert date.fromisoformat(sunday).weekday() == 5  # Saturday or later, not a session
    base = {
        "asof": sunday,
        "from": sessions[0],
        "sma200": avg[sessions.index(anchor)],
        "off_periods": [],
    }
    fails = rp.check_prices(base, spx, spx)
    assert not any("sma200" in f or "Bloomberg as-of" in f for f in fails), fails


def test_self_check_refuses_a_short_history():
    dates = [(date(2020, 1, 6) + timedelta(days=i)).isoformat() for i in range(10)]
    spx = dict.fromkeys(dates, 100.0)
    base = {"asof": dates[-1], "from": dates[0], "sma200": 100.0, "off_periods": []}
    fails = rp.check_prices(base, spx, spx)
    assert any("need" in f for f in fails)


def test_merge_keeps_a_span_starting_on_the_warmup_boundary():
    dates = [(date(2020, 1, 6) + timedelta(days=i)).isoformat() for i in range(400)]
    boundary = dates[rp.MA_WINDOW - 1]
    published = [[boundary, dates[rp.MA_WINDOW + 5]]]
    out = rp.merge_off_periods(published, [], rp.public_start(dates))
    assert out == published


def test_align_to_dates_vix_on_spx_sessions():
    spx_dates = ["2026-09-03", "2026-09-04", "2026-09-08"]
    vix = {"2026-09-03": 15.0, "2026-09-04": 14.5, "2026-09-07": 15.3, "2026-09-08": 16.0}
    assert rp.align_to(spx_dates[:2], vix) == [15.0, 14.5]  # Labor Day bar never leaks in
