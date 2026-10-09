"""Official camera adapters. Snapshots are never promoted to video trajectories."""

import hashlib
import json
import math
import os
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from atlas import config


def now():
    return datetime.now(UTC).isoformat()


class Camera(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str
    city: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    orientation: str | None = None
    image_url: str | None = None
    clip_url: str | None = None
    source_modified_at: str | None = None
    kind: str = "snapshot"
    availability: str = "unknown"


def city_configs():
    return json.loads((config.ROOT / "docs/cities.json").read_text(encoding="utf-8"))


class FeedError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Official feed unavailable (HTTP {status})")


class FeedClient:
    """Bounded reads, finite retries, per-origin rate limiting; no access bypass.

    External URLs are fixed official sources or validated source-provided image
    hosts. Redirects are checked before following. Error text excludes API keys.
    """

    def __init__(self, transport=None, min_interval=0.2):
        self.client = httpx.Client(
            timeout=15,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "ATLAS-traffic-research/3.0 (official public data client)"},
        )
        self.min_interval = min_interval
        self.last = {}
        self.lock = threading.Lock()

    def close(self):
        self.client.close()

    def read(self, url, allowed_hosts, params=None, max_bytes=8_000_000):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username:
            raise ValueError("Source URL is not an approved HTTPS host")
        for attempt in range(3):
            with self.lock:
                delay = self.min_interval - (time.monotonic() - self.last.get(parsed.hostname, 0))
                if delay > 0:
                    time.sleep(delay)
                self.last[parsed.hostname] = time.monotonic()
            try:
                with self.client.stream("GET", url, params=params or None) as response:
                    if response.is_redirect:
                        target = str(response.url.join(response.headers["location"]))
                        # One redirect only; keep the same explicit host allowlist.
                        p = urlparse(target)
                        if p.scheme != "https" or p.hostname not in allowed_hosts:
                            raise ValueError("Unapproved feed redirect")
                        with self.client.stream("GET", target) as redirected:
                            return self._body(redirected, max_bytes)
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        retry = response.headers.get("retry-after", "")
                        # Never retry earlier than a stated, excessive rate limit.
                        if retry and (not retry.isdecimal() or int(retry) > 5):
                            raise FeedError(response.status_code)
                        time.sleep(max(0.5 * 2**attempt, int(retry or 0)))
                        continue
                    return self._body(response, max_bytes)
            except httpx.TransportError:
                if attempt == 2:
                    raise FeedError("transport") from None
                time.sleep(0.5 * 2**attempt)
        raise FeedError("retry_exhausted")

    @staticmethod
    def _body(response, maximum):
        if response.status_code != 200:
            raise FeedError(response.status_code)
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > maximum:
                raise ValueError("Feed response exceeds configured byte budget")
        return bytes(content), dict(response.headers)


