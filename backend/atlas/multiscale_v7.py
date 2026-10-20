"""Actual full-frame and overlapping-crop inference with one shared tracker."""

from types import SimpleNamespace

from .detector import CLASS_MAP, TRAFFIC_CLASSES


class MultiScaleTracker:
    def __init__(self, model, resolution=960, confidence=0.1):
        from ultralytics.trackers.byte_tracker import BYTETracker

        self.model, self.resolution, self.confidence = model, resolution, confidence
        self.classes = [
            i for i, name in model.names.items() if CLASS_MAP.get(name, name) in TRAFFIC_CLASSES
        ]
        self.tracker = BYTETracker(
            SimpleNamespace(
                track_high_thresh=0.2,
                track_low_thresh=0.1,
                new_track_thresh=0.2,
                track_buffer=30,
                match_thresh=0.8,
                fuse_score=True,
            )
        )

    def infer(self, frame):
        import torch
        from torchvision.ops import nms
        from ultralytics.engine.results import Boxes

        height, width = frame.shape[:2]
        # Relative overlapping road crops; no reference annotations or boxes.
        regions = [
            (0, 0, width, height, self.resolution),
            (round(0.375 * width), round(0.125 * height), width, round(0.94 * height), 640),
            (0, round(0.30 * height), round(0.625 * width), round(0.94 * height), 640),
        ]
        detections = []
        for x1, y1, x2, y2, size in regions:
            output = self.model.predict(
                frame[y1:y2, x1:x2],
                imgsz=size,
                conf=self.confidence,
                classes=self.classes,
                device="cpu",
                verbose=False,
            )[0]
            if output.boxes is None:
                continue
            boxes = output.boxes.data.cpu().clone()
            boxes[:, [0, 2]] += x1
            boxes[:, [1, 3]] += y1
            # Reject crop-edge cut boxes; the full frame and overlap cover them.
            if x1 or y1 or x2 < width or y2 < height:
                keep = (
                    (boxes[:, 0] > x1 + 2)
                    & (boxes[:, 1] > y1 + 2)
                    & (boxes[:, 2] < x2 - 2)
                    & (boxes[:, 3] < y2 - 2)
                )
                boxes = boxes[keep]
            detections.append(boxes)
        data = torch.cat(detections) if detections else torch.empty((0, 6))
        if len(data):
            data = data[nms(data[:, :4], data[:, 4], 0.45)]
        tracked = self.tracker.update(Boxes(data.numpy(), frame.shape[:2]), frame)
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
