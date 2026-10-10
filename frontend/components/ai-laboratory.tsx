"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { request } from "@/lib/api";
import { Shell } from "./shell";
import { CityBenchmarks } from "./city-benchmarks";
import { EvidenceLoading } from "./evidence-loading";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";

type Model = {
  model: string;
  selected_on_validation: boolean;
  validation_mae_mph: number;
  metrics: { mae: number; rmse: number; valid_targets: number };
  model_bytes: number;
  all_207_sensor_latency_ms_p95: number;
};
type Study = {
  experiment_id: string;
  recorded_at: string;
  limitations: string[];
  results: {
    horizon_minutes: number;
    selected: string;
    models: Model[];
    persistence: { mae: number };
  }[];
  preview: {
    sensor: string;
    horizon_minutes: number;
    model: string;
    points: {
      timestamp: string;
      actual: number | null;
      predicted: number;
      persistence: number;
    }[];
  }[];
};
type VisionMetrics = {
  detection: {
    map50: number;
    map50_95: number;
    precision: number;
    recall: number;
  };
  tracking: { IDF1: number; HOTA: number; IDSW: number };
  stage_performance: {
    detector_tracker_fps: number;
    memory_peak_rss_mb: number;
  };
};
type GraphStudy = {
  experiment_id: string;
  limitations: string[];
  preview: Study["preview"];
  results: {
    horizon_minutes: number;
    selected_on_validation: string;
    models: {
      model: string;
      validation_mae_mph: number;
      metrics: Model["metrics"];
      parameters: number;
      checkpoint_bytes: number;
      training_seconds: number;
      all_207_sensor_forward_ms_p95: number;
    }[];
  }[];
  paired_analysis: {
    horizon_minutes: number;
    baseline: string;
    reduction_pct: number;
    paired_day_block_ci95_pct: number[];
  }[];
};
type VisionStudy = {
  experiment_id: string;
  original: VisionMetrics;
  candidate: VisionMetrics;
  promotion: string;
  performance_scope: string;
  limits: string[];
};
type FlowStudy = {
  experiment_id: string;
  scope: string;
  limitations: string[];
  rows: {
    sequence: string;
    line_y_normalized: number;
    direction: string;
    bin_seconds: number;
    bins: number;
    observed_crossings: number;
    predicted_crossings: number;
    count_mae_per_bin: number;
    gt_bin_counts: number[];
    predicted_bin_counts: number[];
  }[];
};
type PerceptionV4 = {
  experiment_id: string;
  scope: string;
  limitations: string[];
  promoted: boolean;
  rows: {
    candidate: string;
    metrics: {
      IDF1: number;
      HOTA: number;
      IDSW: number;
      Frag: number;
      visible_vehicle_count_mae: number;
      gate_count_mae_per_2_4s_bin: number;
      process_cpu_seconds: number;
      wall_seconds: number;
      frames: number;
      inferred_frames: number;
    };
    sequences: {
      sequence: string;
      rss_peak_mib: number;
      frame_output_ms: { p50: number; p95: number };
    }[];
  }[];
};
export function AILaboratory() {
  const [data, setData] = useState<Study | null>(null);
  const [error, setError] = useState("");
  const [horizon, setHorizon] = useState(5);
  const [sensor, setSensor] = useState<string | null>(null);
  const [vision, setVision] = useState<VisionStudy | null>(null);
  const [flow, setFlow] = useState<FlowStudy | null>(null);
  const [perceptionError, setPerceptionError] = useState("");
  const [flowRow, setFlowRow] = useState(0);
  const [graph, setGraph] = useState<GraphStudy | null>(null);
  const [graphError, setGraphError] = useState("");
  const [family, setFamily] = useState("classical");
  const [perceptionV4, setPerceptionV4] = useState<PerceptionV4 | null>(null);
  const [perceptionV4Error, setPerceptionV4Error] = useState("");
  useEffect(() => {
    let active = true;
    request<Study>("/api/operations/models/forecast")
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    request<GraphStudy>("/api/operations/models/graph")
      .then((r) => {
        if (active) setGraph(r);
      })
      .catch((e: Error) => {
        if (active) setGraphError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    request<PerceptionV4>("/api/operations/models/vision-v4")
      .then((result) => {
        if (active) setPerceptionV4(result);
      })
      .catch(() => {
        if (active)
          setPerceptionV4Error(
            "New tracking evidence is unavailable; the retained original and detector comparisons remain below.",
          );
      });
    Promise.all([
      request<VisionStudy>("/api/operations/models/vision"),
      request<FlowStudy>("/api/operations/visual-flow"),
    ])
      .then(([v, f]) => {
        if (active) {
          setVision(v);
          setFlow(f);
        }
      })
      .catch((e: Error) => {
        if (active) setPerceptionError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  const view = (family === "neural" ? graph : data)?.preview.find(
    (p) =>
      p.horizon_minutes === horizon && (sensor === null || p.sensor === sensor),
  );
  return (
    <Shell title="AI laboratory" eyebrow="MODELS / HOLDOUTS / REGRESSIONS">
      <p className="city-notice">
        Inspect measured model behavior and failed experiments. Highway
        forecasting, annotated traffic-video accuracy, and exploratory signal
        simulation have separate datasets and acceptance criteria.
      </p>
      <section
        className="city-panel laboratory-primary-panel"
        aria-busy={!graph && !graphError}
      >
        <h2>Learned directional graph forecasting</h2>
        <p>
          A compact neural model learns local, upstream and downstream messages
          over the pinned METR-LA sensor graph. The matched temporal MLP uses
          the same sampled origins and training settings. Models and epochs are
          selected by validation MAE.
        </p>
        {graphError && (
          <p role="alert">Neural evidence unavailable: {graphError}</p>
        )}
        {!graph && !graphError && (
          <EvidenceLoading label="Loading measured neural comparison…" />
        )}
        {graph && (
          <>
            <p>
              Experiment {graph.experiment_id} · 207 highway sensors · CPU-only.
            </p>
            <div
              className="table-wrap"
              role="region"
              aria-label="Neural forecast comparison"
              tabIndex={0}
            >
              <table aria-label="Neural graph model evaluation">
                <thead>
                  <tr>
                    <th>Horizon</th>
                    <th>Candidate</th>
                    <th>Validation MAE</th>
                    <th>Test MAE</th>
                    <th>Test RMSE</th>
                    <th>Parameters</th>
                    <th>Forward p95</th>
                    <th>Train time</th>
                  </tr>
                </thead>
                <tbody>
                  {graph.results.flatMap((h) =>
                    h.models.map((m) => (
                      <tr key={`${h.horizon_minutes}:${m.model}`}>
                        <td>{h.horizon_minutes} min</td>
                        <td>
                          {m.model.replaceAll("_", " ")}
                          {h.selected_on_validation === m.model
                            ? " · selected"
                            : " · alternative"}
                        </td>
                        <td>{m.validation_mae_mph.toFixed(3)} mph</td>
                        <td>{m.metrics.mae.toFixed(3)} mph</td>
                        <td>{m.metrics.rmse.toFixed(3)} mph</td>
                        <td>{m.parameters.toLocaleString()}</td>
                        <td>{m.all_207_sensor_forward_ms_p95.toFixed(3)} ms</td>
                        <td>{m.training_seconds.toFixed(2)} s</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
            <ul>
              {graph.paired_analysis.map((p) => (
                <li key={`${p.horizon_minutes}:${p.baseline}`}>
                  {p.horizon_minutes} min vs {p.baseline.replaceAll("_", " ")}:{" "}
                  {p.reduction_pct.toFixed(2)}% MAE reduction; paired day-block
                  95% interval [{p.paired_day_block_ci95_pct[0].toFixed(2)},{" "}
                  {p.paired_day_block_ci95_pct[1].toFixed(2)}]%. Shared
                  historical test period; external replication pending.
                </li>
              ))}
            </ul>
            <ul>
              {graph.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section className="city-panel">
        <h2>Spatiotemporal forecasting</h2>
        <p>
          Graph-assisted gradient boosting uses past sensor speeds, static
          road-network neighbors, training-only sensor statistics, and calendar
          context. These classical models provide an additional comparison
          against the learned graph model above.
        </p>
        {error && <p role="alert">Model evidence unavailable: {error}</p>}
        {!data && !error && (
          <p role="status">Loading actual METR-LA model evaluation…</p>
        )}
        {data && (
          <>
            <p>
              Experiment {data.experiment_id} · {data.recorded_at} · model
              selection uses validation MAE.
            </p>
            <div
              className="table-wrap"
              role="region"
              aria-label="Classical forecast comparison"
              tabIndex={0}
            >
              <table aria-label="Forecast model evaluation">
                <thead>
                  <tr>
                    <th>Horizon</th>
                    <th>Candidate</th>
                    <th>Validation MAE</th>
                    <th>Test MAE</th>
                    <th>Test RMSE</th>
                    <th>207-sensor p95</th>
                    <th>Model size</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.flatMap((h) =>
                    h.models.map((m) => (
                      <tr key={`${h.horizon_minutes}:${m.model}`}>
                        <td>{h.horizon_minutes} min</td>
                        <td>
                          {m.model.replaceAll("_", " ")}
                          {m.selected_on_validation
                            ? " · selected"
                            : " · alternative"}
                        </td>
                        <td>{m.validation_mae_mph.toFixed(3)} mph</td>
                        <td>{m.metrics.mae.toFixed(3)} mph</td>
                        <td>{m.metrics.rmse.toFixed(3)} mph</td>
                        <td>{m.all_207_sensor_latency_ms_p95.toFixed(2)} ms</td>
                        <td>{(m.model_bytes / 1024).toFixed(0)} KiB</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
            <div className="city-toolbar">
              <label>
                Preview model family{" "}
                <select
                  aria-label="Forecast model family"
                  value={family}
                  onChange={(e) => setFamily(e.target.value)}
                >
                  <option value="classical">Graph-assisted boosting</option>
                  <option value="neural" disabled={!graph}>
                    Learned directional GNN
                  </option>
                </select>
              </label>
              <label>
                Forecast horizon
                <select
                  aria-label="Laboratory forecast horizon"
                  value={horizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                >
                  {data.results.map((h) => (
                    <option key={h.horizon_minutes} value={h.horizon_minutes}>
                      {h.horizon_minutes} minutes
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Preview sensor
                <select
                  aria-label="Forecast preview sensor"
                  value={sensor ?? view?.sensor ?? ""}
                  onChange={(e) => setSensor(e.target.value)}
                >
                  {[...new Set(data.preview.map((p) => p.sensor))].map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
            </div>
            {view ? (
              <div style={{ height: 290 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={view.points}>
                    <CartesianGrid stroke="#263a42" />
                    <XAxis dataKey="timestamp" hide />
                    <YAxis
                      label={{
                        value: "mph",
                        position: "insideLeft",
                        angle: -90,
                      }}
                    />
                    <Tooltip />
                    <Legend />
                    <Line
                      dataKey="actual"
                      name="Actual observed speed"
                      stroke="#e5ecef"
                      dot={false}
                      connectNulls={false}
                    />
                    <Line
                      dataKey="predicted"
                      name="Validation-selected forecast"
                      stroke="#7adac0"
                      dot={false}
                    />
                    <Line
                      dataKey="persistence"
                      name="Persistence"
                      stroke="#97a8ce"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p>No recorded preview for this sensor and horizon.</p>
            )}
            <p>
              The first chronological test-day preview is fixed, not selected
              for favorable errors. The full evaluation covers all 207 sensors.
              Missing observations stay missing in the plot.
            </p>
            <ul>
              {data.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </>
        )}
      </section>
      <CityBenchmarks />
      <section className="city-panel">
        <h2>Tracking quality and adaptive inference</h2>
        <p>
          Actual ATLAS 4 candidates are evaluated on the same complete
          historical annotated sequences. A quality improvement and a CPU cost
          improvement are separate acceptance decisions.
        </p>
        {perceptionV4Error && <p role="status">{perceptionV4Error}</p>}
        {perceptionV4 && (
          <>
            <p>
              {perceptionV4.experiment_id} · {perceptionV4.scope}.
            </p>
            <div
              className="table-wrap"
              role="region"
              aria-label="Advanced tracking comparison scroll area"
              tabIndex={0}
            >
              <table aria-label="Advanced tracking and inference comparison">
                <thead>
                  <tr>
                    <th scope="col">Candidate</th>
                    <th scope="col">IDF1</th>
                    <th scope="col">HOTA</th>
                    <th scope="col">ID switches</th>
                    <th scope="col">Fragmentation</th>
                    <th scope="col">Actual inferences</th>
                    <th scope="col">Process CPU</th>
                    <th scope="col">Wall time</th>
                  </tr>
                </thead>
                <tbody>
                  {perceptionV4.rows.map((row) => (
                    <tr key={row.candidate}>
                      <th scope="row">{row.candidate.replaceAll("_", " ")}</th>
                      <td>{row.metrics.IDF1.toFixed(3)}</td>
                      <td>{row.metrics.HOTA.toFixed(3)}</td>
                      <td>{row.metrics.IDSW}</td>
                      <td>{row.metrics.Frag}</td>
                      <td>
                        {row.metrics.inferred_frames.toLocaleString()} /{" "}
                        {row.metrics.frames.toLocaleString()}
                      </td>
                      <td>{row.metrics.process_cpu_seconds.toFixed(1)} s</td>
                      <td>{row.metrics.wall_seconds.toFixed(1)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              BoT-SORT improves identity continuity at higher measured
              processing cost. Adaptive inference reduces detector calls but
              does not demonstrate a CPU-time improvement and reduces HOTA.
              Production ByteTrack is retained; no candidate is automatically
              promoted.
            </p>
            <details className="tracking-cost-details">
              <summary>
                Per-sequence latency, memory and traffic-count error
              </summary>
              <div
                className="table-wrap"
                role="region"
                aria-label="Tracking sequence cost scroll area"
                tabIndex={0}
              >
                <table aria-label="Per-sequence tracking cost">
                  <thead>
                    <tr>
                      <th scope="col">Candidate / sequence</th>
                      <th scope="col">Output p50</th>
                      <th scope="col">Output p95</th>
                      <th scope="col">Peak RSS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {perceptionV4.rows.flatMap((row) =>
                      row.sequences.map((sequence) => (
                        <tr key={`${row.candidate}:${sequence.sequence}`}>
                          <th scope="row">
                            {row.candidate} · {sequence.sequence}
                          </th>
                          <td>{sequence.frame_output_ms.p50.toFixed(1)} ms</td>
                          <td>{sequence.frame_output_ms.p95.toFixed(1)} ms</td>
                          <td>{sequence.rss_peak_mib.toFixed(1)} MiB</td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
              <ul>
                {perceptionV4.rows.map((row) => (
                  <li key={row.candidate}>
                    {row.candidate}: visible vehicle-count MAE{" "}
                    {row.metrics.visible_vehicle_count_mae.toFixed(3)} per
                    frame; gate-count MAE{" "}
                    {row.metrics.gate_count_mae_per_2_4s_bin.toFixed(3)} per
                    2.4-second bin. These are not physical queue or turning-flow
                    accuracy measurements.
                  </li>
                ))}
              </ul>
            </details>
            <ul>
              {perceptionV4.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section className="city-panel">
        <h2>Computer vision evidence</h2>
        <p>
          The original UA-DETRAC detection and tracking benchmark remains
          frozen. New city snapshots establish source access and real inference;
          their accuracy has not been independently annotated.
        </p>
        {perceptionError && (
          <p role="alert">Perception evidence unavailable: {perceptionError}</p>
        )}
        {!vision && !perceptionError && (
          <p role="status">Loading annotated perception evaluation…</p>
        )}
        {vision && (
          <>
            <p>
              Experiment {vision.experiment_id} · same three predeclared
              UA-DETRAC test sequences and ByteTrack tracker.
            </p>
            <div
              className="table-wrap"
              role="region"
              aria-label="Detector comparison"
              tabIndex={0}
            >
              <table aria-label="Detector candidate comparison">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>mAP@50</th>
                    <th>mAP@50:95</th>
                    <th>Recall</th>
                    <th>IDF1</th>
                    <th>HOTA</th>
                    <th>ID switches</th>
                    <th>Detector / tracker FPS</th>
                    <th>Peak RSS</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["YOLO11n · default", vision.original],
                      ["YOLO26n · candidate", vision.candidate],
                    ] as const
                  ).map(([name, m]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{m.detection.map50.toFixed(3)}</td>
                      <td>{m.detection.map50_95.toFixed(3)}</td>
                      <td>{m.detection.recall.toFixed(3)}</td>
                      <td>{m.tracking.IDF1.toFixed(3)}</td>
                      <td>{m.tracking.HOTA.toFixed(3)}</td>
                      <td>{m.tracking.IDSW}</td>
                      <td>
                        {m.stage_performance.detector_tracker_fps.toFixed(1)}
                      </td>
                      <td>
                        {m.stage_performance.memory_peak_rss_mb.toFixed(0)} MiB
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>{vision.promotion}</p>
            <p>{vision.performance_scope}</p>
            <ul>
              {vision.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </>
        )}
        {flow && (
          <>
            <h3>Validated image-plane crossing counts</h3>
            <p>
              {flow.rows.length} predeclared line / direction / sequence cases ·{" "}
              {flow.rows.reduce((n, r) => n + r.observed_crossings, 0)}{" "}
              annotated crossing events · weighted MAE{" "}
              {(
                flow.rows.reduce(
                  (n, r) => n + r.count_mae_per_bin * r.bins,
                  0,
                ) / flow.rows.reduce((n, r) => n + r.bins, 0)
              ).toFixed(3)}{" "}
              counts per 2.4-second bin. Empty bins are included; an event count
              is not a unique vehicle count.
            </p>
            <label>
              Crossing case{" "}
              <select
                aria-label="Crossing evaluation case"
                value={flowRow}
                onChange={(e) => setFlowRow(Number(e.target.value))}
              >
                {flow.rows.map((r, i) => (
                  <option key={i} value={i}>
                    {r.sequence} · line y={r.line_y_normalized} · {r.direction}
                  </option>
                ))}
              </select>
            </label>
            <div style={{ height: 230 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={flow.rows[flowRow].gt_bin_counts.map((actual, i) => ({
                    seconds: (i * flow.rows[flowRow].bin_seconds).toFixed(1),
                    actual,
                    predicted: flow.rows[flowRow].predicted_bin_counts[i],
                  }))}
                >
                  <CartesianGrid stroke="#263a42" />
                  <XAxis dataKey="seconds" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Line
                    dataKey="actual"
                    name="Annotated crossings"
                    stroke="#e5ecef"
                    dot={false}
                  />
                  <Line
                    dataKey="predicted"
                    name="Tracked crossings"
                    stroke="#7adac0"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p>{flow.scope}</p>
            <ul>
              {flow.limitations.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </>
        )}
        <div className="button-row">
          <Link className="button" href="/benchmarks">
            Open full CV benchmarks
          </Link>
          <Link className="button secondary" href="/workspace">
            Inspect continuous-video processing
          </Link>
          <Link className="text-link" href="/twin">
            Follow the observation-to-twin workflow →
          </Link>
        </div>
      </section>
    </Shell>
  );
}
