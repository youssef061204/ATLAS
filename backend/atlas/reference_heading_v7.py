"""Past-only reference heading, with all four NGSIM cardinal directions.

This corrects a pre-test evaluator fallback, not the detector or calibration.
"""

import numpy as np


def cardinal_heading(directions, past_displacement):
    directions = np.asarray(directions)
    if not np.isin(directions, [1, 2, 3, 4]).all():
        raise ValueError("Unknown NGSIM cardinal direction")
    lookup = np.array([[0, 0], [1, 0], [0, 1], [-1, 0], [0, -1]], dtype=float)
    heading = lookup[directions.astype(int)].copy()
    past = np.asarray(past_displacement, dtype=float)
    norms = np.linalg.norm(past, axis=1)
    valid = np.isfinite(norms) & (norms > 3.0)
    heading[valid] = past[valid] / norms[valid, None]
    return heading
