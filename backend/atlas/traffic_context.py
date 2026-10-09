"""Official reported road events and regional weather; no fabricated sensor fusion."""

import csv
import hashlib
import io
import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from atlas.cities import FeedError, now

INCIDENT_SOURCES = {
    "toronto": (
        "https://secure.toronto.ca/opendata/cart/road_restrictions/v3?format=csv",
        "secure.toronto.ca",
        "https://open.toronto.ca/dataset/road-restrictions/",
    ),
    "london": (
        "https://api.tfl.gov.uk/Road/all/Disruption",
        "api.tfl.gov.uk",
        "https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service",
    ),
    "seattle": (
        "https://web.seattle.gov/Travelers/api/Map/Data?zoomId=13&type=1",
        "web.seattle.gov",
        "https://web.seattle.gov/travelers/",
    ),
    "austin": (
        "https://data.austintexas.gov/resource/dx9v-zd7x.json",
        "data.austintexas.gov",
        "https://data.austintexas.gov/stories/s/9qfg-4swh",
    ),
    "calgary": (
        "https://data.calgary.ca/resource/4jah-h97u.json",
        "data.calgary.ca",
        "https://data.calgary.ca/Transportation-Transit/Current-Traffic-Incidents/4jah-h97u",
    ),
}
AIRPORTS = {
    "toronto": "CYYZ",
    "london": "EGLC",
    "seattle": "KBFI",
    "austin": "KAUS",
    "calgary": "CYYC",
}


def parse_toronto_csv(body):
    """Official CSV has a title row; malformed records are omitted and counted."""
    stream = io.StringIO(body.decode("utf-8-sig"))
    if next(stream).strip() != "Current road restrictions":
        raise ValueError("Unexpected Toronto CSV title/schema")
    reader = csv.DictReader(stream)
    if not {"ID", "Latitude", "Longitude", "Expired", "StartTime"}.issubset(
        reader.fieldnames or []
    ):
        raise ValueError("Unexpected Toronto CSV fields")
    rows, omitted = [], 0
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            omitted += 1
            continue
        try:
            if not (-90 <= float(row["Latitude"]) <= 90 and -180 <= float(row["Longitude"]) <= 180):
                raise ValueError("Invalid reported geometry")
            for field in ("LastUpdated", "StartTime", "EndTime"):
                if row[field]:
                    datetime.fromtimestamp(int(row[field]) / 1000, UTC)
            item = {"id" if k == "ID" else k[0].lower() + k[1:]: v for k, v in row.items()}
            item["expired"] = int(row["Expired"])
            item["planned"] = int(row["Planned"])
            rows.append(item)
        except (ValueError, OverflowError):
            omitted += 1
    return {"Closure": rows, "malformed_records_omitted": omitted}


class RoadEvent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str
    city: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    description: str
    reported_kind: str
    source_status: str
    source_modified_at: str | None = None
    started_at: str | None = None
    ends_at: str | None = None
    source_timezone: str | None = None
    retrieved_at: str
    provenance_class: str = "official_reported_event"
    confirmed_by_atlas: bool = False
    applied_to_simulation: bool = False


def normalize_events(city, data, retrieved):
    result = []
    if city == "toronto":
        for row in data.get("Closure", []):
            if row.get("expired") or not row.get("latitude") or not row.get("longitude"):
                continue

            def timestamp(value):
                return datetime.fromtimestamp(int(value) / 1000, UTC).isoformat() if value else None

            result.append(
                RoadEvent(
                    id=row["id"],
                    city=city,
                    lat=float(row["latitude"]),
                    lon=float(row["longitude"]),
                    description=row.get("name", "") + " — " + row.get("description", ""),
                    reported_kind=row.get("type", "unknown"),
                    source_status=f"non-expired source listing; planned={row.get('planned')}; reported current impact={row.get('currImpact', 'unknown')}",
                    source_modified_at=timestamp(row.get("lastUpdated")),
                    started_at=timestamp(row.get("startTime")),
                    ends_at=timestamp(row.get("endTime")),
                    retrieved_at=retrieved,
                )
            )
    elif city == "london":
        for row in data:
            coords = row.get("geography", {}).get("coordinates")
            if not coords or len(coords) != 2:
                continue
            result.append(
                RoadEvent(
                    id=row["id"],
                    city=city,
                    lon=coords[0],
                    lat=coords[1],
                    description=row.get("currentUpdate") or row.get("comments", ""),
                    reported_kind=row.get("category", "unknown"),
                    source_status=row.get("status", "unknown"),
                    source_modified_at=row.get("lastModifiedTime"),
                    started_at=row.get("startDateTime"),
                    retrieved_at=retrieved,
                )
            )
    elif city == "seattle":
        for feature in data.get("Features", []):
            lat, lon = feature["PointCoordinate"]
            for row in feature.get("Incidents", []):
                # The source uses local civil time with no offset. Preserve raw
                # clock and zone explicitly instead of inventing a capture UTC.
                result.append(
                    RoadEvent(
                        id=row["Id"],
                        city=city,
                        lat=lat,
                        lon=lon,
                        description=row.get("Description", ""),
                        reported_kind=row.get("Type", "unknown"),
                        source_status="source-listed",
                        started_at=row.get("StartDateTime"),
                        source_timezone="America/Los_Angeles",
                        retrieved_at=retrieved,
                    )
                )
    elif city == "austin":
        for row in data:
            if row.get("traffic_report_status") != "ACTIVE":
                continue
            result.append(
                RoadEvent(
                    id=row["traffic_report_id"],
                    city=city,
                    lat=float(row["latitude"]),
                    lon=float(row["longitude"]),
                    description=row.get("issue_reported", "") + " — " + row.get("address", ""),
                    reported_kind=row.get("issue_reported", "unknown"),
                    source_status=row["traffic_report_status"],
                    started_at=row.get("published_date"),
                    source_modified_at=row.get("traffic_report_status_date_time"),
                    retrieved_at=retrieved,
                )
            )
    elif city == "calgary":
        for row in data:
            result.append(
                RoadEvent(
                    id=hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:20],
                    city=city,
                    lat=float(row["latitude"]),
                    lon=float(row["longitude"]),
                    description=row.get("incident_info", "") + " — " + row.get("description", ""),
                    reported_kind="reported_traffic_disruption",
                    source_status="current-source-listed",
                    started_at=row.get("start_dt_utc"),
                    source_modified_at=row.get("modified_dt_utc"),
                    retrieved_at=retrieved,
                )
            )
    else:
        raise ValueError("Unsupported official road event schema")
    return [r.model_dump() for r in result]


