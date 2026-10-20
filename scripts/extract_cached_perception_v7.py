"""Reuse genuine complete ATLAS inference without claiming a new inference run."""

import gzip
import hashlib
import json
from pathlib import Path

from atlas.reality_v7 import result_frames

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_run = json.loads((ROOT / "data/reality-v6/production-pipeline/run.json").read_text())
    source = Path(source_run["result_file"])
    out = ROOT / "data/reality-v7/v6-cached-0-1000"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "run.json").exists():
        raise FileExistsError("Never overwrite a completed extraction")
    count = 0
    with gzip.open(out / "frames.jsonl.gz", "wt", encoding="utf-8") as handle:
        for frame in result_frames(source):
            if frame["index"] >= 10000:
                break
            objects = [
                {key: obj[key] for key in ["id", "class", "confidence", "bbox"]}
                for obj in frame["objects"]
            ]
            handle.write(
                json.dumps({"index": frame["index"], "objects": objects}, separators=(",", ":"))
                + "\n"
            )
            count += 1
    record = {
        "status": "complete cached inference extraction",
        "profile": "v6-cached",
        "window_s": [0, 1000],
        "reused_inference": True,
        "source_run_id": source_run["video_id"],
        "source_result_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "frames_sha256": hashlib.sha256((out / "frames.jsonl.gz").read_bytes()).hexdigest(),
        "extracted_frames": count,
        "source_performance": source_run["performance"],
        "scope": "First 1000 seconds of the already complete 11220-frame ATLAS 6 run. No new detection inference or FPS claim.",
    }
    (out / "run.json").write_bytes(json.dumps(record, indent=2).encode())
    print(json.dumps({"frames": count, "directory": out.name}), flush=True)


if __name__ == "__main__":
    main()
