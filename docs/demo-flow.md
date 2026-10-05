# Portfolio walkthrough

Run `docker compose up --build -d`, then open http://localhost:3000. The bootstrap cache is labeled as actual recorded CV output. Reprocessing runs the model again.

## A 60-second presentation

1. **0–7 seconds — Landing.** “ATLAS turns footage into traffic trajectories, an interactive twin, and reproducible control experiments.” The animated preview is seeded simulated traffic.
2. **7–22 seconds — Intersection.** Play the attributed source, scrub to a different time, and select a bounding box. Show the same anonymous object in the track inspector and synchronized twin. Switch to heatmap. State that this overhead time-lapse uses pixels per playback second.
3. **22–30 seconds — Analytics.** Show actual class counts, stopped queues, speed trends, and dwell. Counts refer to track IDs and can be inflated by fragmentation.
4. **30–36 seconds — Safety and forecast.** Show the calibration requirement, then the measured METR-LA five-minute forecast result and horizon controls. The short clip itself lacks forecasting history; real highway forecasting and the separate controlled model experiment retain explicit scope labels.
5. **36–51 seconds — Signal laboratory.** Run optimization, pause, and scrub the matched baseline/ATLAS twins. Show all three policies, identical arrivals, vehicle delay, queues, throughput, and pedestrian wait.
6. **51–60 seconds — Evidence.** Show UA-DETRAC detection/tracking and CPU processing, real METR-LA holdout, and the negative held-out RESCO result. Controlled synthetic results remain separate. Generated artifacts accompany every number.

## Capture assets

The automated browser integration tests save full-page production screenshots in `artifacts/screenshots/`. With the production application running, record the walkthrough:

```sh
cd frontend
node scripts/record-demo.mjs
```

The resulting silent WebM is `artifacts/demo/atlas-walkthrough.webm`. It records the application performing real operations; it contains no simulated benchmark values or synthetic footage presented as a camera source. Add the narration above when presenting. Source license and original footage attribution remain in [datasets](datasets.md).

The current web-optimized presentation is [58.8-second MP4](../artifacts/portfolio/demo.mp4), with [four optimized screenshots](../artifacts/portfolio). It captures the precomputed public-demo build; the control recording is explicitly controlled simulation. The public walkthrough does not claim new inference occurs during replay.

For a fresh inference demonstration, use Camera setup → Save & reprocess and show the actual SSE processing stages before the walkthrough. First inference may download the aerial checkpoint; allow extra time rather than suggesting cache loading is real-time inference.
