"""Acquire bounded licensed historical aggregate counts for all five cities."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from atlas.city_data_v4 import HistoricalClient, finalize, observation, publish, stamp

CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
SOURCE = {
    "toronto": f"{CKAN}/datastore_search",
    "austin": "https://data.austintexas.gov/resource/sh59-i6y9.json",
    "seattle": "https://data.seattle.gov/resource/gi49-5uh6.json",
    "calgary": "https://data.calgary.ca/resource/vuyp-sbjp.json",
    "london": "https://roadtraffic.dft.gov.uk/api/raw-counts",
}
LICENSE = {
    "toronto": {
        "name": "Open Government Licence - Toronto",
        "url": "https://open.toronto.ca/open-data-licence/",
        "attribution": "Contains information licensed under the Open Government Licence - Toronto.",
    },
    "austin": {
        "name": "City of Austin open data terms",
        "url": "https://data.austintexas.gov/stories/s/ranj-cccq",
        "attribution": "City of Austin Transportation and Public Works; Camera Traffic Counts",
        "status": "metadata licence unspecified; city open-data terms apply",
    },
    "seattle": {
        "name": "Public Domain (published dataset metadata)",
        "url": "https://data.seattle.gov/Transportation/Traffic-Counts-Studies-by-15-Minute-Bins/gi49-5uh6",
        "attribution": "Seattle Department of Transportation",
    },
    "calgary": {
        "name": "Open Government Licence - City of Calgary",
        "url": "https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa",
        "attribution": "Contains information licensed under the Open Government Licence - City of Calgary.",
    },
    "london": {
        "name": "UK Open Government Licence v3.0",
        "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "attribution": "Department for Transport, road traffic statistics; Crown copyright",
    },
}


def socrata(client, city, dataset, params):
    domains = {
        "austin": "data.austintexas.gov",
        "calgary": "data.calgary.ca",
        "seattle": "data.seattle.gov",
    }
    rows, retrieved = client.get(f"https://{domains[city]}/resource/{dataset}.json", params)
    if not isinstance(rows, list):
        raise ValueError("Socrata response is not a row collection")
    if len(rows) >= int(params.get("$limit", 1000)):
        raise ValueError("Bounded query truncated; request a smaller period")
    return rows, retrieved


def toronto(client):
    names = [
        "Bay St / Queen St W (East)",
        "Bay St / Richmond St W",
        "Bay St / Adelaide St W",
        "Bay St / Dundas St W",
    ]
    sites, records = {}, []
    for name in names:
        data, retrieved = client.get(
            SOURCE["toronto"],
            {
                "resource_id": "262469c2-abfe-4756-9068-4ea5c7ba1af7",
                "filters": json.dumps({"location_name": name}),
                "limit": 4000,
                "sort": "start_time asc",
            },
        )
        rows = data["result"]["records"]
        if data["result"]["total"] != len(rows):
            raise ValueError("Incomplete Toronto intersection study archive")
        if not rows:
            continue
        site = str(rows[0]["centreline_id"])
        sites[site] = {
            "name": name,
            "lat": rows[0]["latitude"],
            "lon": rows[0]["longitude"],
            "location_precision": "official_intersection_coordinate",
        }
        for row in rows:
            count = sum(
                row[f"{d}_appr_{v}_{t}"]
                for d in "nesw"
                for v in ("cars", "truck", "bus")
                for t in "rtl"
            )
            records.append(
                observation(
                    "toronto",
                    site,
                    row["start_time"],
                    count,
                    900,
                    retrieved,
                    SOURCE["toronto"],
                    "America/Toronto local civil time; timezone not encoded by source",
                    source_id=str(row["_id"]),
                )
            )
    return finalize(
        "toronto",
        sites,
        records,
        LICENSE["toronto"],
        [
            "One-day studies on irregular historical dates; missing days and periods remain absent.",
            "Counts sum observed car/truck/bus turning movements, exclude bicycles and pedestrians.",
            "Spatial correspondence alone does not validate signal timing, route split or historical road geometry.",
        ],
    )


def austin(client):
    names = [
        "5TH ST / RED RIVER ST",
        "6TH ST / RED RIVER ST",
        "CONGRESS AVE / RIVERSIDE DR",
        "MARTIN LUTHER KING JR BLVD / RED RIVER ST",
    ]
    sites, records = {}, []
    for name in names:
        rows, retrieved = socrata(
            client,
            "austin",
            "sh59-i6y9",
            {
                "$where": f"read_date >= '2020-01-01T00:00:00' AND read_date < '2020-02-01T00:00:00' AND intersection_name='{name}'",
                "$select": "read_date,intersection_name,sum(volume) as count",
                "$group": "read_date,intersection_name",
                "$order": "read_date",
                "$limit": 4000,
            },
        )
        if not rows:
            continue
        site = name
        sites[site] = {
            "name": name,
            "lat": None,
            "lon": None,
            "location_precision": "official_intersection_name; geographic coordinate not in count dataset",
        }
        detector_rows, location_retrieved = socrata(
            client,
            "austin",
            "qpuw-8eeb",
            {
                "$where": f"location_name in ('{name}',' {name}','{name} ',' {name} ')",
                "$limit": 300,
            },
        )
        coordinates = {
            tuple(row["location"]["coordinates"]) for row in detector_rows if row.get("location")
        }
        if len(coordinates) == 1:
            lon, lat = next(iter(coordinates))
            sites[site].update(
                {
                    "lat": lat,
                    "lon": lon,
                    "location_precision": "official_detector_registry_intersection_coordinate",
                    "location_source": "https://data.austintexas.gov/resource/qpuw-8eeb.json",
                    "location_retrieved_at": location_retrieved,
                    "coordinate_match": "exact normalized intersection name; registry contemporary, geometry history unvalidated",
                }
            )
        for row in rows:
            records.append(
                observation(
                    "austin",
                    site,
                    row["read_date"] + "+00:00",
                    row["count"],
                    900,
                    retrieved,
                    SOURCE["austin"],
                    "UTC; source field metadata explicitly specifies UTC",
                    source_id=f"{site}:{row['read_date']}",
                )
            )
    return finalize(
        "austin",
        sites,
        records,
        LICENSE["austin"],
        [
            "Camera-counter counts are historical automated detector outputs, not independently human-annotated ground truth.",
            "Published light/heavy categories and movement bins summed per intersection; source omissions remain absent.",
            "Coordinates obtained from exact-name current official detector registry; historical coordinate stability and connected road graph unvalidated.",
            "Source discontinued: GRIDSMART devices no longer maintained. Published automated counts and speeds have not been independently validated; speed calibration uncertain.",
        ],
    )


def calgary(client):
    locations, _ = socrata(client, "calgary", "sqwx-tjsy", {"$limit": 200})
    # Four geographically distinct published stations closest to the existing downtown study area.
    selected = sorted(
        (r for r in locations if r["condition"] == "OPERATIONAL"),
        key=lambda r: (
            (float(r["latitude"]) - 51.047) ** 2 + ((float(r["longitude"]) + 114.065) * 0.63) ** 2
        ),
    )[:4]
    sites, records = {}, []
    for loc in selected:
        # Retain the published segment; directional counts are separate sensors.
        for field in ("segment_id_nb", "segment_id_sb"):
            site = loc.get(field)
            if not site:
                continue
            rows, retrieved = socrata(
                client,
                "calgary",
                "vuyp-sbjp",
                {
                    "$where": f"study_date >= '2026-08-01T00:00:00' AND study_date < '2026-08-29T00:00:00' AND segment_id='{site}'",
                    "$order": "study_date",
                    "$limit": 3000,
                },
            )
            if not rows:
                continue
            sites[site] = {
                "name": rows[0]["address"],
                "lat": float(loc["latitude"]),
                "lon": float(loc["longitude"]),
                "location_precision": "official_permanent_counter_coordinate",
                "location_source": "https://data.calgary.ca/resource/sqwx-tjsy.json",
            }
            for row in rows:
                records.append(
                    observation(
                        "calgary",
                        site,
                        row["study_date"],
                        row["volume"],
                        900,
                        retrieved,
                        SOURCE["calgary"],
                        "source-naive time; America/Edmonton local interpretation requires operator confirmation",
                        direction=row["direction"],
                        source_id=row["id"],
                    )
                )
    return finalize(
        "calgary",
        sites,
        records,
        LICENSE["calgary"],
        [
            "Permanent counter locations mostly outside the existing downtown SUMO corridor; no calibrated corridor inference.",
            "Published quarter-hour volume retained; source time zone not encoded and must be confirmed before weather fusion.",
            "Counter accuracy and source completeness not independently field-audited.",
        ],
    )


def seattle(client):
    studies, _ = socrata(
        client,
        "seattle",
        "xucb-vzhc",
        {
            "$where": "(title like 'DENNY WAY%' OR title like 'PIKE ST%' OR title like 'PINE ST%') AND start_date > '2025-01-01T00:00:00' AND traffic_flow_dir_id != '11'",
            "$order": "start_date DESC",
            "$limit": 250,
        },
    )
    # Unique location channels, retain all studies for up to four distinct location names.
    locations = []
    for row in studies:
        name = row["title"].split(";")[0]
        if name not in locations:
            locations.append(name)
    locations = locations[:4]
    sites, records = {}, []
    rejected = []
    seen = set()
    for study in studies:
        name = study["title"].split(";")[0]
        if name not in locations:
            continue
        site = study["unitid"] + ":" + study["traffic_flow_dir_id"]
        rows, retrieved = socrata(
            client,
            "seattle",
            "gi49-5uh6",
            {
                "$where": f"study_id='{study['study_id']}'",
                "$order": "count_year,count_month,count_day,count_hour,count_minute",
                "$limit": 800,
            },
        )
        if not rows:
            continue
        sites[site] = {
            "name": name,
            "lat": None,
            "lon": None,
            "location_precision": "official_road_segment_description",
            "unitid": study["unitid"],
            "direction_code": study["traffic_flow_dir_id"],
            "location_source": "https://data.seattle.gov/resource/xucb-vzhc.json",
        }
        for row in rows:
            if float(row["current_count"]) < 0:
                rejected.append(
                    {
                        "source_record_id": row["count_id"],
                        "study_id": row["study_id"],
                        "reason": "negative_source_count_sentinel",
                        "value": row["current_count"],
                    }
                )
                continue
            when = datetime(
                *(int(row[f"count_{x}"]) for x in ("year", "month", "day", "hour", "minute"))
            ).isoformat()
            key = (site, when)
            if key in seen:
                raise ValueError("Seattle studies overlap at the same physical channel/time")
            seen.add(key)
            records.append(
                observation(
                    "seattle",
                    site,
                    when,
                    row["current_count"],
                    900,
                    retrieved,
                    SOURCE["seattle"],
                    "America/Los_Angeles local civil time; source has separate date components",
                    direction=study["traffic_flow_dir_id"],
                    source_id=row["count_id"],
                )
            )
    result = finalize(
        "seattle",
        sites,
        records,
        LICENSE["seattle"],
        [
            "Actual pneumatic/video counter studies; source modality varies by study and no independent annotation accuracy assigned.",
            "Published location descriptions retained without invented latitude/longitude.",
            "Distinct directions are separate channels; aggregate TOTAL FLOW studies excluded to prevent double-counting.",
            "Gaps between historical studies remain absent.",
        ],
    )
    result["rejected_records"] = rejected
    return result


def london(client):
    points = [26430, 18600, 26775, 28214]
    sites, records = {}, []
    for point in points:
        page = 1
        while True:
            data, retrieved = client.get(
                SOURCE["london"],
                {
                    "filter[count_point_id]": point,
                    "page[size]": 500,
                    "page[number]": page,
                    "sort": "count_date,hour,direction_of_travel",
                },
            )
            for row in data["data"]:
                site = str(point)
                sites[site] = {
                    "name": f"{row['road_name']}: {row['start_junction_road_name']} to {row['end_junction_road_name']}",
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "location_precision": "official_count_point_coordinate",
                }
                when = f"{row['count_date']}T{int(row['hour']):02d}:00:00"
                records.append(
                    observation(
                        "london",
                        site,
                        when,
                        row["all_motor_vehicles"],
                        3600,
                        retrieved,
                        SOURCE["london"],
                        "Europe/London local survey hour; offset not encoded",
                        direction=row["direction_of_travel"],
                        source_id=str(row["id"]),
                    )
                )
            if not data.get("next_page_url"):
                break
            page += 1
            if page > 10:
                raise ValueError("London survey budget exceeded")
    # A site-hour counts both measured travel directions exactly once.
    grouped = {}
    for row in records:
        key = (row["site_id"], row["observed_at"])
        if key not in grouped:
            grouped[key] = {
                **row,
                "count": 0,
                "direction": "all_observed_directions",
                "source_record_id": [],
            }
        grouped[key]["count"] += row["count"]
        grouped[key]["source_record_id"].append(row["source_record_id"])
    return finalize(
        "london",
        sites,
        list(grouped.values()),
        LICENSE["london"],
        [
            "Manual survey hourly counts on sparse study days across years, not a continuous detector stream.",
            "All motor vehicles includes motorcycles/light goods/heavy goods/buses, excludes pedal cycles.",
            "Directional counts aggregated per site-hour; no temporal interpolation or current image fusion.",
            "Count points near Holborn are not automatically mapped to existing Whitehall modeled corridor.",
        ],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", choices=list(SOURCE), action="append")
    parser.add_argument("--output", default="artifacts/cities/v4")
    args = parser.parse_args()
    client = HistoricalClient("data/city-count-cache-v4")
    index_path = Path(args.output) / "data-index.json"
    old = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.exists()
        else {"cities": []}
    )
    index = {row["city"]: row for row in old["cities"]}
    attempts = old.get("attempts", [])
    for row in old["cities"]:
        if row.get("status") == "failed":
            attempts.append({**row, "recorded_at": old.get("checked_at")})
    for city in args.city or list(SOURCE):
        try:
            dataset = globals()[city](client)
            if not dataset["records"]:
                raise ValueError("No historical observations retrieved")
            index[city] = {**publish(dataset, args.output), "status": "retrieved"}
            print(
                city, len(dataset["records"]), "bins", len(dataset["sites"]), "channels", flush=True
            )
        except Exception as exc:
            index[city] = {
                "city": city,
                "status": "failed",
                "error_type": type(exc).__name__,
                "reason": str(exc),
            }
            print(city, "failed", type(exc).__name__, str(exc), flush=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(
                {
                    "schema_version": "atlas-historical-count-index-4.0",
                    "checked_at": stamp(),
                    "cities": list(index.values()),
                    "health": old.get("health", []) + client.health,
                    "attempts": attempts,
                    "collector_sha256": __import__("hashlib")
                    .sha256(Path(__file__).read_bytes())
                    .hexdigest(),
                },
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
    client.close()


if __name__ == "__main__":
    main()
