"""Freeze the S01-selected vehicle association before any S03 scoring."""

import json
import zipfile
from datetime import UTC, datetime

from cityflow_research_v7 import ROOT, sha


def main():
    destination = ROOT / "docs/cityflow-v7-frozen.json"
    if destination.exists():
        raise FileExistsError("Never replace an association freeze")
    learned = json.loads((ROOT / "artifacts/reality/v7/cityflow-S01-reid-results.json").read_text())
    color = json.loads((ROOT / "artifacts/reality/v7/cityflow-S01-results.json").read_text())
    chosen = learned["selected"]
    if chosen["result"]["identity"]["IDF1"] <= color["selected"]["result"]["identity"]["IDF1"]:
        raise ValueError("This freeze requires the development winner to be learned ReID")
    files = [
        "scripts/evaluate_cityflow_holdout_v7.py",
        "scripts/cityflow_reid_features_v7.py",
        "scripts/cityflow_research_v7.py",
        "scripts/freeze_cityflow_v7.py",
        "backend/atlas/multicamera_v7.py",
        "backend/atlas/multicamera_reid_v7.py",
        "backend/atlas/multicamera_metrics_v7.py",
        "docs/cityflow-v7-protocol.json",
        "artifacts/reality/v7/cityflow-S01-results.json",
        "artifacts/reality/v7/cityflow-S01-reid-results.json",
        "artifacts/reality/v7/vehicle-reid-model-source.json",
    ]
    archive = ROOT / "artifacts/reality/v7/cityflow-frozen-source.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as handle:
        for file in files:
            handle.write(ROOT / file, file)
    record = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "S03_reference_outcomes_read": False,
        "selected_config": chosen["config"],
        "selected_padding_px_per_edge": chosen["annotation_padding_px_per_edge"],
        "S01_same_cohort_development_idf1": chosen["result"]["identity"]["IDF1"],
        "S01_color_development_idf1": color["selected"]["result"]["identity"]["IDF1"],
        "sources_sha256": {file: sha(ROOT / file) for file in files},
        "archive": archive.relative_to(ROOT).as_posix(),
        "archive_sha256": sha(archive),
        "selection_scope": "S01 only. S03 reports independent, geometry-only and the single selected learned association at 0 and selected annotation padding; never optimize on test results.",
    }
    destination.write_bytes(json.dumps(record, indent=2).encode())
    print(json.dumps({k: v for k, v in record.items() if k != "sources_sha256"}, indent=2))


if __name__ == "__main__":
    main()
