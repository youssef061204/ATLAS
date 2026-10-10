"""Identifiable demand estimation and explicit evidence gates for five-city twins.

No simulator or field accuracy follows from fitting a published counter stream.
Missing observations stay absent. Parameters are estimated only on calibration data.
"""

from collections import defaultdict
from datetime import datetime

import numpy as np
from scipy.optimize import lsq_linear

CITIES = ("toronto", "london", "seattle", "austin", "calgary")


def chronological_split(records, calibration_fraction=0.7, validation_fraction=0.15):
    if not 0 < calibration_fraction < 1 or not 0 < validation_fraction < 1 - calibration_fraction:
        raise ValueError("Invalid chronological split fractions")
    dates = sorted({r["observed_at"][:10] for r in records})
    if len(dates) < 3:
        raise ValueError("Three distinct observation dates are required")
    first = min(max(1, int(len(dates) * calibration_fraction)), len(dates) - 2)
    second = min(
        max(first + 1, int(len(dates) * (calibration_fraction + validation_fraction))),
        len(dates) - 1,
    )
    sets = {
        "calibration": dates[:first],
        "validation": dates[first:second],
        "final": dates[second:],
    }
    partition = {date: name for name, values in sets.items() for date in values}
    return {
        name: [r for r in records if partition[r["observed_at"][:10]] == name] for name in sets
    }, sets


def estimate_nonnegative_demand(design, observed, variance, *, mapping_verified):
    """Weighted least squares OD estimate; a rank-deficient inverse is refused.

    Rows describe verified detector/route incidence, columns OD demand. Variance
    must be supplied explicitly rather than presenting an assumed weight as truth.
    """
    if not mapping_verified:
        raise ValueError("Verified sensor-to-route mapping required")
    matrix, values, variances = (np.asarray(x, dtype=float) for x in (design, observed, variance))
    if (
        matrix.ndim != 2
        or matrix.shape[1] == 0
        or values.shape != (matrix.shape[0],)
        or variances.shape != values.shape
    ):
        raise ValueError("Invalid demand-estimation dimensions")
    if (
        not all(np.isfinite(x).all() for x in (matrix, values, variances))
        or np.any(matrix < 0)
        or np.any(values < 0)
        or np.any(variances <= 0)
    ):
        raise ValueError("Nonfinite or invalid design/count/variance")
    weighted = matrix / np.sqrt(variances[:, None])
    rank = int(np.linalg.matrix_rank(weighted))
    if rank < matrix.shape[1]:
        raise ValueError(f"Unidentifiable OD demand: rank {rank} for {matrix.shape[1]} parameters")
    solution = lsq_linear(weighted, values / np.sqrt(variances), bounds=(0, np.inf), tol=1e-10)
    if not solution.success:
        raise ValueError("Weighted demand estimation failed")
    return {
        "demand": solution.x.tolist(),
        "predicted_counts": (matrix @ solution.x).tolist(),
        "weighted_residual_sum_squares": float(
            np.sum(((matrix @ solution.x - values) ** 2) / variances)
        ),
        "rank": rank,
        "condition_number": float(np.linalg.cond(weighted)),
        "uncertainty": "supplied measurement variances; nonnegative-boundary intervals require bootstrap",
    }


def channel(row):
    return (row["site_id"], row.get("direction"), row["interval_seconds"])


def slot(row):
    time = datetime.fromisoformat(row["observed_at"])
    return (*channel(row), time.hour, time.weekday() >= 5)


class DemandProfile:
    """Exposure-weighted Poisson arrivals shrunk to the training channel mean.

    Rates are vehicles/hour. This estimates a historical demand profile, not a
    physical traffic state. The same site at another year is not concurrent data.
    """

    def __init__(self, records, prior_exposure_hours):
        if not records or not np.isfinite(prior_exposure_hours) or prior_exposure_hours < 0:
            raise ValueError("Training records and nonnegative prior exposure required")
        self.prior = float(prior_exposure_hours)
        self.channels = defaultdict(lambda: [0.0, 0.0])
        self.slots = defaultdict(lambda: [0.0, 0.0])
        seen = set()
        for row in records:
            key = (*channel(row), row["observed_at"])
            if key in seen:
                raise ValueError("Duplicate physical channel/time observation")
            seen.add(key)
            count, seconds = float(row["count"]), float(row["interval_seconds"])
            if not np.isfinite(count) or count < 0 or not np.isfinite(seconds) or seconds <= 0:
                raise ValueError("Invalid count/exposure")
            for target, key in ((self.channels, channel(row)), (self.slots, slot(row))):
                target[key][0] += count
                target[key][1] += seconds / 3600

    def predict(self, row):
        aggregate = self.channels.get(channel(row))
        if aggregate is None:
            return None  # No invented estimate for a never-observed channel.
        baseline = aggregate[0] / aggregate[1]
        local = self.slots.get(slot(row))
        rate = (
            baseline
            if local is None
            else (local[0] + self.prior * baseline) / (local[1] + self.prior)
        )
        return rate * row["interval_seconds"] / 3600


