"""Independent annotated gate crossings, same declared lines for GT and predictions."""

import json
from pathlib import Path

import numpy as np
from atlas.cities import now
from atlas.city_network import sha
from atlas.visual_flow import analyze_tracks


def main():
    root = Path("datasets/ua-detrac")
    manifest = json.loads((root / "manifest.json").read_text())
    cache = Path("datasets/evaluation-runs/detrac-test-baseline-640-0.25")
    rows = []
    for item in manifest["splits"]["test"]:
        sequence = item["sequence"]
        folder = root / "test" / sequence
        frames = json.loads((folder / "frames.json").read_text())
        cached = json.loads((cache / f"{sequence}.json").read_text())
        if cached["signature"]["manifest_sha256"] != sha(root / "manifest.json"):
            raise ValueError("Prediction source mismatch")
        annotation = [f["objects"] for f in frames]
        predictions = cached["tracks"]
        for y in (0.4, 0.6, 0.8):
            start, end = [0.05, y], [0.95, y]
            gt = analyze_tracks(
                annotation, frames[0]["width"], frames[0]["height"], manifest["fps"], start, end
            )
            pred = analyze_tracks(
                predictions, frames[0]["width"], frames[0]["height"], manifest["fps"], start, end
            )
            bins = int(np.ceil(len(frames) / 60))
            duration = 60 / manifest["fps"]
            for direction in ("positive", "negative"):
                true = np.zeros(bins, dtype=int)
                estimated = np.zeros(bins, dtype=int)
                for events, counts in ((gt, true), (pred, estimated)):
                    for event in events:
                        if event["direction"] == direction:
                            counts[min(bins - 1, int(event["t"] / duration))] += 1
                rows.append(
                    {
                        "sequence": sequence,
                        "line_y_normalized": y,
                        "direction": direction,
                        "bin_seconds": duration,
                        "bins": bins,
                        "observed_crossings": int(true.sum()),
                        "predicted_crossings": int(estimated.sum()),
                        "count_mae_per_bin": float(np.abs(true - estimated).mean()),
                        "count_rmse_per_bin": float(np.sqrt(np.mean((true - estimated) ** 2))),
                        "gt_bin_counts": true.tolist(),
                        "predicted_bin_counts": estimated.tolist(),
                    }
                )
    output = {
        "experiment_id": "detrac-virtual-gates-v3-01",
        "registered_geometry": "full-width gates x=.05–.95 at y=.4/.6/.8; all three evaluated, no selection",
        "recorded_at": now(),
        "dataset_manifest_sha256": sha(root / "manifest.json"),
        "counter_source_sha256": sha("backend/atlas/visual_flow.py"),
        "evaluation_source_sha256": sha(__file__),
        "fps": manifest["fps"],
        "model": "Frozen YOLO11n + ByteTrack predictions",
        "rows": rows,
        "scope": "Image-plane directional line-crossing counts against independently annotated trajectories; not turning-movement, physical queue or municipal detector validation",
        "limitations": [
            "Only three original test cameras",
            "Track fragmentation can lose crossings; recross suppression counts each track once per direction",
            "60-frame bins are 2.4 seconds at 25 FPS; short final bins retained",
            "Ground truth gate positions come from annotated vehicle bottom centers, not surveyed road geometry",
        ],
    }
    Path("artifacts/cities/visual-flow.json").write_text(
        json.dumps(output, allow_nan=False), encoding="utf-8"
    )
    print(
        "Evaluated",
        len(rows),
        "line/direction/sequence cases;",
        sum(r["observed_crossings"] for r in rows),
        "annotated gate-crossing events; weighted count MAE",
        sum(r["count_mae_per_bin"] * r["bins"] for r in rows) / sum(r["bins"] for r in rows),
        flush=True,
    )


if __name__ == "__main__":
    main()
