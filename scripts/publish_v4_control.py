"""Publish compact truthful study summaries and lossless raw-evidence bundles."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-directory", type=Path, required=True)
    parser.add_argument(
        "--status",
        choices=["development", "validation", "final", "rejected_diagnostic"],
        required=True,
    )
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archives = []
    for city in sorted({r["city"] for r in source["runs"]}):
        name = args.output.stem + "-" + city + "-raw.jsonl.gz"
        destination = args.output.parent / name
        members, raw_sha = [], hashlib.sha256()
        raw_bytes = 0
        with destination.open("wb") as output:
            with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as bundle:
                for row in source["runs"]:
                    if row["city"] != city:
                        continue
                    path = args.raw_directory / row["raw_archive"]
                    raw = gzip.decompress(path.read_bytes())
                    original = json.loads(raw)
                    # Publication never edits measured values or drops unfavorable rows.
                    if original["metrics"] != row["metrics"]:
                        raise ValueError("Raw result and summary metrics differ")
                    line = (
                        json.dumps(original, separators=(",", ":"), allow_nan=False).encode()
                        + b"\n"
                    )
                    raw_sha.update(line)
                    raw_bytes += len(line)
                    bundle.write(line)
                    members.append(
                        {
                            "city": city,
                            "candidate": row["candidate"],
                            "seed": row["seed"],
                            "individual_archive": row["raw_archive"],
                            "individual_archive_sha256": checksum(path),
                            "original_json_sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
                    row["evidence_bundle"] = name
        archives.append(
            {
                "file": name,
                "gzip_sha256": checksum(destination),
                "raw_sha256": raw_sha.hexdigest(),
                "raw_bytes": raw_bytes,
                "gzip_bytes": destination.stat().st_size,
                "members": members,
            }
        )
    index = args.output.with_name(args.output.stem + "-evidence-index.json")
    index.write_text(
        json.dumps({"status": args.status, "bundles": archives}, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    source["publication_status"] = args.status
    source["evidence_index"] = index.name
    for row in source["runs"]:
        if args.status == "rejected_diagnostic":
            row["trace"], row["decisions"] = [], []
        else:
            # State/topology repeats live in lossless bundles; compact interactive replay remains.
            for frame in row.get("trace", []):
                frame.pop("lane_observations", None)
                frame.pop("movements", None)
    args.output.write_text(
        json.dumps(source, separators=(",", ":"), allow_nan=False), encoding="utf-8", newline="\n"
    )
    print(
        args.output,
        len(source["runs"]),
        "runs;",
        sum(a["gzip_bytes"] for a in archives),
        "raw-evidence gzip bytes",
    )


if __name__ == "__main__":
    main()
