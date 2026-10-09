"use client";
import { CityBenchmarks } from "./city-benchmarks";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  BarChart3,
  Download,
  Radar,
  ScanLine,
} from "lucide-react";
import { Shell } from "./shell";
import { TrendChart } from "./charts";
import { useResult } from "./video-workspace";
import { request, API } from "@/lib/api";
import type { Result } from "@/lib/types";
import { RealBenchmarks, type RealArtifact } from "./real-benchmarks";

export function EmptyData({ error }: { error?: string }) {
  return (
    <div className="panel empty-state">
      <ScanLine size={32} strokeWidth={1} />
      <h2>{error ? "The API is unavailable." : "Observations come first."}</h2>
      <p>
        {error ||
          "Process a video in the intersection workspace to populate this view."}
      </p>
      <Link className="button" href="/workspace">
        Open intersection <ArrowUpRight size={15} />
      </Link>
    </div>
  );
}
function SourceNote({ result }: { result: Result }) {
  return (
    <div className="source-note">
      SOURCE / {result.provenance.source} ·{" "}
      {result.metadata.duration.toFixed(1)} s · {result.summary.unique_tracks}{" "}
      unique tracks ·{" "}
      {result.summary.calibrated
        ? "Verified calibration"
        : "Image-space observations"}
    </div>
  );
}
export function AnalyticsPage() {
  const { result, error } = useResult();
  const last = result?.metrics.at(-1);
  return (
    <Shell
      title="The rhythm of the road"
      eyebrow="TRAFFIC / ANALYTICS"
      action={
        result && (
          <a
            className="button secondary"
            href={`${API}/api/videos/${result.video_id}/result`}
            download
          >
            <Download size={15} /> Export observations
          </a>
        )
      }
    >
      {!result ? (
        <EmptyData error={error} />
      ) : (
        <>
          <SourceNote result={result} />
          <div className="metric-grid">
            {[
              ["UNIQUE VEHICLES", result.summary.vehicles, "observed tracks"],
              ["PEDESTRIANS", result.summary.pedestrians, "anonymous tracks"],
              ["CYCLISTS", result.summary.cyclists, "observed tracks"],
              ["MAXIMUM QUEUE", result.summary.max_queue, "stopped vehicles"],
            ].map(([label, value, unit]) => (
              <div className="stat-card" key={label}>
                <div className="stat-label">{label}</div>
                <div className="stat-value">
                  {value}
                  <span>{unit}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="two-column">
            <section className="panel">
              <div className="panel-heading">
                TRAFFIC COMPOSITION OVER TIME
                <span className="pill">OBSERVED</span>
              </div>
              <TrendChart
                data={result.metrics
                  .filter((_, i) => i % 5 === 0)
                  .map((m) => ({
                    t: +m.t.toFixed(1),
                    vehicles: m.vehicles,
                    pedestrians: m.pedestrians,
                    cyclists: m.cyclists,
                  }))}
                keys={[
                  { key: "vehicles", color: "#9acdbd", name: "Vehicles" },
                  { key: "pedestrians", color: "#d5b884", name: "Pedestrians" },
                  { key: "cyclists", color: "#b6a4d5", name: "Cyclists" },
                ]}
                height={270}
                area
              />
            </section>
            <section className="panel">
              <div className="panel-heading">
                MOTION PROFILE<span className="pill">{last?.speed_unit}</span>
              </div>
              <TrendChart
                data={result.metrics
                  .filter((_, i) => i % 5 === 0)
                  .map((m) => ({
                    t: +m.t.toFixed(1),
                    mean: m.average_speed,
                    median: m.median_speed,
                  }))}
                keys={[
                  { key: "mean", name: "Mean speed", color: "#8faecf" },
                  { key: "median", name: "Median speed", color: "#91c3b2" },
                ]}
                height={270}
              />
            </section>
          </div>
          <div className="two-column">
            <section className="panel">
              <div className="panel-heading">STOPPED QUEUE & DWELL TIME</div>
              <TrendChart
                data={result.metrics
                  .filter((_, i) => i % 5 === 0)
                  .map((m) => ({
                    t: +m.t.toFixed(1),
                    queue: m.queue_length,
                    dwell: m.dwell_time,
                  }))}
                keys={[
                  { key: "queue", name: "Queue (vehicles)", color: "#d4b581" },
                  { key: "dwell", name: "Mean dwell (s)", color: "#91b7cf" },
                ]}
                height={240}
              />
            </section>
            <section className="panel">
              <div className="panel-heading">OBJECT CLASSES</div>
              <div className="composition">
                {Object.entries(result.summary.classes).map(([cls, n]) => (
                  <div key={cls}>
                    <span>{cls}</span>
                    <div>
                      <i
                        style={{
                          width: `${(n / result.summary.unique_tracks) * 100}%`,
                        }}
                      />
                    </div>
                    <strong>{n}</strong>
                  </div>
                ))}
              </div>
              <p className="panel-note">
                Counts represent unique track IDs. Occlusion and identity
                fragmentation can bias counts. Rates in short clips are
                normalized observation rates, not validated arrival demand.
              </p>
            </section>
          </div>
          <p className="provenance-note">
            Throughput and turning counts require an intersection region. Queue:
            vehicle speed below stop threshold for at least one second. Pixel
            speed is an image-space motion proxy.
          </p>
        </>
      )}
    </Shell>
  );
}
export function SafetyPage() {
  const { result, error } = useResult();
  const [selected, setSelected] = useState(0);
  const event = result?.events[selected];
  return (
    <Shell title="Every interaction matters" eyebrow="SAFETY / CONFLICT REVIEW">
      {!result ? (
        <EmptyData error={error} />
      ) : (
        <>
          <SourceNote result={result} />
          <div className="safety-intro panel">
            <Radar size={26} />
            <div>
              <h2>
                {result.summary.calibrated
                  ? `${result.events.length} candidate events for review`
                  : "Calibrate before evaluating physical risk."}
              </h2>
              <p>
                {result.summary.calibrated
                  ? "Constant-velocity projections screen potential conflicts. Replay each event before interpreting it."
                  : "The source has no verified road-plane calibration. TTC and meter-scale separation are intentionally unavailable. Add measured control points in Camera setup."}
              </p>
            </div>
            <Link href="/workspace" className="button secondary">
              Open camera setup <ArrowUpRight size={14} />
            </Link>
          </div>
          <div className="two-column">
            <section className="panel">
              <div className="panel-heading">
                EVENT LOG
                <span className="pill">{result.events.length} EVENTS</span>
              </div>
              {result.events.length ? (
                <div className="event-list">
                  {result.events.map((e, i) => (
                    <button
                      key={e.id}
                      onClick={() => setSelected(i)}
                      className={i === selected ? "selected" : ""}
                    >
                      <span className={`severity ${e.severity}`}>
                        {e.severity}
                      </span>
                      <div>
                        <strong>{e.type.replaceAll("_", " ")}</strong>
                        <small>
                          {e.t.toFixed(1)}s · tracks{" "}
                          {e.participants.join(" / ")}
                        </small>
                      </div>
                      <ArrowUpRight size={15} />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state compact-empty">
                  <Radar size={28} />
                  <h3>
                    {result.summary.calibrated
                      ? "No candidate conflicts detected."
                      : "Physical conflict analysis disabled."}
                  </h3>
                  <p>
                    {result.summary.calibrated
                      ? "An empty log is a valid observation, not evidence of safety."
                      : "Verify metric calibration to enable safety analysis."}
                  </p>
                </div>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">EVENT REPLAY</div>
              {event ? (
                <div className="event-detail">
                  <video
                    key={event.id}
                    controls
                    muted
                    src={`${API}/api/videos/${result.video_id}/source#t=${Math.max(0, event.t - 2)},${event.t + 3}`}
                  />
                  <h3>{event.explanation}</h3>
                  <div className="event-metrics">
                    <div>
                      <span>TTC</span>
                      <strong>
                        {event.ttc === null ? "—" : `${event.ttc}s`}
                      </strong>
                    </div>
                    <div>
                      <span>Separation</span>
                      <strong>
                        {event.separation === null
                          ? "—"
                          : `${event.separation}m`}
                      </strong>
                    </div>
                    <div>
                      <span>Risk screen</span>
                      <strong>{(event.risk_score * 100).toFixed(0)}%</strong>
                    </div>
                  </div>
                  {event.ml_score !== null && (
                    <p className="panel-note">
                      Experimental synthetic-model probability:{" "}
                      {(event.ml_score * 100).toFixed(1)}%. No field validation;
                      not a collision probability.
                    </p>
                  )}
                </div>
              ) : (
                <div className="empty-state compact-empty">
                  <p>
                    Select a detected event to replay its participants and
                    inspect the structured risk features.
                  </p>
                </div>
              )}
            </section>
          </div>
          <div className="methodology panel">
            <div className="eyebrow">
              METHOD / CONSTANT-VELOCITY CLOSEST APPROACH
            </div>
            <h3>Relative motion → projected separation → reviewable alerts.</h3>
            <p>
              Tracks are smoothed with a timestamp-aware least-squares estimate.
              Candidate pairs must be approaching within five seconds and three
              meters, with relative speed above 1 m/s. Hard braking screens
              deceleration below −4 m/s². Severity is a screening level. The
              optional ML score is trained on separately generated synthetic
              conflict scenarios.
            </p>
          </div>
        </>
      )}
    </Shell>
  );
}
type ForecastArtifacts = {
  real_world?: Record<string, RealArtifact>;
  forecast?: {
    scope: string;
    horizons: Record<
      string,
      {
        models: Record<string, { mae: number; rmse: number }>;
        preview: Record<string, number>[];
      }
    >;
  };
};
export function ForecastPage() {
  const { result, error } = useResult();
  const [artifact, setArtifact] = useState<ForecastArtifacts>({});
  const [horizon, setHorizon] = useState("5");
  useEffect(() => {
    request<ForecastArtifacts>("/api/benchmarks")
      .then(setArtifact)
      .catch(() => {});
  }, []);
  const evaluation = artifact.forecast?.horizons[horizon];
  return (
    <Shell
      title="Look a few minutes ahead"
      eyebrow="PREDICTION / SHORT-TERM FORECAST"
    >
      {result ? (
        <>
          <SourceNote result={result} />
          <section className="panel forecast-status">
            <div className="eyebrow">
              YOUR SOURCE /{" "}
              {result.forecast.status.toUpperCase().replaceAll("_", " ")}
            </div>
            <h2>
              {result.forecast.status === "ready"
                ? "A causal forecast from observed traffic."
                : "Good predictions need enough history."}
            </h2>
            <p>{result.forecast.reason || result.forecast.scope}</p>
            {result.forecast.predictions.length > 0 && (
              <div className="metric-grid">
                {result.forecast.predictions.map((p) => (
                  <div className="stat-card" key={p.horizon_minutes}>
                    <div className="stat-label">
                      +{p.horizon_minutes} MINUTES
                    </div>
                    <div className="stat-value">
                      {p.value}
                      <span>active vehicles</span>
                    </div>
                    <p>
                      {p.lower}–{p.upper} exploratory spread
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        <EmptyData error={error} />
      )}
      {artifact.real_world?.real_forecasting && (
        <RealBenchmarks
          artifacts={{ real_forecasting: artifact.real_world.real_forecasting }}
        />
      )}
      {evaluation && (
        <>
          <div className="section-intro">
            <div>
              <div className="eyebrow">
                CONTROLLED / SYNTHETIC FORECAST EXPERIMENT
              </div>
              <h2>Actual vs. predicted</h2>
              <p>{artifact.forecast?.scope}</p>
            </div>
            <div className="mode-tabs">
              {["5", "10", "15"].map((h) => (
                <button
                  className={h === horizon ? "selected" : ""}
                  key={h}
                  onClick={() => setHorizon(h)}
                >
                  +{h} MIN
                </button>
              ))}
            </div>
          </div>
          <section className="panel chart-panel">
            <TrendChart
              data={evaluation.preview}
              x="minute"
              keys={[
                { key: "actual", name: "Synthetic actual", color: "#b8c8ce" },
                {
                  key: "gradient_boosting",
                  name: "Gradient boosting",
                  color: "#9ecfbb",
                },
                { key: "last_value", name: "Last value", color: "#b9a7d4" },
              ]}
              height={320}
            />
          </section>
          <section className="panel">
            <div className="panel-heading">
              TEMPORAL HOLDOUT / HORIZON {horizon} MIN
            </div>
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>Data scope</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(evaluation.models).map(([name, scores]) => (
                  <tr key={name}>
                    <td>{name.replaceAll("_", " ")}</td>
                    <td>{scores.mae.toFixed(3)}</td>
                    <td>{scores.rmse.toFixed(3)}</td>
                    <td>Synthetic traffic sequence</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <p className="provenance-note">
            Training precedes validation and test. Targets crossing the training
            boundary are purged. No experiment score is presented as accuracy on
            uploaded footage.
          </p>
        </>
      )}
    </Shell>
  );
}
type RiskScore = {
  auroc: number;
  auprc: number;
  f1: number;
  brier: number;
  ece: number;
  precision: number;
  recall: number;
  confusion_matrix: number[][];
};
type Benchmarks = {
  real_world?: Record<string, RealArtifact>;
  streams?: {
    scope: string;
    scenarios: {
      concurrent_streams: number;
      total_frames: number;
      wall_seconds: number;
      aggregate_fps: number;
    }[];
  };
  sumo?: {
    scope: string;
    sumo_version: string;
    seed: number;
    runs: Record<
      string,
      {
        greens: number[];
        mean_delay_s: number;
        vehicles_cleared: number;
        scheduled_demand: number;
        unfinished_or_not_inserted: number;
      }
    >;
  };
  pipeline?: {
    scope: string;
    performance: Result["performance"] & { memory_rss_mb: number };
    summary: Result["summary"];
  };
  risk?: { scope: string; models: Record<string, RiskScore>; selected: string };
  cv?: {
    scope: string;
    precision: number;
    recall: number;
    map50: number;
    map50_95: number;
    model: string;
  };
  tracking?: { scope: string; metrics: Record<string, number> };
  simulation?: {
    scope: string;
    mean_delay_reduction_pct: number;
    seeds: number[];
    runs: {
      seed: number;
      runs: {
        policy: string;
        metrics: {
          delay: number;
          throughput: number;
          mean_queue: number;
          pedestrian_wait: number;
          stops: number;
        };
      }[];
    }[];
  };
  load?: {
    scope: string;
    scenarios: {
      clients: number;
      requests: number;
      errors: number;
      rps: number;
      latency_ms: Record<string, number>;
    }[];
  };
};
export function BenchmarkPage() {
  const [data, setData] = useState<Benchmarks>({});
  const [error, setError] = useState("");
  useEffect(() => {
    request<Benchmarks>("/api/benchmarks")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  const p = data.pipeline?.performance;
  const r = data.risk?.models[data.risk.selected];
  return (
    <Shell
      title="Evidence, not estimates"
      eyebrow="ENGINEERING / EVALUATION"
      action={
        <a
          className="button secondary"
          href={`${API}/api/benchmarks`}
          target="_blank"
          rel="noreferrer"
        >
          <Download size={15} /> JSON artifacts
        </a>
      }
    >
      <div className="evaluation-intro">
        <BarChart3 size={23} />
        <p>
          Every number below is loaded from a generated evaluation artifact.
          Each section states its data source and evaluation scope. Missing
          ground truth means no accuracy claim.
        </p>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <CityBenchmarks />
      <RealBenchmarks artifacts={data.real_world || {}} />
      {p && (
        <section className="panel">
          <div className="panel-heading">
            ORIGINAL MIXKIT RUN / ARCHIVED MEASUREMENT
            <span className="pill">REAL VIDEO · CPU</span>
          </div>
          <div className="score-grid">
            <div>
              <span>Sampled FPS</span>
              <strong>{p.processed_fps.toFixed(1)}</strong>
            </div>
            <div>
              <span>Inference P95 (ms)</span>
              <strong>{p.inference_ms.p95.toFixed(0)}</strong>
            </div>
          </div>
          <p className="panel-note">
            Original aerial time-lapse run remains available as a separate
            hardware/configuration measurement. {p.model} · {p.device}.
            Detection quality is evaluated on UA-DETRAC above.
          </p>
        </section>
      )}
      <div className="benchmark-section-heading">
        <div>
          <div className="eyebrow">SEEDED EXPERIMENTS / INTEGRATION CHECKS</div>
          <h2>Controlled / synthetic results</h2>
        </div>
        <span className="pill">SEPARATE EVALUATION</span>
      </div>
      <div className="metric-grid">
        {[
          {
            label: "SYNTHETIC RISK AUPRC",
            value: r?.auprc.toFixed(3) || "—",
            unit: "AUPRC",
            detail: "Independent generated test scenarios",
          },
          {
            label: "SYNTHETIC RISK BRIER",
            value: r?.brier.toFixed(3) || "—",
            unit: "score",
            detail: "Probability calibration on generated data",
          },
          {
            label: "SYNTHETIC RISK AUROC",
            value: r?.auroc.toFixed(3) || "—",
            unit: "AUROC",
            detail: "Independent generated test scenarios",
          },
          {
            label: "SIMULATED DELAY CHANGE",
            value: data.simulation?.mean_delay_reduction_pct.toFixed(1) || "—",
            unit: "% reduction",
            detail: "Held-out arrival seeds",
          },
        ].map((m) => (
          <div className="stat-card" key={m.label}>
            <div className="stat-label">{m.label}</div>
            <div className="stat-value">
              {m.value}
              <span>{m.unit}</span>
            </div>
            <div className="stat-detail">{m.detail}</div>
          </div>
        ))}
      </div>
      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            DETECTION / CV
            <span className="pill">
              {data.cv
                ? "REAL DATA · COCO8 SMOKE CHECK"
                : "GROUND TRUTH REQUIRED"}
            </span>
          </div>
          {data.cv ? (
            <>
              <div className="score-grid">
                {[
                  ["Precision", data.cv.precision],
                  ["Recall", data.cv.recall],
                  ["mAP@50", data.cv.map50],
                  ["mAP@50:95", data.cv.map50_95],
                ].map(([n, v]) => (
                  <div key={n}>
                    <span>{n}</span>
                    <strong>{Number(v).toFixed(3)}</strong>
                  </div>
                ))}
              </div>
              <p className="panel-note">{data.cv.scope}</p>
            </>
          ) : (
            <div className="benchmark-empty">
              <h3>Accuracy is not inferred from a demo.</h3>
              <p>
                Run detection evaluation on a labeled dataset. The optional
                COCO8 command is a small smoke evaluation; it cannot support a
                traffic-domain accuracy claim.
              </p>
              <code>atlas evaluate --only cv</code>
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            TRACKING / ADDITIONAL ANNOTATION FILES
          </div>
          {data.tracking ? (
            <>
              <div className="score-grid">
                {Object.entries(data.tracking.metrics).map(([n, v]) => (
                  <div key={n}>
                    <span>{n}</span>
                    <strong>{v.toFixed(3)}</strong>
                  </div>
                ))}
              </div>
              <p className="panel-note">{data.tracking.scope}</p>
            </>
          ) : (
            <div className="benchmark-empty">
              <h3>UA-DETRAC results are shown above.</h3>
              <p>
                Evaluate additional datasets using matching MOT-format files and
                official TrackEval. The analytic metric self-test remains
                separate from real traffic quality.
              </p>
              <code>atlas evaluate --only tracking --gt GT --pred PRED</code>
            </div>
          )}
        </section>
      </div>
      {data.risk && (
        <section className="panel">
          <div className="panel-heading">
            CONFLICT RISK / MODEL COMPARISON
            <span className="pill">SYNTHETIC ONLY</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>AUROC</th>
                <th>AUPRC</th>
                <th>F1</th>
                <th>Brier</th>
                <th>ECE</th>
                <th>Precision</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.risk.models).map(([name, s]) => (
                <tr key={name}>
                  <td>{name.replaceAll("_", " ")}</td>
                  {[s.auroc, s.auprc, s.f1, s.brier, s.ece, s.precision].map(
                    (v, i) => (
                      <td key={i}>{v.toFixed(3)}</td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="risk-bottom">
            <p className="panel-note">
              {data.risk.scope}
              <br />
              Validation chooses alert thresholds and model. Independent seeds
              produce train, validation, and test sets.
            </p>
            {r && (
              <div className="confusion">
                <span>CONFUSION MATRIX · TRUE × PREDICTED</span>
                <div>
                  {r.confusion_matrix.flat().map((n, i) => (
                    <strong key={i}>
                      {n}
                      <small>{["TN", "FP", "FN", "TP"][i]}</small>
                    </strong>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}
      {data.simulation && (
        <section className="panel">
          <div className="panel-heading">
            SIGNAL CONTROL / EQUIVALENT DEMAND
            <span className="pill">
              {data.simulation.seeds.length} TEST SEEDS
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Seed</th>
                <th>Policy</th>
                <th>Mean delay (s)</th>
                <th>Cleared vehicles</th>
                <th>Mean queue</th>
                <th>Pedestrian wait (s)</th>
                <th>Stops / vehicle</th>
              </tr>
            </thead>
            <tbody>
              {data.simulation.runs.flatMap((run) =>
                run.runs.map((s) => (
                  <tr key={`${run.seed}-${s.policy}`}>
                    <td>{run.seed}</td>
                    <td>{s.policy}</td>
                    <td>{s.metrics.delay.toFixed(2)}</td>
                    <td>{s.metrics.throughput}</td>
                    <td>{s.metrics.mean_queue.toFixed(2)}</td>
                    <td>{s.metrics.pedestrian_wait.toFixed(2)}</td>
                    <td>{s.metrics.stops.toFixed(2)}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
          <p className="panel-note">{data.simulation.scope}</p>
        </section>
      )}
      {data.streams && (
        <section className="panel">
          <div className="panel-heading">
            CONCURRENT CV / MEASURED CPU
            <span className="pill">REAL VIDEO / CONTROLLED LOAD</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Streams</th>
                <th>Processed frames</th>
                <th>Wall time (s)</th>
                <th>Aggregate sampled FPS</th>
              </tr>
            </thead>
            <tbody>
              {data.streams.scenarios.map((s) => (
                <tr key={s.concurrent_streams}>
                  <td>{s.concurrent_streams}</td>
                  <td>{s.total_frames}</td>
                  <td>{s.wall_seconds.toFixed(2)}</td>
                  <td>{s.aggregate_fps.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="panel-note">{data.streams.scope}</p>
        </section>
      )}
      {data.sumo && (
        <section className="panel">
          <div className="panel-heading">
            INDEPENDENT SUMO CROSS-CHECK
            <span className="pill">
              CONTROLLED SIMULATION / SEED {data.sumo.seed}
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Policy</th>
                <th>Green splits (s)</th>
                <th>Reported mean delay (s)</th>
                <th>Cleared vehicles</th>
                <th>Scheduled demand</th>
                <th>Unfinished / not inserted</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.sumo.runs).map(([name, s]) => (
                <tr key={name}>
                  <td>{name.replaceAll("_", " ")}</td>
                  <td>{s.greens.join(" / ")}</td>
                  <td>{s.mean_delay_s.toFixed(2)}</td>
                  <td>{s.vehicles_cleared}</td>
                  <td>{s.scheduled_demand}</td>
                  <td>{s.unfinished_or_not_inserted}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="panel-note">
            {data.sumo.sumo_version}. {data.sumo.scope} Delay excludes vehicles
            SUMO had not inserted by the horizon; compare throughput and
            unfinished demand alongside delay.
          </p>
        </section>
      )}
      {data.load && (
        <section className="panel">
          <div className="panel-heading">
            API LOAD / MEASURED
            <span className="pill">CONTROLLED REQUEST LOAD</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Concurrent clients</th>
                <th>Requests</th>
                <th>Errors</th>
                <th>Requests / s</th>
                <th>P50 ms</th>
                <th>P95 ms</th>
                <th>P99 ms</th>
              </tr>
            </thead>
            <tbody>
              {data.load.scenarios.map((s) => (
                <tr key={s.clients}>
                  <td>{s.clients}</td>
                  <td>{s.requests}</td>
                  <td>{s.errors}</td>
                  <td>{s.rps.toFixed(1)}</td>
                  {[50, 95, 99].map((q) => (
                    <td key={q}>{s.latency_ms[`p${q}`].toFixed(1)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="panel-note">{data.load.scope}</p>
        </section>
      )}
      <div className="methodology panel">
        <div className="eyebrow">REPRODUCIBILITY</div>
        <h3>Raw artifacts belong beside every claim.</h3>
        <p>
          Run <code>atlas evaluate</code> for risk, forecasting, and signal
          experiments. Run <code>atlas benchmark VIDEO</code> for inference
          performance. Use <code>python scripts/load_test.py</code> with the API
          running. Outputs are written to <code>artifacts/</code>.
        </p>
      </div>
    </Shell>
  );
}
