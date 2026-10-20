"use client";

import { useEffect, useId, useState } from "react";
import styles from "./reality-evidence-v7.module.css";

type Identity = { identity: { IDF1: number }; predicted_boxes: number };
type PointReport = {
  identity: { IDF1: number };
  reference_observations: number;
  reference_coverage: number | null;
  instantaneous_count: { mae: number | null };
  empty_reference_cohort: boolean;
};
type Evidence = {
  checkpoint: boolean;
  physical: {
    measured: Record<string, number | boolean | null>;
    acceptance: {
      accepted: boolean;
      checks: Record<
        string,
        { value: number | boolean | null; passed: boolean; missing?: boolean }
      >;
    };
    physical_errors: {
      native_presence_coverage: number;
      within_4m_reference_coverage: number;
      position_by_time_since_birth: {
        lower_s: number;
        upper_s: number | null;
        pairs: number;
        mae: number | null;
      }[];
    };
  };
  cityflow: {
    development: { selected_idf1: number };
    holdout: null | {
      total_decoded_and_processed_frames: number;
      candidates: {
        method: string;
        annotation_padding_px_per_edge: number;
        accepted_links: number;
        result: Identity;
      }[];
      multicamera_filtered_changed_cohort: Identity;
    };
  };
  peachtree: null | {
    reports: Record<string, PointReport>;
    performance: { processed_frames: number; processed_fps: number };
  };
  daytime: {
    current_cpu_recheck: {
      decoded_frames: number;
      frames_with_tracks: number;
      observed_wall_seconds: number;
      inference_p95_ms: number;
    };
    decoded_frames: number;
    frames_with_tracks: number;
    unique_jpeg_frames: number;
    identity_resets: number;
    effective_decoded_fps: number;
    inference_p95_ms: number;
    observed_wall_seconds: number;
    max_receipt_gap_s: number;
    observed_start_utc: string;
    source_catalog: string;
    license: string;
  };
  live: {
    observed_start_utc: string;
    decoded_frames: number;
    inference_frames: number;
    frames_with_tracks: number;
    source_seconds: number;
    segments: number;
    identity_resets: number;
    inference_p95_ms: number;
    receipt_to_result_p95_ms: number;
    peak_sampled_rss_mb: number;
    source_page: string;
    hardware: string;
  };
  forecast: {
    target: string;
    results: {
      horizon_s: number;
      training_origins: number;
      test_origins: number;
      outcomes: Record<string, { mae_vehicles: number }>;
    }[];
  };
  source_artifacts: Record<string, { url: string }>;
};

const tabs = [
  "Physical fidelity",
  "Cross-camera",
  "Independent site",
  "Live ingestion",
  "Video forecasting",
] as const;
const number = (value: number | null | undefined, digits = 3) =>
  value == null ? "Unavailable" : value.toFixed(digits);

