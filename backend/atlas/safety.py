from itertools import combinations

import numpy as np

from .db import uid


def closest_approach(position_a, velocity_a, position_b, velocity_b, horizon=5):
    relative_position = np.asarray(position_b) - np.asarray(position_a)
    relative_velocity = np.asarray(velocity_b) - np.asarray(velocity_a)
    vv = float(relative_velocity @ relative_velocity)
    t = float(-relative_position @ relative_velocity / vv) if vv > 1e-8 else 0
    projected_t = min(max(t, 0), horizon)
    separation = float(np.linalg.norm(relative_position + relative_velocity * projected_t))
    return t, separation, float(np.linalg.norm(relative_velocity))


def risk_features(a, b, ttc, separation, relative_speed, density):
    av, bv = np.array(a["velocity"]), np.array(b["velocity"])
    denominator = max(float(np.linalg.norm(av) * np.linalg.norm(bv)), 1e-8)
    angle = float(np.arccos(np.clip(float(av @ bv) / denominator, -1, 1)))
    vulnerable = int(a["class"] in {"person", "bicycle"} or b["class"] in {"person", "bicycle"})
    return [
        min(max(ttc, 0), 10),
        separation,
        relative_speed,
        angle,
        vulnerable,
        min(a["acceleration"], b["acceleration"]),
        density,
    ]


def segment_pet(a0, a1, b0, b1):
    """Difference between interpolated times at a shared path crossing (center-point PET proxy)."""
    av = np.array(a1["world"]) - np.array(a0["world"])
    bv = np.array(b1["world"]) - np.array(b0["world"])
    matrix = np.column_stack((av, -bv))
    if abs(np.linalg.det(matrix)) < 1e-8:
        return None
    u, v = np.linalg.solve(matrix, np.array(b0["world"]) - np.array(a0["world"]))
    if not (0 <= u <= 1 and 0 <= v <= 1):
        return None
    ta = a0["t"] + float(u) * (a1["t"] - a0["t"])
    tb = b0["t"] + float(v) * (b1["t"] - b0["t"])
    return abs(ta - tb)


class SafetyEngine:
    def __init__(self, calibrated, model=None):
        self.calibrated = calibrated
        self.model = model
        self.events = []
        self.last_alert = {}
        self.previous = {}
        self.segments = []

    def update(self, t, objects):
        if not self.calibrated:
            return []
        emitted = []
        self.segments = [segment for segment in self.segments if t - segment[2]["t"] < 3]
        for obj in objects:
            current = {**obj, "t": t}
            previous = self.previous.get(obj["id"])
            if previous and 0 < t - previous["t"] < 1:
                for other_id, b0, b1 in self.segments:
                    if other_id == obj["id"]:
                        continue
                    pet = segment_pet(previous, current, b0, b1)
                    key = (*sorted((other_id, obj["id"])), "pet")
                    if (
                        pet is not None
                        and 0.05 < pet < 1.5
                        and t - self.last_alert.get(key, -100) > 5
                    ):
                        emitted.append(
                            {
                                "id": uid(),
                                "t": round(t, 3),
                                "participants": [other_id, obj["id"]],
                                "type": "path_encroachment",
                                "severity": "high" if pet < 0.5 else "medium",
                                "ttc": None,
                                "pet": round(pet, 3),
                                "separation": None,
                                "risk_score": round(1 - pet / 2, 3),
                                "ml_score": None,
                                "confidence": min(obj["confidence"], b1["confidence"]),
                                "explanation": f"Tracks {other_id} and {obj['id']} crossed the same path point {pet:.2f} s apart. Center-point PET proxy; excludes body extents.",
                                "trajectories": [previous, current, b0, b1],
                            }
                        )
                        self.last_alert[key] = t
                self.segments.append((obj["id"], previous, current))
            self.previous[obj["id"]] = current
        self.previous = {key: value for key, value in self.previous.items() if t - value["t"] < 3}
        for a, b in combinations(objects, 2):
            if a["speed"] < 0.5 and b["speed"] < 0.5:
                continue
            ttc, separation, relative_speed = closest_approach(
                a["world"], a["velocity"], b["world"], b["velocity"]
            )
            if not (0.15 < ttc < 5 and separation < 3 and relative_speed > 1):
                continue
            key = tuple(sorted((a["id"], b["id"])))
            if t - self.last_alert.get(key, -100) < 5:
                continue
            vulnerable = a["class"] in {"person", "bicycle"} or b["class"] in {"person", "bicycle"}
            score = float(np.clip((1 - ttc / 5) * (1 - separation / 4), 0, 1))
            ml_score = None
            if self.model:
                features = risk_features(a, b, ttc, separation, relative_speed, len(objects))
                ml_score = float(self.model.predict_proba([features])[0, 1])
            severity = (
                "critical"
                if ttc < 1 and separation < 1
                else "high"
                if ttc < 2
                else "medium"
                if ttc < 3
                else "low"
            )
            event = {
                "id": uid(),
                "t": round(t, 3),
                "participants": [a["id"], b["id"]],
                "type": "vulnerable_road_user_conflict" if vulnerable else "projected_conflict",
                "severity": severity,
                "ttc": round(ttc, 2),
                "separation": round(separation, 2),
                "risk_score": round(score, 3),
                "ml_score": ml_score,
                "confidence": min(a["confidence"], b["confidence"]),
                "explanation": f"Tracks {a['id']} and {b['id']} project to {separation:.1f} m separation in {ttc:.1f} s under constant velocity.",
                "trajectories": [
                    {"id": o["id"], "world": o["world"], "velocity": o["velocity"]} for o in (a, b)
                ],
                "model_scope": "synthetic conflict model; not validated for road safety"
                if ml_score is not None
                else "geometric screen",
            }
            emitted.append(event)
            self.last_alert[key] = t
        for o in objects:
            key = (o["id"], "braking")
            if o["acceleration"] < -4 and t - self.last_alert.get(key, -100) > 5:
                emitted.append(
                    {
                        "id": uid(),
                        "t": round(t, 3),
                        "participants": [o["id"]],
                        "type": "hard_braking",
                        "severity": "medium",
                        "ttc": None,
                        "separation": None,
                        "risk_score": 0.5,
                        "confidence": o["confidence"],
                        "ml_score": None,
                        "explanation": f"Track {o['id']} decelerated at {o['acceleration']:.1f} m/s²; verify calibration and replay.",
                        "trajectories": [
                            {"id": o["id"], "world": o["world"], "velocity": o["velocity"]}
                        ],
                    }
                )
                self.last_alert[key] = t
        self.events.extend(emitted)
        return emitted
