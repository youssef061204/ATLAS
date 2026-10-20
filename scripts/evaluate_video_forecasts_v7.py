"""Chronological actual-video occupancy forecasting pilot, with honest duration limits.

The target is mean independently observed visible vehicles during a future 30 s
window, not arterial flow, speed, or unique vehicle counts. All models are fixed
before this first pilot score. No source annotations are fed to the CV pipeline.
"""

import gzip
import json
from pathlib import Path

import cv2
import numpy as np
from calibrate_physics_v7 import reference_states, sha
from diagnose_ngsim_v7 import DATA, ROOT, development_observations
from reconstruct_ngsim_v6 import road_model
from scipy.spatial import cKDTree
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def main():
    publication = ROOT / "artifacts/reality/v7/video-occupancy-forecast-pilot.json"
    if publication.exists():
        raise FileExistsError("Preserve first pilot results")
    out = ROOT / "data/reality-v7/video-forecast-pilot"
    out.mkdir(parents=True, exist_ok=True)
    protocol = {
        "registered_before_pilot_scores": True,
        "train_all_target_times_before_s": 600,
        "test_forecast_origins_s": [600, 1000],
        "annotation_complete_known_interval_s": [0, 1000],
        "lookback_s": 60,
        "origin_stride_s": 10,
        "horizons_s": [60, 180, 300],
        "target": "Independent body-centre ROI visible-vehicle count averaged over [origin+horizon, origin+horizon+30). Not flow or unique vehicles.",
        "models": [
            "raw_cv_persistence_30s",
            "development_bias_corrected_persistence",
            "training_target_mean",
            "ridge_alpha10",
        ],
        "features": "Trailing actual-CV mean/std/linear trend over 60s and mean/min/max over 30s; no future input, identities or target leakage.",
        "geometry": "Frozen first-300-second road curve and camera homography, fixed region; no region selection on test errors",
        "selection": "No hyperparameter or winner selection; report every fixed model at every supported horizon",
        "uncertainty": "Too short for a credible separate five-minute interval-calibration set; no calibrated prediction interval claim",
        "source_sha256": sha(Path(__file__)),
    }
    with (out / "protocol.json").open("x", encoding="utf-8") as handle:
        json.dump(protocol, handle, indent=2)
    source = development_observations(1001)
    road, _ = road_model(source)
    _, truth = reference_states(source, road)
    actual = np.array([len(truth[t * 10]) for t in range(1000)], dtype=float)
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    normal = np.gradient(curve, axis=0)[:, ::-1] * [1, -1]
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    tree = cKDTree(curve)
    matrix = np.asarray(json.loads((DATA / "camera4-calibration.json").read_text())["raw_to_world"])
    cache = ROOT / "data/reality-v7/full-v7-lankershim/frames.jsonl.gz"
    observed = np.zeros(1000)
    scored_frames = 0
    with gzip.open(cache, "rt", encoding="utf-8") as handle:
        for line in handle:
            frame = json.loads(line)
            index = frame["index"]
            if index >= 10000:
                break
            if index % 10:
                continue
            boxes = [
                v["bbox"]
                for v in frame["objects"]
                if v["class"] in {"car", "bus", "truck", "motorcycle"} and not v.get("inferred")
            ]
            if boxes:
                boxes = np.asarray(boxes)
                xy = cv2.perspectiveTransform(
                    ((boxes[:, :2] + boxes[:, 2:]) / 2).reshape(-1, 1, 2), matrix
                )[:, 0]
                _, nearest = tree.query(xy)
                lateral = np.sum((xy - curve[nearest]) * normal[nearest], axis=1)
                observed[index // 10] = (
                    (grid[nearest] >= 1090) & (grid[nearest] <= 1360) & (abs(lateral) <= 16)
                ).sum()
            scored_frames += 1
    if scored_frames != 1000:
        raise ValueError("Incomplete actual CV count series")

    def feature(t):
        # At origin t, only samples strictly before t are visible.
        a, b = observed[t - 60 : t], observed[t - 30 : t]
        trend = np.polyfit(np.arange(60), a, 1)[0]
        return [a.mean(), a.std(), trend, b.mean(), b.min(), b.max()]

    rows = []
    bias = float(np.mean(actual[:300] - observed[:300]))
    for horizon in protocol["horizons_s"]:
        train = np.array([t for t in range(60, 600, 10) if t + horizon + 30 <= 600])
        test = np.array([t for t in range(600, 1000, 10) if t + horizon + 30 <= 1000])
        x = np.asarray([feature(int(t)) for t in train])
        y = np.array([actual[t + horizon : t + horizon + 30].mean() for t in train])
        model = make_pipeline(StandardScaler(), Ridge(alpha=10))
        model.fit(x, y)
        target = np.array([actual[t + horizon : t + horizon + 30].mean() for t in test])
        persistence = np.array([observed[t - 30 : t].mean() for t in test])
        estimates = {
            "raw_cv_persistence_30s": persistence,
            "development_bias_corrected_persistence": np.maximum(0, persistence + bias),
            "training_target_mean": np.full(len(test), y.mean()),
            "ridge_alpha10": np.maximum(
                0, model.predict(np.asarray([feature(int(t)) for t in test]))
            ),
        }
        outcomes = {}
        for name, predicted in estimates.items():
            errors = predicted - target
            outcomes[name] = {
                "mae_vehicles": float(np.abs(errors).mean()),
                "rmse_vehicles": float(np.sqrt(np.mean(errors**2))),
                "bias_vehicles": float(errors.mean()),
            }
        row = {
            "horizon_s": horizon,
            "training_origins": len(train),
            "test_origins": len(test),
            "first_test_origin_s": int(test[0]),
            "last_test_origin_s": int(test[-1]),
            "outcomes": outcomes,
            "series": [
                {
                    "origin_s": int(t),
                    "target_vehicles": float(target[i]),
                    **{name: float(pred[i]) for name, pred in estimates.items()},
                }
                for i, t in enumerate(test)
            ],
        }
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "series"}), flush=True)
    artifact = {
        "split": "Chronological pilot on known Lankershim recording, not a new independent-city holdout",
        "protocol": protocol,
        "protocol_sha256": sha(out / "protocol.json"),
        "actual_cv_count_frames": scored_frames,
        "cv_frames_sha256": sha(cache),
        "development_count_bias_correction_vehicles": bias,
        "results": rows,
        "unsupported_horizons_s": [900, 1800],
        "limitations": [
            "Single short recording and one intersection; strongly overlapping forecast targets are not independent samples",
            "Five-minute test has only eight forecast origins, covering 70 seconds of origin times; no robust long-horizon generalization or uncertainty claim",
            "Observed occupancy depends on camera footprint and annotation coverage; it is not a field flow forecast",
            "15/30 minute forecasts cannot be evaluated honestly with this source duration and chronological fitting",
            "No METR-LA result is replaced or transferred to this video domain; no forecast-driven controller promotion",
        ],
        "source_sha256": sha(Path(__file__)),
    }
    publication.write_bytes(json.dumps(artifact, indent=2).encode())


if __name__ == "__main__":
    main()
