import importlib.util
import json
import xml.etree.ElementTree as ET
import zipfile

import httpx
import numpy as np
import pytest
from atlas import config
from atlas.api import app
from atlas.evaluation import data as dataset_data
from atlas.evaluation.artifacts import BenchmarkArtifact
from atlas.evaluation.data import DETRAC_ARCHIVES, DETRAC_SEQUENCES, parse_detrac_csv
from atlas.evaluation.forecasting import causal_fill, chronological_masks, forecast_scores
from atlas.evaluation.signal import CANDIDATES, build_period, choose_phase, trip_metrics
from atlas.evaluation.vision import coco_ground_truth, ignore_predictions, matches, tracking_input
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_annotation_conversion_and_rejection(tmp_path):
    path = tmp_path / "annotations.csv"
    header = "filename,width,height,class,xmin,ymin,xmax,ymax,target_id\n"
    path.write_text(
        header
        + "img00001.jpg,100,80,vehicle,1,2,11,12,7\nimg00001.jpg,100,80,ignored,20,20,40,40,0\nimage000002.jpg,100,80,vehicle,1,2,11,12,8\n"
    )
    frames = parse_detrac_csv(path, 1)
    assert list(frames) == [1]
    assert frames[1]["objects"][0]["id"] == 7
    assert frames[1]["ignored"] == [[20, 20, 40, 40]]
    path.write_text(header + "img00001.jpg,100,80,vehicle,10,2,1,12,7\n")
    with pytest.raises(ValueError, match="box"):
        parse_detrac_csv(path)


def test_ignored_regions_preserve_valid_matches_and_empty_cases():
    gt = [{"id": 1, "bbox": [0, 0, 10, 10]}]
    predictions = [{"id": 5, "bbox": [0, 0, 10, 10]}, {"id": 6, "bbox": [20, 20, 25, 25]}]
    assert ignore_predictions(gt, predictions, [[0, 0, 30, 30]]) == predictions[:1]
    assert matches([], predictions) == []
    frames = [
        {
            "frame": 1,
            "filename": "img00001.jpg",
            "width": 40,
            "height": 40,
            "objects": gt,
            "ignored": [[20, 20, 30, 30]],
        }
    ]
    coco, mapping = coco_ground_truth({"camera": frames})
    assert len(coco["annotations"]) == 2
    assert coco["annotations"][1]["iscrowd"] == 1
    assert len(mapping) == 1
    data = tracking_input(frames, [predictions[:1]])
    assert data["num_gt_ids"] == data["num_tracker_ids"] == 1


def test_official_tracking_metrics_perfect_and_identity_break():
    trackeval = pytest.importorskip("trackeval")
    frames = [{"objects": [{"id": 1, "bbox": [0, 0, 10, 10]}]} for _ in range(4)]
    perfect = tracking_input(frames, [[{"id": 3, "bbox": [0, 0, 10, 10]}]] * 4)
    broken = tracking_input(frames, [[{"id": i, "bbox": [0, 0, 10, 10]}] for i in range(4)])
    metric = trackeval.metrics.Identity()
    assert metric.eval_sequence(perfect)["IDF1"] == 1
    assert metric.eval_sequence(broken)["IDF1"] < 1


def test_causal_fill_and_temporal_splits():
    values = np.array([[10.0], [0.0], [20.0], [0.0], [999.0]])
    filled, valid = causal_fill(values, 3)
    assert filled[:, 0].tolist() == [10, 10, 20, 20, 999]
    assert not valid[1, 0]
    origins = np.arange(6, 100)
    masks = chronological_masks(origins, 3, 60, 80, 100)
    assert not (masks["train"] & masks["test"]).any()
    assert not (masks["validation"] & masks["test"]).any()
    assert np.max((origins + 2)[masks["train"]]) < 60
    assert np.min(origins[masks["test"]]) >= 80
    assert set(DETRAC_SEQUENCES["test"]).isdisjoint(DETRAC_SEQUENCES["validation"])


def test_forecast_scores_mask_missing_and_low_speed_mape():
    actual = np.array([0.0, 2.0, 10.0])
    predicted = np.array([100.0, 4.0, 12.0])
    score = forecast_scores(actual, predicted, actual > 0)
    assert score["mae"] == score["rmse"] == 2
    assert score["valid_targets"] == 2
    assert score["mape_targets"] == 1
    assert score["mape_pct"] == pytest.approx(20)