def count_metrics(records, predictions):
    paired = [
        (row, value) for row, value in zip(records, predictions, strict=True) if value is not None
    ]
    if not paired:
        return {"rows": 0, "coverage_fraction": 0.0}
    observed = np.asarray([r["count"] for r, _ in paired], dtype=float)
    predicted = np.asarray([p for _, p in paired], dtype=float)
    if not np.isfinite(predicted).all() or np.any(predicted < 0):
        raise ValueError("Invalid predicted count")
    error = predicted - observed
    interval = np.asarray([r["interval_seconds"] for r, _ in paired], dtype=float)
    observed_flow, predicted_flow = observed * 3600 / interval, predicted * 3600 / interval
    total = observed_flow + predicted_flow
    geh = np.sqrt(
        np.divide(
            2 * (predicted_flow - observed_flow) ** 2,
            total,
            out=np.zeros_like(total),
            where=total > 0,
        )
    )
    return {
        "rows": len(paired),
        "coverage_fraction": len(paired) / len(records),
        "count_mae": float(np.abs(error).mean()),
        "count_rmse": float(np.sqrt(np.mean(error**2))),
        "count_normalized_mae": float(np.abs(error).mean() / observed.mean())
        if observed.mean() > 0
        else None,
        "flow_mae_vph": float(np.abs(predicted_flow - observed_flow).mean()),
        "flow_rmse_vph": float(np.sqrt(np.mean((predicted_flow - observed_flow) ** 2))),
        "geh_below_5_fraction": float((geh < 5).mean()),
        "speed_error": None,
        "travel_time_error": None,
        "physical_queue_error": None,
        "occupancy_error": None,
    }


def date_bootstrap_mae(records, predictions, seed=51001, replicates=2000, minimum_dates=3):
    errors = defaultdict(list)
    for row, prediction in zip(records, predictions, strict=True):
        if prediction is not None:
            errors[row["observed_at"][:10]].append(abs(prediction - row["count"]))
    if len(errors) < minimum_dates:
        return {
            "interval": None,
            "reason": "insufficient independent observation dates",
            "dates": len(errors),
        }
    blocks = list(errors.values())
    totals, sizes = np.asarray([sum(x) for x in blocks]), np.asarray([len(x) for x in blocks])
    draws = np.random.default_rng(seed).integers(0, len(blocks), (replicates, len(blocks)))
    estimates = totals[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    return {
        "interval": np.quantile(estimates, [0.025, 0.975]).tolist(),
        "dates": len(blocks),
        "method": "whole-date cluster percentile bootstrap; serial dependence may remain",
    }


def readiness(document, alignment):
    records = document["records"]
    dates = sorted({r["observed_at"][:10] for r in records})
    mapped = [s for s in alignment.get("sites", []) if s.get("mapped") is True]
    alternatives = []
    for site_id, location in document["sites"].items():
        latitude, longitude = location.get("lat"), location.get("lon")
        alternatives.append(
            {
                "site_id": site_id,
                "name": location["name"],
                "candidate_bbox": [
                    longitude - 0.004,
                    latitude - 0.003,
                    longitude + 0.004,
                    latitude + 0.003,
                ]
                if latitude is not None and longitude is not None
                else None,
                "status": "candidate around official sensor; historical mapping still required"
                if latitude is not None
                else "requires official segment geometry join",
            }
        )
    return {
        "city": document["city"],
        "record_count": len(records),
        "observation_dates": len(dates),
        "period": [dates[0], dates[-1]],
        "source_years": sorted({d[:4] for d in dates}),
        "native_intervals_seconds": sorted({r["interval_seconds"] for r in records}),
        "license": document["license"],
        "sources": sorted({r["source"] for r in records}),
        "inputs": {
            "counts": "directly observed source outputs; independent accuracy unquantified",
            "arrival_profile": "estimated with uncertainty",
            "sensor_to_road_mapping": "unavailable"
            if not mapped
            else "requires scope verification",
            "signal_plans": "assumed",
            "driver_behavior": "assumed",
            "turn_probabilities": "derived from observations; mapping unverified"
            if document["city"] == "toronto"
            else "unavailable",
            "speeds": "unavailable",
            "travel_times": "unavailable",
            "physical_queues": "unavailable",
            "occupancy": "unavailable",
        },
        "evidence_level": 1,
        "twin_status": "exploratory",
        "verified_sensor_mappings": len(mapped),
        "calibratable_scope": "historical channel arrival profile only; no identifiable network OD inverse supplied",
        "alternative_corridor_candidates": alternatives,
        "blockers": [
            "Verified historical sensor-to-road/approach mappings",
            "Independent dynamic-state observations not used as simulator input",
            "Contemporaneous signal and lane configuration or bounded validated sensitivity",
        ],
        "limitations": document["limitations"],
    }
