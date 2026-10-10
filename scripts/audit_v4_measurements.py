"""Qualify invalid recorded telemetry without rewriting frozen raw metric values."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path("artifacts/cities/v4")
    sources, affected = {}, []
    for name in (
        "controller-heldout-nominal.json",
        "controller-heldout-low.json",
        "controller-heldout-high.json",
        "cooperative-q-results.json",
    ):
        path = root / name
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        study = json.loads(path.read_text())
        for row in study["runs"]:
            metrics = row["metrics"]
            assert metrics["mean_delay_s"] >= 0 and metrics["modeled_safety_violations"] == 0
            invalid = {
                key: metrics[key]
                for key in ("co2_model_kg", "fuel_model_kg")
                if metrics.get(key, 0) is not None and metrics.get(key, 0) < 0
            }
            if invalid:
                affected.append(
                    {
                        "source": name,
                        "city": row["city"],
                        "policy": row["policy"],
                        "seed": row["seed"],
                        "invalid_recorded_values": invalid,
                        "unavailable_comparisons": [
                            "co2_model_kg",
                            "fuel_model_kg",
                            "stops_per_vehicle",
                        ],
                        "qualification": "Invalid vehicle subscription sentinels contaminate integrals and potentially stop events. Raw values remain unchanged for audit. No emissions/stop benefit can be inferred from this episode or affected aggregate.",
                    }
                )
    (root / "measurement-quality.json").write_text(
        json.dumps(
            {
                "source_sha256": sources,
                "affected_episodes": affected,
                "scope": "Traffic delay/completion use separate SUMO trip outputs; modeled lane queues and signal safety remain separate. Preserves recorded invalid values, does not manufacture corrected quantities.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "Qualified", len(affected), "episodes with invalid vehicle telemetry; raw values preserved"
    )


if __name__ == "__main__":
    main()
