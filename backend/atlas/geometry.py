import cv2
import numpy as np

from .schemas import Calibration, Region


class Projection:
    def __init__(self, calibration: Calibration | None):
        self.matrix = None
        self.verified = bool(calibration and calibration.verified)
        if calibration:
            source = np.array(calibration.image, dtype=np.float64)
            target = np.array(calibration.world, dtype=np.float64)
            if np.linalg.matrix_rank(source - source.mean(axis=0)) < 2:
                raise ValueError("Calibration image points are collinear")
            if np.linalg.matrix_rank(target - target.mean(axis=0)) < 2:
                raise ValueError("Calibration world points are collinear")
            self.matrix, _ = cv2.findHomography(source, target, method=0)
            if self.matrix is None or not np.isfinite(self.matrix).all():
                raise ValueError("Could not solve calibration homography")
            if np.linalg.cond(self.matrix) > 1e12:
                raise ValueError("Calibration is numerically unstable")

    def point(self, x: float, y: float):
        if self.matrix is None:
            return [x, y]
        value = self.matrix @ np.array([x, y, 1])
        if abs(value[2]) < 1e-8:
            raise ValueError("Point projects to infinity; revise calibration")
        return (value[:2] / value[2]).tolist()


def contains(region: Region, point):
    return (
        cv2.pointPolygonTest(np.array(region.polygon, dtype=np.float32), tuple(point), False) >= 0
    )


def heading_direction(vx: float, vy: float):
    if abs(vx) > abs(vy):
        return "E" if vx > 0 else "W"
    return "S" if vy > 0 else "N"


def motion(points, coordinate="world"):
    """Least-squares motion over the last 0.75 s; timestamps account for frame sampling."""
    if len(points) < 3:
        return 0.0, 0.0
    recent = [p for p in points[-12:] if p["t"] >= points[-1]["t"] - 0.75]
    if len(recent) < 3:
        recent = points[-3:]
    times = np.array([p["t"] for p in recent])
    centered = times - times.mean()
    denominator = float(centered @ centered)
    if denominator < 1e-8:
        return 0.0, 0.0
    xy = np.array([p[coordinate] for p in recent])
    velocity = centered @ (xy - xy.mean(axis=0)) / denominator
    return float(velocity[0]), float(velocity[1])
