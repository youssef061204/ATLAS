"use client";

import { useEffect, useMemo, useState } from "react";
import { API, request } from "@/lib/api";
import { TrendChart } from "./charts";

type Summary = { mean: number; std: number; ci95: number[] };
type Frame = {
  t: number;
  queue: number;
  phase: number;
  clearance: boolean;
  executed_state: string;
  switches: number;
  lane_queues: Record<string, number>;
};
type Study = {
  seed: number[];
  scope: string;
  metrics: {
    controllers: Record<string, Record<string, Summary>>;
    runs_per_controller: number;
    paired_comparisons?: Record<
      string,
      {
        mean_paired_improvement_pct: number;
        paired_improvement_ci95_pct: number[];
        wins: number;
      }
    >;
  };
  methodology?: {
    selection: { selected: string; settings: { family: string } };
  };
  results?: { replay: Record<string, Frame[]>; replay_seed: number };
};
const policies = [
  { key: "fixed", name: "Fixed", color: "#98a7b0" },
  { key: "max_pressure", name: "Max-pressure", color: "#64a8ff" },
  { key: "atlas_original", name: "ATLAS Original", color: "#edb36b" },
  { key: "atlas_improved", name: "ATLAS Improved", color: "#55e6be" },
];
const f = (n: number, digits = 2) => n.toFixed(digits);
type Transfer = {
  metrics: { transfer_controllers: Record<string, Record<string, Summary>> };
};

