import hashlib
import math
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import psutil
from pydantic import BaseModel, Field, model_validator

from atlas import config


class BenchmarkArtifact(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    benchmark_type: str
    data_provenance: Literal["real", "real-world-derived", "synthetic", "controlled"]
    dataset: str
    dataset_version: str
    model: str
    date: datetime
    hardware: dict[str, Any]
    split: dict[str, Any]
    seed: int | list[int] | None
    metrics: dict[str, Any]
    scope: str
    methodology: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def finite_values(self):
        def check(value):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(
                    "Benchmark numbers must be finite; use null for unavailable metrics"
                )
            if isinstance(value, dict):
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(self.metrics)
        check(self.results)
        return self


def checksum(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hardware():
    cpu = platform.processor()
    if platform.system() == "Windows":
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        ) as key:
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    return {
        "cpu": cpu,
        "logical_cores": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 2),
        "os": platform.platform(),
        "python": platform.python_version(),
        "device": config.DEVICE,
    }


def write_artifact(
    name,
    *,
    benchmark_type,
    data_provenance,
    dataset,
    dataset_version,
    model,
    split,
    seed=None,
    metrics,
    scope,
    methodology=None,
    results=None,
):
    artifact = BenchmarkArtifact(
        benchmark_type=benchmark_type,
        data_provenance=data_provenance,
        dataset=dataset,
        dataset_version=dataset_version,
        model=model,
        date=datetime.now(UTC).isoformat(),
        hardware=hardware(),
        split=split,
        seed=seed,
        metrics=metrics,
        scope=scope,
        methodology=methodology or {},
        results=results or {},
    )
    directory = config.ARTIFACTS / "benchmarks"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(target)
    return artifact.model_dump(mode="json")
