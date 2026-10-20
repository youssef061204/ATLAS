"""Bounded FP32 inference for unchanged YOLO weights on existing Intel hardware.

Uses the installed Ultralytics letterbox, NMS and box scaling operations. Three
fixed-shape compiled graphs are cached for the selected overlapping-crop profile.
No quantization, dataset calibration or hidden reduced-precision inference.
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np


class OpenVINOModel:
    def __init__(self, directory, device="CPU", threads=2):
        import openvino as ov
        import yaml

        self.ov, self.core = ov, ov.Core()
        if device not in {"CPU", "GPU"} or device not in self.core.available_devices:
            raise ValueError("Requested Intel inference device unavailable")
        self.directory = Path(directory)
        self.xml = next(self.directory.glob("*.xml"))
        metadata = yaml.safe_load((self.directory / "metadata.yaml").read_text(encoding="utf-8"))
        self.names = {int(k): v for k, v in metadata["names"].items()}
        self.stride = int(metadata["stride"])
        self.device, self.threads, self.compiled = device, threads, {}

    def predict(self, frame, imgsz=960, conf=0.1, classes=None, **_):
        import torch
        from ultralytics.data.augment import LetterBox
        from ultralytics.engine.results import Boxes
        from ultralytics.utils import nms, ops

        image = LetterBox((imgsz, imgsz), auto=True, stride=self.stride)(image=frame)
        tensor = (
            np.ascontiguousarray(image[..., ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255
        )
        shape = tuple(tensor.shape)
        if shape not in self.compiled:
            if len(self.compiled) >= 4:
                raise ValueError("Input shapes exceed bounded compiled-model cache")
            model = self.core.read_model(self.xml)
            model.reshape(list(shape))
            config = {
                "PERFORMANCE_HINT": "LATENCY",
                "INFERENCE_PRECISION_HINT": self.ov.Type.f32,
            }
            if self.device == "CPU":
                config["NUM_STREAMS"] = 1
                config["INFERENCE_NUM_THREADS"] = self.threads
            self.compiled[shape] = self.core.compile_model(model, self.device, config)
        compiled = self.compiled[shape]
        result = compiled(tensor)[compiled.output(0)]
        rows = nms.non_max_suppression(
            torch.from_numpy(result),
            conf,
            0.7,
            classes,
            False,
            max_det=300,
            nc=len(self.names),
            end2end=False,
        )[0]
        rows[:, :4] = ops.scale_boxes(shape[2:], rows[:, :4], frame.shape)
        return [SimpleNamespace(boxes=Boxes(rows, frame.shape[:2]))]

    def runtime(self):
        return {
            "engine": "OpenVINO",
            "device": self.device,
            "precision": "FP32",
            "cpu_threads": self.threads if self.device == "CPU" else None,
            "compiled_shapes": [list(shape) for shape in self.compiled],
            "execution_devices": sorted(
                {
                    str(device)
                    for model in self.compiled.values()
                    for device in model.get_property("EXECUTION_DEVICES")
                }
            ),
        }
