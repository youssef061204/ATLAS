"""Score a completed frozen raw-video run against independent Peachtree observations.

No reference rows are read until complete production output and frozen inputs pass.
All temporal cohorts and the fixed GIS/road region are reported, without shrinking
the region to hide occlusions or selecting the most favorable test cohort.
"""

import argparse
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import shapefile
from atlas.point_metrics_v7 import evaluate_points
from atlas.reality_v7 import result_frames
from calibrate_peachtree_v7 import DATA, ORIGIN, ORIGIN_SECONDS, ROOT, SCALE
from peachtree_reference_v7 import body_centers


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def references(end):
    columns = [
        "Vehicle_ID",
        "Frame_ID",
        "Global_Time",
        "Global_X",
        "Global_Y",
        "v_length",
        "v_Vel",
        "Direction",
    ]
    parts = []
    for rows in pd.read_csv(
        DATA / "support/NGSIM_Peachtree_Vehicle_Trajectories.csv", usecols=columns, chunksize=50000
    ):
        keep = (rows.Global_Time - (rows.Frame_ID - 1) * 100 == ORIGIN_SECONDS) & (
            rows.Frame_ID <= end * 10 + 1
        )
        parts.append(rows[keep])
    rows = pd.concat(parts, ignore_index=True).sort_values(["Vehicle_ID", "Frame_ID"])
    if rows.duplicated(["Vehicle_ID", "Frame_ID"]).any():
        raise ValueError("Duplicate independent reference state")
    rows["t"] = (rows.Frame_ID - 1) / 10
    return rows


def eligibility(calibration, protocol):
    reader = shapefile.Reader(str(DATA / "support/gis-files/camera-coverage.shp"))
    camera = next(row.shape for row in reader.iterShapeRecords() if row.record[0] == 1)
    polygon = (np.asarray(camera.points) - ORIGIN) * SCALE
    polygons = [np.float32(p) for p in protocol["region"]["processed_plane_polygons"]]
    inverse = np.linalg.inv(np.asarray(calibration["rectified_to_world"]))

    def inside(point):
        if not np.isfinite(point).all():
            return False
        if cv2.pointPolygonTest(np.float32(polygon), tuple(map(float, point)), False) < 0:
            return False
        p = cv2.perspectiveTransform(np.float64([[point]]), inverse)[0, 0]
        return any(
            cv2.pointPolygonTest(poly, tuple(map(float, p)), False) >= 0 for poly in polygons
        )

    return inside


