"""Summarize published municipal count coverage without implying calibration."""

import gzip
import json
import math
from datetime import datetime
from pathlib import Path

from atlas.city_data_v4 import stamp


def distance(point, start, end):
    lon, lat = point
    sx, sy = 111320 * math.cos(math.radians(lat)), 111320
    x1, y1 = (start[0] - lon) * sx, (start[1] - lat) * sy
    x2, y2 = (end[0] - lon) * sx, (end[1] - lat) * sy
    dx, dy = x2 - x1, y2 - y1
    ratio = max(0, min(1, -(x1 * dx + y1 * dy) / (dx * dx + dy * dy))) if dx * dx + dy * dy else 0
    return math.hypot(x1 + ratio * dx, y1 + ratio * dy)


def main():
    out = Path("artifacts/cities/v4")
    networks = json.loads(Path("artifacts/cities/networks.json").read_text(encoding="utf-8"))[
        "networks"
    ]
    summaries = []
    for city in ("toronto", "london", "seattle", "austin", "calgary"):
        data = json.loads(gzip.decompress((out / f"data-{city}.json.gz").read_bytes()))
        network = next(row for row in networks if row["city"] == city)
        sites = []
        for site_id, location in data["sites"].items():
            rows = [r for r in data["records"] if r["site_id"] == site_id]
            dates = sorted({r["observed_at"][:10] for r in rows})
            times = sorted(datetime.fromisoformat(r["observed_at"]) for r in rows)
            interval = rows[0]["interval_seconds"]
            gaps = sum(
                (b - a).total_seconds() != interval for a, b in zip(times, times[1:], strict=False)
            )
            nearest = None
            if location["lat"] is not None and location["lon"] is not None:
                candidates = [
                    (distance((location["lon"], location["lat"]), a, b), road["id"])
                    for road in network["roads"]
                    for a, b in zip(road["coordinates"], road["coordinates"][1:], strict=False)
                ]
                nearest = min(candidates) if candidates else None
            sites.append(
                {
                    "site_id": site_id,
                    "location": location,
                    "records": len(rows),
                    "study_dates": len(dates),
                    "first_date": dates[0],
                    "last_date": dates[-1],
                    "gap_count": gaps,
                    "interval_seconds": interval,
                    "source_reported_zero_bins": sum(r["count"] == 0 for r in rows),
                    "mean_count_per_interval": sum(r["count"] for r in rows) / len(rows),
                    "nearest_modeled_road": {
                        "id": nearest[1],
                        "distance_m": round(nearest[0], 1),
                        "mapping_status": "geographic_nearest_only_not_validated",
                    }
                    if nearest
                    else None,
                    "preview": rows[:3],
                }
            )
        summaries.append(
            {
                "city": city,
                "record_count": data["record_count"],
                "channels": len(sites),
                "distinct_location_names": len({s["location"]["name"] for s in sites}),
                "rejected_records": len(data.get("rejected_records", [])),
                "sites": sites,
                "calibration": "none_independently_validated",
                "limits": data["limitations"],
            }
        )
    (out / "data-coverage.json").write_text(
        json.dumps(
            {
                "schema_version": "atlas-city-data-coverage-4.0",
                "generated_at": stamp(),
                "cities": summaries,
                "method": "Nearest-road distances use local equirectangular projection; no camera FOV or detector movement matching established.",
            },
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    for row in summaries:
        print(
            row["city"],
            row["record_count"],
            row["distinct_location_names"],
            "locations; road distances",
            [
                s["nearest_modeled_road"]["distance_m"] if s["nearest_modeled_road"] else None
                for s in row["sites"]
            ],
        )


if __name__ == "__main__":
    main()
