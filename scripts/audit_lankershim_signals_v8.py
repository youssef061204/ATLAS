"""Quantify Lankershim RSM cycle alignment and source limits.

This is a source audit, not a reconstructed lamp-state history. The 2005 FHWA
metadata gives the trajectory origin as RSM 08:27:34; RSM89 is Main Street.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from atlas.rsm_v8 import completed_cycle_at, previous_row_at, read_rsm

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "data/reality-v6/support/signal-timing/real-time-split-monitor-reports"
    / "Original Text files/RSM089-061605.txt"
)
SHEET = ROOT / "data/reality-v6/support/signal-timing/signal-timing-sheets/int089.pdf"
METADATA = ROOT / "data/reality-v6/lankershim-metadata.pdf"
OUT = ROOT / "artifacts/reality/v8/signal-rsm89-audit.json"
ORIGIN_S = 8 * 3600 + 27 * 60 + 34
VIDEO_SECONDS = 1122


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit() -> dict[str, object]:
    rows = read_rsm(SOURCE)
    gaps = [
        (right.end_s - left.end_s, left.cycle_s, right.cycle_s)
        for left, right in zip(rows, rows[1:], strict=False)
    ]
    selected = [completed_cycle_at(rows, ORIGIN_S + t) for t in range(VIDEO_SECONDS)]
    old = [previous_row_at(rows, ORIGIN_S + t) for t in range(VIDEO_SECONDS)]
    unique = {row.end_s: row for row in selected}
    nonzero = Counter()
    for row in unique.values():
        for phase, seconds in enumerate(row.phase_split_s, start=1):
            if seconds:
                nonzero[str(phase)] += 1
    return {
        "schema": "atlas-v8-rsm89-source-audit-1",
        "source": {
            "rsm89_sha256": digest(SOURCE),
            "timing_sheet_089_sha256": digest(SHEET),
            "fhwa_metadata_sha256": digest(METADATA),
            "intersection": "Lankershim Boulevard at Main Street/MTA Driveway",
            "metadata_trajectory_start_controller_clock": "08:27:34",
            "metadata_scope": "FHWA says first trajectory dataset starts at 08:27:34 in the RSM report; source video clock alignment and lamp states are separate questions.",
        },
        "cycle_timestamp_evidence": {
            "report_cycles": len(rows),
            "consecutive_timestamp_gaps": len(gaps),
            "gaps_equal_current_row_cycle": sum(delta == current for delta, _, current in gaps),
            "gaps_equal_previous_row_cycle": sum(delta == previous for delta, previous, _ in gaps),
            "interpretation": "Each timestamp marks the end of that row's reported cycle. This follows from variable-length cycles as well as the FHWA description of cycle-by-cycle green splits.",
        },
        "at_v7_full_video_1hz": {
            "controller_clock_origin_s": ORIGIN_S,
            "duration_s": VIDEO_SECONDS,
            "samples": len(selected),
            "prior_row_selection_disagrees": sum(
                a.end_s != b.end_s for a, b in zip(selected, old, strict=True)
            ),
            "prior_row_phase_splits_disagree": sum(
                a.phase_split_s != b.phase_split_s for a, b in zip(selected, old, strict=True)
            ),
            "interpretation": "ATLAS 7 uses the preceding completed cycle's row as if it begins the current cycle. Row disagreement does not prove a lamp-state disagreement at every second.",
        },
        "controller_phase_evidence": {
            "cycles_overlapping_video": len(unique),
            "cycles_with_nonzero_phase_split": dict(
                sorted(nonzero.items(), key=lambda pair: int(pair[0]))
            ),
            "cycles_with_main_phase_2_below_cycle": sum(
                row.phase_split_s[1] < row.cycle_s for row in unique.values()
            ),
            "source_type": "Controller-reported green splits, not recorded phase-transition events or independently observed lamps",
            "timing_sheet_date": "2002-05-13; available historical plan, not proof it remained unchanged in 2005",
            "pedestrian_calls_in_rsm": False,
        },
        "physical_signal_verified": False,
        "blocking_unknowns": [
            "Exact within-cycle phase onset, order, yellow/clearance and pedestrian calls cannot be recovered from split totals alone.",
            "The RSM row correction must be tested as an assumption-labeled simulation ablation, not called observed lamp timing.",
            "The 2002 timing sheet and 2005 RSM do not by themselves establish visible 2005 lamp states at the camera.",
        ],
        "source_sha256": digest(Path(__file__)),
    }


def main() -> None:
    report = audit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUT),
                **report["cycle_timestamp_evidence"],
                **report["at_v7_full_video_1hz"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
