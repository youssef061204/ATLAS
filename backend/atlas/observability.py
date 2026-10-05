import json

from prometheus_client.core import GaugeMetricFamily

from . import db


class PipelineCollector:
    """Read worker-persisted measurements; process-local counters would disappear in the API."""

    def collect(self):
        values = db.rows("SELECT id,status,metadata FROM videos ORDER BY created_at DESC LIMIT 100")
        frames = GaugeMetricFamily(
            "atlas_processed_frames", "Sampled frames in current persisted runs", labels=["video"]
        )
        inference = GaugeMetricFamily(
            "atlas_inference_latency_ms",
            "Measured per-video detector/tracker quantiles",
            labels=["video", "quantile"],
        )
        failures = GaugeMetricFamily("atlas_failed_videos", "Videos currently in a failed state")
        queue = GaugeMetricFamily("atlas_queue_depth", "Videos waiting for an inference worker")
        memory = GaugeMetricFamily(
            "atlas_worker_rss_mb", "Last measured worker resident memory", labels=["video"]
        )
        durations = GaugeMetricFamily(
            "atlas_pipeline_duration_seconds", "Measured completed job durations", labels=["video"]
        )
        for value in values:
            metadata = json.loads(value["metadata"])
            performance = metadata.get("performance") or metadata.get("live_performance")
            if performance:
                frames.add_metric([value["id"]], performance.get("processed_frames", 0))
                for quantile, latency in performance.get("inference_ms", {}).items():
                    inference.add_metric([value["id"], quantile], latency)
                if "memory_rss_mb" in performance:
                    memory.add_metric([value["id"]], performance["memory_rss_mb"])
                if "wall_seconds" in performance:
                    durations.add_metric([value["id"]], performance["wall_seconds"])
        failures.add_metric([], sum(v["status"] == "failed" for v in values))
        queue.add_metric([], sum(v["status"] == "queued" for v in values))
        yield from [frames, inference, failures, queue, memory, durations]
