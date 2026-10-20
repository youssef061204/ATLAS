"""Live video tracking with low-score recovery and explicit provider-overlay rejection.

This is separate from frozen NGSIM/CityFlow perception experiments. The reviewed
Disneyland camera overlay regions are not road space. Filtering is logged and
never changes the source video shown during a visual audit.
"""

from types import SimpleNamespace

import numpy as np

from atlas.detector import CLASS_MAP, YOLOTracker


def source_overlay(box, shape):
    height, width = shape[:2]
    x1, y1, x2, y2 = box
    x, y = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
    return (x < 0.4 and y < 0.12) or (x > 0.7 and y < 0.1)


class LiveTracker(YOLOTracker):
    def __post_init__(self):
        super().__post_init__()
        self.reset_tracking()

    def reset_tracking(self):
        """Discard temporal identities while retaining immutable inference weights/cache."""
        from ultralytics.trackers.byte_tracker import BYTETracker

        self.tracker = BYTETracker(
            SimpleNamespace(
                track_high_thresh=0.25,
                track_low_thresh=0.1,
                new_track_thresh=0.25,
                track_buffer=8,
                match_thresh=0.9,
                fuse_score=False,
            )
        )
        self.raw_detections = 0
        self.overlay_rejections = 0

    def infer(self, frame):
        from ultralytics.engine.results import Boxes

        result = self.model.predict(
            frame,
            conf=0.1,
            classes=self.class_ids,
            imgsz=self.settings.resolution,
            device="cpu",
            verbose=False,
        )[0]
        data = (
            result.boxes.data.cpu().numpy()
            if result.boxes is not None
            else np.empty((0, 6), dtype=np.float32)
        )
        self.raw_detections += len(data)
        keep = np.array([not source_overlay(row[:4], frame.shape) for row in data], dtype=bool)
        self.overlay_rejections += int((~keep).sum())
        data = data[keep]
        tracked = self.tracker.update(Boxes(data, frame.shape[:2]), frame)
        return [
            {
                "id": int(row[4]),
                "class": CLASS_MAP.get(
                    self.model.names[int(row[6])], self.model.names[int(row[6])]
                ),
                "confidence": float(row[5]),
                "bbox": row[:4].astype(float).tolist(),
            }
            for row in tracked
        ]
