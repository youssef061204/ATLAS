"""Extract every actual CV frame without rerunning inference or reading reference labels."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from atlas.reality_v7 import result_frames


def extract(source_run, output, profile):
    record = json.loads(source_run.read_text())
    source = Path(record["result_file"])
    with source.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if record.get("result_sha256") not in (None, digest):
        raise ValueError("Result checksum mismatch")
    if (output / "run.json").exists():
        raise FileExistsError("Preserve completed extraction")
    output.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(output / "frames.jsonl.gz", "wt", encoding="utf-8") as handle:
        for frame in result_frames(source):
            if frame["index"] != count:
                raise ValueError("Missing or duplicate consecutive frame")
            objects = [
                {key: obj[key] for key in ["id", "class", "confidence", "bbox"]}
                for obj in frame["objects"]
            ]
            handle.write(
                json.dumps({"index": count, "objects": objects}, separators=(",", ":")) + "\n"
            )
            count += 1
    if count != record["performance"]["processed_frames"]:
        raise ValueError("Extraction does not cover full production inference")
    result = {
        "profile": profile,
        "status": "complete cached inference extraction",
        "window_s": [0, count / 10],
        "extracted_frames": count,
        "reused_inference": True,
        "source_run_id": record["video_id"],
        "source_result_sha256": digest,
        "source_performance": record["performance"],
        "frames_sha256": hashlib.file_digest(
            (output / "frames.jsonl.gz").open("rb"), "sha256"
        ).hexdigest(),
        "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Full consecutive 10 Hz NGSIM production result, no reference labels or new inference FPS claim.",
    }
    (output / "run.json").write_bytes(json.dumps(result, indent=2).encode())
    print(json.dumps({"directory": str(output), "frames": count}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    extract(args.source_run, args.output, args.profile)
