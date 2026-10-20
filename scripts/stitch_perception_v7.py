"""Apply a label-free continuity candidate to an actual consecutive-frame CV run."""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from atlas.track_continuity_v7 import interpolate_short_gaps, stitch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--interpolate", action="store_true")
    parser.add_argument("--suffix", default="continuity-v2")
    parser.add_argument("--max-missing", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 < args.max_missing <= 1.5:
        raise ValueError("Offline interpolation is bounded to 1.5 seconds")
    source = args.directory
    out = source.with_name(
        source.name + "-" + args.suffix + ("-interpolated" if args.interpolate else "")
    )
    out.mkdir(parents=True, exist_ok=True)
    if (out / "run.json").exists():
        raise FileExistsError("Preserve prior continuity experiment")
    run = json.loads((source / "run.json").read_text())
    calibration = json.loads((ROOT / "data/reality-v6/camera4-calibration.json").read_text())
    with gzip.open(source / "frames.jsonl.gz", "rt", encoding="utf-8") as handle:
        frames = [json.loads(line) for line in handle]
    started = time.perf_counter()
    frames, joins = stitch(frames, np.asarray(calibration["raw_to_world"]))
    inserted = 0
    if args.interpolate:
        frames, inserted = interpolate_short_gaps(frames, max_missing_s=args.max_missing)
    wall = time.perf_counter() - started
    with gzip.open(out / "frames.jsonl.gz", "wt", encoding="utf-8") as handle:
        for frame in frames:
            handle.write(json.dumps(frame, separators=(",", ":")) + "\n")
    module = ROOT / "backend/atlas/track_continuity_v7.py"
    run = {
        **run,
        "profile": run["profile"]
        + "-"
        + args.suffix
        + ("-interpolated" if args.interpolate else ""),
        "parent_frames_sha256": run["frames_sha256"],
        "frames_sha256": hashlib.sha256((out / "frames.jsonl.gz").read_bytes()).hexdigest(),
        "postprocessing": {
            "joins": sum(row.get("kind") == "handoff" for row in joins),
            "contradiction_splits": sum(row.get("kind") == "contradiction_split" for row in joins),
            "inferred_boxes": inserted,
            "wall_seconds": wall,
            "max_handoff_gap_s": 1,
            "max_missing_interpolation_s": args.max_missing if args.interpolate else 0,
            "source_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
            "uses_reference_labels": False,
        },
    }
    (out / "run.json").write_bytes(json.dumps(run, indent=2).encode())
    (out / "joins.json").write_bytes(json.dumps(joins, indent=2).encode())
    (out / "executed-continuity.py").write_bytes(module.read_bytes())
    print(json.dumps(run["postprocessing"], indent=2), flush=True)


if __name__ == "__main__":
    main()
