"""S01-only vehicle ReID development ablation; S03 remains inaccessible here."""

import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from atlas.multicamera_metrics_v7 import evaluate
from atlas.multicamera_reid_v7 import associate
from cityflow_reid_features_v7 import extract
from cityflow_research_v7 import DATA, ROOT, load, sha


def main():
    cv2.setNumThreads(1)
    publication = ROOT / "artifacts/reality/v7/cityflow-S01-reid-results.json"
    if publication.exists():
        raise FileExistsError("Preserve vehicle ReID development results")
    tracks, geometry, rois, metadata, records = load("S01")
    features = extract("S01", tracks, metadata)
    feature_directory = ROOT / "data/reality-v7/cityflow-reid-S01"
    feature_record = json.loads((feature_directory / "run.json").read_text())
    if sha(feature_directory / "features.npz") != feature_record["features_sha256"]:
        raise ValueError("Corrupt appearance descriptors")
    expected = {(t["camera"], t["id"]) for t in tracks}
    if not set(features) <= expected:
        raise ValueError("Descriptors belong to a different set of source tracks")
    maps, accepted, diagnostics = {}, {}, {}
    for gate in [0.55, 0.65, 0.75, 0.85, 0.95]:
        maps[gate], accepted[gate], diagnostics[gate] = associate(
            geometry, features, appearance_gate=gate
        )
        local = {
            "appearance_gate": gate,
            "model_sha256": feature_record["model_sha256"],
            "reference_identities_used": False,
            "mapping": [
                [camera, identity, global_id]
                for (camera, identity), global_id in maps[gate].items()
            ],
            "accepted": accepted[gate],
            "diagnostics": diagnostics[gate],
        }
        (feature_directory / f"association-{gate}.json").write_bytes(
            json.dumps(local, indent=2).encode()
        )
    # Only S01 development references can be loaded by this program.
    annotations = {
        camera: np.loadtxt(DATA / f"train/S01/{camera}/gt/gt.txt", delimiter=",", ndmin=2)
        for camera in metadata
    }
    candidates = []
    for gate in maps:
        for padding in [0, 10]:
            result = evaluate(tracks, maps[gate], rois, metadata, annotations, padding=padding)
            record = {
                "config": {"method": "geometry_time_vehicle_reid", "appearance_gate": gate},
                "annotation_padding_px_per_edge": padding,
                "accepted_links": len(accepted[gate]),
                "diagnostics": diagnostics[gate],
                "result": result,
            }
            candidates.append(record)
            print(
                json.dumps(
                    {
                        "appearance_gate": gate,
                        "padding": padding,
                        "accepted_links": len(accepted[gate]),
                        "idf1": result["identity"]["IDF1"],
                    }
                ),
                flush=True,
            )
    selected = min(
        [r for r in candidates if r["annotation_padding_px_per_edge"] == 10],
        key=lambda r: (-r["result"]["identity"]["IDF1"], r["accepted_links"]),
    )
    gate = selected["config"]["appearance_gate"]
    camera_groups = defaultdict(set)
    for (camera, _), identity in maps[gate].items():
        camera_groups[identity].add(camera)
    multicamera = {identity for identity, cameras in camera_groups.items() if len(cameras) >= 2}
    filtered = evaluate(
        tracks, maps[gate], rois, metadata, annotations, padding=10, selected=multicamera
    )
    artifact = {
        "scene": "S01",
        "split": "Development only; no S03 outcomes read",
        "candidate_tracklets": len(tracks),
        "model": "Pretrained OSNet-AIN vehicle-reid-0001, 512-dimensional vehicle-specific descriptors",
        "feature_model_sha256": feature_record["model_sha256"],
        "actual_crop_samples": feature_record["actual_crop_samples"],
        "decoded_source_frames": feature_record["decoded_source_frames"],
        "candidates": candidates,
        "selected": selected,
        "multicamera_filtered_changed_cohort": filtered,
        "source_sha256": sha(Path(__file__)),
        "feature_source_sha256": sha(ROOT / "scripts/cityflow_reid_features_v7.py"),
        "protocol_sha256": sha(ROOT / "docs/cityflow-v7-protocol.json"),
        "input_result_sha256": {r["camera"]: r["result_sha256"] for r in records},
        "scope": "New learned vehicle-descriptor ablation with the same detection cohort and geometric/time gates. Annotation padding remains a separate convention adjustment. No CityFlow training, no raw data/crops/embeddings published. Do not transfer vendor benchmark accuracy to ATLAS.",
    }
    publication.write_bytes(json.dumps(artifact, indent=2).encode())
    print(
        json.dumps(
            {
                "selected": selected["config"],
                "development_idf1": selected["result"]["identity"]["IDF1"],
                "filtered_different_cohort": filtered["identity"]["IDF1"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
