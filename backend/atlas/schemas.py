import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Point = tuple[float, float]


class Calibration(BaseModel):
    image: list[Point] = Field(min_length=4, max_length=16)
    world: list[Point] = Field(min_length=4, max_length=16)
    verified: bool = False
    note: str = Field(default="User-provided road-plane control points", max_length=500)

    @model_validator(mode="after")
    def valid_points(self):
        if len(self.image) != len(self.world):
            raise ValueError("Image/world point counts must match")
        if not all(math.isfinite(v) for p in self.image + self.world for v in p):
            raise ValueError("Calibration points must be finite")
        return self


class Region(BaseModel):
    id: str = Field(max_length=80)
    kind: Literal["inbound", "outbound", "crosswalk", "intersection", "waiting", "stop_line"]
    polygon: list[Point] = Field(min_length=3, max_length=64)
    direction: Literal["N", "E", "S", "W"] | None = None

    @model_validator(mode="after")
    def valid_polygon(self):
        if not all(math.isfinite(v) for p in self.polygon for v in p):
            raise ValueError("Region points must be finite")
        area = sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(self.polygon, self.polygon[1:] + self.polygon[:1], strict=True)
        )
        if abs(area) < 1e-8:
            raise ValueError("Region polygon must enclose an area")
        return self


class CameraConfig(BaseModel):
    detector_profile: Literal["coco", "aerial"] = "coco"
    calibration: Calibration | None = None
    regions: list[Region] = Field(default_factory=list, max_length=32)
    confidence: float = Field(default=0.25, ge=0.05, le=0.95)
    resolution: int = Field(default=640, ge=320, le=1280, multiple_of=32)
    sample_every: int = Field(default=3, ge=1, le=30)
    tracker: Literal["bytetrack.yaml", "botsort.yaml"] = "bytetrack.yaml"


class IntersectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class StreamIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    intersection_id: str
    duration_seconds: int = Field(default=30, ge=5, le=300)


class SimulationConfig(BaseModel):
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    duration: int = Field(default=300, ge=60, le=1200)
    demand: list[float] = Field(default=[0.38, 0.12, 0.32, 0.10], min_length=4, max_length=4)
    pedestrian_rate: float = Field(default=0.06, ge=0, le=1)
    min_green: int = Field(default=12, ge=8, le=30)
    max_green: int = Field(default=60, ge=30, le=90)
    yellow: int = Field(default=3, ge=3, le=5)
    all_red: int = Field(default=2, ge=2, le=5)
    pedestrian_interval: int = Field(default=12, ge=10, le=25)
    video_id: str | None = None

    @model_validator(mode="after")
    def valid_demand(self):
        if any(not math.isfinite(x) or x < 0 or x > 1.5 for x in self.demand):
            raise ValueError("Demand must be 0–1.5 vehicles/sec per approach")
        if self.min_green > self.max_green or self.pedestrian_interval > self.max_green:
            raise ValueError("Green constraints are inconsistent")
        return self
