"""Bounded official-source discovery; preserve metadata, errors and retrieval dates.

Discovery is not ingestion or validation. Existing ATLAS 4 datasets stay frozen.
"""

import hashlib
import json
from pathlib import Path

from atlas.city_data_v4 import HistoricalClient, stamp

REQUESTS = [
    (
        "austin",
        "radar counts and speeds as an alternative to discontinued vision counters",
        "https://data.austintexas.gov/api/views/i626-g7ub.json",
        {},
    ),
    (
        "austin",
        "current traffic-study request inventory; requests are not measurements",
        "https://data.austintexas.gov/api/views/4zky-76x4.json",
        {},
    ),
    (
        "london",
        "actual Whitehall hourly survey observations, distinct from AADF",
        "https://roadtraffic.dft.gov.uk/api/raw-counts",
        {
            "filter[count_point_id]": 27663,
            "page[size]": 500,
            "page[number]": 1,
            "sort": "count_date,hour,direction_of_travel",
        },
    ),
    (
        "toronto",
        "turning-study metadata and related geometry",
        "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show",
        {"id": "traffic-volumes-at-intersections-for-all-modes"},
    ),
    (
        "toronto",
        "official street centreline metadata",
        "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show",
        {"id": "toronto-centreline-tcl"},
    ),
    (
        "london",
        "alternative Whitehall count-point metadata; not annual counts as hourly truth",
        "https://roadtraffic.dft.gov.uk/api/count-points",
        {"filter[road_name]": "A3212", "page[size]": 100, "page[number]": 1},
    ),
    (
        "seattle",
        "study register field definitions and licensing",
        "https://data.seattle.gov/api/views/xucb-vzhc.json",
        {},
    ),
    (
        "seattle",
        "official study segment identifiers",
        "https://data.seattle.gov/resource/xucb-vzhc.json",
        {
            "$where": "title like 'DENNY WAY%' AND start_date > '2026-01-01T00:00:00'",
            "$order": "start_date DESC",
            "$limit": 10,
        },
    ),
    (
        "austin",
        "alternative Traffic Count Study Area metadata",
        "https://data.austintexas.gov/api/views/cqdh-farx.json",
        {},
    ),
    (
        "austin",
        "independent study-area geometry and report references",
        "https://data.austintexas.gov/resource/cqdh-farx.json",
        {"$limit": 10},
    ),
    (
        "austin",
        "discontinued camera-counter limitations",
        "https://data.austintexas.gov/api/views/sh59-i6y9.json",
        {},
    ),
    (
        "calgary",
        "permanent count sensor metadata",
        "https://data.calgary.ca/api/views/sqwx-tjsy.json",
        {},
    ),
    (
        "calgary",
        "signal location definitions; timing plans not inferred",
        "https://data.calgary.ca/api/views/qr97-4jvx.json",
        {},
    ),
    (
        "calgary",
        "traffic count timestamp and measurement definitions",
        "https://data.calgary.ca/api/views/vuyp-sbjp.json",
        {},
    ),
]


def summarize(data):
    if isinstance(data, list):
        return {"sample_rows": data, "sample_only": True}
    if "result" in data:
        package = data["result"]
        return {
            key: package.get(key)
            for key in (
                "id",
                "name",
                "title",
                "notes",
                "license_id",
                "license_title",
                "license_url",
                "metadata_modified",
                "resources",
            )
        }
    if "columns" in data:
        return {
            "name": data.get("name"),
            "description": data.get("description"),
            "license": data.get("license"),
            "metadata": data.get("metadata"),
            "rowsUpdatedAt": data.get("rowsUpdatedAt"),
            "columns": [
                {key: c.get(key) for key in ("fieldName", "name", "description", "dataTypeName")}
                for c in data["columns"]
                if not c.get("fieldName", "").startswith(":")
            ],
        }
    return data


def main():
    client = HistoricalClient("data/city-calibration-v5/source-cache")
    rows = []
    try:
        for city, purpose, url, params in REQUESTS:
            item = {"city": city, "purpose": purpose, "url": url, "params": params}
            try:
                data, retrieved = client.get(url, params)
                item.update(status="retrieved", retrieved_at=retrieved, metadata=summarize(data))
                item["response_sha256"] = client.health[-1]["source_response_sha256"]
            except Exception as exc:
                item.update(
                    status="unavailable",
                    checked_at=stamp(),
                    error_type=type(exc).__name__,
                    reason=str(exc),
                )
            rows.append(item)
            print(city, purpose, item["status"], flush=True)
    finally:
        client.close()
    artifact = {
        "schema_version": "atlas-calibration-source-discovery-5.0",
        "generated_at": stamp(),
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requests": rows,
        "health": client.health,
        "limitations": [
            "Small source samples and metadata are discovery evidence, not calibrated observations.",
            "Alternative corridors require temporal and approach mapping validation before simulation fitting.",
        ],
    }
    output = Path("artifacts/cities/v5/source-discovery.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
