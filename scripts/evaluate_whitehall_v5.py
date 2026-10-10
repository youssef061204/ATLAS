"""Evaluate actual alternative-corridor counts, separate from old London cohorts."""

import gzip
import hashlib
import json
from pathlib import Path

from atlas.calibration_v5 import (
    DemandProfile,
    chronological_split,
    count_metrics,
    date_bootstrap_mae,
)
from atlas.city_data_v4 import HistoricalClient, finite_count, stamp


def main():
    protocol_path = Path("docs/whitehall-v5-protocol.json")
    protocol = json.loads(protocol_path.read_bytes())
    client = HistoricalClient("data/city-calibration-v5/geometry-cache")
    try:
        document, retrieved = client.get(
            protocol["endpoint"],
            {
                "filter[count_point_id]": protocol["count_point_id"],
                "page[size]": 500,
                "page[number]": 1,
                "sort": "count_date,hour,direction_of_travel",
            },
        )
        if document.get("next_page_url"):
            raise ValueError("Incomplete bounded raw count retrieval")
        records = []
        for row in document["data"]:
            assert row["count_point_id"] == protocol["count_point_id"]
            records.append(
                {
                    "site_id": str(row["count_point_id"]),
                    "observed_at": f"{row['count_date']}T{int(row['hour']):02d}:00:00",
                    "direction": row["direction_of_travel"],
                    "interval_seconds": 3600,
                    "count": finite_count(row["all_motor_vehicles"]),
                    "source": protocol["endpoint"],
                }
            )
        partitions, dates = chronological_split(records)
        candidates = []
        for strength in protocol["candidate_prior_exposure_hours"]:
            model = DemandProfile(partitions["calibration"], strength)
            values = [model.predict(r) for r in partitions["validation"]]
            candidates.append(
                {
                    "prior_exposure_hours": strength,
                    "validation": count_metrics(partitions["validation"], values),
                }
            )
        selected = min(candidates, key=lambda c: c["validation"]["count_mae"])
        model = DemandProfile(partitions["calibration"], selected["prior_exposure_hours"])
        predictions = [model.predict(r) for r in partitions["final"]]
        output = Path("artifacts/cities/v5")
        raw = json.dumps(
            {
                "schema_version": "atlas-whitehall-observations-5.0",
                "city": "london",
                "count_point_id": protocol["count_point_id"],
                "records": records,
                "license": {
                    "name": "UK Open Government Licence v3.0",
                    "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                    "attribution": "Contains public sector information licensed under the Open Government Licence v3.0; Department for Transport road traffic statistics.",
                },
                "source_response_sha256": client.health[-1]["source_response_sha256"],
                "retrieved_at": retrieved,
                "time_basis": "source published count date and survey hour; timezone not independently established",
            },
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        (output / "data-whitehall.json.gz").write_bytes(gzip.compress(raw, mtime=0))
        result = {
            "schema_version": "atlas-whitehall-demand-evaluation-5.0",
            "evaluated_at": stamp(),
            "count_point_id": protocol["count_point_id"],
            "record_count": len(records),
            "split_dates": dates,
            "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "estimator_sha256": hashlib.sha256(
                Path("backend/atlas/calibration_v5.py").read_bytes()
            ).hexdigest(),
            "data_sha256": hashlib.sha256(
                (output / "data-whitehall.json.gz").read_bytes()
            ).hexdigest(),
            "candidates": candidates,
            "selected_prior_exposure_hours": selected["prior_exposure_hours"],
            "final": count_metrics(partitions["final"], predictions),
            "mae_95ci": date_bootstrap_mae(partitions["final"], predictions),
            "evidence_level": 1,
            "independent_simulation_state_validation": False,
            "final_series": [
                {**row, "estimated_demand_count": prediction, "simulated_count": None}
                for row, prediction in zip(partitions["final"], predictions, strict=True)
            ],
            "limitations": protocol["limitations"],
        }
        (output / "whitehall-results.json").write_text(
            json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "rows": len(records),
                    "selected": selected["prior_exposure_hours"],
                    "final": result["final"],
                    "dates": dates,
                },
                indent=2,
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
