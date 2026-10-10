"""Runtime integrity and measurement-domain behavior using isolated test models."""

import gzip
import json
from pathlib import Path

import numpy as np
import pytest
import torch
from atlas.city_forecast_v4 import CityMessageNetwork
from atlas.city_runtime_v4 import CityForecastRuntime, digest


def write_json(path, record):
    path.write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def trusted_runtime(tmp_path):
    models = tmp_path / "models"
    data = tmp_path / "data"
    models.mkdir()
    data.mkdir()
    protocol_path = tmp_path / "protocol.json"
    write_json(protocol_path, {"neural": {"hidden": 24}})
    sites = {
        "one": {"lat": 43.6, "lon": -79.4},
        "two": {"lat": 43.6005, "lon": -79.4},
        "far": {"lat": 45.0, "lon": -79.4},
    }
    history = [
        {"observed_at": f"2025-01-01T08:{minute:02d}:00", "count": count}
        for minute, count in [(0, 10), (15, 20), (30, 30)]
    ]
    document = {
        "city": "toronto",
        "sites": sites,
        "records": [
            {
                "site_id": site,
                "direction": None,
                "interval_seconds": 900,
                "time_basis": "America/Toronto local civil",
                **row,
            }
            for site in sites
            for row in history
        ],
    }
    archive = data / "data-toronto.json.gz"
    archive.write_bytes(gzip.compress(json.dumps(document).encode(), mtime=0))
    scale = {"mean": 4.0, "std": 1.0}
    model = CityMessageNetwork(graph=False)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.output.bias.fill_(0.1)
    checkpoint_path = models / "toronto-temporal_mlp.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "scale": scale,
            "graph": False,
            "data_sha256": digest(archive),
            "protocol_sha256": digest(protocol_path),
        },
        checkpoint_path,
    )
    feature_hash = digest(Path(__file__).resolve().parents[1] / "atlas/city_forecast_v4.py")
    manifest = {
        "experiment_id": "isolated-runtime-fixture",
        "cities": {
            "toronto": {
                "validation_selected": "temporal_mlp",
                "data_sha256": digest(archive),
                "protocol_sha256": digest(protocol_path),
                "feature_source_sha256": feature_hash,
                "checkpoints": {
                    "temporal_mlp": {
                        "path": checkpoint_path.name,
                        "sha256": digest(checkpoint_path),
                    }
                },
                "scales": {"temporal_mlp": scale},
            }
        },
    }
    manifest_path = models / "runtime-manifest.json"
    write_json(manifest_path, manifest)
    evidence = {
        "experiment_id": manifest["experiment_id"],
        "protocol_sha256": digest(protocol_path),
        "source_sha256": {"model": feature_hash},
        "runtime_manifest_sha256": digest(manifest_path),
        "cities": [
            {
                "city": "toronto",
                "status": "evaluated",
                "validation_selected": "temporal_mlp",
                "data_sha256": digest(archive),
                "uncertainty": {"radius_count": 5.0, "nominal_coverage": 0.9, "test_coverage": 0.8},
                "models": [
                    {"name": "temporal_mlp", "test": {"mae_count_per_native_interval": 2}},
                    {"name": "persistence", "test": {"mae_count_per_native_interval": 1}},
                ],
            }
        ],
    }
    evidence_path = data / "city-forecast.json"
    write_json(evidence_path, evidence)
    payload = {
        "city": "toronto",
        "site_id": "one",
        "direction": None,
        "time_basis": "America/Toronto local civil",
        "interval_seconds": 900,
        "measurement_kind": "historical_motor_vehicle_count",
        "history": history,
    }
    runtime = CityForecastRuntime(models, evidence_path, data, protocol_path)
    return (
        runtime,
        payload,
        manifest,
        evidence,
        manifest_path,
        evidence_path,
        checkpoint_path,
        archive,
    )


def test_actual_weights_only_forward_interval_and_shadow_regression(trusted_runtime):
    runtime, payload, *_ = trusted_runtime
    result = runtime.predict(payload)
    expected = np.expm1(np.log1p(30 * 4) + 0.1) / 4
    assert result["predicted_count"] == pytest.approx(expected, rel=1e-6)
    assert result["forecast_at"] == "2025-01-01T08:45:00"
    assert result["interval"]["upper"] == pytest.approx(expected + 5)
    assert result["shadow"]["persistence_count"] == 30
    assert result["monitoring"]["selected_candidate_regressed_persistence_on_holdout"]
    assert result["monitoring"]["mode"] == "shadow_research_inference"
    assert not result["monitoring"]["operational_promotion"]


def test_cached_checkpoint_is_rechecked_before_every_call(trusted_runtime):
    runtime, payload, _, _, _, _, checkpoint, _ = trusted_runtime
    runtime.predict(payload)
    checkpoint.write_bytes(checkpoint.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="checkpoint checksum"):
        runtime.predict(payload)


