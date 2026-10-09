"""Bounded official historical counts and fresh corridor CV aggregates; no images saved."""

import json
from pathlib import Path

from atlas.cities import Camera, CityAdapter, FeedClient, SnapshotPerception, now
from atlas.city_network import sha
from atlas.intelligence import assimilate, camera_alignment, count_forecast

HOST = "ckan0.cf.opendata.inter.prod-toronto.ca"
BASE = f"https://{HOST}/api/3/action"


def fetch(client, action, parameters):
    body, _ = client.read(f"{BASE}/{action}", [HOST], parameters)
    result = json.loads(body)
    if not result.get("success"):
        raise ValueError("Official CKAN query failed")
    return result["result"]


def main():
    client = FeedClient(min_interval=0.5)
    try:
        package = fetch(
            client, "package_show", {"id": "traffic-volumes-at-intersections-for-all-modes"}
        )
        summary = fetch(
            client,
            "datastore_search",
            {"resource_id": "6afa3b1f-f6a5-4235-8bd6-7568411c19f4", "q": "Bay", "limit": 100},
        )
        matches = [
            r for r in summary["records"] if r["location_name"] == "Bay St / Queen St W (East)"
        ]
        if len(matches) != 1:
            raise ValueError("Ambiguous historical count location")
        location = matches[0]
        rows = fetch(
            client,
            "datastore_search",
            {
                "resource_id": "262469c2-abfe-4756-9068-4ea5c7ba1af7",
                "filters": json.dumps({"count_id": location["latest_count_id"]}),
                "limit": 100,
                "sort": "start_time asc",
            },
        )
        if rows["total"] != len(rows["records"]):
            raise ValueError("Incomplete official count study")
        fields = [
            f"{direction}_appr_{vehicle}_{turn}"
            for direction in "nesw"
            for vehicle in ("cars", "truck", "bus")
            for turn in "rtl"
        ]
        if any(any(r[f] is None or r[f] < 0 for f in fields) for r in rows["records"]):
            raise ValueError("Missing or invalid movement counts")
        total = sum(sum(r[f] for f in fields) for r in rows["records"])
        if total != location["total_vehicle"]:
            raise ValueError("Raw and official summary counts disagree")
        counts = {
            "schema_version": "atlas-traffic-observations-3.0",
            "city": "toronto",
            "retrieved_at": now(),
            "kind": "historical_turning_counts",
            "source": f"{BASE}/datastore_search",
            "resource_id": "262469c2-abfe-4756-9068-4ea5c7ba1af7",
            "study": location,
            "interval_seconds": 900,
            "timezone": "America/Toronto",
            "unit": "vehicles per interval",
            "provenance_class": "official_observation",
            "coverage": "One intersection, one historical study day; not current conditions",
            "license": package.get("license_title"),
            "license_url": "https://open.toronto.ca/open-data-licence/",
            "attribution": "Contains information licensed under the Open Government Licence – Toronto.",
            "independent_of_camera_date": True,
            "records": rows["records"],
        }
        Path("artifacts/cities/toronto-counts.json").write_text(
            json.dumps(counts, allow_nan=False), encoding="utf-8"
        )
        report = next(
            c
            for c in json.loads(
                Path("artifacts/cities/source-health.json").read_text(encoding="utf-8")
            )["cities"]
            if c["city"] == "toronto"
        )
        camera = next(c for c in report["cameras"] if c["id"] == "8113")
        image, observation = CityAdapter("toronto", client).snapshot(Camera(**camera))
        observation = SnapshotPerception().process(image, observation)
        network = next(
            n
            for n in json.loads(Path("artifacts/cities/networks.json").read_text(encoding="utf-8"))[
                "networks"
            ]
            if n["city"] == "toronto"
        )
        state = assimilate(observation)
        result = {
            "city": "toronto",
            "camera": camera,
            "observation": observation,
            "alignment": camera_alignment(camera, network),
            "estimated_state": state,
            "forecast": count_forecast(state),
            "historical_detector_source": "toronto-counts.json",
            "detector_fusion": {
                "status": "not_fused",
                "reason": "July 2025 counts and October 2026 snapshot measure different times and different quantities",
            },
            "mode": "recorded_official_observation",
            "calibration": {"status": "unvalidated", "independent_validation": None},
            "collector_sha256": sha(__file__),
        }
        Path("artifacts/cities/toronto-intelligence.json").write_text(
            json.dumps(result, allow_nan=False), encoding="utf-8"
        )
        print(
            "Verified",
            len(rows["records"]),
            "historical bins /",
            total,
            "motor vehicles; snapshot",
            observation["counts"],
            flush=True,
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
