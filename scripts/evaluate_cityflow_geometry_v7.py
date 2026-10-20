"""Run real S02 cached detections through label-blind calibrated association.

S02 is already exposed ATLAS 6 regression data, not a new independent holdout.
Raw CityFlow predictions, GPS tracks and association maps remain local.
"""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from atlas.multicamera_v7 import GeoTracklet, associate_geometry
from evaluate_cityflow_v6 import CAMERAS, DATA, evaluate

ROOT = Path(__file__).resolve().parents[1]


def main():
    candidates = []
    geometric = []
    rois = {}
    expected = {}
    source_records = []
    offsets = {
        cam: float(t)
        for cam, t in (
            line.split() for line in (DATA / "cam_timestamp/S02.txt").read_text().splitlines()
        )
    }
    for camera in CAMERAS:
        record = json.loads((DATA / "pipeline" / f"{camera}-run.json").read_text())
        path = Path(record["result_file"])
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        result = json.loads(path.read_text())
        expected[camera] = result["performance"]["decoded_frames"]
        roi = cv2.imread(str(DATA / f"validation/S02/{camera}/roi.jpg"), cv2.IMREAD_GRAYSCALE)
        rois[camera] = roi
        text = (
            (DATA / f"validation/S02/{camera}/calibration.txt")
            .read_text()
            .splitlines()[0]
            .split(":", 1)[1]
        )
        matrix = np.linalg.inv(
            np.array([[float(v) for v in row.split()] for row in text.split(";")])
        )
        source_records.append(
            {"camera": camera, "result_sha256": digest, "decoded_frames": expected[camera]}
        )
        for track in result["tracks"]:
            points = track["points"]
            if track["class"] not in {"car", "truck", "bus", "motorcycle"} or len(points) < 3:
                continue
            areas = []
            support = []
            for p in points:
                x1, y1, x2, y2 = p["bbox"]
                areas.append((x2 - x1) * (y2 - y1))
                x, y = int((x1 + x2) / 2), int((y1 + y2) / 2)
                support.append(0 <= x < roi.shape[1] and 0 <= y < roi.shape[0] and roi[y, x] > 127)
            if np.median(areas) < 1000 or np.mean(support) < 0.5:
                continue
            candidates.append({"camera": camera, "id": track["id"], "points": points})
            pixels = np.array(
                [[(p["bbox"][0] + p["bbox"][2]) / 2, p["bbox"][3], 1] for p in points]
            )
            gps = pixels @ matrix.T
            gps = gps[:, :2] / gps[:, 2, None]
            xy = (gps - [42.491916, -90.723723]) * [111320, 111320 * np.cos(np.deg2rad(42.491916))]
            times = np.array([p["t"] + offsets[camera] for p in points])
            valid = np.isfinite(xy).all(axis=1) & (np.linalg.norm(xy, axis=1) < 1000)
            geometric.append(GeoTracklet(camera, track["id"], times[valid], xy[valid]))
        del result
    mapping, accepted, diagnostics = associate_geometry(geometric)
    out = ROOT / "data/reality-v7/cityflow-S02-geometry"
    out.mkdir(parents=True, exist_ok=True)
    frozen = {
        "mapping": [[cam, identity, global_id] for (cam, identity), global_id in mapping.items()],
        "accepted": accepted,
        "diagnostics": diagnostics,
        "reference_identities_used": False,
        "sources": source_records,
    }
    (out / "association-before-scoring.json").write_bytes(json.dumps(frozen, indent=2).encode())
    baseline = {(track["camera"], track["id"]): i + 1 for i, track in enumerate(candidates)}
    before = evaluate(candidates, baseline, rois, expected)
    # Same exact detector/tracker observations, source ROI and official GT cohort.
    if not np.isclose(before["identity"]["IDF1"], 0.260123961981429, atol=1e-8):
        raise ValueError(f"Cached baseline cohort changed: {before['identity']['IDF1']}")
    after = evaluate(candidates, mapping, rois, expected)
    assert before["predicted_boxes"] == after["predicted_boxes"]
    publication = {
        "scope": __doc__,
        "candidate_tracklets": len(candidates),
        "accepted_links": len(accepted),
        "diagnostics": diagnostics,
        "before_association": before,
        "after_association_same_detections": after,
        "idf1_change": after["identity"]["IDF1"] - before["identity"]["IDF1"],
        "source_sha256": hashlib.sha256(
            (ROOT / "backend/atlas/multicamera_v7.py").read_bytes()
        ).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "local_mapping_sha256": hashlib.sha256(
            (out / "association-before-scoring.json").read_bytes()
        ).hexdigest(),
        "limitations": [
            "Known S02 regression scene; no independent generalization claim",
            "Manual homography and source timestamps have unquantified world-position/synchronization uncertainty",
            "Ground-contact approximation from box bottom-center; no independent surveyed physical accuracy",
            "No raw video, predictions, appearance vectors or GPS trajectories redistributed",
        ],
    }
    (ROOT / "artifacts/reality/v7/cityflow-S02-geometry-results.json").write_bytes(
        json.dumps(publication, indent=2).encode()
    )
    print(
        json.dumps(
            {
                key: publication[key]
                for key in [
                    "candidate_tracklets",
                    "accepted_links",
                    "diagnostics",
                    "idf1_change",
                    "before_association",
                    "after_association_same_detections",
                ]
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
