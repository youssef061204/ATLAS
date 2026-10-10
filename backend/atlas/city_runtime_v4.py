"""Trusted shadow inference on native municipal count histories.

City counts and highway speeds have separate models. Snapshot visible-object stock
is never accepted as an interval flow measurement. No model promotion or online
training occurs here. Requests cannot choose checkpoints or file-system paths.
"""

import gzip
import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field
from threadpoolctl import threadpool_limits

from atlas import config
from atlas.city_forecast_v4 import CityMessageNetwork, TrainingScale

CITIES = ("toronto", "london", "seattle", "austin", "calgary")
LEARNED = ("temporal_mlp", "geographic_message_network", "histogram_gradient_boosting")
_HGB_INFERENCE_LOCK = threading.Lock()


class CountBin(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    observed_at: str = Field(min_length=16, max_length=40)
    count: float = Field(strict=True, ge=0, le=1_000_000)


class NeighborHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: str = Field(min_length=1, max_length=150)
    direction: str | None = None
    history: list[CountBin] = Field(min_length=3, max_length=3)


class CityCountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    city: Literal["toronto", "london", "seattle", "austin", "calgary"]
    site_id: str = Field(min_length=1, max_length=150)
    direction: str | None = None
    time_basis: str = Field(min_length=1, max_length=200)
    interval_seconds: Literal[900, 3600]
    measurement_kind: Literal["historical_motor_vehicle_count"]
    history: list[CountBin] = Field(min_length=3, max_length=3)
    neighbors: list[NeighborHistory] = Field(default_factory=list, max_length=32)


def digest(path, maximum=64_000_000):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise ValueError("Trusted runtime artifact exceeds size budget")
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Version of this actual loaded module, not a later edited file on disk.
_RUNTIME_SOURCE_SHA256 = digest(Path(__file__))


def strict_json(raw):
    def reject(value):
        raise ValueError("Nonfinite runtime metadata")

    return json.loads(raw, parse_constant=reject)


@lru_cache(maxsize=5)
def source_document(path, expected):
    # Caller checks compressed source bytes before consulting this bounded cache.
    with gzip.open(path, "rb") as handle:
        raw = handle.read(64_000_001)
    if len(raw) > 64_000_000:
        raise ValueError("Historical runtime source exceeds decompressed budget")
    document = strict_json(raw)
    channels = {}
    for record in document["records"]:
        key = (record["site_id"], record.get("direction"), record["interval_seconds"])
        entry = channels.setdefault(key, {"basis": set(), "awareness": set()})
        entry["basis"].add(record["time_basis"])
        entry["awareness"].add(
            datetime.fromisoformat(record["observed_at"]).utcoffset() is not None
        )
    # Retain only small validated source registries, not every historical record.
    return {"city": document["city"], "sites": document["sites"], "channels": channels}


@lru_cache(maxsize=10)
def checkpoint_model(path, expected, graph, hidden):
    if path.endswith(".joblib"):
        # Only the server-configured locally trained checkpoint, whose digest is
        # pinned by a versioned evidence manifest, reaches this loader.
        return joblib.load(path), None
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    model = CityMessageNetwork(graph=graph, hidden=hidden)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    return model.eval(), checkpoint


def dates(history, source_aware):
    stamps = []
    for row in history:
        if isinstance(row.count, bool) or not row.count.is_integer():
            raise ValueError("Source measurements must be whole motor-vehicle counts")
        value = datetime.fromisoformat(row.observed_at.replace("Z", "+00:00"))
        aware = value.utcoffset() is not None
        if aware != source_aware or (source_aware and value.utcoffset() != timedelta(0)):
            raise ValueError("Observation timezone offset differs from verified source time basis")
        stamps.append(value)
    return stamps


def source_channel(document, site_id, direction, interval):
    if site_id not in document["sites"]:
        raise ValueError("Unknown official source site")
    channel = document["channels"].get((site_id, direction, interval))
    if not channel:
        raise ValueError("Unknown source direction or native interval")
    if len(channel["basis"]) != 1 or len(channel["awareness"]) != 1:
        raise ValueError("Source has ambiguous timestamp semantics")
    return next(iter(channel["basis"])), next(iter(channel["awareness"]))


def geographic_distance(first, second):
    if any(first.get(key) is None or second.get(key) is None for key in ("lat", "lon")):
        return float("inf")
    latitude = np.radians((first["lat"] + second["lat"]) / 2)
    return float(
        np.hypot(
            (first["lat"] - second["lat"]) * 111195,
            (first["lon"] - second["lon"]) * 111195 * np.cos(latitude),
        )
    )


class CityForecastRuntime:
    def __init__(self, model_root=None, evidence_path=None, data_root=None, protocol_path=None):
        # These overrides support isolated tests and server deployment configuration;
        # HTTP inputs never expose them.
        self.model_root = Path(model_root or config.DATA / "models/city-v4").resolve()
        self.data_root = Path(data_root or config.ARTIFACTS / "cities/v4").resolve()
        self.evidence_path = Path(evidence_path or self.data_root / "city-forecast.json")
        self.protocol_path = Path(
            protocol_path or config.ROOT / "docs/city-forecast-v4-protocol.json"
        )

    def predict(self, supplied):
        started = time.perf_counter()
        request = (
            supplied
            if isinstance(supplied, CityCountInput)
            else CityCountInput.model_validate(supplied)
        )
        evidence = strict_json(self.evidence_path.read_bytes())
        manifest_path = self.model_root / "runtime-manifest.json"
        if digest(manifest_path, 1_000_000) != evidence.get("runtime_manifest_sha256"):
            raise ValueError("Runtime manifest checksum differs from versioned evaluation evidence")
        manifest = strict_json(manifest_path.read_bytes())
        entry = manifest["cities"].get(request.city)
        study = next((row for row in evidence["cities"] if row["city"] == request.city), None)
        if not entry or not study or study.get("status") != "evaluated":
            raise ValueError("City has no evaluated native count forecast")
        if (
            manifest["experiment_id"] != evidence["experiment_id"]
            or entry["validation_selected"] != study["validation_selected"]
        ):
            raise ValueError("Runtime selection differs from frozen validation selection")
        if (
            digest(self.protocol_path) != entry["protocol_sha256"]
            or entry["protocol_sha256"] != evidence["protocol_sha256"]
        ):
            raise ValueError("Runtime protocol version mismatch")
        feature_path = Path(__file__).with_name("city_forecast_v4.py")
        if (
            digest(feature_path) != entry["feature_source_sha256"]
            or entry["feature_source_sha256"] != evidence["source_sha256"]["model"]
        ):
            raise ValueError("Runtime causal feature source version mismatch")
        source_path = self.data_root / f"data-{request.city}.json.gz"
        if (
            digest(source_path) != entry["data_sha256"]
            or entry["data_sha256"] != study["data_sha256"]
        ):
            raise ValueError("Runtime municipal source checksum mismatch")
        document = source_document(str(source_path), entry["data_sha256"])
        if document["city"] != request.city:
            raise ValueError("Municipal archive city mismatch")
        basis, source_aware = source_channel(
            document, request.site_id, request.direction, request.interval_seconds
        )
        if request.time_basis != basis:
            raise ValueError("Input time basis differs from verified source semantics")
        stamps = dates(request.history, source_aware)
        step = timedelta(seconds=request.interval_seconds)
        if any(b - a != step for a, b in zip(stamps, stamps[1:], strict=False)):
            raise ValueError(
                "Three measured source bins must be strictly chronological and contiguous"
            )
        if any(
            stamp.second or stamp.microsecond or (stamp.minute * 60) % request.interval_seconds
            for stamp in stamps
        ):
            raise ValueError("Measured source bins are not aligned to native interval boundaries")
        target = stamps[-1] + step
        hour = target.hour + target.minute / 60
        valid_neighbors, seen = [], set()
        for neighbor in request.neighbors:
            if neighbor.site_id == request.site_id or neighbor.site_id in seen:
                raise ValueError("Duplicate or self-referential neighbor source")
            seen.add(neighbor.site_id)
            other_basis, other_aware = source_channel(
                document, neighbor.site_id, neighbor.direction, request.interval_seconds
            )
            if (
                neighbor.direction != request.direction
                or other_basis != basis
                or other_aware != source_aware
            ):
                raise ValueError(
                    "Neighbor source does not match local native measurement semantics"
                )
            if dates(neighbor.history, other_aware) != stamps:
                raise ValueError(
                    "Neighbor histories must use the identical three causal timestamps"
                )
            if (
                geographic_distance(
                    document["sites"][request.site_id], document["sites"][neighbor.site_id]
                )
                > 1500
            ):
                raise ValueError("Neighbor source lacks verified coordinates within 1500 metres")
            valid_neighbors.append(
                [row.count * 3600 / request.interval_seconds for row in neighbor.history]
            )
        row = {
            "history_flow_vph": [
                bin.count * 3600 / request.interval_seconds for bin in request.history
            ],
            "neighbor_flow_vph": np.mean(valid_neighbors, axis=0).tolist()
            if valid_neighbors
            else [0.0] * 3,
            "neighbor_sites": len(valid_neighbors),
            "interval_seconds": request.interval_seconds,
            "calendar": [
                float(np.sin(2 * np.pi * hour / 24)),
                float(np.cos(2 * np.pi * hour / 24)),
                float(np.sin(2 * np.pi * target.weekday() / 7)),
                float(np.cos(2 * np.pi * target.weekday() / 7)),
                float(np.log1p(request.interval_seconds) / 10),
            ],
        }
        selected = entry["validation_selected"]
        if selected not in LEARNED:
            raise ValueError(
                "Validation-selected baseline has no registered native checkpoint; inference unavailable"
            )
        checkpoint_entry = entry["checkpoints"][selected]
        basename = checkpoint_entry["path"]
        if not re.fullmatch(r"[a-z0-9_-]+\.(pt|joblib)", basename):
            raise ValueError("Untrusted checkpoint filename")
        checkpoint_path = (self.model_root / basename).resolve()
        if checkpoint_path.parent != self.model_root:
            raise ValueError("Checkpoint resolves outside trusted model directory")
        if digest(checkpoint_path) != checkpoint_entry["sha256"]:
            raise ValueError("Native checkpoint checksum mismatch")
        protocol = strict_json(self.protocol_path.read_bytes())
        model, checkpoint = checkpoint_model(
            str(checkpoint_path),
            checkpoint_entry["sha256"],
            selected == "geographic_message_network",
            protocol["neural"]["hidden"],
        )
        scale_info = entry["scales"][selected]
        if (
            not all(math.isfinite(scale_info[key]) for key in ("mean", "std"))
            or scale_info["std"] < 0.1
        ):
            raise ValueError("Invalid frozen training normalization")
        if checkpoint is not None:
            if (
                checkpoint["data_sha256"] != entry["data_sha256"]
                or checkpoint["protocol_sha256"] != entry["protocol_sha256"]
                or checkpoint["scale"] != scale_info
                or checkpoint["graph"] != (selected == "geographic_message_network")
            ):
                raise ValueError("Checkpoint training provenance or architecture mismatch")
        scale = TrainingScale.__new__(TrainingScale)
        scale.mean, scale.std = scale_info["mean"], scale_info["std"]
        features = scale.features([row])
        if selected == "histogram_gradient_boosting":
            # Bound tiny HGB requests rather than launching host-wide OpenMP work.
            # Serialize this temporary native-library thread setting for this runtime.
            with _HGB_INFERENCE_LOCK, threadpool_limits(limits=4, user_api="openmp"):
                normalized = model.predict(features)
        else:
            with torch.inference_mode():
                normalized = model(torch.tensor(features)).numpy()
        count = float(scale.counts(normalized, [row])[0])
        if not math.isfinite(count) or count < 0:
            raise ValueError("City model returned an invalid count forecast")
        radius = study["uncertainty"]["radius_count"]
        if radius is not None and (not math.isfinite(radius) or radius < 0):
            raise ValueError("Invalid frozen uncertainty interval")
        maximum_z = float(np.max(np.abs(features[0, :3])))
        selected_test = next(m for m in study["models"] if m["name"] == selected)["test"][
            "mae_count_per_native_interval"
        ]
        baseline_test = next(m for m in study["models"] if m["name"] == "persistence")["test"][
            "mae_count_per_native_interval"
        ]
        return {
            "experiment_id": evidence["experiment_id"],
            "city": request.city,
            "site_id": request.site_id,
            "direction": request.direction,
            "forecast_at": target.isoformat(),
            "time_basis": basis,
            "interval_seconds": request.interval_seconds,
            "predicted_count": count,
            "units": "motor vehicles/next native interval",
            "interval": {
                "lower": max(0, count - radius) if radius is not None else None,
                "upper": count + radius if radius is not None else None,
                "nominal_coverage": study["uncertainty"]["nominal_coverage"],
                "calibration": "Frozen validation residual marginal split-conformal interval; chronological shift can invalidate coverage",
                "observed_holdout_coverage": study["uncertainty"].get("test_coverage"),
            },
            "model": selected,
            "model_version": checkpoint_entry["sha256"],
            "provenance": {
                "data_sha256": entry["data_sha256"],
                "protocol_sha256": entry["protocol_sha256"],
                "feature_source_sha256": entry["feature_source_sha256"],
                "runtime_manifest_sha256": evidence["runtime_manifest_sha256"],
                "runtime_source_sha256": _RUNTIME_SOURCE_SHA256,
                "count_history": "caller_supplied_measured_counts_not_independently_verified",
                "site_location": document["sites"][request.site_id],
            },
            "monitoring": {
                "maximum_absolute_training_history_z": maximum_z,
                "ood_history_z_gt_3": maximum_z > 3,
                "ood_detection_accuracy": "not independently evaluated",
                "observed_neighbor_sites": len(valid_neighbors),
                "neighbor_graph": "Undirected geographic proximity, not surveyed directed traffic flow",
                "selected_candidate_regressed_persistence_on_holdout": selected_test
                > baseline_test,
                "online_learning": False,
                "operational_promotion": False,
                "mode": "shadow_research_inference",
            },
            "shadow": {
                "persistence_count": request.history[-1].count,
                "candidate_minus_persistence_count": count - request.history[-1].count,
                "observed_target_count": None,
            },
            "runtime_ms": (time.perf_counter() - started) * 1000,
            "scope": "Municipal native-interval motor count forecast; no highway-speed metric transfer, snapshot demand fusion or field actuation",
        }


def predict_city_counts(payload):
    return CityForecastRuntime().predict(payload)
