"""Develop on S01; score S03 only after exact association/annotation freeze."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from atlas.multicamera_metrics_v7 import evaluate
from atlas.multicamera_reid_v7 import associate
from atlas.multicamera_v7 import associate_geometry
from cityflow_research_v7 import DATA, ROOT, appearances, load, sha


def main():
    cv2.setNumThreads(1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=["S01", "S03"], required=True)
    args = parser.parse_args()
    frozen = None
    if args.scene == "S03":
        frozen = json.loads((ROOT / "docs/cityflow-v7-frozen.json").read_text())
        for path, digest in frozen["sources_sha256"].items():
            if sha(ROOT / path) != digest:
                raise ValueError(f"Frozen source changed: {path}")
    out = ROOT / f"data/reality-v7/cityflow-{args.scene}-candidates"
    out.mkdir(parents=True, exist_ok=True)
    publication_path = ROOT / f"artifacts/reality/v7/cityflow-{args.scene}-results.json"
    if publication_path.exists():
        raise FileExistsError("Preserve completed benchmark")
    tracks, geometry, rois, metadata, records = load(args.scene)
    features = appearances(args.scene, tracks, metadata)
    baseline = {(t["camera"], t["id"]): i + 1 for i, t in enumerate(tracks)}
    configs = [
        {"method": "independent", "appearance_gate": None},
        {"method": "geometric_overlap", "appearance_gate": None},
    ]
    configs += (
        [{"method": "geometry_time_color", "appearance_gate": gate} for gate in [0.85, 0.9, 0.95]]
        if frozen is None
        else [frozen["selected_config"]]
    )
    configs = [dict(t) for t in {json.dumps(t, sort_keys=True): t for t in configs}.values()]
    mappings, links, diagnostics = {}, {}, {}
    for config in configs:
        key = json.dumps(config, sort_keys=True)
        method = config["method"]
        if method == "independent":
            mapping, accepted, diagnostic = baseline, [], {}
        elif method == "geometric_overlap":
            mapping, accepted, diagnostic = associate_geometry(geometry)
        else:
            mapping, accepted, diagnostic = associate(
                geometry, features, appearance_gate=config["appearance_gate"]
            )
        # Freeze identity decisions before loading any reference boxes/identities.
        record = {
            "config": config,
            "mapping": [
                [camera, identity, global_id] for (camera, identity), global_id in mapping.items()
            ],
            "accepted": accepted,
            "diagnostics": diagnostic,
            "reference_identities_used": False,
        }
        local = out / f"association-{len(mappings)}.json"
        local.write_bytes(json.dumps(record, indent=2).encode())
        mappings[key], links[key], diagnostics[key] = mapping, accepted, diagnostic
    # First reference-label read. S03 is unreachable without a valid freeze.
    annotations = {
        camera: np.loadtxt(DATA / f"train/{args.scene}/{camera}/gt/gt.txt", delimiter=",", ndmin=2)
        for camera in metadata
    }
    candidates = []
    paddings = (
        [0, 10, 20] if frozen is None else sorted({0, frozen["selected_padding_px_per_edge"]})
    )
    for config in configs:
        key = json.dumps(config, sort_keys=True)
        for padding in paddings:
            result = evaluate(tracks, mappings[key], rois, metadata, annotations, padding=padding)
            candidates.append(
                {
                    "config": config,
                    "annotation_padding_px_per_edge": padding,
                    "accepted_links": len(links[key]),
                    "diagnostics": diagnostics[key],
                    "result": result,
                }
            )
            print(
                json.dumps(
                    {
                        "scene": args.scene,
                        "config": config,
                        "padding": padding,
                        "links": len(links[key]),
                        "idf1": result["identity"]["IDF1"],
                        "predicted_boxes": result["predicted_boxes"],
                    }
                ),
                flush=True,
            )
    if frozen is None:
        selected = min(
            candidates,
            key=lambda row: (
                -row["result"]["identity"]["IDF1"],
                row["accepted_links"],
                row["annotation_padding_px_per_edge"],
            ),
        )
        config, padding = selected["config"], selected["annotation_padding_px_per_edge"]
    else:
        config, padding = frozen["selected_config"], frozen["selected_padding_px_per_edge"]
        selected = next(
            row
            for row in candidates
            if row["config"] == config and row["annotation_padding_px_per_edge"] == padding
        )
    key = json.dumps(config, sort_keys=True)
    cameras = defaultdict(set)
    for (camera, _), identity in mappings[key].items():
        cameras[identity].add(camera)
    selected_multicamera = {identity for identity, sources in cameras.items() if len(sources) >= 2}
    filtered = evaluate(
        tracks,
        mappings[key],
        rois,
        metadata,
        annotations,
        padding=padding,
        selected=selected_multicamera,
    )
    artifact = {
        "scene": args.scene,
        "split": "development selection"
        if frozen is None
        else "frozen locally held-out camera/intersection group",
        "candidate_tracklets": len(tracks),
        "total_decoded_and_processed_frames": sum(
            r["performance"]["processed_frames"] for r in records
        ),
        "camera_runs": [
            {
                **r,
                "performance": {
                    **r["performance"],
                    "model": r["performance"]["model"].replace(chr(92), "/").split("/")[-1],
                },
            }
            for r in records
        ],
        "candidates": candidates,
        "selected": selected,
        "multicamera_filtered_changed_cohort": filtered,
        "source_sha256": sha(Path(__file__)),
        "protocol_sha256": sha(ROOT / "docs/cityflow-v7-protocol.json"),
        "scope": "Actual complete videos; local noncommercial research, aggregate publication only. No CityFlow detector training. S01/S03 are both in Dubuque, not cross-city validation or an official leaderboard submission.",
        "limitations": [
            "Only multi-camera vehicles are annotated; not all visible vehicle ground truth",
            "Annotation padding changes IoU convention, not measured physical localization",
            "HSV/Lab color descriptors are not a trained vehicle-ReID network",
            "Source synchronization and manual homographies have unquantified uncertainty",
            "Filtered results change the predicted cohort and must be separate",
            "No source media, crops, appearance descriptors or GPS trajectories redistributed",
        ],
    }
    publication_path.write_bytes(json.dumps(artifact, indent=2).encode())
    print(
        json.dumps(
            {
                "selected_config": config,
                "selected_padding_px_per_edge": padding,
                "selected_idf1": selected["result"]["identity"]["IDF1"],
                "filtered_separate_idf1": filtered["identity"]["IDF1"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
