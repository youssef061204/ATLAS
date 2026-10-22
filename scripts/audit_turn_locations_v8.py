"""Locate diagnostic route turns at official Lankershim signal markers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import shapefile
from atlas.turn_location_v8 import classify_turn

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/reality-v6/trajectory-pages"
MARKERS = ROOT / "data/reality-v6/support/gis-files/signals-and-ramp-meters"
ROUTES = ROOT / "artifacts/reality/v8/reference-route-ablation-development.json"
OUT = ROOT / "artifacts/reality/v8/turn-location-development-audit.json"
LOCAL = ROOT / "data/reality-v8/turn-location-development-detail.json"
EPOCH = 1118935680000


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    if OUT.exists() or LOCAL.exists():
        raise FileExistsError("Preserve measured turn-location audit")
    changed = json.loads(ROUTES.read_text(encoding="utf-8"))["changed_route_records"]
    identities = {int(item["reference_id"]) for item in changed}
    source_pages = []
    frames = []
    for path in sorted(SOURCE.glob("*.csv.gz")):
        chunk = pd.read_csv(
            path,
            usecols=[
                "vehicle_id",
                "frame_id",
                "global_time",
                "global_x",
                "global_y",
                "local_y",
                "direction",
                "movement",
            ],
        )
        subset = chunk[
            chunk.vehicle_id.isin(identities)
            & (chunk.global_time - (chunk.frame_id - 1) * 100 == EPOCH)
            & (chunk.global_time < EPOCH + 300000)
        ]
        if not subset.empty:
            source_pages.append({"file": path.name, "sha256": sha(path)})
            frames.append(subset)
    observations = pd.concat(frames, ignore_index=True).sort_values(["vehicle_id", "global_time"])
    turn = observations[observations.direction.isin([1, 3])].groupby("vehicle_id").first()
    signals = shapefile.Reader(str(MARKERS))
    points = {
        int(record.Signal_No): tuple(map(float, shape.points[0]))
        for record, shape in zip(signals.records(), signals.shapes(), strict=True)
        if record.Signal_No in (88, 89, 90)
    }
    if set(points) != {88, 89, 90}:
        raise ValueError("Official GIS did not contain all three corridor signal markers")
    detail = []
    for item in changed:
        identity = int(item["reference_id"])
        if identity not in turn.index:
            raise ValueError(f"Route trial has no observed turn for {identity}")
        first = turn.loc[identity]
        movement_codes = sorted(
            set(map(int, observations.loc[observations.vehicle_id == identity, "movement"]))
        )
        if not set(movement_codes) & {2, 3}:
            raise ValueError("Official movement field lacks a turn label")
        assigned = classify_turn((float(first.global_x), float(first.global_y)), points)
        detail.append(
            {
                "reference_id": identity,
                "first_turn_s": (int(first.global_time) - EPOCH) / 1000,
                "first_turn_local_y_ft": float(first.local_y),
                "first_turn_direction": int(first.direction),
                "movement_codes": movement_codes,
                **assigned,
            }
        )
    nearest = Counter(row["nearest_signal"] for row in detail)
    supported = Counter(row["supported_signal"] for row in detail)
    report = {
        "schema": "atlas-v8-turn-location-diagnostic-1",
        "scope": "Already exposed 0-300 s development; future observed direction is an oracle label unavailable to causal route prediction",
        "routes_in_rejected_single_junction_oracle_trial": len(detail),
        "nearest_official_signal_counts": {str(key): nearest[key] for key in (88, 89, 90)},
        "within_50m_official_signal_counts": {str(key): supported[key] for key in (88, 89, 90)},
        "outside_50m_of_any_marker": supported[None],
        "finding": "The initial 63-route ablation placed corridor turns at one modeled Main Street junction; most independently observed turns occurred near other signals. That ablation is rejected as a faithful route correction.",
        "source_marker_shp_sha256": sha(MARKERS.with_suffix(".shp")),
        "source_pages": source_pages,
        "rejected_trial_sha256": sha(ROUTES),
        "local_detail_sha256": None,
        "individual_reference_ids_published": False,
        "source_sha256": sha(Path(__file__)),
    }
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(json.dumps(detail, indent=2) + "\n", encoding="utf-8")
    report["local_detail_sha256"] = sha(LOCAL)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "routes_in_rejected_single_junction_oracle_trial",
                    "nearest_official_signal_counts",
                    "within_50m_official_signal_counts",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