class CityAdapter:
    def __init__(self, city, client):
        self.settings = city_configs()[city]
        self.city, self.client = city, client

    def discover(self):
        s = self.settings
        parameters = {}
        if self.city == "toronto":
            parameters = {"where": "1=1", "outFields": "*", "outSR": 4326, "f": "json"}
        elif self.city in {"austin", "calgary"}:
            parameters = {"$limit": 5000}
        elif self.city == "london" and os.getenv("ATLAS_TFL_APP_KEY"):
            parameters = {"app_key": os.environ["ATLAS_TFL_APP_KEY"]}
        body, _ = self.client.read(s["endpoint"], s["hosts"], parameters)
        data = json.loads(body)
        if isinstance(data, dict) and data.get("error"):
            raise FeedError(data["error"].get("code", "source_error"))
        if self.city == "toronto" and data.get("exceededTransferLimit"):
            raise ValueError("Incomplete ArcGIS catalog; pagination required")
        rows = data.get("features", []) if self.city == "toronto" else data
        if self.city == "seattle":
            rows = data.get("Features", [])
        cameras = []
        for row in rows:
            cameras.extend(self.normalize(row))
        return cameras, hashlib.sha256(body).hexdigest()

    def normalize(self, row):
        city = self.city
        if city == "toronto":
            a = row["attributes"]
            return [
                Camera(
                    id=str(a["REC_ID"]),
                    city=city,
                    name=f"{a['MAINROAD']} / {a.get('CROSSROAD') or ''}",
                    lat=a["LATITUDE"],
                    lon=a["LONGITUDE"],
                    image_url=a.get("IMAGEURL"),
                )
            ]
        if city == "london":
            props = {p["key"]: p["value"] for p in row.get("additionalProperties", [])}
            return [
                Camera(
                    id=row["id"],
                    city=city,
                    name=row["commonName"],
                    lat=row["lat"],
                    lon=row["lon"],
                    orientation=props.get("view"),
                    image_url=props.get("imageUrl"),
                    clip_url=props.get("videoUrl"),
                    availability=props.get("available", "unknown"),
                    source_modified_at=next(
                        (
                            p.get("modified")
                            for p in row.get("additionalProperties", [])
                            if p["key"] == "imageUrl"
                        ),
                        None,
                    ),
                )
            ]
        if city == "seattle":
            lat, lon = row["PointCoordinate"]
            return [
                Camera(
                    id=c["Id"],
                    city=city,
                    name=c["Description"],
                    lat=lat,
                    lon=lon,
                    image_url="https://www.seattle.gov/trafficcams/images/" + c["ImageUrl"],
                )
                for c in row.get("Cameras", [])
                if c["Type"] == "sdot"
            ]
        if city == "austin":
            coordinates = row.get("location", {}).get("coordinates")
            if not coordinates:
                return []
            lon, lat = coordinates
            return [
                Camera(
                    id=row["camera_id"],
                    city=city,
                    name=row["location_name"].strip(),
                    lat=lat,
                    lon=lon,
                    image_url=row.get("screenshot_address"),
                    source_modified_at=row.get("modified_date"),
                    availability=row.get("camera_status", "unknown"),
                )
            ]
        lon, lat = row["point"]["coordinates"]
        address = row["camera_url"]["url"].replace(
            "http://trafficcam.calgary.ca/", "https://trafficcam.calgary.ca/"
        )
        return [
            Camera(
                id=address.rsplit("/", 1)[-1].split(".")[0],
                city=city,
                name=row["camera_location"],
                lat=lat,
                lon=lon,
                image_url=address,
            )
        ]

    def snapshot(self, camera):
        if camera.city != self.city or not camera.image_url:
            raise ValueError("Camera does not belong to this adapter or has no image")
        body, headers = self.client.read(
            camera.image_url, self.settings["hosts"], max_bytes=2_000_000
        )
        if not headers.get("content-type", "").lower().startswith("image/"):
            raise ValueError("Camera did not return an image")
        image = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.size > 20_000_000:
            raise ValueError("Invalid or excessive image dimensions")
        modified = headers.get("last-modified")
        try:
            modified = parsedate_to_datetime(modified).isoformat() if modified else None
        except (TypeError, ValueError):
            modified = None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        observation = {
            "id": hashlib.sha256(body).hexdigest(),
            "city": self.city,
            "camera_id": camera.id,
            "source": camera.image_url,
            "retrieved_at": now(),
            "captured_at": None,
            "source_last_modified_at": modified,
            "timestamp_semantics": "HTTP Last-Modified is a freshness proxy, not verified capture time",
            "kind": "snapshot",
            "confidence": None,
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
            "quality": {
                "brightness": float(gray.mean()),
                "laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            },
            "retention": "Image processed in memory; only aggregate observations retained",
            "speed_mps": None,
            "trajectories": None,
            "flow_veh_hour": None,
            "licensing": self.settings["licensing"],
        }
        age = (
            (datetime.now(UTC) - datetime.fromisoformat(modified)).total_seconds()
            if modified
            else None
        )
        observation["freshness_proxy_seconds"] = age
        observation["freshness_status"] = (
            "unknown"
            if age is None
            else "future_source_clock"
            if age < -60
            else "stale_proxy"
            if age > self.settings["refresh_seconds"] * 3
            else "recent_http_modification"
        )
        return image, observation


class SnapshotPerception:
    """Independent image detection; no tracker IDs persist across snapshots."""

    def __init__(self):
        from ultralytics import YOLO

        self.model = YOLO(config.MODEL)

    def process(self, image, observation):
        tick = time.perf_counter()
        output = self.model.predict(
            image, classes=[0, 1, 2, 3, 5, 7], conf=0.3, imgsz=640, device="cpu", verbose=False
        )[0]
        counts, confidence = {}, []
        for cls, score in zip(
            output.boxes.cls.cpu().tolist(), output.boxes.conf.cpu().tolist(), strict=True
        ):
            name = self.model.names[int(cls)]
            counts[name] = counts.get(name, 0) + 1
            confidence.append(score)
        return observation | {
            "provenance_class": "vision_derived",
            "model": config.MODEL,
            "counts": counts,
            "detections": [
                {
                    "class": self.model.names[int(cls)],
                    "score": float(score),
                    "box_normalized": [float(v) for v in box],
                }
                for cls, score, box in zip(
                    output.boxes.cls.cpu().tolist(),
                    output.boxes.conf.cpu().tolist(),
                    output.boxes.xyxyn.cpu().tolist(),
                    strict=True,
                )
            ],
            "confidence": float(np.mean(confidence)) if confidence else None,
            "inference_ms": (time.perf_counter() - tick) * 1000,
            "queue_estimate": None,
            "density_veh_km": None,
            "limitations": "Uncalibrated snapshot counts; confidence is a model score, not accuracy. No speed, flow, turns, or persistent tracking.",
        }


def validate_catalog(cameras):
    identities = [c.id for c in cameras]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate source camera IDs")
    if any(not math.isfinite(c.lat + c.lon) for c in cameras):
        raise ValueError("Invalid camera coordinates")


def inspect_city(city, client, detector=None, samples=2):
    adapter = CityAdapter(city, client)
    report = {
        "city": city,
        "checked_at": now(),
        "settings": adapter.settings,
        "mode": "source_check",
        "cameras": [],
        "observations": [],
        "image_checks": [],
    }
    try:
        cameras, digest = adapter.discover()
        validate_catalog(cameras)
        report.update(
            status="metadata_available",
            metadata_sha256=digest,
            cameras=[c.model_dump() for c in cameras],
        )
        # Prefer source-declared available Austin cameras; desired cameras may not exist.
        selected = sorted(
            cameras,
            key=lambda c: (c.availability.upper() not in {"ACTIVE", "TURNED_ON", "TRUE"}, c.id),
        )[:samples]
        for camera in selected:
            try:
                image, observation = adapter.snapshot(camera)
                if detector:
                    observation = detector.process(image, observation)
                report["observations"].append(observation)
                report["image_checks"].append(
                    {"camera_id": camera.id, "status": "accessible", "digest": observation["id"]}
                )
            except (FeedError, ValueError) as exc:
                report["image_checks"].append(
                    {
                        "camera_id": camera.id,
                        "status": "restricted"
                        if isinstance(exc, FeedError) and exc.status in {401, 403}
                        else "unavailable",
                        "reason": str(exc),
                    }
                )
    except (FeedError, ValueError, KeyError) as exc:
        report.update(status="blocked", reason=str(exc))
    return report
