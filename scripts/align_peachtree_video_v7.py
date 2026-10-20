"""Measure development raw/reference video alignment using actual road pixels only."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v7/peachtree"


def main():
    cv2.setNumThreads(1)
    calibration = json.loads((DATA / "calibration-development.json").read_text())
    h = np.diag([0.5, 0.5, 1.0]) @ np.array(calibration["raw_to_rectified"])
    mask = np.zeros((172, 320), np.uint8)
    cv2.fillPoly(mask, [np.int32([[0, 49], [319, 78], [319, 121], [0, 120]])], 1)
    targets = {}
    for index in [600, 1200, 1800]:
        image = cv2.resize(cv2.imread(str(DATA / f"processed-development-{index}.jpg")), (320, 172))
        b, g, r = np.moveaxis(image.astype(float), 2, 0)
        annotation = ((g > 170) & (g > r + 35) & (g > b + 35)) | (
            (r > 130) & (b > 110) & (r > g + 25) & (b > g + 20)
        )
        allowed = mask.astype(bool) & ~cv2.dilate(
            annotation.astype(np.uint8), np.ones((3, 3), np.uint8)
        ).astype(bool)
        targets[index] = (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(float), allowed)
    capture = cv2.VideoCapture(
        str(ROOT / "data/reality-v7/official-videos/peachtree-camera1-1245pm-0100pm.avi")
    )
    scores = {index: [] for index in targets}
    for index in range(3000):
        ok, image = capture.read()
        if not ok:
            raise ValueError("Development decoding incomplete")
        if index % 2:
            continue
        warped = cv2.warpPerspective(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), h, (320, 172)).astype(
            float
        )
        for target, (reference, allowed) in targets.items():
            residual = warped[allowed] - reference[allowed]
            # Remove only a global brightness offset, not vehicle geometry.
            error = float(np.mean((residual - np.median(residual)) ** 2))
            scores[target].append((error, index))
    records = []
    for target, candidates in scores.items():
        coarse = sorted(candidates)[0][1]
        dense = []
        reference, allowed = targets[target]
        for index in range(max(0, coarse - 3), min(3000, coarse + 4)):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, image = capture.read()
            if not ok:
                raise ValueError("Exact development frame unavailable")
            warped = cv2.warpPerspective(
                cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), h, (320, 172)
            ).astype(float)
            residual = warped[allowed] - reference[allowed]
            dense.append((float(np.mean((residual - np.median(residual)) ** 2)), index))
        best = sorted(dense)[:5]
        records.append(
            {
                "processed_frame": target,
                "best_raw_frame": best[0][1],
                "offset_frames": best[0][1] - target,
                "coarse_raw_frame": coarse,
                "best_mse": best[0][0],
                "top_candidates": [{"raw_frame": f, "mse": e} for e, f in best],
            }
        )
    capture.release()
    result = {
        "scope": "Raw and reference road-image comparison within first 300 seconds only; no held-out labels or pixels inspected",
        "development_frames": records,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "caution": "This measures image registration/time correspondence, not traffic tracking accuracy. Ambiguous minima must not be accepted as source synchronization.",
    }
    (DATA / "development-time-alignment.json").write_bytes(json.dumps(result, indent=2).encode())
    print(json.dumps(records, indent=2), flush=True)


if __name__ == "__main__":
    main()
