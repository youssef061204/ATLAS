"""Actual authenticated native HTTP inference and warm request profile.

Caller supplies ATLAS_OPERATOR_KEY; authorization headers are never persisted.
Known first chronological test histories come from actual official count archives.
"""

import argparse
import gzip
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
from atlas.city_forecast_v4 import samples
from atlas.city_runtime_v4 import digest, geographic_distance


def payload(city, document):
    rows, _ = samples(document)
    selected = next(row for row in rows if row["split"] == "test")
    target = datetime.fromisoformat(selected["time"])
    moments = [
        target - timedelta(seconds=selected["interval_seconds"] * index) for index in (3, 2, 1)
    ]
    indexed = {
        (row["site_id"], row["direction"], datetime.fromisoformat(row["observed_at"])): row
        for row in document["records"]
    }
    histories = [
        indexed[(selected["site_id"], selected["direction"], moment)] for moment in moments
    ]
    neighbors = []
    for site in document["sites"]:
        if (
            site == selected["site_id"]
            or geographic_distance(document["sites"][site], document["sites"][selected["site_id"]])
            > 1500
        ):
            continue
        records = [indexed.get((site, selected["direction"], moment)) for moment in moments]
        if all(
            record and record["interval_seconds"] == selected["interval_seconds"]
            for record in records
        ):
            neighbors.append(
                {
                    "site_id": site,
                    "direction": selected["direction"],
                    "history": [
                        {"observed_at": record["observed_at"], "count": record["count"]}
                        for record in records
                    ],
                }
            )
    return {
        "city": city,
        "site_id": selected["site_id"],
        "direction": selected["direction"],
        "time_basis": histories[0]["time_basis"],
        "interval_seconds": selected["interval_seconds"],
        "measurement_kind": "historical_motor_vehicle_count",
        "history": [
            {"observed_at": row["observed_at"], "count": row["count"]} for row in histories
        ],
        "neighbors": neighbors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    parser.add_argument("--warm-requests", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.warm_requests <= 100:
        raise ValueError("Warm verification budget must be 1?100 per city")
    key = os.environ.get("ATLAS_OPERATOR_KEY")
    if not key:
        raise ValueError("Authenticated native operator key required")
    root = Path("artifacts/cities/v4")
    evidence = json.loads((root / "city-forecast.json").read_text(encoding="utf-8"))
    requests = {
        city: payload(
            city, json.loads(gzip.decompress((root / f"data-{city}.json.gz").read_bytes()))
        )
        for city in ("toronto", "london", "seattle", "austin", "calgary")
    }
    results = []
    with httpx.Client(timeout=30) as client:
        endpoint = args.url.rstrip("/") + "/api/operations/models/city/infer"
        unauthenticated = client.post(endpoint, json=requests["toronto"])
        if unauthenticated.status_code not in (401, 403):
            raise ValueError("Native inference did not enforce operator authentication")
        headers = {"Authorization": f"Bearer {key}"}
        for city, request in requests.items():
            cold_start = time.perf_counter()
            response = client.post(endpoint, json=request, headers=headers)
            cold_ms = (time.perf_counter() - cold_start) * 1000
            response.raise_for_status()
            result = response.json()
            if result["provenance"].get("runtime_source_sha256") != digest(
                Path("backend/atlas/city_runtime_v4.py")
            ):
                raise ValueError(
                    "Native API uses an older runtime module; restart owned API after research jobs finish"
                )
            elapsed, server = [], []
            for _ in range(args.warm_requests):
                started = time.perf_counter()
                response = client.post(endpoint, json=request, headers=headers)
                elapsed.append((time.perf_counter() - started) * 1000)
                response.raise_for_status()
                current = response.json()
                server.append(current["runtime_ms"])
                if current["predicted_count"] != result["predicted_count"]:
                    raise ValueError("Frozen repeated input produced inconsistent predictions")
            preview = next(study for study in evidence["cities"] if study["city"] == city)[
                "preview"
            ][0]
            if abs(preview["predicted"] - result["predicted_count"]) > 1e-4:
                raise ValueError(
                    "Native first-test forecast differs from actual frozen evaluation preview"
                )
            results.append(
                {
                    "city": city,
                    "status": "passed",
                    "input": request,
                    "response": result,
                    "initial_http_request_ms": cold_ms,
                    "warm_request_count": len(elapsed),
                    "warm_http_ms_p50": float(np.percentile(elapsed, 50)),
                    "warm_http_ms_p95": float(np.percentile(elapsed, 95)),
                    "warm_server_runtime_ms_p50": float(np.percentile(server, 50)),
                    "warm_server_runtime_ms_p95": float(np.percentile(server, 95)),
                    "raw_warm_http_ms": elapsed,
                    "raw_warm_server_runtime_ms": server,
                    "frozen_preview_prediction_matches": True,
                }
            )
            print(
                city,
                "HTTP profile",
                results[-1]["warm_http_ms_p50"],
                results[-1]["warm_http_ms_p95"],
                flush=True,
            )
        invalid = client.post(
            endpoint,
            json={**requests["toronto"], "measurement_kind": "snapshot_visible_count"},
            headers=headers,
        )
        if invalid.status_code not in (400, 422):
            raise ValueError("Snapshot stock was accepted as measured traffic flow")
    artifact = {
        "schema_version": "atlas-city-count-native-runtime-profile-4.0",
        "recorded_at": datetime.now().astimezone().isoformat(),
        "runtime_manifest_sha256": evidence["runtime_manifest_sha256"],
        "authentication_enforced_status": unauthenticated.status_code,
        "snapshot_stock_rejected_status": invalid.status_code,
        "cities": results,
        "environment": "Native Docker Linux API, loopback HTTP, caller's Windows browser host; one serial client",
        "scope": "Real frozen model inference on actual recorded municipal count histories; first test preview parity; requests exclude source acquisition and frontend rendering.",
        "limitations": [
            "Repeated identical source histories exercise warm caches, not an API throughput or concurrent-load SLA.",
            "Initial request may reflect earlier process activity and is not a guaranteed cold-start measurement.",
            "No new forecast accuracy or operational field benefit follows from a latency profile.",
            "All candidates remain shadow research; no automatic model promotion.",
        ],
    }
    (root / "city-runtime-profile.json").write_text(
        json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
