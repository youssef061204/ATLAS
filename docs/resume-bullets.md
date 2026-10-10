# Verified resume bullets

Current 5.0: [evidence-backed role bullets](atlas-5-resume-bullets.md) and [measured results](atlas-5-results.md) cover five-city readiness, strict transfer, 2,550 new simulation episodes and verified private bounded execution. The controller failed promotion; Austin zero-shot regressed; independently validated city twins remain zero. Six new complete CPU repeats measured 18.33 / 15.06 FPS on one sequence, separate from the historical 29.4 FPS below.

Current 4.0 work: [generated, evidence-backed role bullets](atlas-4-resume-bullets.md) cover official five-city ingestion, city forecasts, continuous-video tracking, cached planning and qualified cooperative-control gains and regressions. [Complete current results](atlas-4-results.md). The stronger original highway, CPU-pipeline and Cologne results remain below.

Current 3.0 research addition: implemented a 3,617-parameter directional graph neural traffic forecaster, measuring **2.344 mph** five-minute METR-LA MAE versus the original **2.490 mph** (5.85% reduction; paired day-block 95% interval 5.59–6.13%). Validation-selected epoch, 207 sensors, one training seed and the shared historical test period; independent external replication and city-domain calibration remain outstanding. See [generated role-specific candidates](RESUME_BULLETS.md) and [complete verified metrics](VERIFIED_ENGINEERING_METRICS.md).

The three original verified bullets remain below with their original dataset and controller scope:

- Built a traffic digital twin with synchronized video and 3D replay; processed 4,260 real annotated traffic frames at 29.4 FPS on an Intel i7 CPU, including inference, analytics, and persistence.
- Evaluated pretrained YOLO11n and production ByteTrack on three complete UA-DETRAC test sequences, measuring 0.898 mAP@50 and 0.793 IDF1; achieved 2.490 mph five-minute METR-LA MAE versus 2.813 persistence across all 207 sensors under chronological holdout.
- Replaced failed cyclic signal search with validation-selected, constraint-aware MPC, measuring 20.53 s mean delay and 65.7% paired reduction versus fixed timing (45.3% versus max-pressure) across 10 unseen RESCO Cologne1 seeds with bootstrap confidence intervals and separate ablations.

Sources: `artifacts/benchmarks/real_video_pipeline.json`, `real_detection.json`, `real_tracking.json`, `real_forecasting.json`, and `improved_signal_control.json`. RESCO is real-world-derived simulation, not a field trial. The original 66.45 s failure remains published in `original_signal_control_failed.json`; untuned Ingolstadt1 transfer failed to beat either baseline. Forecast ablations show only a small, uncertain benefit. UA-DETRAC covers a predeclared subset, not the full challenge; GPU and field safety benefits are unmeasured. Regenerate with `python scripts/export_artifacts.py`.
