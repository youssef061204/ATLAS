"""Finite virtual-gate counting for verified continuous video, never snapshots."""

from collections import Counter

import numpy as np


class CrossingCounter:
    def __init__(self, start, end, deadband=0.005, max_gap_seconds=0.2):
        self.start, self.end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
        if (
            self.start.shape != (2,)
            or self.end.shape != (2,)
            or not np.all(np.isfinite([self.start, self.end]))
        ):
            raise ValueError("Gate requires two finite normalized image points")
        self.delta = self.end - self.start
        self.length = float(np.linalg.norm(self.delta))
        if self.length < 0.01 or deadband < 0 or max_gap_seconds <= 0:
            raise ValueError("Invalid gate geometry or continuity limit")
        self.deadband, self.max_gap = deadband, max_gap_seconds
        self.states = {}
        self.counts = Counter()
        self.time = None

    def update(self, t, objects, continuous=True):
        if not continuous:
            raise ValueError(
                "Crossing counts require verified continuous video; snapshots are unsupported"
            )
        if not np.isfinite(t) or self.time is not None and t <= self.time:
            raise ValueError("Video timestamps must be finite and strictly increasing")
        self.time = t
        events = []
        if len({o["id"] for o in objects}) != len(objects):
            raise ValueError("Duplicate track IDs in one frame")
        for obj in objects:
            point = np.asarray(obj["point"], dtype=float)
            if point.shape != (2,) or not np.all(np.isfinite(point)):
                raise ValueError("Invalid tracked image point")
            relative = point - self.start
            distance = (
                float(self.delta[0] * relative[1] - self.delta[1] * relative[0]) / self.length
            )
            side = 1 if distance > self.deadband else -1 if distance < -self.deadband else 0
            previous = self.states.get(obj["id"])
            if previous and t - previous["last_seen"] > self.max_gap:
                previous = None
            state = previous or {"last_seen": t, "side": 0, "point": point, "counted": set()}
            if side and state["side"] and side != state["side"]:
                # Intersection with the finite gate, not its infinite extension.
                a = state["point"]
                b = point
                before = float(
                    self.delta[0] * (a - self.start)[1] - self.delta[1] * (a - self.start)[0]
                )
                after = float(
                    self.delta[0] * (b - self.start)[1] - self.delta[1] * (b - self.start)[0]
                )
                intersection = a + (b - a) * before / (before - after)
                position = float((intersection - self.start) @ self.delta) / (self.length**2)
                direction = "positive" if side > 0 else "negative"
                if 0 <= position <= 1 and direction not in state["counted"]:
                    state["counted"].add(direction)
                    self.counts[direction] += 1
                    events.append({"track_id": obj["id"], "direction": direction, "t": float(t)})
            if side:
                state.update(side=side, point=point)
            state["last_seen"] = t
            self.states[obj["id"]] = state
        # Forget terminated tracks; memory is bounded by a short continuity window.
        self.states = {
            key: state
            for key, state in self.states.items()
            if t - state["last_seen"] <= self.max_gap
        }
        return events


def analyze_tracks(frames, width, height, fps, start, end):
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("Verified dimensions and video cadence required")
    counter = CrossingCounter(start, end)
    events = []
    for i, objects in enumerate(frames):
        events.extend(
            counter.update(
                i / fps,
                [
                    {
                        "id": o["id"],
                        "point": [(o["bbox"][0] + o["bbox"][2]) / 2 / width, o["bbox"][3] / height],
                    }
                    for o in objects
                ],
            )
        )
    return events