def test_manifest_and_source_tampering_rejected(trusted_runtime):
    runtime, payload, _, _, manifest_path, _, _, archive = trusted_runtime
    runtime.predict(payload)
    original = manifest_path.read_bytes()
    manifest_path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="manifest checksum"):
        runtime.predict(payload)
    manifest_path.write_bytes(original)
    archive.write_bytes(archive.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="source checksum"):
        runtime.predict(payload)


def test_neighbor_temporal_alignment_distance_and_missing_mask(trusted_runtime):
    runtime, payload, *_ = trusted_runtime
    assert runtime.predict(payload)["monitoring"]["observed_neighbor_sites"] == 0
    neighbor = {"site_id": "two", "direction": None, "history": payload["history"]}
    payload["neighbors"] = [neighbor]
    assert runtime.predict(payload)["monitoring"]["observed_neighbor_sites"] == 1
    payload["neighbors"] = [{**neighbor, "site_id": "far"}]
    with pytest.raises(ValueError, match="1500"):
        runtime.predict(payload)
    payload["neighbors"] = [
        {
            **neighbor,
            "history": [
                {**row, "observed_at": row["observed_at"].replace("08:", "09:")}
                for row in neighbor["history"]
            ],
        }
    ]
    with pytest.raises(ValueError, match="identical"):
        runtime.predict(payload)


def test_visible_stock_and_invalid_cadence_or_offset_are_rejected(trusted_runtime):
    runtime, payload, *_ = trusted_runtime
    with pytest.raises(ValueError):
        runtime.predict({**payload, "measurement_kind": "snapshot_visible_count"})
    with pytest.raises(ValueError, match="time basis"):
        runtime.predict({**payload, "time_basis": "invented UTC"})
    with pytest.raises(ValueError, match="timezone"):
        runtime.predict(
            {
                **payload,
                "history": [
                    {**row, "observed_at": row["observed_at"] + "+00:00"}
                    for row in payload["history"]
                ],
            }
        )
    with pytest.raises(ValueError, match="contiguous"):
        runtime.predict(
            {
                **payload,
                "history": [payload["history"][0], payload["history"][2], payload["history"][1]],
            }
        )
    for count in (True, -1, float("nan"), float("inf"), 1.5):
        with pytest.raises(ValueError):
            runtime.predict(
                {**payload, "history": [{**row, "count": count} for row in payload["history"]]}
            )


def test_resealed_manifest_still_cannot_choose_path_outside_models(trusted_runtime):
    runtime, payload, manifest, evidence, manifest_path, evidence_path, *_ = trusted_runtime
    manifest["cities"]["toronto"]["checkpoints"]["temporal_mlp"]["path"] = "../../user-file.pt"
    write_json(manifest_path, manifest)
    evidence["runtime_manifest_sha256"] = digest(manifest_path)
    write_json(evidence_path, evidence)
    with pytest.raises(ValueError, match="filename"):
        runtime.predict(payload)


def test_extreme_measured_flow_is_flagged_without_autopromotion(trusted_runtime):
    runtime, payload, *_ = trusted_runtime
    result = runtime.predict(
        {**payload, "history": [{**row, "count": 900_000} for row in payload["history"]]}
    )
    assert result["monitoring"]["ood_history_z_gt_3"]
    assert result["monitoring"]["ood_detection_accuracy"] == "not independently evaluated"
    assert not result["monitoring"]["online_learning"]


def test_trusted_local_hgb_checkpoint_uses_frozen_scale(trusted_runtime):
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor

    runtime, payload, manifest, evidence, manifest_path, evidence_path, checkpoint_path, _ = (
        trusted_runtime
    )
    model = HistGradientBoostingRegressor(max_iter=2, early_stopping=False).fit(
        np.zeros((8, 12)), np.zeros(8)
    )
    path = checkpoint_path.parent / "toronto-histogram_gradient_boosting.joblib"
    joblib.dump(model, path)
    entry = manifest["cities"]["toronto"]
    entry["validation_selected"] = "histogram_gradient_boosting"
    entry["checkpoints"]["histogram_gradient_boosting"] = {
        "path": path.name,
        "sha256": digest(path),
    }
    entry["scales"]["histogram_gradient_boosting"] = entry["scales"]["temporal_mlp"]
    evidence["cities"][0]["validation_selected"] = "histogram_gradient_boosting"
    evidence["cities"][0]["models"].append(
        {"name": "histogram_gradient_boosting", "test": {"mae_count_per_native_interval": 2}}
    )
    write_json(manifest_path, manifest)
    evidence["runtime_manifest_sha256"] = digest(manifest_path)
    write_json(evidence_path, evidence)
    result = runtime.predict(payload)
    assert result["model"] == "histogram_gradient_boosting"
    assert result["predicted_count"] == pytest.approx(np.expm1(4.0) / 4)
