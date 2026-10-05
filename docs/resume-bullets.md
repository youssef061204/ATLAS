# Verified resume bullets

- Built a traffic intelligence platform with synchronized video and 3D replay; processed 4,260 actual annotated traffic frames at 29.4 FPS on an Intel i7 CPU, including inference, analytics, and persistence, with 35.7 ms p95 detector/tracker latency.
- Evaluated pretrained YOLO11n and production ByteTrack on three complete UA-DETRAC test sequences, measuring 0.898 mAP@50 and 0.793 IDF1; benchmarked causal forecasting on all 207 METR-LA sensors with chronological held-out evaluation.
- Developed constrained signal search yielding 37.5% lower simulated mean delay across three held-out synthetic seeds; audited four controllers over 12 held-out RESCO Cologne runs and identified 15.7% higher ATLAS delay under the realistic demand shift.

Sources: `artifacts/benchmarks/real_video_pipeline.json`, `real_detection.json`, `real_tracking.json`, `real_forecasting.json`, `realistic_signal_control.json`, and `artifacts/simulation.json`. UA-DETRAC results cover a predeclared three-sequence subset, not the full challenge. RESCO is real-world-derived simulation; the 37.5% improvement is controlled synthetic evaluation. No field safety benefit or GPU performance is claimed. Regenerate with `python scripts/export_artifacts.py`.
