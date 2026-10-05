"""Verify official evaluator against analytic cases; this is not tracking accuracy."""

import tempfile
from pathlib import Path

import numpy as np
from atlas.experiments import evaluate_mot

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    gt = np.array([[frame, 1, frame, 10, 5, 5, 1, 1, 1] for frame in range(1, 21)], dtype=float)
    pred = gt.copy()
    np.savetxt(folder / "gt.csv", gt, delimiter=",")
    np.savetxt(folder / "pred.csv", pred, delimiter=",")
    perfect = evaluate_mot(folder / "gt.csv", folder / "pred.csv", "tracking-metric-validation")
    assert perfect["metrics"]["HOTA"] == 1
    assert perfect["metrics"]["IDF1"] == 1
    assert perfect["metrics"]["MOTA"] == 1
    pred[10:, 1] = 2
    np.savetxt(folder / "pred.csv", pred, delimiter=",")
    switched = evaluate_mot(folder / "gt.csv", folder / "pred.csv", "tracking-metric-validation")
    switched["scope"] = (
        "Synthetic analytic evaluator checks, not tracking accuracy on footage. One known identity switch."
    )
    from atlas.experiments import save

    save("tracking-metric-validation", switched)
    assert switched["metrics"]["IDSW"] == 1
    assert switched["metrics"]["IDF1"] == 0.5
    print(
        "Official HOTA / CLEAR / Identity metrics verified; one identity switch lowers IDF1 to 0.5"
    )
