"""Measure actual CV-to-SUMO attrition without touching reserved test labels."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from atlas.reality_v7 import result_frames
from cv_driven_ngsim_v6 import geometry_mapper, inside
from reconstruct_ngsim_v6 import DATA, EPOCH, road_model

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reality/v7"


def development_observations(end=1000):
    """Read only known development/regression data, using necessary numeric columns."""
    columns = [
        "vehicle_id",
        "frame_id",
        "global_time",
        "local_x",
        "local_y",
        "global_x",
        "global_y",
        "v_length",
        "v_vel",
        "lane_id",
        "section_id",
        "direction",
    ]
    frames = []
    for path in sorted((DATA / "trajectory-pages").glob("*.gz")):
        rows = pd.read_csv(path, usecols=columns)
        selected = (rows.global_time - (rows.frame_id - 1) * 100 == EPOCH) & (
            rows.global_time < EPOCH + end * 1000
        )
        if selected.any():
            frames.append(rows[selected])
    result = pd.concat(frames, ignore_index=True).sort_values(["vehicle_id", "global_time"])
    result["t"] = (result.global_time - EPOCH) / 1000
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    observations = development_observations()
    road, geometry = road_model(observations)
    local = geometry_mapper(road)
    calibration = json.loads((DATA / "camera4-calibration.json").read_text())
    matrix = np.asarray(calibration["raw_to_world"])
    run = json.loads((DATA / "production-pipeline/run.json").read_text())
    source = Path(run["result_file"])
    tracks = {}
    crossings = Counter()
    samples = []
    for frame in result_frames(source):
        t = frame["index"] / 10
        if t >= 1000:
            break
        objects = [
            o for o in frame["objects"] if o["class"] in {"car", "bus", "truck", "motorcycle"}
        ]
        centers = np.array(
            [
                [(o["bbox"][0] + o["bbox"][2]) / 2, (o["bbox"][1] + o["bbox"][3]) / 2]
                for o in objects
            ]
        )
        if not len(centers):
            continue
        world = cv2.perspectiveTransform(centers.reshape(1, -1, 2), matrix)[0]
        positions = local(world)
        for obj, point in zip(objects, positions, strict=True):
            identity = obj["id"]
            track = tracks.get(identity)
            if track is None:
                track = tracks[identity] = {
                    "birth_s": t,
                    "birth_local_ft": point.tolist(),
                    "born_inside": inside(point),
                    "observations": 0,
                    "gaps": 0,
                    "ever_inside": False,
                    "boundary_crossing": False,
                    "last_s": t,
                    "last_point": point,
                }
            elif not inside(track["last_point"]) and inside(point):
                if t - track["last_s"] <= 0.3:
                    track["boundary_crossing"] = True
                    crossings["all_contiguous_entry_events"] += 1
            if t - track["last_s"] > 0.3:
                track["gaps"] += 1
            track["observations"] += 1
            track["ever_inside"] |= inside(point)
            track["last_s"], track["last_point"] = t, point
        if frame["index"] == 1200:
            samples = objects
    summary = {}
    for name, start, end in [("development", 0, 300), ("known_validation", 600, 1000)]:
        cohort = [r for r in tracks.values() if start <= r["birth_s"] < end]
        interior = [r for r in cohort if r["ever_inside"]]
        summary[name] = {
            "born_track_ids": len(cohort),
            "ever_inside_network_ids": len(interior),
            "born_inside_network_ids": sum(r["born_inside"] for r in cohort),
            "ids_with_contiguous_boundary_crossing": sum(r["boundary_crossing"] for r in interior),
            "interior_ids_without_boundary_crossing": sum(
                not r["boundary_crossing"] for r in interior
            ),
            "short_tracks_lt_10_frames": sum(r["observations"] < 10 for r in interior),
            "ids_with_gaps_gt_0_3_s": sum(r["gaps"] > 0 for r in interior),
        }
        summary[name] = {key: int(value) for key, value in summary[name].items()}
    # Actual source pixels and actual predictions. No invented reference boxes.
    capture = cv2.VideoCapture(str(DATA / "lankershim-camera4-0830am-0845am.avi"))
    capture.set(cv2.CAP_PROP_POS_FRAMES, 1200)
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError("Diagnostic source frame failed to decode")
    for obj in samples:
        x1, y1, x2, y2 = map(round, obj["bbox"])
        track = tracks[obj["id"]]
        color = (80, 180, 240) if track["born_inside"] else (120, 230, 120)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)
        cv2.putText(image, str(obj["id"]), (x1, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
    cv2.imwrite(
        str(OUT / "development-boundary-diagnostic.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 94]
    )
    report = {
        "scope": "Development and previously exposed validation only; no reserved test outcomes read",
        "window_s": [0, 1000],
        "cohorts": summary,
        "interpretation": "Track IDs are fragmented predictions, not unique observed vehicles. Boundary exclusion and duplicate births must both be solved; admitting every birth would overcount.",
        "diagnostic_image": {
            "frame": 1200,
            "time_s": 120,
            "orange": "ID born inside network",
            "green": "ID born outside network",
            "boxes": "Actual ATLAS predictions; not independent annotations",
        },
        "geometry": geometry,
        "input_result_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUT / "boundary-diagnostics.json").write_bytes(json.dumps(report, indent=2).encode())
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
