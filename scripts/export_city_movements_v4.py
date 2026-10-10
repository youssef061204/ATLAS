"""Publish genuine historical Toronto movements from the bounded ingestion cache.

Run ingest_city_data_v4.py first. Raw cached API responses stay ignored; this export
contains licensed aggregate movements with response digests, no camera images.
"""

import gzip
import hashlib
import json
from pathlib import Path


def main():
    rows, responses = [], []
    for path in Path("data/city-count-cache-v4").glob("*.json"):
        cache = json.loads(path.read_text(encoding="utf-8"))
        if (
            cache["url"].endswith("/datastore_search")
            and cache["params"].get("resource_id") == "262469c2-abfe-4756-9068-4ea5c7ba1af7"
        ):
            body = cache["body"].encode()
            if hashlib.sha256(body).hexdigest() != cache["sha256"]:
                raise ValueError("Count cache digest mismatch")
            response = json.loads(body)
            rows.extend(response["result"]["records"])
            responses.append(
                {
                    "params": cache["params"],
                    "sha256": cache["sha256"],
                    "retrieved_at": cache["retrieved_at"],
                }
            )
    if not rows or len({row["_id"] for row in rows}) != len(rows):
        raise ValueError("Missing or duplicated official source rows")
    record = {
        "schema_version": "atlas-historical-turn-movements-4.0",
        "city": "toronto",
        "license": {
            "name": "Open Government Licence - Toronto",
            "url": "https://open.toronto.ca/open-data-licence/",
            "attribution": "Contains information licensed under the Open Government Licence - Toronto.",
        },
        "source": "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/datastore_search",
        "resource_id": "262469c2-abfe-4756-9068-4ea5c7ba1af7",
        "time_basis": "America/Toronto source-local civil time",
        "interval_seconds": 900,
        "source_responses": responses,
        "records": sorted(rows, key=lambda row: (row["start_time"], row["centreline_id"])),
        "limitations": [
            "Actual historical count movements, not current camera observations.",
            "Approach labels are source-defined, not automatically matched to SUMO edge movements.",
            "Historical geometry, signal timing, queue/travel time measurements unavailable; no independent twin calibration.",
        ],
    }
    raw = json.dumps(record, separators=(",", ":"), allow_nan=False).encode()
    output = Path("artifacts/cities/v4/data-toronto-movements.json.gz")
    output.write_bytes(gzip.compress(raw, mtime=0))
    print(
        len(rows), "actual historical bins; SHA256", hashlib.sha256(output.read_bytes()).hexdigest()
    )


if __name__ == "__main__":
    main()
