"""Bundle compact cached output from a completed real inference run, never generated tracks."""

import gzip
import hashlib
import json

from atlas import config, db

db.init()
measured = json.loads((config.ARTIFACTS / "pipeline.json").read_text())
row = {"id": measured["video_id"]}
source = config.DATA / "results" / f"{row['id']}.json"
result = json.loads(source.read_text())
result["provenance"]["source_sha256"] = hashlib.sha256(
    (config.DATA / "demo.mp4").read_bytes()
).hexdigest()
result["provenance"]["sample_scope"] = (
    "Mixkit #1755 overhead time-lapse; frame timestamps are playback time, not surveyed real-world elapsed time"
)
result["provenance"]["model_source"] = (
    "https://huggingface.co/dronefreak/visdrone-yolov8n/tree/b5ca8d362341457ad715a5314da0931ea58bb237"
)
target = config.ARTIFACTS / "demo"
target.mkdir(exist_ok=True)
with gzip.open(target / "result.json.gz", "wt", encoding="utf-8", compresslevel=9) as output:
    json.dump(result, output, separators=(",", ":"), allow_nan=False)
(target / "manifest.json").write_text(
    json.dumps(
        {
            "generated_at": result["provenance"]["generated_at"],
            "source_sha256": result["provenance"]["source_sha256"],
            "model": result["performance"]["model"],
            "frames": len(result["frames"]),
            "scope": result["provenance"]["sample_scope"],
            "artifact_sha256": hashlib.sha256((target / "result.json.gz").read_bytes()).hexdigest(),
        },
        indent=2,
    )
)
print(
    f"Cached {len(result['frames'])} actual frames in {(target / 'result.json.gz').stat().st_size} bytes"
)
