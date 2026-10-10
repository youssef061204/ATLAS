"""Resolve official current sensor geometry without asserting historical lane mapping."""

import gzip
import hashlib
import json
from pathlib import Path

from atlas.cities import FeedClient
from atlas.city_data_v4 import HistoricalClient, stamp


def main():
    root = Path("artifacts/cities/v5")
    client = HistoricalClient("data/city-calibration-v5/geometry-cache")
    feed = FeedClient()
    results = []
    try:
        for city in ("toronto", "london", "seattle", "austin", "calgary"):
            item = {
                "city": city,
                "historical_sensor_mapping_verified": False,
                "independent_dynamic_state_validation": False,
            }
            try:
                if city == "seattle":
                    document = json.loads(
                        gzip.decompress(
                            Path("artifacts/cities/v4/data-seattle.json.gz").read_bytes()
                        )
                    )
                    unitids = sorted({r["unitid"] for r in document["sites"].values()})
                    studies, retrieved = client.get(
                        "https://data.seattle.gov/resource/xucb-vzhc.json",
                        {
                            "$where": "unitid in ("
                            + ",".join("'" + v + "'" for v in unitids)
                            + ") AND traffic_flow_dir_id != '11'",
                            "$select": "unitid,compkey",
                            "$group": "unitid,compkey",
                            "$limit": 500,
                        },
                    )
                    if len(studies) >= 500:
                        raise ValueError("Bounded segment join truncated")
                    keys = sorted({int(r["compkey"]) for r in studies if r.get("compkey")})
                    if not keys:
                        raise ValueError("No official segment join keys")
                    url = "https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/Seattle_Streets_1/FeatureServer/0/query"
                    raw, _ = feed.read(
                        url,
                        {"services.arcgis.com"},
                        {
                            "f": "json",
                            "where": "COMPKEY IN (" + ",".join(map(str, keys)) + ")",
                            "outFields": "COMPKEY,UNITID,ONSTREET",
                            "outSR": 4326,
                            "returnGeometry": "true",
                            "resultRecordCount": 100,
                        },
                    )
                    response = json.loads(raw)
                    if response.get("error") or response.get("exceededTransferLimit"):
                        raise ValueError("Official geometry join failed or truncated")
                    segments = []
                    for feature in response.get("features", []):
                        points = [p for path in feature["geometry"]["paths"] for p in path]
                        xs, ys = [p[0] for p in points], [p[1] for p in points]
                        segments.append(
                            {
                                "attributes": feature["attributes"],
                                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                                "precision": "official current street segment extent; counter location within segment unknown",
                            }
                        )
                    item.update(
                        status="current_segment_geometry_resolved",
                        source=url,
                        retrieved_at=retrieved,
                        source_response_sha256=hashlib.sha256(raw).hexdigest(),
                        segments=segments,
                        official_join_keys=keys,
                        matched_keys=sorted({s["attributes"]["COMPKEY"] for s in segments}),
                        missing_keys=sorted(
                            set(keys) - {s["attributes"]["COMPKEY"] for s in segments}
                        ),
                        licensing="Seattle Department of Transportation public GIS; raw geometry not redistributed; source retained",
                        limitation="COMPKEY resolves current street segment, not exact historical lane/counter position or municipal signal plans",
                    )
                elif city == "london":
                    data, retrieved = client.get(
                        "https://roadtraffic.dft.gov.uk/api/raw-counts",
                        {
                            "filter[count_point_id]": 27663,
                            "page[size]": 500,
                            "page[number]": 1,
                            "sort": "count_date,hour,direction_of_travel",
                        },
                    )
                    if data.get("next_page_url"):
                        raise ValueError("Whitehall raw count query incomplete")
                    rows = data["data"]
                    item.update(
                        status="alternative_whitehall_observations_acquired",
                        count_point_id=27663,
                        source="https://roadtraffic.dft.gov.uk/api/raw-counts",
                        retrieved_at=retrieved,
                        source_response_sha256=client.health[-1]["source_response_sha256"],
                        hourly_direction_rows=len(rows),
                        study_dates=sorted({r["count_date"] for r in rows}),
                        source_latitude=float(rows[0]["latitude"]),
                        source_longitude=float(rows[0]["longitude"]),
                        road=rows[0]["road_name"],
                        licensing="UK Open Government Licence v3.0",
                        limitation="Real directional hourly manual surveys, not annual estimated counts. Historical lane geometry and speed/travel-time/queue truth remain absent.",
                    )
                elif city == "toronto":
                    data, retrieved = client.get(
                        "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show",
                        {"id": "intersection-file-city-of-toronto"},
                    )
                    package = data["result"]
                    item.update(
                        status="official_intersection_geometry_register_located",
                        source="https://open.toronto.ca/dataset/intersection-file-city-of-toronto/",
                        retrieved_at=retrieved,
                        resources=[
                            {
                                "name": r["name"],
                                "id": r["id"],
                                "format": r["format"],
                                "datastore_active": r.get("datastore_active"),
                            }
                            for r in package["resources"]
                        ],
                        limitation="Current official intersection identifiers can support survey joins; historical approach-to-OSM clustering remains unverified.",
                    )
                elif city == "austin":
                    data, retrieved = client.get(
                        "https://data.austintexas.gov/api/views/6yd9-yz29.json"
                    )
                    item.update(
                        status="radar_sensor_registry_located",
                        source="https://data.austintexas.gov/Transportation-and-Mobility/Travel-Sensors/6yd9-yz29",
                        retrieved_at=retrieved,
                        field_definitions=[
                            {"field": r["fieldName"], "description": r.get("description")}
                            for r in data["columns"]
                            if not r["fieldName"].startswith(":")
                        ],
                        limitation="Radar source also discontinued in 2021. Sensor registry provides device correspondence, but historic reliability and speed/occupancy units need verification.",
                    )
                else:
                    url = "https://trafficcounts.calgary.ca/config.json"
                    raw, _ = feed.read(url, {"trafficcounts.calgary.ca"})
                    data = json.loads(raw)
                    # Never publish entire app configuration or any potential API keys.
                    item.update(
                        status="caltracs_public_app_metadata_retrieved",
                        source=url,
                        source_response_sha256=hashlib.sha256(raw).hexdigest(),
                        map_item_id=data.get("map", {}).get("itemId"),
                        map_portal=data.get("map", {}).get("portalUrl"),
                        licensing="CalTRACS Open Government Licence - City of Calgary; official help terms",
                        limitation="CalTRACS documents actual speed/classification reports, but usable co-located export retrieval and timezone verification are still pending.",
                    )
            except Exception as exc:
                item.update(status="blocked", error_type=type(exc).__name__, reason=str(exc))
            results.append(item)
            print(city, item["status"], flush=True)
    finally:
        client.close()
        feed.close()
    artifact = {
        "schema_version": "atlas-calibration-geometry-investigation-5.0",
        "checked_at": stamp(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cities": results,
        "health": client.health,
    }
    (root / "geometry-investigation.json").write_text(
        json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
