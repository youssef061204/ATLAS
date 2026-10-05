# Verified resume bullets

- Built a traffic digital twin with synchronized video and 3D replay; processed 4,260 real annotated traffic frames at 29.4 FPS on an Intel i7 CPU, including inference, analytics, and persistence.
- Evaluated pretrained YOLO11n and production ByteTrack on three complete UA-DETRAC test sequences, measuring 0.898 mAP@50 and 0.793 IDF1; achieved 2.490 mph five-minute METR-LA MAE versus 2.813 persistence across all 207 sensors under chronological holdout.
- Replaced failed cyclic signal search with validation-selected, constraint-aware MPC, measuring 20.53 s mean delay and 65.7% paired reduction versus fixed timing (45.3% versus max-pressure) across 10 unseen RESCO Cologne1 seeds with bootstrap confidence intervals and separate ablations.

Sources: `artifacts/benchmarks/real_video_pipeline.json`, `real_detection.json`, `real_tracking.json`, `real_forecasting.json`, and `improved_signal_control.json`. RESCO is real-world-derived simulation, not a field trial. The original 66.45 s failure remains published in `original_signal_control_failed.json`; untuned Ingolstadt1 transfer failed to beat either baseline. Forecast ablations show only a small, uncertain benefit. UA-DETRAC covers a predeclared subset, not the full challenge; GPU and field safety benefits are unmeasured. Regenerate with `python scripts/export_artifacts.py`.
