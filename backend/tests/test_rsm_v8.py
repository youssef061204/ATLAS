from __future__ import annotations

from pathlib import Path

import pytest
from atlas.rsm_v8 import completed_cycle_at, parse_rsm, previous_row_at, read_rsm


def test_variable_length_cycles_use_current_row_as_completed_cycle() -> None:
    rows = parse_rsm(
        "00:01:00 1 60 0 0 50 0 10 0 50 0 10\n"
        "00:02:20 2 80 5 0 55 5 20 0 55 0 25\n"
        "00:03:20 3 60 0 0 45 5 10 0 45 0 15\n"
    )
    assert rows[1].start_s == rows[0].end_s
    assert completed_cycle_at(rows, 61) is rows[1]
    assert previous_row_at(rows, 61) is rows[0]
    assert completed_cycle_at(rows, 80) is rows[1]
    assert completed_cycle_at(rows, 140) is rows[2]


def test_missing_report_interval_cannot_be_filled_with_guessed_signal() -> None:
    rows = parse_rsm("00:01:00 1 60 0 0 50 0 10 0 50 0 10\n00:02:30 1 60 0 0 45 0 15 0 45 0 15\n")
    with pytest.raises(ValueError, match="not covered"):
        completed_cycle_at(rows, 70)


def test_official_rsm89_has_cycle_end_pattern() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "data/reality-v6/support/signal-timing/real-time-split-monitor-reports"
        / "Original Text files/RSM089-061605.txt"
    )
    if not source.exists():
        pytest.skip("Raw licensed source data is excluded from source control")
    rows = read_rsm(source)
    assert len(rows) > 800
    assert all(
        right.end_s - left.end_s == right.cycle_s
        for left, right in zip(rows, rows[1:], strict=False)
    )
    assert any(right.cycle_s != left.cycle_s for left, right in zip(rows, rows[1:], strict=False))
    assert completed_cycle_at(rows, 8 * 3600 + 27 * 60 + 34).end_s == 8 * 3600 + 28 * 60 + 35