def inspect_context(client):
    cities = []
    for city, (url, host, terms) in INCIDENT_SOURCES.items():
        retrieved = now()
        report = {
            "city": city,
            "retrieved_at": retrieved,
            "source": url,
            "terms": terms,
            "events": [],
            "coverage": "Source-listed reported disruptions, not a comprehensive crash database",
            "minimum_refresh_seconds": 300,
        }
        params = (
            {
                "$limit": 100,
                "$where": "traffic_report_status='ACTIVE'",
                "$order": "published_date DESC",
            }
            if city == "austin"
            else {"$limit": 100}
            if city == "calgary"
            else None
        )
        try:
            body, _ = client.read(url, [host], params, max_bytes=8_000_000)
            data = parse_toronto_csv(body) if city == "toronto" else json.loads(body)
            if isinstance(data, dict) and "error" in data:
                raise ValueError("Official event feed returned an error")
            report.update(
                status="available",
                payload_sha256=hashlib.sha256(body).hexdigest(),
                events=normalize_events(city, data, retrieved),
            )
            if city == "toronto":
                report["malformed_records_omitted"] = data["malformed_records_omitted"]
                report["coverage"] = (
                    "Non-expired source listings include scheduled future work and daily windows; not every listing is an active closure. Malformed CSV records are omitted and counted. Official JSON was unavailable due to invalid escaping."
                )
            report["coverage"] = (
                "At most 100 active reports; truncated coverage possible"
                if city == "austin"
                else report["coverage"]
            )
        except (FeedError, ValueError, KeyError, TypeError) as exc:
            report.update(
                status="restricted"
                if isinstance(exc, FeedError) and exc.status in {401, 403}
                else "unavailable",
                reason=str(exc),
            )
        cities.append(report)
    url = "https://aviationweather.gov/api/data/metar"
    weather = []
    retrieved = now()
    try:
        body, _ = client.read(
            url,
            ["aviationweather.gov"],
            {"ids": ",".join(AIRPORTS.values()), "format": "json"},
            max_bytes=1_000_000,
        )
        data = json.loads(body)
        by_station = {r["icaoId"]: r for r in data}
        for city, airport in AIRPORTS.items():
            row = by_station.get(airport)
            if not row:
                weather.append({"city": city, "status": "unavailable", "station": airport})
                continue
            observed = datetime.fromtimestamp(row["obsTime"], UTC).isoformat()
            weather.append(
                {
                    "city": city,
                    "station": airport,
                    "status": "available",
                    "observed_at": observed,
                    "retrieved_at": retrieved,
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "temperature_c": row.get("temp"),
                    "wind_speed_knots": row.get("wspd"),
                    "visibility_reported": row.get("visib"),
                    "reported_weather": row.get("wxString"),
                    "source": url,
                    "provenance_class": "official_weather_observation",
                    "scope": "Regional airport observation; not intersection microclimate",
                    "fusion_status": "context_only; temporal/coverage alignment must be established before model fusion",
                    "minimum_refresh_seconds": 3600,
                }
            )
    except (FeedError, ValueError, KeyError, TypeError) as exc:
        weather = [
            {"city": city, "station": airport, "status": "unavailable", "reason": str(exc)}
            for city, airport in AIRPORTS.items()
        ]
    return {
        "schema_version": "atlas-city-context-3.0",
        "recorded_at": now(),
        "mode": "recorded_official_source_checks",
        "cities": cities,
        "weather": weather,
        "limitations": [
            "Reported events are not confirmed by ATLAS",
            "No automatic signal actuation or simulation closure mapping",
            "Context not used as validated forecasting covariates",
            "Only one-time access checked; source uptime not established",
        ],
    }
