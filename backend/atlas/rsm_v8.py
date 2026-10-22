"""Read FHWA's cycle-by-cycle RSM report without inventing lamp states.

The report describes completed controller cycles. Its time column is the end
of the reported cycle: successive timestamps differ by the *current* row's
cycle length, including when the programmed length changes. A split duration
alone does not identify the onset or order of every phase within the cycle.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

_CLOCK = re.compile(r"^\d{2}:\d{2}:\d{2}$")


@dataclass(frozen=True)
class RsmCycle:
    end_s: int
    plan: int
    cycle_s: int
    offset_s: int
    phase_split_s: tuple[int, int, int, int, int, int, int, int]

    @property
    def start_s(self) -> int:
        return self.end_s - self.cycle_s

    def as_dict(self) -> dict[str, object]:
        return {
            "start_clock_s": self.start_s,
            "end_clock_s_exclusive": self.end_s,
            "plan": self.plan,
            "cycle_s": self.cycle_s,
            "offset_s": self.offset_s,
            "phase_split_s": list(self.phase_split_s),
        }


def parse_rsm(text: str) -> list[RsmCycle]:
    """Parse the report's eight split columns, retaining zero-duration phases."""
    rows: list[RsmCycle] = []
    for number, line in enumerate(text.splitlines(), start=1):
        fields = line.split()
        if not fields or not _CLOCK.fullmatch(fields[0]):
            continue
        if len(fields) != 12:
            raise ValueError(f"RSM line {number}: expected time and 11 integers")
        hh, mm, ss = (int(part) for part in fields[0].split(":"))
        if not (hh < 24 and mm < 60 and ss < 60):
            raise ValueError(f"RSM line {number}: invalid controller clock")
        plan, cycle, offset, *splits = (int(part) for part in fields[1:])
        if cycle <= 0 or len(splits) != 8 or any(value < 0 for value in splits):
            raise ValueError(f"RSM line {number}: invalid cycle or phase split")
        rows.append(RsmCycle(hh * 3600 + mm * 60 + ss, plan, cycle, offset, tuple(splits)))
    if not rows:
        raise ValueError("No RSM cycle rows found")
    if any(right.end_s <= left.end_s for left, right in zip(rows, rows[1:], strict=False)):
        raise ValueError("RSM cycle timestamps must increase")
    return rows


def read_rsm(path: Path) -> list[RsmCycle]:
    return parse_rsm(path.read_text(encoding="utf-8"))


def completed_cycle_at(rows: list[RsmCycle], controller_clock_s: int) -> RsmCycle:
    """Return the row whose completed cycle contains this clock instant.

    Intervals are half-open [end - duration, end). At a report timestamp, the
    next cycle has just started. A missing interval is an error, never a signal
    state guessed from a neighboring record.
    """
    ends = [row.end_s for row in rows]
    index = bisect.bisect_right(ends, controller_clock_s)
    if index == len(rows):
        raise ValueError("Controller clock is after the final completed cycle")
    row = rows[index]
    if not row.start_s <= controller_clock_s < row.end_s:
        raise ValueError("Controller clock is not covered by an RSM cycle")
    return row


def previous_row_at(rows: list[RsmCycle], controller_clock_s: int) -> RsmCycle:
    """Reproduce ATLAS 7's latest-prior-row lookup for a controlled comparison."""
    ends = [row.end_s for row in rows]
    index = bisect.bisect_right(ends, controller_clock_s) - 1
    if index < 0:
        raise ValueError("Controller clock precedes first RSM report")
    return rows[index]
