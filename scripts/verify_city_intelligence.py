"""Actual authorized five-city smoke runs; no field-benefit or availability claim."""

import json
import os
import time
from pathlib import Path

import httpx
from atlas.cities import now
from atlas.intelligence import camera_alignment


def main():
    base = os.environ.get("ATLAS_API_URL", "http://127.0.0.1:8002")
    headers = {"Authorization": "Bearer " + os.environ["ATLAS_OPERATOR_KEY"]}
    with httpx.Client(base_url=base, timeout=90) as client:
        catalogs = client.get("/api/operations/cities").raise_for_status().json()["cities"]
        networks = client.get("/api/operations/networks").raise_for_status().json()["networks"]
        records = []
        for index, report in enumerate(catalogs):
            network = next(item for item in networks if item["city"] == report["city"])
            eligible = []
            for camera in report["cameras"]:
                alignment = camera_alignment(camera, network)
                if alignment["candidates"] and alignment["candidates"][0]["distance_m"] <= 1000:
                    eligible.append((alignment["candidates"][0]["distance_m"], camera))
            eligible.sort(key=lambda item: item[0])
            record = {
                "city": report["city"],
                "eligible_geographic_candidates": len(eligible),
                "attempts": [],
            }
            records.append(record)
            for distance, camera in eligible[:2]:
                attempt = {
                    "camera_id": camera["id"],
                    "geographic_distance_m": distance,
                    "checked_at": now(),
                }
                record["attempts"].append(attempt)
                try:
                    response = client.post(
                        f"/api/operations/cities/{report['city']}/cameras/{camera['id']}/observe",
                        headers=headers,
                    )
                    response.raise_for_status()
                    context = response.json()
                    context.pop("image_data_url", None)
                    attempt["context"] = context
                    if context["estimated_state"]["mean"] <= 0:
                        attempt["state"] = "zero_motor_observation_not_simulated"
                        continue
                    job = (
                        client.post(
                            "/api/operations/intelligence/experiments",
                            headers=headers,
                            json={
                                "city": report["city"],
                                "observation_id": context["observation"]["id"],
                                "seed": 21101 + index,
                                "duration": 120,
                                "baseline": "original_mpc",
                                "assumptions": {
                                    "acknowledge_exploratory": True,
                                    "residence_seconds": 60,
                                    "corridor_multiplier": 1,
                                },
                            },
                        )
                        .raise_for_status()
                        .json()
                    )
                    deadline = time.monotonic() + 120
                    while job["state"] not in {"complete", "failed", "cancelled", "interrupted"}:
                        if time.monotonic() > deadline:
                            raise TimeoutError(
                                "Job deadline elapsed; inspect persisted worker state"
                            )
                        time.sleep(0.5)
                        job = (
                            client.get(f"/api/operations/jobs/{job['id']}")
                            .raise_for_status()
                            .json()
                        )
                    attempt["job"] = job
                    attempt["state"] = job["state"]
                    if job["state"] == "complete":
                        attempt["experiment"] = (
                            client.get(job["result_path"]).raise_for_status().json()
                        )
                    break
                except (httpx.HTTPError, ValueError, TimeoutError) as exc:
                    attempt["state"] = "unavailable"
                    attempt["reason"] = str(exc)
            print(record["city"], [item["state"] for item in record["attempts"]], flush=True)
            Path("artifacts/cities/city-intelligence-smoke.json").write_text(
                json.dumps(
                    {
                        "checked_at": now(),
                        "scope": "One-time near-corridor official snapshot processing and paired 120-second conditional SUMO smoke checks. No independent FOV/lane/demand calibration; not city performance evaluation or uptime. Camera imagery not retained.",
                        "records": records,
                    },
                    indent=2,
                    allow_nan=False,
                ),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