def evaluate(run_path, development=False):
    correction = json.loads((ROOT / "docs/peachtree-evaluator-v7-correction.json").read_text())
    for path, digest in correction["sources_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError(f"Corrected evaluator changed: {path}")
    frozen = json.loads((ROOT / "docs/peachtree-v7-frozen.json").read_text())
    perception = json.loads((ROOT / "docs/perception-v7-frozen.json").read_text())
    for path, digest in {**frozen["sources_sha256"], **perception["sources_sha256"]}.items():
        if sha(ROOT / path) != digest:
            raise ValueError(f"Frozen source changed: {path}")
    checks = [
        (DATA / "calibration-development.json", "calibration_sha256"),
        (DATA / "development-time-alignment.json", "alignment_sha256"),
    ]
    for path, key in checks:
        if sha(path) != frozen[key]:
            raise ValueError(f"Frozen calibration/alignment changed: {path.name}")
    run = json.loads(run_path.read_text())
    if (
        run["performance"]["processed_frames"] != 14961
        or run["performance"]["decoded_frames"] != 14961
    ):
        raise ValueError("A complete production recording must precede scoring")
    source = Path(run["result_file"])
    if sha(source) != run["result_sha256"]:
        raise ValueError("Production result checksum mismatch")
    protocol = json.loads((ROOT / "docs/peachtree-v7-protocol.json").read_text())
    calibration = json.loads((DATA / "calibration-development.json").read_text())
    inside = eligibility(calibration, protocol)
    matrix = np.asarray(calibration["raw_to_world"])
    start, end = (60, 300) if development else (600, 900)
    # Geometry and candidate were frozen before this first read of test labels.
    rows = references(end)
    first = rows.groupby("Vehicle_ID").t.min().to_dict()
    rows["cx"], rows["cy"] = body_centers(rows).T
    truth = defaultdict(list)
    for r in rows[
        (rows.t >= start) & (rows.t < end) & ((rows.Frame_ID - 1) % 10 == 0)
    ].itertuples():
        point = np.array([r.cx, r.cy])
        if inside(point):
            truth[round(r.t)].append(
                {"id": int(r.Vehicle_ID), "point": point, "speed": r.v_Vel * 0.3048}
            )
    predictions, births, trails = defaultdict(list), {}, defaultdict(deque)
    processed = 0
    for frame in result_frames(source):
        if frame["index"] != processed:
            raise ValueError("Incomplete or duplicate production frames")
        processed += 1
        t = (frame["index"] - frozen["raw_frame_offset"]) / 10
        for obj in frame["objects"]:
            if obj["class"] not in {"car", "bus", "truck", "motorcycle"}:
                continue
            identity = obj["id"]
            births.setdefault(identity, t)
            x1, y1, x2, y2 = obj["bbox"]
            point = cv2.perspectiveTransform(
                np.float64([[[(x1 + x2) / 2, (y1 + y2) / 2]]]), matrix
            )[0, 0]
            history = trails[identity]
            if history and t - history[-1][0] > 0.3:
                history.clear()
            history.append((t, point))
            while history and history[0][0] < t - 0.75:
                history.popleft()
            speed = None
            if len(history) >= 3:
                times = np.array([v[0] for v in history])
                points = np.array([v[1] for v in history])
                centered = times - times.mean()
                speed = float(
                    np.linalg.norm(
                        centered @ (points - points.mean(axis=0)) / (centered @ centered)
                    )
                )
            if (
                start <= t < end
                and (frame["index"] - frozen["raw_frame_offset"]) % 10 == 0
                and inside(point)
            ):
                predictions[round(t)].append(
                    {"id": identity, "point": point, "speed": speed, "inferred": False}
                )
    if processed != 14961:
        raise ValueError("Scoring did not traverse complete production result")
    reports = {}
    for cohort, lower in [
        ("full_window", None),
        ("calibration_disjoint", 300.000001),
        ("fresh_tracks", start),
    ]:
        a = {
            t: [r for r in rr if lower is None or first[r["id"]] >= lower]
            for t, rr in truth.items()
        }
        b = {
            t: [r for r in rr if lower is None or births[r["id"]] >= lower]
            for t, rr in predictions.items()
        }
        reports[cohort] = evaluate_points(a, b, start, end)
    artifact = {
        "site": "Peachtree camera 1",
        "split": "development" if development else "frozen independent-location temporal holdout",
        "scope": "Model selected on Lankershim, development-only site calibration, actual raw source video; independent annotations never feed detection. Not a full CityFlow/UA-DETRAC box benchmark or physical twin acceptance.",
        "reference_heading_correction_sha256": sha(
            ROOT / "docs/peachtree-evaluator-v7-correction.json"
        ),
        "raw_frame_offset": frozen["raw_frame_offset"],
        "reports": reports,
        "model_frozen_sha256": sha(ROOT / "docs/perception-v7-frozen.json"),
        "calibration_frozen_sha256": sha(ROOT / "docs/peachtree-v7-frozen.json"),
        "production_result_sha256": run["result_sha256"],
        "scoring_source_sha256": sha(Path(__file__)),
        "metrics_source_sha256": sha(ROOT / "backend/atlas/point_metrics_v7.py"),
        "performance": run["performance"],
        "limitations": [
            "Spatial/temporal calibration checks are development diagnostics, not global accuracy bounds",
            "Roof/footprint parallax and manual reference transcription uncertainty remain unquantified",
            "Matched errors are conditional on a fixed 4 m gate; coverage and unmatched observations remain reported",
            "Full-window and calibration-disjoint/fresh-track cohorts must not be silently substituted for each other",
            "Reference session ends well before the complete raw video; no accuracy claim for the unannotated tail",
        ],
    }
    output = (
        ROOT
        / "artifacts/reality/v7"
        / (
            "peachtree-development-evaluation-corrected.json"
            if development
            else "peachtree-frozen-holdout-evaluation-corrected.json"
        )
    )
    if output.exists():
        raise FileExistsError("Preserve first completed evaluation")
    output.write_bytes(json.dumps(artifact, indent=2).encode())
    print(
        json.dumps(
            {
                k: {name: value for name, value in report.items() if name != "per_frame"}
                for k, report in reports.items()
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    evaluate(args.run, args.development)
