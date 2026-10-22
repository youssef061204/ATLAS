"""Research-only, post-hoc audit of the frozen CityFlow S01 and S03 runs.

This reads S03 labels that were already opened in ATLAS 7. Its output is a
failure-attribution diagnostic, not a new untouched holdout or candidate search.
Only aggregate counts are published; source media and identity labels stay local.
"""

import json
from pathlib import Path

import numpy as np
from atlas.multicamera_audit_v8 import audit_annotation_evidence
from cityflow_research_v7 import DATA, ROOT, load, sha


def main():
    frozen = json.loads((ROOT / "docs/cityflow-v7-frozen.json").read_text(encoding="utf-8"))
    for relative, digest in frozen["sources_sha256"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"Frozen CityFlow source changed: {relative}")
    publication = ROOT / "artifacts/reality/v8/cityflow-annotation-audit.json"
    if publication.exists():
        raise FileExistsError("Preserve first post-hoc audit result")
    scenes = {}
    for scene, relative in (
        ("S01", "data/reality-v7/cityflow-reid-S01/association-0.55.json"),
        (
            "S03",
            "data/reality-v7/cityflow-reid-S03/frozen-association-geometry_time_vehicle_reid.json",
        ),
    ):
        tracks, _, rois, metadata, _ = load(scene)
        association_path = ROOT / relative
        association = json.loads(association_path.read_text(encoding="utf-8"))
        if association.get("reference_identities_used") is not False:
            raise ValueError("Association was not made blind to reference identities")
        annotations = {
            camera: np.loadtxt(DATA / f"train/{scene}/{camera}/gt/gt.txt", delimiter=",", ndmin=2)
            for camera in metadata
        }
        result = audit_annotation_evidence(
            tracks,
            rois,
            metadata,
            annotations,
            association["accepted"],
            padding=frozen["selected_padding_px_per_edge"],
        )
        if scene == "S03":
            historical = json.loads(
                (ROOT / "artifacts/reality/v7/cityflow-S03-frozen-results.json").read_text(
                    encoding="utf-8"
                )
            )
            selected = next(
                row
                for row in historical["candidates"]
                if row["method"] == historical["selected_config"]["method"]
                and row["annotation_padding_px_per_edge"] == frozen["selected_padding_px_per_edge"]
            )
            if (
                result["totals"]["predicted_boxes"] != selected["result"]["predicted_boxes"]
                or result["totals"]["annotated_boxes"] != selected["result"]["annotated_boxes"]
                or sum(result["accepted_link_audit"]["all"].values()) != selected["accepted_links"]
            ):
                raise ValueError("Audit cohort differs from frozen S03 primary evaluation")
        scenes[scene] = {
            **result,
            "association_sha256": sha(association_path),
            "source_gt_sha256": {
                camera: sha(DATA / f"train/{scene}/{camera}/gt/gt.txt") for camera in metadata
            },
        }
    report = {
        "purpose": "Post-hoc error attribution of existing v7 results; S03 is already opened and cannot be used to choose a new association model or claim a fresh test",
        "unchanged_primary_metric": "TrackEval IDF1 with all original prediction boxes; see frozen v7 results",
        "scope": "Only officially annotated multi-camera vehicles have reference identities; other actual vehicles can be present in video",
        "matching": "One-to-one per-frame IoU >= 0.5 after frozen 10-px annotation-convention padding; raw ROI eligibility unchanged",
        "link_verification": "Both endpoint tracklets require >=3 matched boxes and >=80% dominant reference identity; unverifiable links stay separate",
        "interpretation": "Prediction annotation-match fraction is not detector precision: unlabeled vehicles can be correct detections",
        "v7_freeze_sha256": sha(ROOT / "docs/cityflow-v7-frozen.json"),
        "source_sha256": sha(Path(__file__)),
        "scenes": scenes,
        "media_or_reference_identities_redistributed": False,
    }
    publication.parent.mkdir(parents=True, exist_ok=True)
    publication.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(publication),
                "scenes": {
                    scene: {
                        "totals": row["totals"],
                        "accepted_link_audit": row["accepted_link_audit"],
                        "accepted_link_kinds": row["accepted_link_kinds"],
                    }
                    for scene, row in scenes.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
