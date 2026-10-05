"use client";

import { useState } from "react";
import { API } from "@/lib/api";
import { TrendChart } from "./charts";
import { SignalStudy } from "./signal-study";

type Scores = {
  mae: number;
  rmse: number;
  mape_pct: number | null;
  unit: string;
};
type Summary = { mean: number; std: number };
export type RealArtifact = {
  schema_version: string;
  benchmark_type: string;
  data_provenance: string;
  dataset: string;
  dataset_version: string;
  model: string;
  date: string;
  hardware: { cpu: string; ram_gb: number; device: string };
  split: { sequences?: string[]; frames_per_sequence?: Record<string, number> };
  scope: string;
  metrics: {
    map50?: number;
    map50_95?: number;
    precision?: number;
    recall?: number;
    f1?: number;
    HOTA?: number;
    IDF1?: number;
    MOTA?: number;
    MOTP?: number;
    IDSW?: number;
    Frag?: number;
    CLR_FP?: number;
    CLR_FN?: number;
    active_vehicle_count_mae?: number;
    active_vehicle_count_rmse?: number;
    frames?: number;
    generated_events?: number;
    pipeline_fps?: number;
    detector_tracker_fps?: number;
    memory_peak_rss_mb?: number;
    inference_ms?: Record<string, number>;
    cpu_machine_capacity_percent?: number;
    seconds_per_minute_video?: number;
    horizons?: Record<string, Record<string, Scores>>;
    controllers?: Record<string, Record<string, Summary>>;
    mean_delay_reduction_pct?: number;
    delay_reduction_std_pct?: number;
    runs_per_controller?: number;
  };
  results?: {
    horizons?: Record<
      string,
      {
        preview_sensor: string;
        preview: Record<string, string | number | null>[];
      }
    >;
  };
};

