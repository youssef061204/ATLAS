import hashlib
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from . import config
from .schemas import CameraConfig

CLASSES = [0, 1, 2, 3, 5, 7]
AERIAL_URL = "https://huggingface.co/dronefreak/visdrone-yolov8n/resolve/b5ca8d362341457ad715a5314da0931ea58bb237/best.pt"
AERIAL_SHA256 = "060866322c84caa59d7cbd7874efbe1af5e957a862169f2ac6778a8e7e3c4851"
CLASS_MAP = {"pedestrian": "person", "people": "person", "motor": "motorcycle", "van": "car"}
TRAFFIC_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}


def aerial_weights():
    path = config.DATA / "visdrone-yolov8n.pt"
    if not path.exists():
        temporary = path.with_suffix(".download")
        try:
            urllib.request.urlretrieve(AERIAL_URL, temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != AERIAL_SHA256:
                raise ValueError("Aerial model checksum mismatch")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != AERIAL_SHA256:
        raise ValueError("Aerial model checksum mismatch; remove the cached weight and retry")
    return path


class DetectorTracker(Protocol):
    def infer(self, frame: np.ndarray) -> list[dict]: ...


@dataclass
class YOLOTracker:
    settings: CameraConfig

    def __post_init__(self):
        from ultralytics import YOLO

        self.model_identifier = (
            "YOLOv8n-VisDrone" if self.settings.detector_profile == "aerial" else config.MODEL
        )
        self.model = YOLO(
            aerial_weights() if self.settings.detector_profile == "aerial" else config.MODEL
        )
        self.class_ids = [
            i
            for i, name in self.model.names.items()
            if CLASS_MAP.get(name, name) in TRAFFIC_CLASSES
        ]

    def infer(self, frame):
        results = self.model.track(
            frame,
            persist=True,
            tracker=self.settings.tracker,
            classes=self.class_ids,
            conf=self.settings.confidence,
            imgsz=self.settings.resolution,
            device=config.DEVICE,
            verbose=False,
        )[0]
        if results.boxes is None or results.boxes.id is None:
            return []
        return [
            {
                "id": int(track_id),
                "class": CLASS_MAP.get(self.model.names[int(cls)], self.model.names[int(cls)]),
                "confidence": round(float(conf), 4),
                "bbox": [round(float(x), 2) for x in box],
            }
            for box, track_id, cls, conf in zip(
                results.boxes.xyxy.cpu().numpy(),
                results.boxes.id.cpu().numpy(),
                results.boxes.cls.cpu().numpy(),
                results.boxes.conf.cpu().numpy(),
                strict=True,
            )
        ]
