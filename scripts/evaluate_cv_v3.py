"""New detector/tracker experiment; historical CV evidence remains unchanged."""

import hashlib
import json
from pathlib import Path

from atlas import config
from atlas.evaluation.vision import evaluate_vision


def main():
    protocol = Path("docs/cv-v3-protocol.json")
    settings = json.loads(protocol.read_text(encoding="utf-8"))
    path = Path("yolo26n.pt")
    if hashlib.sha256(path.read_bytes()).hexdigest() != settings["weight_sha256"]:
        raise ValueError("Candidate checkpoint differs from registered protocol")
    config.MODEL = str(path.resolve())
    config.ARTIFACTS = config.ROOT / "artifacts/cv-v3"
    config.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = evaluate_vision(
        split="test",
        resolution=settings["resolution"],
        confidence=settings["precision_recall_confidence"],
        variant="yolo26n-v3",
    )
    config.ARTIFACTS.joinpath("experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": settings["experiment_id"],
                "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
                "results": results,
                "historical_evidence_modified": False,
            },
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    print("CV candidate evaluated", results, flush=True)


if __name__ == "__main__":
    main()
