"""Preserve signed displacement diagnosis on already exposed Lankershim windows."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas.physical_metrics_v7 import birth_correspondence
from atlas.residuals_v8 import residual_audit
from calibrate_physics_v7 import native_states, reference_states
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import road_model

ROOT = Path(__file__).resolve().parents[1]
V7 = ROOT / "data/reality-v7/eager-insertion"
ORACLE = ROOT / "data/reality-v8/reference-demand-development"
PUBLIC = ROOT / "artifacts/reality/v8/physical-residual-development.json"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def direction_map(source):
    eligible = source[(source.frame_id - 1) % 10 == 0]
    return {
        (round(row.t), str(row.vehicle_id)): int(row.direction) for row in eligible.itertuples()
    }


def main():
    if PUBLIC.exists():
        raise FileExistsError("Preserve measured residual audit")
    source = development_observations(1000)
    road, _ = road_model(source)
    all_states, scoring = reference_states(source, road)
    directions = direction_map(source)
    entries = json.loads((V7 / "duration-1122/inputs.json").read_text(encoding="utf-8"))["entries"]
    mapping, _ = birth_correspondence(entries, all_states)
    cv_dir = V7 / "duration-1122"
    oracle_dir = ORACLE
    oracle_mapping = {
        vehicle.get("id").removeprefix("ref_"): {
            "native_id": vehicle.get("id"),
            "birth_s": float(vehicle.get("depart")),
        }
        for vehicle in ET.parse(oracle_dir / "routes.xml").findall("vehicle")
    }
    result = {
        "schema": "atlas-v8-signed-physical-residual-1",
        "development_cv_30_300": residual_audit(
            mapping, scoring, native_states(V7 / "duration-300"), directions, road, 30, 300
        ),
        "development_oracle_30_300": residual_audit(
            oracle_mapping, scoring, native_states(oracle_dir), directions, road, 30, 300
        ),
        "known_regression_cv_600_1000": residual_audit(
            mapping, scoring, native_states(cv_dir), directions, road, 600, 1000
        ),
        "source_scope": "30-300 s already exposed development and 600-1000 s already exposed regression; no new holdout",
        "physical_twin_accepted": False,
        "source_sha256": sha(Path(__file__)),
        "native_fcd_sha256": {
            "cv_development": sha(V7 / "duration-300/simulation.fcd.xml.gz"),
            "oracle_development": sha(oracle_dir / "simulation.fcd.xml.gz"),
            "cv_known_regression": sha(cv_dir / "simulation.fcd.xml.gz"),
        },
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: value["groups"]["all"]
                for key, value in result.items()
                if key.endswith("_300") or key.endswith("_1000")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
