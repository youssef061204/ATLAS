from collections import Counter
from statistics import mean, median

import numpy as np

from .geometry import contains, heading_direction, motion

VEHICLES = {"car", "truck", "bus", "motorcycle"}


class TrajectoryEngine:
    def __init__(self, projection, regions):
        self.projection = projection
        self.regions = regions
        self.tracks = {}
        self.metrics = []
        self.exited = set()
        self.turns = Counter()

    def update(self, t, detections):
        objects = []
        for detection in detections:
            track_id = detection["id"]
            track = self.tracks.setdefault(
                track_id,
                {
                    "id": track_id,
                    "class": detection["class"],
                    "points": [],
                    "stopped_duration": 0,
                    "entry_time": None,
                    "exit_time": None,
                    "entry_direction": None,
                },
            )
            x1, y1, x2, y2 = detection["bbox"]
            image = [(x1 + x2) / 2, y2]
            world = self.projection.point(*image)
            point = {"t": round(t, 4), "image": image, "world": world}
            points = track["points"]
            points.append(point)
            vx, vy = motion(points, "world" if self.projection.verified else "image")
            speed = float(np.hypot(vx, vy))
            previous = points[-2] if len(points) > 1 else None
            dt = t - previous["t"] if previous else 0
            acceleration = (speed - previous["speed"]) / dt if dt > 0 and len(points) > 4 else 0
            direction = heading_direction(vx, vy)
            memberships = [r for r in self.regions if contains(r, image)]
            lane = next((r for r in memberships if r.direction), None)
            if lane:
                direction = lane.direction
            stopped = speed < (0.5 if self.projection.verified else 3.0) and len(points) >= 3
            stopped_duration = (
                (previous["stopped_duration"] + dt)
                if previous and stopped and previous["stopped"]
                else 0
            )
            if stopped:
                track["stopped_duration"] += dt
            inside = any(r.kind == "intersection" for r in memberships)
            if inside and track["entry_time"] is None:
                track["entry_time"] = t
                track["entry_direction"] = direction
            if previous and previous["inside_intersection"] and not inside:
                track["exit_time"] = t
                if track_id not in self.exited:
                    self.exited.add(track_id)
                    self.turns[f"{track['entry_direction']}→{direction}"] += 1
            point.update(
                {
                    "bbox": detection["bbox"],
                    "confidence": detection["confidence"],
                    "speed": round(speed, 3),
                    "velocity": [round(vx, 3), round(vy, 3)],
                    "heading": round(float(np.arctan2(vy, vx)), 3),
                    "acceleration": round(acceleration, 3),
                    "stopped": stopped,
                    "stopped_duration": round(stopped_duration, 3),
                    "direction": direction,
                    "regions": [r.id for r in memberships],
                    "inside_intersection": inside,
                }
            )
            objects.append({"id": track_id, "class": track["class"], **point})
        vehicle_objects = [o for o in objects if o["class"] in VEHICLES]
        stopped_objects = [
            o for o in vehicle_objects if o["stopped"] and o["stopped_duration"] >= 1
        ]
        inbound_ids = {r.id for r in self.regions if r.kind == "inbound"}
        if inbound_ids:
            stopped_objects = [o for o in stopped_objects if inbound_ids.intersection(o["regions"])]
        recent_ids = [tr for tr in self.tracks.values() if t - 60 <= tr["points"][0]["t"] <= t]
        observed = max(min(t, 60), 1)
        counts = Counter(tr["class"] for tr in recent_ids)
        speeds = [o["speed"] for o in vehicle_objects if len(self.tracks[o["id"]]["points"]) >= 3]
        approach = Counter(o["direction"] for o in vehicle_objects)
        world_area = self._road_area()
        metric = {
            "t": round(t, 3),
            "active_objects": len(objects),
            "vehicles": len(vehicle_objects),
            "pedestrians": sum(o["class"] == "person" for o in objects),
            "cyclists": sum(o["class"] == "bicycle" for o in objects),
            "vehicles_per_minute": round(sum(counts[c] for c in VEHICLES) * 60 / observed, 2),
            "pedestrians_per_minute": round(counts["person"] * 60 / observed, 2),
            "cyclists_per_minute": round(counts["bicycle"] * 60 / observed, 2),
            "average_speed": round(mean(speeds), 2) if speeds else 0,
            "median_speed": round(median(speeds), 2) if speeds else 0,
            "speed_unit": "m/s" if self.projection.verified else "px/s",
            "queue_length": len(stopped_objects),
            "max_queue": max([len(stopped_objects)] + [m["queue_length"] for m in self.metrics]),
            "average_stop_duration": round(
                mean([self.tracks[o["id"]]["stopped_duration"] for o in vehicle_objects]), 2
            )
            if vehicle_objects
            else 0,
            "occupancy": sum(o["inside_intersection"] for o in objects),
            "throughput": len(self.exited),
            "approaches": dict(approach),
            "turns": dict(self.turns),
            "density_per_1000_m2": round(len(vehicle_objects) * 1000 / world_area, 2)
            if world_area
            else None,
            "dwell_time": round(
                mean([t - self.tracks[o["id"]]["points"][0]["t"] for o in objects]), 2
            )
            if objects
            else 0,
        }
        self.metrics.append(metric)
        return objects, metric

    def _road_area(self):
        if not self.projection.verified:
            return None
        regions = [r for r in self.regions if r.kind == "intersection"]
        if not regions:
            return None
        polygon = np.array([self.projection.point(*p) for p in regions[0].polygon])
        x, y = polygon[:, 0], polygon[:, 1]
        area = abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2
        return float(area) if area > 0 else None

    def summary(self):
        counts = Counter(t["class"] for t in self.tracks.values())
        return {
            "unique_tracks": len(self.tracks),
            "classes": dict(counts),
            "vehicles": sum(counts[c] for c in VEHICLES),
            "pedestrians": counts["person"],
            "cyclists": counts["bicycle"],
            "throughput": len(self.exited),
            "turns": dict(self.turns),
            "max_queue": max((m["queue_length"] for m in self.metrics), default=0),
            "calibrated": self.projection.verified,
        }
