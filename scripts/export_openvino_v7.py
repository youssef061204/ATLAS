"""Export unchanged pretrained weights to FP32 OpenVINO; no quantization or labels."""

import argparse
import hashlib
import json
from pathlib import Path

import torch
from ultralytics import YOLO
from ultralytics.utils import torch_utils

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["aerial", "yolo11n", "yolo11s"], default="aerial")
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch_utils.NUM_THREADS = 2
    source = ROOT / ("data/visdrone-yolov8n.pt" if args.model == "aerial" else args.model + ".pt")
    directory = ROOT / "data/reality-v7/openvino"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / source.name
    if not target.exists():
        target.write_bytes(source.read_bytes())
    if target.read_bytes() != source.read_bytes():
        raise ValueError("Export input weight differs")
    record = directory / f"{args.model}-export.json"
    if record.exists():
        raise FileExistsError("Preserve completed model export")
    model = YOLO(target)
    exported = Path(
        model.export(format="openvino", dynamic=True, quantize=32, imgsz=960, batch=1, device="cpu")
    )
    files = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in exported.iterdir()
        if p.is_file()
    }
    import openvino as ov

    result = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "precision": "FP32, no quantization or data calibration",
        "model_directory": str(exported),
        "files_sha256": files,
        "openvino_version": ov.__version__,
        "torch_version": torch.__version__,
        "exporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_labels_used": False,
    }
    record.write_bytes(json.dumps(result, indent=2).encode())
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