def test_signal_period_and_all_demand_denominator(tmp_path):
    source = tmp_path / "routes.xml"
    target = tmp_path / "period.xml"
    source.write_text(
        '<routes><vType id="car"/><trip id="before" depart="9"/><trip id="a" depart="10"/><trip id="b" depart="19"/><trip id="after" depart="20"/></routes>'
    )
    assert build_period(source, target, 10, 10) == {"a": 0, "b": 9}
    trip = ET.fromstring('<tripinfo id="a" timeLoss="2" departDelay="1" arrival="8" duration="7"/>')
    score = trip_metrics([trip], {"a": 0, "b": 9}, 10, {}, [0, 2], {"a": "north"})
    assert score["mean_delay_s"] == 2
    assert score["completed_trips"] == 1
    assert score["not_inserted"] == 1
    assert score["unfinished_vehicles"] == 1
    assert score["pedestrian_wait_s"] is None
    assert all(a + b + 6 * 12 + 8 * 5 <= 200 for a, b in CANDIDATES)
    assert choose_phase("max_pressure", 0, 11, [0, 20], [0, 20], [12, 12], [0, 0]) == 0
    assert choose_phase("max_pressure", 0, 12, [1, 20], [0, 20], [12, 12], [0, 181]) == 1


def test_committed_artifacts_schema_and_api(database, monkeypatch):
    paths = list((config.ARTIFACTS / "benchmarks").glob("*.json"))
    assert paths
    for path in paths:
        BenchmarkArtifact.model_validate_json(path.read_text())
    item = json.loads(paths[0].read_text())
    item["metrics"] = {"bad": float("nan")}
    with pytest.raises(ValidationError, match="finite"):
        BenchmarkArtifact.model_validate(item)
    with TestClient(app) as client:
        response = client.get("/api/benchmarks")
        assert response.status_code == 200
        assert response.json()["real_world"]["real_detection"]["data_provenance"] == "real"
        assert client.get("/api/benchmarks/real_tracking").status_code == 200
        assert client.get("/api/benchmarks/not_present").status_code == 404
        assert client.get("/api/benchmarks/bad.name").status_code == 422


def test_real_runner_skips_unprepared_data_without_download(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "real_runner", config.ROOT / "scripts" / "evaluate_real.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "EVALUATIONS", {"vision": ("vision", "evaluate_vision", tmp_path / "absent")}
    )
    monkeypatch.setattr("sys.argv", ["evaluate_real.py"])
    module.main()
    assert "SKIPPED vision" in capsys.readouterr().out


def test_local_archive_preparation_generates_verified_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_data, "DATASETS", tmp_path / "datasets")
    archives = tmp_path / "archives"
    archives.mkdir()
    for split, (name, _) in DETRAC_ARCHIVES.items():
        with zipfile.ZipFile(archives / name, "w") as bundle:
            for sequence in DETRAC_SEQUENCES[split]:
                folder = f"traffic/{sequence}/"
                bundle.writestr(folder, "")
                bundle.writestr(
                    folder + "annotations.csv",
                    "filename,width,height,class,xmin,ymin,xmax,ymax,target_id\nimg00001.jpg,40,40,vehicle,1,1,10,10,1\n",
                )
                bundle.writestr(folder + "img00001.jpg", b"fixture-member-for-extraction-only")
    manifest = dataset_data.prepare_detrac(1, 1, archives)
    assert len(manifest["splits"]["test"]) == 3
    assert len(manifest["splits"]["validation"]) == 2
    assert all(len(s["image_sha256"]["img00001.jpg"]) == 64 for s in manifest["splits"]["test"])
    root = dataset_data.DATASETS / "ua-detrac"
    name = DETRAC_SEQUENCES["test"][0]
    assert len(dataset_data.validated_detrac_frames(root, "test", name, manifest)) == 1
    (root / "test" / name / "img00001.jpg").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="image checksum"):
        dataset_data.validated_detrac_frames(root, "test", name, manifest)


def test_range_downloader_rejects_wrong_status_and_archive_size():
    remote = dataset_data.RemoteZip("https://fixture.test/archive", 10)
    remote.client.close()
    for status, total in [(200, 10), (206, 11)]:
        remote.client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request, status=status, total=total: httpx.Response(
                    status, headers={"content-range": f"bytes 0-2/{total}"}, content=b"abc"
                )
            )
        )
        with pytest.raises(ValueError, match="range"):
            remote.fetch(0, 2)
        remote.client.close()
    remote.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                206, headers={"content-range": "bytes 0-2/10"}, content=b"abc"
            )
        )
    )
    assert remote.read(3) == b"abc"
    remote.close()


def test_official_detection_metric_perfect_fixture():
    pytest.importorskip("pycocotools")
    from atlas.evaluation.vision import evaluate_detection

    frames = [
        {
            "frame": 1,
            "filename": "img00001.jpg",
            "width": 40,
            "height": 40,
            "objects": [{"id": 1, "bbox": [1, 1, 11, 11]}],
            "ignored": [],
        }
    ]
    gt, mapping = coco_ground_truth({"camera": frames})
    score = evaluate_detection(
        gt,
        [
            {
                "image_id": mapping[("camera", 1)],
                "category_id": 1,
                "bbox": [1, 1, 10, 10],
                "score": 0.99,
            }
        ],
    )
    assert score["map50"] == pytest.approx(1)
    assert score["map50_95"] == pytest.approx(1)
