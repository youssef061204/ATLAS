"""Historical municipal count ingestion, separate from live camera observations.

Source counts are retained in their published time basis. Missing bins are absent,
never zero-filled. Geographic proximity is explicitly not a calibrated road mapping.
"""

import gzip
import hashlib
import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from atlas.cities import FeedClient

HOSTS = {
    "data.austintexas.gov",
    "data.calgary.ca",
    "data.seattle.gov",
    "roadtraffic.dft.gov.uk",
    "ckan0.cf.opendata.inter.prod-toronto.ca",
}


def stamp():
    return datetime.now(UTC).isoformat()


def finite_count(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a traffic count")
    result = float(value)
    if not math.isfinite(result) or result < 0 or not result.is_integer():
        raise ValueError("Invalid motor-vehicle count")
    return int(result)


class HistoricalClient:
    """Validated HTTPS, bounded reads, retries/throttling, SHA-checked TTL cache.

    Cached retrieval time remains the original network retrieval time. Failed refresh
    does not silently serve expired data as fresh. Raw caches stay outside git.
    """

    def __init__(self, cache, ttl=86400, feed=None):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.feed = feed or FeedClient(min_interval=0.5)
        self.health = []

    def close(self):
        self.feed.close()

    def get(self, url, params=None):
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in HOSTS:
            raise ValueError("Unapproved historical source")
        request = {"url": url, "params": params or {}}
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        path = self.cache / f"{key}.json"
        started = time.perf_counter()
        try:
            if path.exists():
                cached = json.loads(path.read_text(encoding="utf-8"))
                age = time.time() - datetime.fromisoformat(cached["retrieved_at"]).timestamp()
                raw = cached["body"].encode()
                if hashlib.sha256(raw).hexdigest() != cached["sha256"]:
                    raise ValueError("Historical cache digest mismatch")
                if 0 <= age < self.ttl:
                    self.health.append(
                        {
                            **request,
                            "checked_at": stamp(),
                            "cache": True,
                            "retrieved_at": cached["retrieved_at"],
                            "source_response_sha256": cached["sha256"],
                            "status": "ok",
                        }
                    )
                    return json.loads(raw), cached["retrieved_at"]
            raw, _ = self.feed.read(url, HOSTS, params, max_bytes=15_000_000)
            result = json.loads(raw)
            if isinstance(result, dict) and (result.get("error") or result.get("success") is False):
                raise ValueError("Official API returned an error")
            retrieved = stamp()
            normalized = raw.decode("utf-8-sig").encode()
            path.write_text(
                json.dumps(
                    {
                        **request,
                        "retrieved_at": retrieved,
                        "sha256": hashlib.sha256(normalized).hexdigest(),
                        "body": normalized.decode(),
                    }
                ),
                encoding="utf-8",
            )
            self.health.append(
                {
                    **request,
                    "checked_at": retrieved,
                    "retrieved_at": retrieved,
                    "cache": False,
                    "status": "ok",
                    "bytes": len(raw),
                    "source_response_sha256": hashlib.sha256(normalized).hexdigest(),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
            return result, retrieved
        except Exception as exc:
            self.health.append(
                {
                    **request,
                    "checked_at": stamp(),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                }
            )
            raise


def observation(
    city, site, when, value, interval, retrieved, source, time_basis, direction=None, source_id=None
):
    date = datetime.fromisoformat(when)
    if interval not in (900, 3600):
        raise ValueError("Unsupported source interval")
    return {
        "city": city,
        "site_id": site,
        "observed_at": date.isoformat(),
        "interval_seconds": interval,
        "count": finite_count(value),
        "data_type": "historical_motor_vehicle_count",
        "units": "vehicles/interval",
        "retrieved_at": retrieved,
        "source": source,
        "time_basis": time_basis,
        "direction": direction,
        "source_record_id": source_id,
        "freshness": "historical; not simultaneous with current cameras",
        "uncertainty": {"status": "source_measurement_error_not_quantified"},
    }


def finalize(city, sites, records, license_info, limitations):
    keys = set()
    for row in records:
        key = (row["site_id"], row["observed_at"], row["direction"])
        if key in keys:
            raise ValueError("Duplicate normalized count bin")
        keys.add(key)
        if row["site_id"] not in sites:
            raise ValueError("Count site is absent from location registry")
    records.sort(key=lambda r: (r["observed_at"], r["site_id"], r["direction"] or ""))
    for row in records:
        row["license"] = license_info["name"]
        row["location"] = sites[row["site_id"]]
    return {
        "schema_version": "atlas-historical-city-counts-4.0",
        "city": city,
        "collected_at": stamp(),
        "license": license_info,
        "sites": sites,
        "records": records,
        "record_count": len(records),
        "counts_by_site": dict(Counter(r["site_id"] for r in records)),
        "period_start": records[0]["observed_at"] if records else None,
        "period_end": records[-1]["observed_at"] if records else None,
        "live_fusion": "prohibited_without_temporal_spatial_compatibility",
        "calibration": "not_independently_field_calibrated",
        "limitations": limitations,
    }


def publish(dataset, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(dataset, separators=(",", ":"), allow_nan=False).encode()
    path = root / f"data-{dataset['city']}.json.gz"
    path.write_bytes(gzip.compress(raw, mtime=0))
    return {
        "city": dataset["city"],
        "artifact": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "records": dataset["record_count"],
        "sites": len(dataset["sites"]),
        "period_start": dataset["period_start"],
        "period_end": dataset["period_end"],
        "license": dataset["license"],
        "limitations": dataset["limitations"],
    }
