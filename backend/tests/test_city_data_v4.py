"""Historical-data contracts: prevent fake observations and stale provenance."""

import gzip
import json

import httpx
import pytest
from atlas.cities import FeedClient
from atlas.city_data_v4 import HistoricalClient, finalize, observation, publish


def test_cache_retains_retrieval_and_rejects_tampering(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[{"count": 3}])

    client = HistoricalClient(
        tmp_path, feed=FeedClient(transport=httpx.MockTransport(respond), min_interval=0)
    )
    url = "https://data.calgary.ca/resource/vuyp-sbjp.json"
    first, retrieved = client.get(url)
    second, cached_retrieved = client.get(url)
    assert first == second and retrieved == cached_retrieved
    assert len(calls) == 1 and client.health[-1]["cache"]
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data["body"] = "[]"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest"):
        client.get(url)
    assert client.health[-1]["status"] == "failed"
    client.close()


def test_unapproved_host_and_nonfinite_counts_rejected(tmp_path):
    client = HistoricalClient(tmp_path)
    with pytest.raises(ValueError, match="Unapproved"):
        client.get("https://example.org/data")
    client.close()
    for value in (-1, "nan", "inf", 1.5, True):
        with pytest.raises(ValueError):
            observation(
                "toronto",
                "1",
                "2025-01-01T08:00:00",
                value,
                900,
                "2026-01-01T00:00:00+00:00",
                "official",
                "local",
            )


def test_historical_gaps_retained_no_zero_fill_or_current_fusion(tmp_path):
    sites = {"1": {"name": "Official site", "lat": 43.6, "lon": -79.3}}
    rows = [
        observation(
            "toronto", "1", when, count, 900, "2026-01-01T00:00:00+00:00", "official", "local"
        )
        for when, count in [("2025-01-01T08:00:00", 3), ("2025-01-01T08:30:00", 5)]
    ]
    dataset = finalize("toronto", sites, rows, {"name": "test licence"}, [])
    entry = publish(dataset, tmp_path)
    decoded = json.loads(gzip.decompress((tmp_path / entry["artifact"]).read_bytes()))
    assert decoded["record_count"] == 2
    assert all(r["data_type"] == "historical_motor_vehicle_count" for r in decoded["records"])
    assert decoded["live_fusion"].startswith("prohibited")
    with pytest.raises(ValueError, match="Duplicate"):
        finalize("toronto", sites, rows + rows[:1], {"name": "test"}, [])


def test_expired_cache_failure_is_not_returned_as_fresh(tmp_path):
    status = [200]
    transport = httpx.MockTransport(lambda request: httpx.Response(status[0], json=[{"count": 1}]))
    client = HistoricalClient(tmp_path, ttl=0, feed=FeedClient(transport=transport, min_interval=0))
    url = "https://data.seattle.gov/resource/gi49-5uh6.json"
    client.get(url)
    status[0] = 403
    with pytest.raises(RuntimeError):
        client.get(url)
    assert client.health[-1]["status"] == "failed"
    client.close()


def load_collector():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "atlas_count_collector_tests",
        Path(__file__).resolve().parents[2] / "scripts/ingest_city_data_v4.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_austin_source_utc_and_exact_registry_locations():
    module = load_collector()

    class Source:
        def get(self, url, params):
            if "qpuw-8eeb" in url:
                assert "location_name in" in params["$where"]
                return [{"location": {"coordinates": [-97.73, 30.26]}}], "2026-10-09T00:00:00+00:00"
            return [
                {"read_date": "2020-01-01T00:00:00.000", "count": "3"}
            ], "2026-10-09T00:00:00+00:00"

    data = module.austin(Source())
    assert len(data["sites"]) == 4
    assert all(row["observed_at"].endswith("+00:00") for row in data["records"])
    assert all(row["count"] == 3 for row in data["records"])
    assert all(site["lat"] == 30.26 for site in data["sites"].values())
    assert "discontinued" in " ".join(data["limitations"])


def test_seattle_negative_source_sentinel_excluded_and_audited():
    module = load_collector()

    class Source:
        def get(self, url, params):
            if "xucb-vzhc" in url:
                return [
                    {
                        "study_id": "1",
                        "title": "DENNY WAY, W/O 2ND AVE; W FLOW",
                        "unitid": "1",
                        "traffic_flow_dir_id": "4",
                    }
                ], "2026-10-09T00:00:00+00:00"
            rows = [
                {
                    "count_year": "2025",
                    "count_month": "1",
                    "count_day": "2",
                    "count_hour": "8",
                    "count_minute": str(minute),
                    "count_id": str(minute),
                    "study_id": "1",
                    "current_count": str(count),
                }
                for minute, count in [(0, -1), (15, 3)]
            ]
            return rows, "2026-10-09T00:00:00+00:00"

    data = module.seattle(Source())
    assert len(data["records"]) == 1 and data["records"][0]["count"] == 3
    assert data["rejected_records"][0]["value"] == "-1"
    assert data["records"][0]["observed_at"] == "2025-01-02T08:15:00"


def test_london_actual_direction_counts_aggregate_once():
    module = load_collector()

    class Source:
        def get(self, url, params):
            point = params["filter[count_point_id]"]
            rows = [
                {
                    "id": point * 2 + index,
                    "road_name": "A40",
                    "start_junction_road_name": "West",
                    "end_junction_road_name": "East",
                    "latitude": "51.51",
                    "longitude": "-0.1",
                    "count_date": "2025-06-01",
                    "hour": 8,
                    "direction_of_travel": direction,
                    "all_motor_vehicles": count,
                }
                for index, (direction, count) in enumerate([("E", 3), ("W", 5)])
            ]
            return {"data": rows, "next_page_url": None}, "2026-10-09T00:00:00+00:00"

    data = module.london(Source())
    assert len(data["records"]) == 4
    assert all(row["count"] == 8 and row["interval_seconds"] == 3600 for row in data["records"])
    assert all(len(row["source_record_id"]) == 2 for row in data["records"])
