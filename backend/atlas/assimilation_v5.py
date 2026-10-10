"""Confidence-aware assimilation of compatible, independently mapped traffic sensors.

This module cannot turn single-image visible counts into arrival flow or queues.
Its variance inputs must come from an explicit measurement model, not confidence
scores mislabeled as calibrated physical uncertainty.
"""

import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Measurement:
    identity: str
    modality: str
    metric: str
    value: float
    variance: float
    observed_at: datetime
    interval_seconds: float
    footprint_id: str
    mapping_verified: bool
    temporal_coverage_fraction: float = 1
    spatial_coverage_fraction: float = 1
    correlation_group: str = "unknown"
    independent_group_verified: bool = False


def assimilate(
    measurements,
    *,
    now,
    metric,
    footprint_id,
    prior_mean=None,
    prior_variance=None,
    elapsed_seconds=0,
    process_variance_per_second=1,
):
    if now.tzinfo is None:
        raise ValueError("Assimilation clock must have an explicit timezone")
    if metric not in {"arrival_flow_vph", "queue_vehicles", "occupancy_fraction"}:
        raise ValueError("Unsupported compatible physical metric")
    if (
        not math.isfinite(elapsed_seconds)
        or elapsed_seconds < 0
        or not math.isfinite(process_variance_per_second)
        or process_variance_per_second < 0
    ):
        raise ValueError("Invalid process uncertainty")
    if (prior_mean is None) != (prior_variance is None):
        raise ValueError("Prior mean and variance must be supplied together")
    if prior_mean is not None and (
        not math.isfinite(prior_mean)
        or prior_mean < 0
        or not math.isfinite(prior_variance)
        or prior_variance <= 0
        or metric == "occupancy_fraction"
        and prior_mean > 1
    ):
        raise ValueError("Invalid physical-state prior")
    rejected, eligible, seen = [], [], set()
    for value in measurements:
        reason = None
        if value.identity in seen:
            reason = "duplicate_observation_identity"
        elif value.modality not in {"detector", "camera"}:
            reason = "unsupported_modality"
        elif value.metric != metric:
            reason = "incompatible_units_or_metric"
        elif not value.mapping_verified or value.footprint_id != footprint_id:
            reason = "unverified_or_different_spatial_mapping"
        elif value.observed_at.tzinfo is None:
            reason = "unverified_timestamp_basis"
        elif (
            not all(
                math.isfinite(v)
                for v in (
                    value.value,
                    value.variance,
                    value.interval_seconds,
                    value.temporal_coverage_fraction,
                    value.spatial_coverage_fraction,
                )
            )
            or value.value < 0
            or value.variance <= 0
            or value.interval_seconds <= 0
            or metric == "occupancy_fraction"
            and value.value > 1
        ):
            reason = "invalid_physical_measurement_or_variance"
        elif (
            not 0 < value.temporal_coverage_fraction <= 1
            or not 0 < value.spatial_coverage_fraction <= 1
        ):
            reason = "invalid_coverage"
        elif value.temporal_coverage_fraction < 0.95 or value.spatial_coverage_fraction < 0.95:
            reason = "insufficient_matched_spatiotemporal_coverage"
        else:
            age = (now - value.observed_at).total_seconds()
            if age < 0:
                reason = "future_observation"
            elif age > min(300, 2 * value.interval_seconds):
                reason = "stale_observation"
        seen.add(value.identity)
        if reason:
            rejected.append({"identity": value.identity, "reason": reason})
        else:
            eligible.append(value)
    # Unknown dependence never earns extra precision from multiple observations.
    groups = {}
    for value in eligible:
        group = (
            value.correlation_group if value.independent_group_verified else "unknown_dependence"
        )
        previous = groups.get(group)
        if previous is None or value.variance < previous.variance:
            if previous is not None:
                rejected.append(
                    {"identity": previous.identity, "reason": "overlap_or_unverified_independence"}
                )
            groups[group] = value
        else:
            rejected.append(
                {"identity": value.identity, "reason": "overlap_or_unverified_independence"}
            )
    eligible = list(groups.values())
    disagreements = []
    detector = [v for v in eligible if v.modality == "detector"]
    for camera in [v for v in eligible if v.modality == "camera"]:
        if any(
            abs(camera.value - d.value) > 3 * math.sqrt(camera.variance + d.variance)
            for d in detector
        ):
            eligible.remove(camera)
            rejected.append(
                {"identity": camera.identity, "reason": "sensor_disagreement_camera_quarantined"}
            )
            disagreements.append(camera.identity)
    precision, numerator = 0.0, 0.0
    if prior_mean is not None:
        variance = prior_variance + elapsed_seconds * process_variance_per_second
        precision, numerator = 1 / variance, prior_mean / variance
    for value in eligible:
        age = (now - value.observed_at).total_seconds()
        variance = value.variance + process_variance_per_second * age
        precision += 1 / variance
        numerator += value.value / variance
    return {
        "metric": metric,
        "footprint_id": footprint_id,
        "mean": numerator / precision if precision else None,
        "variance": 1 / precision if precision else None,
        "used_observations": [v.identity for v in eligible],
        "rejected_observations": rejected,
        "sensor_disagreements": disagreements,
        "mode": "measurement_update"
        if eligible
        else "prediction_only"
        if precision
        else "unavailable",
        "scope": "conditional on supplied calibrated variance and verified measurement correspondence; no empirical fusion benefit implied",
    }
