"""Reproduce narrow count-demand estimation without claiming validated city twins."""

import gzip
import hashlib
import json
from pathlib import Path

from atlas.calibration_v5 import (
    DemandProfile,
    chronological_split,
    count_metrics,
    date_bootstrap_mae,
    readiness,
)
from atlas.city_data_v4 import stamp


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol_path = Path("docs/calibration-v5-protocol.json")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    source = Path(protocol["input_root"])
    output = Path("artifacts/cities/v5")
    output.mkdir(parents=True, exist_ok=True)
    alignment = {
        r["city"]: r
        for r in json.loads((source / "data-network-alignment.json").read_text())["cities"]
    }
    cities, previews = [], {}
    for city in protocol["cities"]:
        path = source / f"data-{city}.json.gz"
        document = json.loads(gzip.decompress(path.read_bytes()))
        partitions, dates = chronological_split(document["records"])
        candidates = []
        for strength in protocol["candidate_prior_exposure_hours"]:
            model = DemandProfile(partitions["calibration"], strength)
            predictions = [model.predict(r) for r in partitions["validation"]]
            candidates.append(
                {
                    "prior_exposure_hours": strength,
                    "validation": count_metrics(partitions["validation"], predictions),
                }
            )
        eligible = [c for c in candidates if c["validation"].get("rows", 0) > 0]
        selected = min(eligible, key=lambda c: c["validation"]["count_mae"]) if eligible else None
        item = {
            **readiness(document, alignment[city]),
            "source_sha256": digest(path),
            "split_dates": dates,
            "candidate_results": candidates,
            "selected_prior_exposure_hours": selected["prior_exposure_hours"] if selected else None,
        }
        if selected:
            model = DemandProfile(partitions["calibration"], selected["prior_exposure_hours"])
            predictions = [model.predict(r) for r in partitions["final"]]
            final = count_metrics(partitions["final"], predictions)
            item["count_demand_regression"] = {
                "final": final,
                "mae_95ci": date_bootstrap_mae(partitions["final"], predictions),
                "final_is_new_unseen_cohort": False,
                "scope": "held-out rows within previously published ATLAS 4 data; demand-profile reconstruction only",
            }
            thresholds = protocol["acceptance"]
            checks = {
                "calibration_dates": len(dates["calibration"])
                >= thresholds["minimum_calibration_dates"],
                "validation_dates": len(dates["validation"])
                >= thresholds["minimum_validation_dates"],
                "final_dates": len(dates["final"]) >= thresholds["minimum_final_dates"],
                "final_rows": final["rows"] >= thresholds["minimum_final_rows"],
                "normalized_mae": final.get("count_normalized_mae") is not None
                and final["count_normalized_mae"] <= thresholds["count_normalized_mae_max"],
                "geh": final.get("geh_below_5_fraction", 0)
                >= thresholds["flow_geh_below_5_fraction_min"],
                "new_unseen_cohort": False,
                "independent_dynamics": False,
            }
            item["acceptance_checks"] = checks
            previews[city] = [
                {
                    "observed_at": r["observed_at"],
                    "site_id": r["site_id"],
                    "direction": r.get("direction"),
                    "interval_seconds": r["interval_seconds"],
                    "observed_count": r["count"],
                    "estimated_demand_count": p,
                    "simulated_count": None,
                    "scope": "historical demand estimate; no simulated state available",
                }
                for r, p in zip(partitions["final"], predictions, strict=True)
            ]
        cities.append(item)
        print(
            city,
            "exploratory",
            item.get("count_demand_regression", {}).get("final", {}),
            flush=True,
        )
    artifact = {
        "schema_version": "atlas-calibration-readiness-5.0",
        "generated_at": stamp(),
        "protocol_sha256": digest(protocol_path),
        "estimator_sha256": digest(Path("backend/atlas/calibration_v5.py")),
        "evaluator_sha256": digest(Path(__file__)),
        "independently_validated_twins": 0,
        "cities": cities,
        "limitations": protocol["limitations"],
    }
    (output / "calibration-readiness.json").write_text(
        json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8"
    )
    payload = json.dumps(
        {"schema_version": "atlas-count-demand-series-5.0", "cities": previews},
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    (output / "count-demand-series.json.gz").write_bytes(gzip.compress(payload, mtime=0))


if __name__ == "__main__":
    main()