export function SignalStudy({ replay = false }: { replay?: boolean }) {
  const [study, setStudy] = useState<Study | null>(null);
  const [ablations, setAblations] = useState<Study | null>(null);
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [index, setIndex] = useState(120);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([
      request<Study>("/api/benchmarks/improved_signal_control").catch(
        () => null,
      ),
      request<Study>("/api/benchmarks/signal_control_ablations").catch(
        () => null,
      ),
      request<Transfer>("/api/benchmarks/signal_control_generalization").catch(
        () => null,
      ),
    ]).then(([a, b, c]) => {
      if (active) {
        setStudy(a);
        setAblations(b);
        setTransfer(c);
      }
    });
    return () => {
      active = false;
    };
  }, []);
  const frames = study?.results?.replay;
  const length = frames?.atlas_improved.length ?? 0;
  useEffect(() => {
    if (!playing || !length) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % length), 200);
    return () => clearInterval(timer);
  }, [playing, length]);
  const chart = useMemo(
    () =>
      frames?.atlas_improved.map((r, i) => ({
        t: r.t,
        ...Object.fromEntries(
          policies.map((p) => [p.key, frames[p.key][i].queue]),
        ),
      })) ?? [],
    [frames],
  );
  if (!study) return null;
  const comparisons = study.metrics.paired_comparisons;
  return (
    <section
      className="panel signal-study"
      aria-label="Improved signal-control study"
    >
      <div className="panel-heading">
        RESCO / CONTROLLER EVOLUTION{" "}
        <span className="pill">
          {study.metrics.runs_per_controller} HELD-OUT SEEDS
        </span>
      </div>
      <h2>Feedback replaces the failed timing schedule</h2>
      <p className="panel-note">
        {study.scope} The original 66.45 s three-seed result remains published;
        all four controllers here use the same ten new seeds and resolved
        routes.
      </p>
      <div className="score-grid">
        {comparisons &&
          ["fixed", "max_pressure", "atlas_original"].map((key) => {
            const c = comparisons[key];
            return (
              <div key={key}>
                <span>
                  Paired reduction vs{" "}
                  {policies.find((p) => p.key === key)?.name}
                </span>
                <strong>{f(c.mean_paired_improvement_pct, 1)}%</strong>
                <small>
                  95% bootstrap CI{" "}
                  {c.paired_improvement_ci95_pct
                    .map((v) => f(v, 1))
                    .join(" to ")}
                  % · {c.wins}/{study.seed.length} wins
                </small>
              </div>
            );
          })}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Held-out signal-control metrics">
          <thead>
            <tr>
              <th>Controller</th>
              <th>Delay ± SD (s)</th>
              <th>95% CI (s)</th>
              <th>Mean queue</th>
              <th>Vehicles/h</th>
              <th>Completed</th>
              <th>Stops/vehicle</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => {
              const m = study.metrics.controllers[p.key];
              return (
                <tr key={p.key}>
                  <td style={{ color: p.color }}>{p.name}</td>
                  <td>
                    {f(m.mean_delay_s.mean)} ± {f(m.mean_delay_s.std)}
                  </td>
                  <td>{m.mean_delay_s.ci95.map((n) => f(n)).join("–")}</td>
                  <td>{f(m.mean_queue.mean)}</td>
                  <td>{f(m.throughput_vehicles_per_hour.mean, 0)}</td>
                  <td>{f(m.completed_trips.mean, 1)}</td>
                  <td>{f(m.stops_per_vehicle.mean, 3)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {replay && frames && (
        <>
          <div className="panel-heading">
            ACTUAL SUMO QUEUES / SEED {study.results?.replay_seed}{" "}
            <span className="pill">PRECOMPUTED REAL-DATA DEMO</span>
          </div>
          <TrendChart
            data={chart}
            keys={policies.map((p) => ({ ...p, name: p.name }))}
            height={230}
          />
          <div className="mode-tabs" id="resco-replay-controls">
            <button onClick={() => setPlaying((p) => !p)}>
              {playing ? "Pause RESCO replay" : "Play RESCO replay"}
            </button>
            <span>
              t = {frames.atlas_improved[index]?.t} s · 25× playback · recorded
              every 5 s
            </span>
          </div>
          <label>
            SUMO replay time
            <input
              aria-label="SUMO replay time"
              type="range"
              min={0}
              max={length - 1}
              value={index}
              onChange={(e) => {
                setPlaying(false);
                setIndex(Number(e.target.value));
              }}
              style={{ width: "100%" }}
            />
          </label>
          <div className="score-grid">
            {policies.map((p) => {
              const row = frames[p.key][index];
              return (
                <div key={p.key}>
                  <span style={{ color: p.color }}>{p.name}</span>
                  <strong>{row.queue} queued</strong>
                  <small>
                    Phase {row.phase + 1} ·{" "}
                    {row.clearance ? "protected clearance" : "green"} ·{" "}
                    {row.switches} switches
                  </small>
                  <p className="panel-note">
                    <code>{row.executed_state}</code>
                  </p>
                </div>
              );
            })}
          </div>
        </>
      )}
      {transfer && (
        <p className="panel-note">
          Untuned Ingolstadt1 transfer did not beat the baselines: ATLAS{" "}
          {f(
            transfer.metrics.transfer_controllers.atlas_improved.mean_delay_s
              .mean,
          )}{" "}
          s, fixed{" "}
          {f(transfer.metrics.transfer_controllers.fixed.mean_delay_s.mean)} s,
          max-pressure{" "}
          {f(
            transfer.metrics.transfer_controllers.max_pressure.mean_delay_s
              .mean,
          )}{" "}
          s across five seeds. This result supports Cologne1 performance, not
          universal superiority.
        </p>
      )}
      <details>
        <summary>Inspect ablations and reproducibility</summary>
        <p className="panel-note">
          Selected {study.methodology?.selection.selected}:{" "}
          {study.methodology?.selection.settings.family}. Twenty pressure/MPC
          candidates, ten tuning demand cases, five validation cases.
          All-scheduled delay includes unfinished trips and insertion waiting.
          Common 10–60 s green envelope, 3 s yellow, 2 s all-red.
        </p>
        {ablations && (
          <div style={{ overflowX: "auto" }}>
            <table aria-label="Signal-control ablations">
              <thead>
                <tr>
                  <th>Frozen variant</th>
                  <th>Delay ± SD (s)</th>
                  <th>Seeds</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ablations.metrics.controllers).map(
                  ([key, metrics]) => (
                    <tr key={key}>
                      <td>{key.replaceAll("_", " ")}</td>
                      <td>
                        {f(metrics.mean_delay_s.mean)} ±{" "}
                        {f(metrics.mean_delay_s.std)}
                      </td>
                      <td>{ablations.metrics.runs_per_controller}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
        <p className="panel-note">
          Ablations use separate unseen seeds and never reselect the controller.
          Forecasts are causal junction arrivals; METR-LA highway speed
          forecasts serve a different target.
        </p>
        <p className="panel-note">
          Forecasting added only a small, uncertain benefit in the separate
          ablation study. Individual component effects should not be treated as
          established field benefits.
        </p>
        {[
          ["improved_signal_control", "Final results & replay"],
          ["signal_control_selection", "All candidate results"],
          ["signal_controller_audit", "Fairness audit"],
          ["signal_control_ablations", "Ablations"],
          ["signal_control_generalization", "Untuned transfer & stress"],
        ].map(([key, name]) => (
          <p key={key}>
            <a
              href={`${API}/api/benchmarks/${key}`}
              target="_blank"
              rel="noreferrer"
            >
              {name} ↗
            </a>
          </p>
        ))}
      </details>
    </section>
  );
}
