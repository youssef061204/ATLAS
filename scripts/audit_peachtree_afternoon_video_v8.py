"""Audit the sealed Peachtree afternoon raw video without opening trajectory labels."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from verify_peachtree_afternoon_source_v8 import DECLARED_FRAMES, ROOT, verify

VIDEO = ROOT / "data/reality-v7/official-videos/peachtree-camera5-0400pm-0415pm.avi"
OUT = ROOT / "artifacts/reality/v8/peachtree-afternoon-source-integrity.json"


def main() -> None:
    if OUT.exists():
        raise FileExistsError("Preserve the completed source-integrity artifact")
    source = verify(require_video=True)
    cv2.setNumThreads(1)
    capture = cv2.VideoCapture(str(VIDEO))
    if not capture.isOpened():
        raise ValueError("Raw afternoon video could not be opened")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if (width, height) != (640, 480) or not 9.99 <= fps <= 10.01:
        raise ValueError("Unexpected raw video geometry or frame rate")
    count = changing = exact_duplicates = 0
    differences = []
    sample_hashes = {}
    previous = None
    while True:
        decoded, frame = capture.read()
        if not decoded:
            break
        if frame.shape != (480, 640, 3):
            raise ValueError(f"Unexpected frame shape at {count}: {frame.shape}")
        if count in (0, 1, 2, 600, 3000, 6000, 9000, 14980):
            sample_hashes[str(count)] = hashlib.sha256(frame.tobytes()).hexdigest()
        current = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if previous is not None:
            difference = float(np.mean(cv2.absdiff(current, previous)))
            differences.append(difference)
            changing += difference > 0.5
            exact_duplicates += difference == 0
        previous = current
        count += 1
    capture.release()
    if count != DECLARED_FRAMES or exact_duplicates != source["exact_duplicate_consecutive_pairs"]:
        raise ValueError("Decoded source differs from the official acquisition manifest")
    if changing / len(differences) <= 0.95:
        raise ValueError("Insufficient frame-to-frame motion for a continuous-video source")
    report = {
        "schema": "atlas-v8-peachtree-afternoon-source-integrity-1",
        **source,
        "width": width,
        "height": height,
        "container_duration_seconds": count / fps,
        "consecutive_frame_pairs": len(differences),
        "consecutive_pairs_with_mean_gray_change_gt_0_5": changing,
        "mean_consecutive_gray_change": float(np.mean(differences)),
        "p5_consecutive_gray_change": float(np.percentile(differences, 5)),
        "decoded_frame_sha256_samples": sample_hashes,
        "continuous_video_confirmed": True,
        "raw_video_redistributed": False,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "decoded_frames": count,
                "changing_pairs": changing,
                "exact_duplicate_pairs": exact_duplicates,
                "duration_seconds": count / fps,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