export function RealityEvidenceV7() {
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState(false);
  const [tab, setTab] = useState<(typeof tabs)[number]>("Physical fidelity");
  const id = useId();
  useEffect(() => {
    const controller = new AbortController();
    fetch("/demo/reality/v7/research.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Evidence unavailable");
        return response.json();
      })
      .then(setData)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, []);
  const link = (name: string, label: string) =>
    data?.source_artifacts[name] ? (
      <a
        href={data.source_artifacts[name].url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {label} ↗
      </a>
    ) : null;
  return (
    <section className={styles.report} aria-labelledby={`${id}-heading`}>
      <span className={styles.eyebrow}>ATLAS 7 / MEASURED EXPERIMENTS</span>
      <h2 id={`${id}-heading`}>
        Inspect the evidence behind the reconstruction.
      </h2>
      <p>
        Separate detection quality, physical prediction, cross-camera
        association and stream operation. Each result keeps its own dataset,
        denominator and limitations.
      </p>
      <div className={styles.tabs} aria-label="Choose experiment report">
        {tabs.map((name) => (
          <button
            key={name}
            aria-pressed={tab === name}
            aria-controls={`${id}-panel`}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div id={`${id}-panel`} className={styles.panel}>
        {error ? (
          <p role="alert">
            Experiment evidence could not load. No replacement metrics are
            shown.
          </p>
        ) : !data ? (
          <p role="status">Loading verified experiment artifacts…</p>
        ) : (
          <>
            {data.checkpoint ? (
              <p className={styles.note}>
                Local engineering checkpoint. Pending experiments are not
                release results.
              </p>
            ) : null}
            {tab === "Physical fidelity" ? (
              <>
                <div className={styles.topline}>
                  <h3>Free-running SUMO, independently measured.</h3>
                  <span className={styles.status}>
                    {data.physical.acceptance.accepted
                      ? "Accepted"
                      : "Acceptance not met"}
                  </span>
                </div>
                <p>
                  One observed CV birth pose initializes each admitted vehicle.
                  Later video states never force the simulation. Desired speed
                  and following time were selected on 0–300 s, then checked on
                  the known 600–1,000 s regression interval.
                </p>
                <div className={styles.stats}>
                  <div>
                    <strong>
                      {number(
                        data.physical.measured
                          .uncapped_position_mae_m as number,
                        2,
                      )}{" "}
                      m
                    </strong>
                    <span>Uncapped position MAE</span>
                  </div>
                  <div>
                    <strong>
                      {number(
                        data.physical.physical_errors
                          .within_4m_reference_coverage * 100,
                        1,
                      )}
                      %
                    </strong>
                    <span>All reference states within 4 m</span>
                  </div>
                  <div>
                    <strong>
                      {number(
                        data.physical.physical_errors.native_presence_coverage *
                          100,
                        1,
                      )}
                      %
                    </strong>
                    <span>Reference states with a native prediction</span>
                  </div>
                </div>
                <p>
                  These physical errors are distinct from the CV detector’s
                  conditional 4 m matching score. Missing vehicles remain in the
                  coverage denominator, and errors above 4 m remain in position
                  MAE.
                </p>
                <div
                  className={styles.scroll}
                  tabIndex={0}
                  role="region"
                  aria-label="Scrollable experiment table"
                >
                  <table>
                    <caption>
                      Native position error grows after initialization
                    </caption>
                    <thead>
                      <tr>
                        <th>Time since CV birth</th>
                        <th>Pairs</th>
                        <th>Position MAE</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.physical.physical_errors.position_by_time_since_birth.map(
                        (row) => (
                          <tr key={row.lower_s}>
                            <td>
                              {row.lower_s}–{row.upper_s ?? "∞"} s
                            </td>
                            <td>{row.pairs}</td>
                            <td>{number(row.mae, 2)} m</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
                <p className={styles.note}>
                  No accepted physical twin or new controller promotion.
                  Approximate signal stages lack independent lamp-state
                  confirmation. Birth-conditioned reconstruction differs from
                  ATLAS 6’s boundary-only input; it is not a field intervention.
                </p>
                {link(
                  "physical-current-acceptance.json",
                  "Inspect every acceptance criterion",
                )}{" "}
                {link(
                  "physical-calibrated-regression.json",
                  "Original and calibrated native models",
                )}
              </>
            ) : null}
            {tab === "Cross-camera" ? (
              <>
                <h3>Vehicle ReID with geometry and time constraints.</h3>
                <p>
                  S01 development selected pretrained vehicle-specific
                  512-dimensional descriptors with conservative geometric and
                  temporal gates. Development IDF1 is{" "}
                  {number(data.cityflow.development.selected_idf1, 4)}. S03 is a
                  separate locally held-out intersection/camera group in
                  Dubuque, not cross-city validation.
                </p>
                {data.cityflow.holdout ? (
                  <>
                    <p>
                      {data.cityflow.holdout.total_decoded_and_processed_frames.toLocaleString(
                        "en-US",
                      )}{" "}
                      consecutive frames processed across all six S03 cameras,
                      including the 8 FPS source. The association model and
                      annotation convention were frozen before S03 reference
                      scoring.
                    </p>
                    <div
                      className={styles.scroll}
                      tabIndex={0}
                      role="region"
                      aria-label="Scrollable experiment table"
                    >
                      <table>
                        <caption>
                          S03 held-out results, identical detection cohort
                        </caption>
                        <thead>
                          <tr>
                            <th>Association</th>
                            <th>Box convention</th>
                            <th>IDF1</th>
                            <th>Predicted boxes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.cityflow.holdout.candidates.map((row) => (
                            <tr
                              key={`${row.method}-${row.annotation_padding_px_per_edge}`}
                            >
                              <td>
                                {row.method === "independent"
                                  ? "Independent camera IDs"
                                  : row.method === "geometric_overlap"
                                    ? "Geometry only"
                                    : "Geometry + time + vehicle ReID"}
                              </td>
                              <td>
                                {row.annotation_padding_px_per_edge
                                  ? `+${row.annotation_padding_px_per_edge} px / edge`
                                  : "Raw detector boxes"}
                              </td>
                              <td>{number(row.result.identity.IDF1, 4)}</td>
                              <td>
                                {row.result.predicted_boxes.toLocaleString(
                                  "en-US",
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p>
                      Separately filtering predictions to identities linked
                      across cameras gives{" "}
                      {number(
                        data.cityflow.holdout
                          .multicamera_filtered_changed_cohort.identity.IDF1,
                        4,
                      )}{" "}
                      IDF1. That changes the prediction cohort and is not a
                      same-detection improvement.
                    </p>
                  </>
                ) : (
                  <p role="status">
                    The complete six-camera held-out run is still processing; no
                    test outcome is available.
                  </p>
                )}
                <p className={styles.note}>
                  Reference annotations cover multi-camera vehicles only. Box
                  padding follows the source annotation convention and does not
                  improve physical localization. All raw CityFlow media, crops,
                  descriptors and trajectories stay local under its research
                  license. The failed ATLAS 6 S02 appearance ablation remains
                  archived.
                </p>
                {link(
                  "cityflow-S03-frozen-results.json",
                  "Inspect held-out scores and limitations",
                )}{" "}
                {link(
                  "cityflow-S01-reid-results.json",
                  "Development model ablations",
                )}
              </>
            ) : null}
            {tab === "Independent site" ? (
              <>
                <h3>Peachtree: a new camera and city.</h3>
                <p>
                  The Lankershim-selected detector processes the actual Atlanta
                  raw video. Image/world calibration uses only the first 300 s;
                  a four-frame clock offset is frozen from development image
                  checks. The test is 600–900 s, with every predeclared cohort
                  reported.
                </p>
                {data.peachtree ? (
                  <>
                    <p>
                      All{" "}
                      {data.peachtree.performance.processed_frames.toLocaleString(
                        "en-US",
                      )}{" "}
                      consecutive frames processed. FP32 OpenVINO uses the Intel
                      integrated GPU; this is separate from the Lankershim CPU
                      throughput figure.
                    </p>
                    <div
                      className={styles.scroll}
                      tabIndex={0}
                      role="region"
                      aria-label="Scrollable experiment table"
                    >
                      <table>
                        <caption>
                          Peachtree 1 Hz world-point test, fixed 4 m gate
                        </caption>
                        <thead>
                          <tr>
                            <th>Cohort</th>
                            <th>Reference states</th>
                            <th>Point IDF1</th>
                            <th>Coverage</th>
                            <th>Count MAE</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(data.peachtree.reports).map(
                            ([key, row]) => (
                              <tr key={key}>
                                <td>{key.replaceAll("_", " ")}</td>
                                <td>{row.reference_observations}</td>
                                <td>
                                  {row.empty_reference_cohort
                                    ? "Unestimable"
                                    : number(row.identity.IDF1, 4)}
                                </td>
                                <td>
                                  {number(
                                    row.reference_coverage == null
                                      ? null
                                      : row.reference_coverage * 100,
                                    1,
                                  )}
                                  %
                                </td>
                                <td>
                                  {number(row.instantaneous_count.mae, 2)}
                                </td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <p role="status">
                    The complete 14,961-frame video is still processing; no site
                    test outcome is available.
                  </p>
                )}
                <p className={styles.note}>
                  These are calibrated point metrics, not bounding-box IDF1 or
                  physical SUMO acceptance. A pre-test cardinal-heading
                  correction leaves all calibration fit controls unchanged but
                  worsens the separate temporal check RMSE to 2.19 m.
                  Lankershim’s reserved tail remains a weak result; its strict
                  fresh-track cohort has no eligible reference observations and
                  cannot estimate generalization.
                </p>
                {link(
                  "peachtree-frozen-holdout-evaluation-corrected.json",
                  "Inspect independent-site test",
                )}{" "}
                {link(
                  "evaluation-full-v7-lankershim-1020-1120-window.json",
                  "Inspect failed Lankershim tail test",
                )}
              </>
            ) : null}
            {tab === "Live ingestion" ? (
              <>
                <div className={styles.topline}>
                  <h3>Daytime traffic video, processed frame by frame.</h3>
                  <span className={styles.status}>Archived native trial</span>
                </div>
                <p>
                  Taiwan Freeway Bureau camera 21840, National Road 2 / Danan
                  interchange. Actual daytime pixels and vehicle boxes were
                  inspected from this camera. The sustained trial began at{" "}
                  {data.daytime.observed_start_utc}, with verified TLS and
                  bounded reconnection.
                </p>
                <div className={styles.stats}>
                  <div>
                    <strong>{data.daytime.decoded_frames}</strong>
                    <span>MJPEG frames decoded and processed</span>
                  </div>
                  <div>
                    <strong>{data.daytime.frames_with_tracks}</strong>
                    <span>Frames with predicted vehicle tracks</span>
                  </div>
                  <div>
                    <strong>
                      {data.daytime.inference_p95_ms.toFixed(0)} ms
                    </strong>
                    <span>p95 inference / Intel integrated GPU</span>
                  </div>
                </div>
                <p>
                  {data.daytime.observed_wall_seconds.toFixed(1)} seconds of
                  continuous multipart MJPEG ingestion,{" "}
                  {data.daytime.effective_decoded_fps.toFixed(2)} effective
                  decoded FPS. The provider closed connections repeatedly:{" "}
                  {data.daytime.identity_resets} identity resets, maximum
                  receipt gap {data.daytime.max_receipt_gap_s.toFixed(2)} s. IDs
                  are never claimed to persist across reconnects. No snapshot
                  polling or retained video archive.
                </p>
                <p className={styles.note}>
                  This verifies useful daytime video ingestion and visible
                  detections, not ground-truth tracking accuracy or physical
                  speeds. The visual audit confirms the source scene; later
                  follow-up audit images expired before inspection and supply no
                  additional visual-continuity claim.
                </p>
                <a
                  href={data.daytime.source_catalog}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Official dataset and attribution ↗
                </a>
                <a
                  href={data.daytime.license}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open Government Data License ↗
                </a>
                {link(
                  "live-taiwan-21840-daylight.json",
                  "Inspect daytime stream telemetry",
                )}
                {link(
                  "live-taiwan-visual-audit.json",
                  "Inspect daylight verification scope",
                )}
                <p>
                  A separate release-session CPU recheck processed{" "}
                  {data.daytime.current_cpu_recheck.decoded_frames} frames (
                  {data.daytime.current_cpu_recheck.frames_with_tracks} with
                  tracks) in{" "}
                  {data.daytime.current_cpu_recheck.observed_wall_seconds.toFixed(
                    1,
                  )}{" "}
                  s measured wall time, with{" "}
                  {data.daytime.current_cpu_recheck.inference_p95_ms.toFixed(0)}{" "}
                  ms p95 inference. Two actual frames visually confirm moving
                  trucks in daylight. The optional Intel GPU is unavailable in
                  this later session; the earlier GPU timings remain archived,
                  not presented as current hardware availability.
                </p>
                <hr />
                <div className={styles.topline}>
                  <h3>Continuous Caltrans video. Actual tracking.</h3>
                  <span className={styles.status}>
                    Archived nighttime trial
                  </span>
                </div>
                <p>
                  Official I-5 / Disneyland Drive HLS, processed natively on the{" "}
                  {data.live.hardware}. This telemetry was recorded at{" "}
                  {data.live.observed_start_utc}; it is not current traffic or
                  an always-on public backend.
                </p>
                <div className={styles.stats}>
                  <div>
                    <strong>{data.live.source_seconds.toFixed(0)} s</strong>
                    <span>{data.live.segments} consecutive HLS segments</span>
                  </div>
                  <div>
                    <strong>
                      {data.live.decoded_frames.toLocaleString("en-US")}
                    </strong>
                    <span>Actual decoded video frames</span>
                  </div>
                  <div>
                    <strong>{data.live.inference_p95_ms.toFixed(0)} ms</strong>
                    <span>p95 inference / sampled frames</span>
                  </div>
                </div>
                <p>
                  {data.live.inference_frames} inference frames,{" "}
                  {data.live.frames_with_tracks} with predicted tracks;{" "}
                  {data.live.identity_resets} stream-gap tracking resets. Every
                  source frame was decoded, inference sampled every third frame.
                  An actual car retained its ID in two inspected frames two
                  seconds apart. Temporary video and audit images were deleted.
                </p>
                <p className={styles.note}>
                  No ground-truth tracking accuracy or unique-vehicle count is
                  claimed for this nighttime experiment.
                  Segment-receipt-to-result p95 is{" "}
                  {(data.live.receipt_to_result_p95_ms / 1000).toFixed(2)} s;
                  without a source camera timestamp this is not
                  camera-to-display latency. The public demo uses precomputed
                  real-video results.
                </p>
                <a
                  href={data.live.source_page}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Official source camera ↗
                </a>{" "}
                {link(
                  "live-i5-disneyland-11n-640-openvino-everythird-night.json",
                  "Inspect actual stream telemetry",
                )}{" "}
                {link("live-visual-audit.json", "Visual continuity audit")}
              </>
            ) : null}
            {tab === "Video forecasting" ? (
              <>
                <h3>A small chronological video-domain pilot.</h3>
                <p>
                  {data.forecast.target} Inputs are past raw CV counts. Fixed
                  models train only on targets before 600 s; test forecast
                  origins begin at 600 s, and every target ends before 1,000 s.
                </p>
                <div
                  className={styles.scroll}
                  tabIndex={0}
                  role="region"
                  aria-label="Scrollable experiment table"
                >
                  <table>
                    <caption>
                      Future 30-second mean occupancy MAE, vehicles
                    </caption>
                    <thead>
                      <tr>
                        <th>Horizon</th>
                        <th>Test origins</th>
                        <th>CV persistence</th>
                        <th>Training mean</th>
                        <th>Ridge</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.forecast.results.map((row) => (
                        <tr key={row.horizon_s}>
                          <td>{row.horizon_s / 60} min</td>
                          <td>{row.test_origins}</td>
                          <td>
                            {number(
                              row.outcomes.raw_cv_persistence_30s.mae_vehicles,
                              2,
                            )}
                          </td>
                          <td>
                            {number(
                              row.outcomes.training_target_mean.mae_vehicles,
                              2,
                            )}
                          </td>
                          <td>
                            {number(row.outcomes.ridge_alpha10.mae_vehicles, 2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className={styles.note}>
                  One short recording, overlapping targets, only eight
                  five-minute test origins. No calibrated uncertainty,
                  independent-city forecast validation or robust long-horizon
                  claim. Fifteen- and thirty-minute forecasts lack sufficient
                  source duration. METR-LA highway results remain separate.
                </p>
                {link(
                  "video-occupancy-forecast-pilot.json",
                  "Inspect every baseline, origin and limitation",
                )}
              </>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
