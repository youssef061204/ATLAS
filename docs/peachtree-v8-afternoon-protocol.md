# Peachtree afternoon: sealed physical holdout protocol

**Status (21 October 2026): source reservation, no outcome scoring.** ATLAS has
inspected the official archive directory and video header, and acquired the
official Peachtree supporting archive. It has **not** acquired, decoded, aligned,
or scored the 4:00 p.m. camera-5 video at the time this protocol was written.
The 4:00–4:15 p.m. trajectory rows have not been opened for evaluation. The
Peachtree noon camera-1 result in [ATLAS 7](reality-v7-results.md) is already
known. The afternoon period is a new **time-of-day/demand** test on the same
Peachtree corridor, not a new city or a field intervention.

## Reserved official sources

| Role | Exact source and verification | License |
| --- | --- | --- |
| Raw detector input | [FHWA Peachtree video catalog](https://data.transportation.gov/Automobiles/Next-Generation-Simulation-NGSIM-Program-Peachtree/mupt-aksf), archive `https://data.transportation.gov/download/mupt-aksf/application%2Fx-zip-compressed`, member `NGSIM Peachtree Videos/peachtree-camera5-0400pm-0415pm.avi`; 468,006,912 bytes, ZIP CRC32 `9f2f36f4`. | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| Reference positions, tracks, speed and movements | [FHWA NGSIM trajectories and support](https://data.transportation.gov/Automobiles/Next-Generation-Simulation-NGSIM-Vehicle-Trajector/8ect-6jqj), attachment `https://data.transportation.gov/api/views/8ect-6jqj/files/7244a8b5-077f-4851-bc06-3cfc7a75f0b0?download=true`, member `NGSIM_Peachtree_Vehicle_Trajectories.csv`; source SHA-256 `1ec10349176788ca199132677154b9b7d207b7ec9605bfa16b600660085a76d9`. | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| Geometry and signal observations | The same support attachment contains `peachtree-street-cad-diagram.zip`, `peachtree-street-gis-files.zip`, and `peachtree-street-signal-timing.zip`. The latter includes 16 directional `Peachtree_*_0400-0415.csv` signal-change files for 10th, 11th, 12th and 14th streets. The [FHWA metadata](https://data.transportation.gov/api/views/8ect-6jqj/files/8b5a833b-e286-467f-8c55-af45be37c8ab?download=true&filename=4-+Peachtree+Street+Metadata+Documentation.pdf) says signal changes were extracted from separate field videos. | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |

The archive header reports 14,981 frames and a consistent RIFF size for the
raw afternoon camera-5 AVI. This does **not** establish a complete decode or
reference alignment. The video container can run longer than the nominal
15-minute annotated trajectory period. Only the verified intersection of video,
camera-5 GIS coverage and reference time is eligible for accuracy scoring. The
processed AVI has overlays from the reference extraction; it must **never** be
detector input. Local raw source files, trajectories and native simulation output
remain Git-ignored.

### Source-only acquisition after this reservation

The raw member was subsequently acquired and [audited without reading
afternoon trajectory rows](../artifacts/reality/v8/peachtree-afternoon-source-integrity.json).
ZIP CRC32 and SHA-256 both verify; raw SHA-256 is
`eab90364a9f8fb936362ccae4f23355b3d23b47a951a2e8abba1fd541baf68b6`.
All **14,981/14,981 frames** decode at 640 × 480 and 10.00001 FPS, giving a
source-container duration of about **24:58**. Of 14,980 consecutive pairs,
**14,978** have mean grayscale change above 0.5 and **two** are exact pixel
duplicates. This establishes a continuous moving-video source, not an accuracy
result or evidence that its full duration is independently annotated. No
Peachtree afternoon trajectory metric has been computed.

The official noon orthophoto, its world file, camera-5 coverage polygon and
noon raw video have also been [source-audited](../artifacts/reality/v8/peachtree-noon-camera5-registration-readiness.json).
The orthophoto has 0.25 survey-foot pixels and the official GIS polygon maps
inside it, but this does not calibrate the oblique camera image. An exploratory
raw-video-to-orthophoto feature match at noon frame 600 produced only five
RANSAC inliers and has no independent road-plane control points or verified
raw/reference clock offset. There is therefore **no frozen camera-5 metric
registration or physical candidate**. The afternoon labels stay sealed. The
next step is to establish paired noon video/reference frames and road-plane
control points with independent noon checks before freezing a candidate.

## Pre-outcome freeze and data firewall

1. Use only Peachtree **noon** camera-5 footage, noon reference trajectories,
   noon signal logs and official CAD/GIS to develop image-to-world registration,
   camera footprint, stop-line and lane geometry, legal turns, signal mapping,
   CV birth/route policy, SUMO dynamics and the scorer. Split development and
   validation by whole reference identity. The noon camera-1 holdout and
   Lankershim/CityFlow known results remain disclosed; they are not new tests.
2. Before reading **any afternoon trajectory rows**, record SHA-256 of the
   perception code/config/model, registration, network, route generator, SUMO
   config, scorer and this protocol in a frozen manifest. The existing
   Lankershim-selected detector model has SHA-256
   `060866322c84caa59d7cbd7874efbe1af5e957a862169f2ac6778a8e7e3c4851`.
   There is **no frozen Peachtree camera-5 physical candidate yet**. Until that
   manifest exists, afternoon labels must stay sealed and no acceptance score
   may be computed.
3. Acquire the exact raw archive member, verify ZIP CRC32, record its SHA-256,
   decode all declared frames, check frame-to-frame changes, and record FPS,
   dimensions and source duration. If camera 5 fails complete integrity, stop
   and amend this protocol **before** inspecting labels; camera 2 has a
   consistent archive header but is not a silently interchangeable test.
4. Determine the afternoon raw/reference offset from only the first 60 seconds
   of raw and official processed imagery, without reading afternoon trajectory
   rows. Record the paired frame evidence and freeze the offset before scoring.
   The noon camera-1 four-frame offset does not transfer automatically. Use
   `(Frame_ID - 1)/10` within the afternoon reference session, with an explicit
   session key; do not treat source `Global_Time` as a clean uniform epoch or
   reuse vehicle IDs across sessions.
5. Run the frozen detector/tracker over the **whole continuous raw AVI**. For
   the physical trial, native SUMO may receive only causal CV-derived arrivals,
   lane/route predictions and speed estimates, documented road geometry, and
   observed exogenous afternoon signal changes. Do not inject future vehicle
   positions, completed destinations, observed discharge, reference queues or
   outcome-derived speed commands. Report any reference-boundary initialization
   only as a separate oracle diagnostic.

## Frozen scoring rule

The primary afternoon window is **120 ≤ reference time < 780 seconds** after
4:00 p.m. The preceding 120 seconds are warm-up; the final 120 seconds are
reserved for source-edge and trip-censoring checks. A reference state is eligible
when its body centre lies inside the **noon-frozen camera-5 road polygon** and
the synchronized raw frame exists. Occluded reference vehicles remain eligible.
Predicted states use the same polygon, 1 Hz clock and fixed 4 m one-to-one
spatial gate. Report both all eligible identities and a strict fresh-track
cohort that excludes any reference identity present during warm-up; never swap
cohorts after seeing scores. Stable identity keys include the afternoon session.

For perception, report raw point IDF1, reference coverage, conditional matched
position and speed MAE, unmatched counts, and visible count MAE. Inferred gap
fills may be shown only as a separately labeled secondary result. For the
free-running physical twin, report reference-state presence, fraction of **all
eligible** reference states represented within 4 m, conditional matched
position/speed MAE with coverage, visible-count MAE/bias, directional flow
error by 30-second bin, lane/approach queue-count MAE and discharge timing, and
paired segment travel-time error/distribution with the eligible, matched and
censored trip denominators. A queue is a vehicle slower than 0.5 m/s for at
least 2 seconds inside a noon-frozen upstream lane segment. Independently
validate the mapped signal-state clock against the official change log; source
green/yellow/red event semantics and approach assignment must be checked before
claiming lamp accuracy. Include source measurement uncertainty and temporal
block confidence intervals where supportable.

Keep the [ATLAS 7 physical acceptance gates](reality-v7-protocol.json)
unchanged: normalized count MAE ≤ 0.20, directional-flow normalized absolute
error ≤ 0.20, queue-count MAE ≤ 2 vehicles, matched position MAE ≤ 4 m,
matched reference coverage ≥ 0.80, matched speed MAE ≤ 2 m/s, travel-time
Wasserstein distance ≤ 2 s, and independently verified signal state. Missing
evidence or any failed supported gate means **no accepted physical twin**.
ATLAS's observed trajectory replay is visualization, not predictive simulation;
simulated controller comparisons are not observed intervention outcomes.

Run `python scripts/verify_peachtree_afternoon_source_v8.py` to check the
published archive/source metadata without reading any trajectory rows. Once
the raw local video is acquired, add `--require-video` to verify the source
manifest and actual video SHA-256. These are source-integrity checks, **not
accuracy evaluation**.