function number(value: number | undefined | null, digits = 3) {
  return value == null ? "Unmeasured" : value.toFixed(digits);
}
function Provenance({ item, name }: { item: RealArtifact; name: string }) {
  return (
    <div className="benchmark-provenance">
      <p className="panel-note">{item.scope}</p>
      <p className="panel-note">
        {item.dataset} · revision {item.dataset_version.slice(0, 10)} ·{" "}
        {item.model} · {item.date.slice(0, 10)}
      </p>
      <a
        href={`${API}/api/benchmarks/${name}`}
        target="_blank"
        rel="noreferrer"
      >
        Inspect result & methodology ↗
      </a>
    </div>
  );
}
export function RealBenchmarks({
  artifacts,
}: {
  artifacts: Record<string, RealArtifact>;
}) {
  const [horizon, setHorizon] = useState("5");
  const detection = artifacts.real_detection;
  const tracking = artifacts.real_tracking;
  const analytics = artifacts.real_analytics;
  const forecast = artifacts.real_forecasting;
  const systems = artifacts.real_video_pipeline;
  const signals = artifacts.realistic_signal_control;
  const safety = artifacts.real_safety_qualitative;
  const preview = forecast?.results?.horizons?.[horizon];
  return (
    <section aria-labelledby="real-world-heading">
      <div className="benchmark-section-heading">
        <div>
          <div className="eyebrow">
            ANNOTATIONS / MEASUREMENTS / PUBLISHED SCENARIOS
          </div>
          <h2 id="real-world-heading">Real-world results</h2>
        </div>
        <span className="pill">MEASURED ARTIFACTS</span>
      </div>
      {!detection && !forecast && !signals && (
        <div className="panel benchmark-empty">
          <h3>Real-data artifacts are not installed.</h3>
          <p>
            Prepare the external datasets and run the real evaluation command.
            Scores will appear after actual measurements.
          </p>
          <code>python scripts/evaluate_real.py</code>
        </div>
      )}
      <div className="two-column">
        {detection && (
          <section className="panel">
            <div className="panel-heading">
              UA-DETRAC / PRETRAINED DETECTION
              <span className="pill">REAL DATA</span>
            </div>
            <div className="score-grid">
              {[
                ["mAP@50", detection.metrics.map50],
                ["mAP@50:95", detection.metrics.map50_95],
                ["Precision", detection.metrics.precision],
                ["Recall", detection.metrics.recall],
              ].map(([label, score]) => (
                <div key={String(label)}>
                  <span>{label}</span>
                  <strong>{number(score as number)}</strong>
                </div>
              ))}
            </div>
            <p className="panel-note">
              {Object.values(detection.split.frames_per_sequence || {})
                .reduce((a, b) => a + b, 0)
                .toLocaleString()}{" "}
              annotated frames · {detection.split.sequences?.length} complete
              test sequences · merged vehicle class · untouched 640px pretrained
              baseline.
            </p>
            <Provenance item={detection} name="real_detection" />
          </section>
        )}
        {tracking && (
          <section className="panel">
            <div className="panel-heading">
              UA-DETRAC / PRODUCTION TRACKER
              <span className="pill">REAL DATA</span>
            </div>
            <div className="score-grid">
              {[
                ["IDF1", tracking.metrics.IDF1],
                ["HOTA", tracking.metrics.HOTA],
                ["MOTA", tracking.metrics.MOTA],
                ["MOTP (IoU)", tracking.metrics.MOTP],
              ].map(([label, score]) => (
                <div key={String(label)}>
                  <span>{label}</span>
                  <strong>{number(score as number)}</strong>
                </div>
              ))}
            </div>
            <p className="panel-note">
              {tracking.metrics.IDSW} identity switches ·{" "}
              {tracking.metrics.Frag} fragments · {tracking.metrics.CLR_FP}{" "}
              false positives · {tracking.metrics.CLR_FN} false negatives.
              Official TrackEval aggregation; not the UA-DETRAC challenge
              PR-MOTA protocol.
            </p>
            <Provenance item={tracking} name="real_tracking" />
          </section>
        )}
      </div>
      {analytics && (
        <section className="panel">
          <div className="panel-heading">
            ANNOTATION-DERIVED TRAFFIC COUNTS
            <span className="pill">REAL DATA</span>
          </div>
          <div className="score-grid">
            <div>
              <span>Active vehicle count MAE</span>
              <strong>
                {number(analytics.metrics.active_vehicle_count_mae)}
              </strong>
            </div>
            <div>
              <span>Active vehicle count RMSE</span>
              <strong>
                {number(analytics.metrics.active_vehicle_count_rmse)}
              </strong>
            </div>
          </div>
          <p className="panel-note">
            Per-frame counts compare observed tracked vehicles with annotated
            boxes after the declared ignored-region policy. Physical speed,
            queues, and calibrated safety accuracy remain unvalidated.
          </p>
          <Provenance item={analytics} name="real_analytics" />
        </section>
      )}
      {forecast && (
        <section className="panel">
          <div className="panel-heading">
            METR-LA / CHRONOLOGICAL FORECASTING
            <span className="pill">REAL DATA · MPH</span>
          </div>
          <div className="mode-tabs">
            {["5", "10", "15"].map((h) => (
              <button
                key={h}
                className={horizon === h ? "selected" : ""}
                onClick={() => setHorizon(h)}
                aria-pressed={horizon === h}
              >
                {h} MIN
              </button>
            ))}
          </div>
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>MAE (mph)</th>
                <th>RMSE (mph)</th>
                <th>MAPE, ≥5 mph (%)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(forecast.metrics.horizons?.[horizon] || {}).map(
                ([name, score]) => (
                  <tr key={name}>
                    <td>{name.replaceAll("_", " ")}</td>
                    <td>{number(score.mae)}</td>
                    <td>{number(score.rmse)}</td>
                    <td>{number(score.mape_pct, 2)}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          {preview && (
            <>
              <p className="panel-note">
                Actual versus predicted · fixed sensor {preview.preview_sensor}{" "}
                · first chronological test day · {horizon}-minute horizon.
              </p>
              <TrendChart
                data={preview.preview
                  .filter((_, i) => i % 3 === 0)
                  .map((row, i) => ({
                    t: i * 15,
                    actual: row.actual === null ? null : Number(row.actual),
                    persistence: Number(row.persistence),
                    atlas: Number(row.atlas_gradient_boosting),
                  }))}
                keys={[
                  { key: "actual", name: "Measured speed", color: "#d5b884" },
                  { key: "persistence", name: "Persistence", color: "#8191a0" },
                  {
                    key: "atlas",
                    name: "ATLAS gradient boosting",
                    color: "#9acdbd",
                  },
                ]}
                height={280}
              />
            </>
          )}
          <p className="panel-note">
            All 207 sensors · chronological 70/10/20 split · training-only
            fitting · missing targets masked. Highway speed forecasting does not
            validate intersection vehicle-count forecasts.
          </p>
          <Provenance item={forecast} name="real_forecasting" />
        </section>
      )}
      {systems && (
        <section className="panel">
          <div className="panel-heading">
            COMPLETE PIPELINE / ANNOTATED TRAFFIC FOOTAGE
            <span className="pill">REAL VIDEO · CPU</span>
          </div>
          <div className="score-grid">
            {[
              ["Pipeline FPS", systems.metrics.pipeline_fps],
              ["Inference P50 ms", systems.metrics.inference_ms?.p50],
              ["Inference P95 ms", systems.metrics.inference_ms?.p95],
              ["Peak RSS MB", systems.metrics.memory_peak_rss_mb],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <span>{label}</span>
                <strong>{number(value as number, 1)}</strong>
              </div>
            ))}
          </div>
          <p className="panel-note">
            {systems.metrics.frames?.toLocaleString()} real frames ·{" "}
            {number(systems.metrics.seconds_per_minute_video, 1)} processing
            seconds per minute of footage ·{" "}
            {number(systems.metrics.cpu_machine_capacity_percent, 1)}% logical
            CPU capacity. {systems.hardware.cpu} · {systems.hardware.ram_gb} GB
            RAM.
          </p>
          <Provenance item={systems} name="real_video_pipeline" />
        </section>
      )}
      {safety && (
        <section className="panel">
          <div className="panel-heading">
            SAFETY / REAL FOOTAGE QUALITATIVE CHECK
            <span className="pill">CALIBRATION UNAVAILABLE</span>
          </div>
          <p className="panel-note">
            Safety engine invoked over {safety.metrics.frames?.toLocaleString()}{" "}
            real frames; {safety.metrics.generated_events} generated events with
            physical screens gated off. Zero events does not mean zero
            conflicts. TTC/PET/separation distributions and event replays
            require verified metric calibration. Supervised real-world conflict
            accuracy remains unmeasured.
          </p>
          <Provenance item={safety} name="real_safety_qualitative" />
        </section>
      )}
      {signals && <SignalStudy />}
      {signals && (
        <section className="panel">
          <div className="panel-heading">
            RESCO COLOGNE / HELD-OUT DEMAND PERIOD
            <span className="pill">REAL-WORLD-DERIVED SIMULATION</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Controller</th>
                <th>Mean delay ± SD (s)</th>
                <th>Completed trips</th>
                <th>Mean queue</th>
                <th>Stops / vehicle</th>
                <th>Travel time (s)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(signals.metrics.controllers || {}).map(
                ([name, s]) => (
                  <tr key={name}>
                    <td>{name.replaceAll("_", " ")}</td>
                    <td>
                      {s.mean_delay_s.mean.toFixed(2)} ±{" "}
                      {s.mean_delay_s.std.toFixed(2)}
                    </td>
                    <td>{s.completed_trips.mean.toFixed(1)}</td>
                    <td>{s.mean_queue.mean.toFixed(2)}</td>
                    <td>{s.stops_per_vehicle.mean.toFixed(2)}</td>
                    <td>{s.completed_mean_travel_time_s.mean.toFixed(2)}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          <p className="panel-note">
            {signals.metrics.runs_per_controller} held-out seeds per controller.
            ATLAS delay change versus fixed:{" "}
            {number(signals.metrics.mean_delay_reduction_pct, 1)}% reduction (
            {number(signals.metrics.delay_reduction_std_pct, 1)}{" "}
            percentage-point SD). A negative reduction means higher delay; this
            result is retained. Travel time uses completed trips; delay includes
            unfinished and not-inserted demand.
          </p>
          <Provenance item={signals} name="realistic_signal_control" />
        </section>
      )}
    </section>
  );
}
