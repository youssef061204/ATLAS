"""Evaluate the single frozen S01-selected association on all six S03 videos.

Raw and annotation-aligned scores share exactly the same observations. Reference
identities are read only after all three association maps have been written.
"""

import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from atlas.multicamera_metrics_v7 import evaluate
from atlas.multicamera_reid_v7 import associate
from atlas.multicamera_v7 import associate_geometry
from cityflow_reid_features_v7 import extract
from cityflow_research_v7 import DATA, ROOT, load, sha


def main():
    cv2.setNumThreads(1)
    frozen = json.loads((ROOT / "docs/cityflow-v7-frozen.json").read_text())
    for path, digest in frozen["sources_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError(f"Frozen source changed: {path}")
    publication = ROOT / "artifacts/reality/v7/cityflow-S03-frozen-results.json"
    if publication.exists():
        raise FileExistsError("Preserve first held-out result")
    tracks, geometry, rois, metadata, records = load("S03")
    if sum(m["frame_count"] for m in metadata.values()) != 13517 or len(metadata) != 6:
        raise ValueError("All six complete S03 source videos are mandatory")
    features = extract("S03", tracks, metadata)
    directory = ROOT / "data/reality-v7/cityflow-reid-S03"
    feature_record = json.loads((directory / "run.json").read_text())
    if sha(directory / "features.npz") != feature_record["features_sha256"]:
        raise ValueError("Corrupt held-out descriptors")
    methods = {}
    methods["independent"] = ({(t["camera"], t["id"]): i + 1 for i, t in enumerate(tracks)}, [], {})
    methods["geometric_overlap"] = associate_geometry(geometry)
    methods["geometry_time_vehicle_reid"] = associate(
        geometry, features, appearance_gate=frozen["selected_config"]["appearance_gate"]
    )
    for method, (mapping, links, diagnostic) in methods.items():
        record = {
            "method": method,
            "mapping": [
                [camera, identity, global_id] for (camera, identity), global_id in mapping.items()
            ],
            "accepted": links,
            "diagnostics": diagnostic,
            "reference_identities_used": False,
            "freeze_sha256": sha(ROOT / "docs/cityflow-v7-frozen.json"),
        }
        (directory / f"frozen-association-{method}.json").write_bytes(
            json.dumps(record, indent=2).encode()
        )
    # First held-out annotation read: no subsequent model/threshold selection.
    annotations = {
        camera: np.loadtxt(DATA / f"train/S03/{camera}/gt/gt.txt", delimiter=",", ndmin=2)
        for camera in metadata
    }
    candidates = []
    for method, (mapping, links, diagnostic) in methods.items():
        for padding in [0, frozen["selected_padding_px_per_edge"]]:
            result = evaluate(tracks, mapping, rois, metadata, annotations, padding=padding)
            row = {
                "method": method,
                "annotation_padding_px_per_edge": padding,
                "accepted_links": len(links),
                "diagnostics": diagnostic,
                "result": result,
            }
            candidates.append(row)
            print(
                json.dumps(
                    {
                        "method": method,
                        "padding": padding,
                        "idf1": result["identity"]["IDF1"],
                        "predicted_boxes": result["predicted_boxes"],
                    }
                ),
                flush=True,
            )
    chosen = frozen["selected_config"]["method"]
    mapping, links, _ = methods[chosen]
    cameras = defaultdict(set)
    for (camera, _), identity in mapping.items():
        cameras[identity].add(camera)
    selected = {identity for identity, group in cameras.items() if len(group) >= 2}
    filtered = evaluate(
        tracks,
        mapping,
        rois,
        metadata,
        annotations,
        padding=frozen["selected_padding_px_per_edge"],
        selected=selected,
    )
    expected_counts = {r["result"]["predicted_boxes"] for r in candidates}
    if len(expected_counts) != 1:
        raise ValueError("Association/padding changed the primary observation cohort")
    report = {
        "scene": "S03",
        "split": "Frozen locally held-out Dubuque intersection/camera group, not cross-city or official challenge evaluation",
        "total_decoded_and_processed_frames": sum(
            r["performance"]["processed_frames"] for r in records
        ),
        "candidate_tracklets": len(tracks),
        "candidates": candidates,
        "selected_config": frozen["selected_config"],
        "selected_padding_px_per_edge": frozen["selected_padding_px_per_edge"],
        "multicamera_filtered_changed_cohort": filtered,
        "camera_runs": [
            {
                "camera": r["camera"],
                "metadata": r["metadata"],
                "source_sha256": r["source_sha256"],
                "result_sha256": r["result_sha256"],
                "calibration_sha256": r["calibration_sha256"],
            }
            for r in records
        ],
        "feature_samples": feature_record["actual_crop_samples"],
        "feature_source_sha256": feature_record["source_sha256"],
        "feature_model_sha256": feature_record["model_sha256"],
        "freeze_sha256": sha(ROOT / "docs/cityflow-v7-frozen.json"),
        "source_sha256": sha(Path(__file__)),
        "limitations": [
            "Pretrained detector and vehicle ReID; no dataset-specific training",
            "Annotation padding is a convention adjustment, not improved physical localization",
            "Only multi-camera vehicles are annotated; unmatched single-camera predictions remain false positives in the primary denominator",
            "Filtered result changes the prediction cohort and is never a same-detection improvement",
            "Provided homographies and incomplete camera synchronization have unquantified errors",
            "Noncommercial local research only; no raw video, crops, embeddings, GPS or source annotations redistributed",
        ],
    }
    publication.write_bytes(json.dumps(report, indent=2).encode())
    print(
        json.dumps(
            {
                "complete": True,
                "output": str(publication),
                "filtered_changed_cohort_idf1": filtered["identity"]["IDF1"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
