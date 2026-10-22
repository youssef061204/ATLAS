"""Check each oracle route ablation against original FHWA movement labels."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "data/reality-v6/trajectory-pages"
ABLATION = ROOT / "artifacts/reality/v8/reference-route-ablation-development.json"
OUT = ROOT / "artifacts/reality/v8/reference-turn-label-check-development.json"
EPOCH = 1118935680000


def main() -> None:
    changed = json.loads(ABLATION.read_text(encoding="utf-8"))["changed_route_records"]
    identities = {int(row["reference_id"]) for row in changed}
    movements = defaultdict(set)
    directions = defaultdict(set)
    source_pages = []
    for path in sorted(PAGES.glob("*.csv.gz")):
        with gzip.open(path, "rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        chunk = pd.read_csv(
            path,
            usecols=["vehicle_id", "frame_id", "global_time", "movement", "direction"],
        )
        relevant = chunk[
            chunk.vehicle_id.isin(identities)
            & (chunk.global_time - (chunk.frame_id - 1) * 100 == EPOCH)
            & (chunk.global_time < EPOCH + 300000)
        ]
        if relevant.empty:
            continue
        source_pages.append({"page": path.name, "sha256": digest})
        for row in relevant.itertuples():
            movements[int(row.vehicle_id)].add(int(row.movement))
            directions[int(row.vehicle_id)].add(int(row.direction))
    unsupported = [
        row["reference_id"] for row in changed if not movements[int(row["reference_id"])] & {2, 3}
    ]
    if unsupported:
        raise ValueError(f"Oracle route lacked official turn-movement evidence: {unsupported}")
    report = {
        "schema": "atlas-v8-oracle-turn-label-check-1",
        "scope": "Previously exposed 0-300 s development; labels derived from future completed tracks and unavailable to causal prediction",
        "changed_oracle_routes": len(changed),
        "routes_with_official_turn_movement_2_or_3": len(changed) - len(unsupported),
        "movement_code_sets": {
            ",".join(map(str, codes)): count
            for codes, count in sorted(
                Counter(tuple(sorted(movements[identity])) for identity in identities).items()
            )
        },
        "direction_code_sets": {
            ",".join(map(str, codes)): count
            for codes, count in sorted(
                Counter(tuple(sorted(directions[identity])) for identity in identities).items()
            )
        },
        "fhwa_data_dictionary": "Direction 1/2/3/4 means east/north/west/south; Movement 1/2/3 means through/left/right. See FHWA NGSIM Lankershim data dictionary.",
        "published_reference_ids": False,
        "source_pages": source_pages,
        "ablation_sha256": hashlib.sha256(ABLATION.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "changed_oracle_routes",
                    "routes_with_official_turn_movement_2_or_3",
                    "movement_code_sets",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
