"""Compare observed through passage to native SUMO passage at modeled Main Street."""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from atlas.crossing_v8 import observed_crossing
from atlas.rsm_v8 import read_rsm
from atlas.signal_ablation_v8 import approximate_stage
from reconstruct_ngsim_v6 import EPOCH, rsm_rows, signal_stage

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "data/reality-v6/trajectory-pages"
ORACLE = ROOT / "data/reality-v8/reference-demand-development"
RSM = (
    ROOT
    / "data/reality-v6/support/signal-timing/real-time-split-monitor-reports"
    / "Original Text files/RSM089-061605.txt"
)
OUT = ROOT / "artifacts/reality/v8/main-through-crossing-development.json"
END = 300


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def observed():
    frames = []
    hashes = []
    for path in sorted(PAGES.glob("*.csv.gz")):
        source = pd.read_csv(
            path,
            usecols=[
                "vehicle_id",
                "frame_id",
                "global_time",
                "local_x",
                "local_y",
                "direction",
                "movement",
                "lane_id",
            ],
        )
        source = source[
            (source.global_time - (source.frame_id - 1) * 100 == EPOCH)
            & (source.global_time < EPOCH + END * 1000)
        ]
        if not source.empty:
            hashes.append({"file": path.name, "sha256": sha(path)})
            frames.append(source)
    if not frames:
        raise ValueError("No FHWA trajectory pages found")
    source = pd.concat(frames, ignore_index=True).sort_values(["vehicle_id", "global_time"])
    source["t"] = (source.global_time - EPOCH) / 1000
    crossings = {}
    fields = ("t", "local_x", "local_y", "direction", "movement", "lane_id")
    for identity, track in source.groupby("vehicle_id"):
        rows = track[list(fields)].to_dict("records")
        for before, after in zip(rows, rows[1:], strict=False):
            time = observed_crossing(before, after)
            if time is not None:
                crossings[str(int(identity))] = {
                    "direction": int(before["direction"]),
                    "observed_time_s": time,
                }
                break
    return crossings, hashes


def native(crossings):
    first = {}
    path = ORACLE / "simulation.fcd.xml.gz"
    with gzip.open(path, "rb") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag != "timestep":
                continue
            second = float(element.get("time"))
            for vehicle in element:
                identity = vehicle.get("id").removeprefix("ref_")
                row = crossings.get(identity)
                if row is None:
                    continue
                expected = "N_out" if row["direction"] == 2 else "S_out"
                if vehicle.get("lane", "").startswith(expected):
                    first.setdefault(identity, second)
            element.clear()
    return first


def summary(delays):
    if not delays:
        return {"paired": 0, "mean_s": None, "median_s": None, "p90_s": None}
    values = np.asarray(delays)
    return {
        "paired": len(values),
        "mean_s": float(np.mean(values)),
        "median_s": float(np.median(values)),
        "p90_s": float(np.percentile(values, 90)),
        "native_earlier_than_observed": int(np.count_nonzero(values < 0)),
    }


def main():
    if OUT.exists():
        raise FileExistsError("Preserve measured through-crossing audit")
    crossings, pages = observed()
    simulated = native(crossings)
    timing = rsm_rows()
    cycles = read_rsm(RSM)
    grouped = defaultdict(list)
    legacy_stages = Counter()
    corrected_stages = Counter()
    for identity, row in crossings.items():
        direction = row["direction"]
        second = row["observed_time_s"]
        legacy_stages[(direction, signal_stage(second, timing))] += 1
        corrected_stages[(direction, approximate_stage(30454 + second, cycles))] += 1
        if identity in simulated:
            grouped[direction].append(simulated[identity] - second)
    report = {
        "schema": "atlas-v8-estimated-main-through-crossing-1",
        "window_s": [0, END],
        "source_scope": "Already exposed development data and oracle reference-initialized native SUMO; not independent validation",
        "through_movement_filter": "FHWA movement=1, stable direction 2 or 4, lanes 1-4, local |x|<70 ft, adjacent samples <=0.2 s",
        "cross_section": "Interpolated passage of local_y=1045 ft, the ATLAS 7 modeled junction, not a surveyed stop line",
        "observed_crossings": {
            "northbound": sum(r["direction"] == 2 for r in crossings.values()),
            "southbound": sum(r["direction"] == 4 for r in crossings.values()),
        },
        "native_first_outgoing_edge_sample_minus_observed_s": {
            "northbound": summary(grouped[2]),
            "southbound": summary(grouped[4]),
        },
        "native_sampling_caveat": "FCD is 1 Hz and first outgoing-edge sample occurs after internal junction traversal. Differences include sampling and topology offsets; they are not exact stop-line delay.",
        "legacy_approximate_stage_at_observed_crossing": {
            f"direction_{direction}_{stage}": count
            for (direction, stage), count in sorted(legacy_stages.items())
        },
        "cycle_end_approximate_stage_at_observed_crossing": {
            f"direction_{direction}_{stage}": count
            for (direction, stage), count in sorted(corrected_stages.items())
        },
        "stage_caveat": "Both stage models are assumptions from green split totals; neither is an independently observed lamp state. A crossing time alone does not establish the visible color.",
        "source_pages": pages,
        "source_rsm_sha256": sha(RSM),
        "oracle_native_fcd_sha256": sha(ORACLE / "simulation.fcd.xml.gz"),
        "source_sha256": sha(Path(__file__)),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["native_first_outgoing_edge_sample_minus_observed_s"], indent=2))


if __name__ == "__main__":
    main()
