"""Operator geometry and continuous-video queue estimates with explicit calibration gaps."""

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


def polygon_contains(point, polygon):
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


class SceneRegion(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    city: str
    camera_id: str
    observation_id: str
    road_id: str
    name: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern="^(road_region|approach_lane|crosswalk)$", default="road_region")
    polygon: list[list[float]] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def geometry(self):
        points = np.asarray(self.polygon)
        if points.shape != (len(self.polygon), 2) or np.any(points < 0) or np.any(points > 1):
            raise ValueError("Region points must be normalized image coordinates in [0,1]")
        area = (
            abs(
                np.sum(
                    points[:, 0] * np.roll(points[:, 1], -1)
                    - points[:, 1] * np.roll(points[:, 0], -1)
                )
            )
            / 2
        )
        if area < 0.001:
            raise ValueError("Region must have nonzero usable area")

        # Reject crossing non-adjacent edges; geometry corrections stay inspectable.
        def cross(a, b, c):
            return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))

        for i in range(len(points)):
            a, b = points[i], points[(i + 1) % len(points)]
            for j in range(i + 1, len(points)):
                if j in {i, (i + 1) % len(points)} or (j + 1) % len(points) == i:
                    continue
                c, d = points[j], points[(j + 1) % len(points)]
                if np.any(
                    np.maximum(np.minimum(a, b), np.minimum(c, d))
                    > np.minimum(np.maximum(a, b), np.maximum(c, d))
                ):
                    continue
                if cross(a, b, c) * cross(a, b, d) <= 0 and cross(c, d, a) * cross(c, d, b) <= 0:
                    raise ValueError("Region cannot self-intersect")
        return self


def assign_detections(region, detections):
    return [
        d
        for d in detections
        if polygon_contains(
            [(d["box_normalized"][0] + d["box_normalized"][2]) / 2, d["box_normalized"][3]],
            region.polygon,
        )
    ]


def region_observation(region, observation, revision):
    from collections import Counter

    detections = assign_detections(region, observation.get("detections", []))
    return {
        **observation,
        "counts": dict(Counter(d["class"] for d in detections)),
        "detections": detections,
        "counts_before_region": observation.get("counts", {}),
        "operator_region_revision": revision,
        "operator_region": region.model_dump(),
        "count_scope": "Observed detection bottom centers inside the operator region; lane mapping not independently validated",
    }


class PlanarCalibration:
    def __init__(self, image_points, world_points_m):
        image, world = (
            np.asarray(image_points, dtype=float),
            np.asarray(world_points_m, dtype=float),
        )
        if (
            image.shape != world.shape
            or image.ndim != 2
            or image.shape[1] != 2
            or len(image) < 4
            or not np.all(np.isfinite([image, world]))
        ):
            raise ValueError("Four or more finite paired image/world points required")
        if (
            np.linalg.matrix_rank(np.c_[image, np.ones(len(image))]) < 3
            or np.linalg.matrix_rank(np.c_[world, np.ones(len(world))]) < 3
        ):
            raise ValueError("Calibration points must span a plane")
        rows, targets = [], []
        for (x, y), (u, v) in zip(image, world, strict=True):
            rows.extend([[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]])
            targets.extend([u, v])
        matrix = np.asarray(rows)
        if np.linalg.matrix_rank(matrix) < 8 or np.linalg.cond(matrix) > 1e10:
            raise ValueError("Degenerate or ill-conditioned calibration")
        self.matrix = np.r_[np.linalg.lstsq(matrix, targets, rcond=None)[0], 1].reshape(3, 3)
        self.training_error_m = float(np.linalg.norm(self.project(image) - world, axis=1).mean())
        self.status = "operator_supplied_not_independently_validated"

    def project(self, points):
        p = np.asarray(points, dtype=float)
        if p.ndim != 2 or p.shape[1] != 2 or not np.all(np.isfinite(p)):
            raise ValueError("Finite image-plane points required")
        homogeneous = np.c_[p, np.ones(len(p))] @ self.matrix.T
        if np.any(np.abs(homogeneous[:, 2]) < 1e-8):
            raise ValueError("Point lies at the calibration horizon")
        return homogeneous[:, :2] / homogeneous[:, 2:]

    def holdout(self, image_points, world_points_m):
        predicted = self.project(image_points)
        truth = np.asarray(world_points_m)
        if truth.shape != predicted.shape or len(truth) < 2 or not np.all(np.isfinite(truth)):
            raise ValueError("At least two independent finite surveyed holdout points required")
        return {
            "mean_error_m": float(np.linalg.norm(predicted - truth, axis=1).mean()),
            "points": len(truth),
            "scope": "Operator-supplied independent correspondence errors; ATLAS cannot attest survey provenance",
        }


class VisualQueueEstimator:
    def __init__(
        self, polygon, calibration, stop_line_world_m, stopped_speed_m_s=0.5, dwell_seconds=2
    ):
        self.polygon, self.calibration = polygon, calibration
        self.stop_line = np.asarray(stop_line_world_m, dtype=float)
        if (
            self.stop_line.shape != (2, 2)
            or not np.all(np.isfinite(self.stop_line))
            or np.linalg.norm(self.stop_line[1] - self.stop_line[0]) < 0.1
        ):
            raise ValueError("Finite physical stop line required")
        self.speed, self.dwell = stopped_speed_m_s, dwell_seconds
        self.tracks = {}
        self.time = None

    def update(self, t, objects, continuous=True):
        if not continuous:
            raise ValueError(
                "Queue motion classification requires continuous video; snapshot counts are not queues"
            )
        if not np.isfinite(t) or self.time is not None and t <= self.time:
            raise ValueError("Finite increasing video timestamps required")
        self.time = t
        queued = []
        classes = {"stopped": 0, "slow": 0, "flowing": 0, "motion_unavailable": 0}
        if len({o["id"] for o in objects}) != len(objects):
            raise ValueError("Unique IDs required per frame")
        for obj in objects:
            if not polygon_contains(obj["point"], self.polygon):
                continue
            position = self.calibration.project([obj["point"]])[0]
            previous = self.tracks.get(obj["id"])
            if previous is None or t - previous["t"] > 0.2:
                stopped_since = None
                classes["motion_unavailable"] += 1
            else:
                speed = float(np.linalg.norm(position - previous["position"]) / (t - previous["t"]))
                stopped_since = (
                    previous["stopped_since"]
                    if previous["stopped_since"] is not None
                    else previous["t"]
                )
                if speed <= self.speed:
                    classes["stopped"] += 1
                    if t - stopped_since >= self.dwell:
                        queued.append(position)
                else:
                    stopped_since = None
                    classes["slow" if speed <= 2 else "flowing"] += 1
            self.tracks[obj["id"]] = {"t": t, "position": position, "stopped_since": stopped_since}
        self.tracks = {k: v for k, v in self.tracks.items() if t - v["t"] <= 0.2}
        direction = self.stop_line[1] - self.stop_line[0]
        normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
        extent = max((abs(float((p - self.stop_line[0]) @ normal)) for p in queued), default=0.0)
        return {
            "queue_candidate_vehicles": len(queued),
            "queue_candidate_extent_m": extent,
            "motion_classes": classes,
            "calibration_status": self.calibration.status,
            "field_validated": False,
            "scope": "Continuous track bottom centers in operator lane ROI; stationary dwell plus operator planar calibration. Not independently annotated queue validation.",
        }
