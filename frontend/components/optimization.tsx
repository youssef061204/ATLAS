"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  GitBranch,
  LoaderCircle,
  Pause,
  Play,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import { DEMO_MODE, post, request } from "@/lib/api";
import type { Simulation } from "@/lib/types";
import { Shell } from "./shell";
import { Twin } from "./twin";
import { TrendChart } from "./charts";
import { useResult } from "./video-workspace";

export function OptimizationPage() {
  const { result } = useResult();
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const [seed, setSeed] = useState(42);
  const [source, setSource] = useState("scenario");
  const [demand, setDemand] = useState([0.38, 0.12, 0.32, 0.1]);
  const [showSettings, setShowSettings] = useState(false);
  const clock = useRef(0);
  useEffect(() => {
    if (!DEMO_MODE) return;
    let active = true;
    request<Simulation>("/api/simulations/demo")
      .then((data) => {
        if (active) {
          setSimulation(data);
          setTime(120);
          clock.current = 120;
        }
      })
      .catch((error) => {
        if (active) setError(error.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!playing || !simulation) return;
    let frame: number;
    let previous = 0;
    const tick = (t: number) => {
      if (previous)
        clock.current = Math.min(
          simulation.settings.duration,
          clock.current + ((t - previous) / 1000) * speed,
        );
      previous = t;
      setTime(clock.current);
      if (clock.current >= simulation.settings.duration) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, simulation]);
  async function run() {
    setBusy(true);
    setError("");
    setPlaying(false);
    try {
      const data = await post<Simulation>("/api/simulations", {
        seed,
        duration: 300,
        demand,
        ...(source === "video" && result ? { video_id: result.video_id } : {}),
      });
      setSimulation(data);
      clock.current = 0;
      setTime(0);
      setPlaying(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const baseline = simulation?.runs[0];
  const atlas = simulation?.runs[2];
  const at = Math.floor(time);
  const a = baseline?.frames[Math.min(at, baseline.frames.length - 1)];
  const b = atlas?.frames[Math.min(at, atlas.frames.length - 1)];
  return (
    <Shell
      title="A better cycle starts here"
      eyebrow="SIGNAL LAB / OPTIMIZATION"
      action={
        <>
          <button
            className="button secondary"
            disabled={DEMO_MODE}
            onClick={() => setShowSettings(!showSettings)}
          >
            <SlidersHorizontal size={15} /> Demand settings
          </button>
          <button className="button" onClick={run} disabled={busy}>
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <GitBranch size={16} />
            )}
            {busy
              ? "Evaluating policies…"
              : DEMO_MODE
                ? "Replay precomputed comparison"
                : "Optimize intersection"}
            <ArrowUpRight size={14} />
          </button>
        </>
      }
    >
      <div className="optimization-intro">
        <div>
          <span className="eyebrow">SAME ARRIVALS. DIFFERENT DECISIONS.</span>
          <p>
            A microscopic intersection simulator compares fixed timing, an
            adaptive queue policy, and constrained signal search. Independent
            tuning seeds select green durations; the comparison runs on held-out
            demand.
          </p>
        </div>
        <span className="pill">
          {DEMO_MODE
            ? "PRECOMPUTED / CONTROLLED SIMULATION"
            : "SIMULATION / NOT FIELD RESULTS"}
        </span>
      </div>
      {showSettings && (
        <div className="panel demand-panel">
          <div className="form-grid">
            <label>
              Arrival source
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="scenario">Seeded research scenario</option>
                <option value="video" disabled={!result}>
                  Observed video track arrivals
                </option>
              </select>
            </label>
            <label>
              Evaluation seed
              <input
                type="number"
                min={0}
                max={2147483647}
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </label>
            {demand.map((v, i) => (
              <label key={i}>
                {["N", "E", "S", "W"][i]} demand · vehicles/s
                <input
                  type="number"
                  min="0"
                  max="1.5"
                  step=".02"
                  value={v}
                  disabled={source === "video"}
                  onChange={(e) =>
                    setDemand(
                      demand.map((x, j) =>
                        j === i ? Number(e.target.value) : x,
                      ),
                    )
                  }
                />
              </label>
            ))}
          </div>
          <p className="panel-note">
            Two protected straight-through phases. Min green 12 s · max green 60
            s · yellow 3 s · all-red 2 s · pedestrian interval 12 s. Video
            demand uses first track observations and direction proxies; it is
            exploratory.
          </p>
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      {!simulation ? (
        <div className="panel optimization-empty">
          <div className="split-illustration">
            <div>
              <span>FIXED TIMING</span>
              <div className="signal-stack">
                <i />
                <i />
                <i className="on" />
              </div>
              <small>30s / 30s</small>
            </div>
            <ArrowRight size={32} strokeWidth={1} />
            <div>
              <span>CONSTRAINED SEARCH</span>
              <div className="signal-stack">
                <i />
                <i className="on amber" />
                <i />
              </div>
              <small>Measured objectives</small>
            </div>
          </div>
          <h2>Watch the same demand take two paths.</h2>
          <p>
            Search green splits using delay, pedestrian wait, queue length, and
            approach fairness.
            <br />
            Then replay both runs simultaneously and inspect every metric.
          </p>
          <button className="button" onClick={run} disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <GitBranch size={16} />
            )}
            {busy ? "Running reproducible search…" : "Optimize intersection"}
          </button>
        </div>
      ) : (
        <>
          <div className="comparison-head">
            <div>
              <span className="baseline-tag">BASELINE</span>
              <h2>Fixed-time control</h2>
              <p>30s N/S + 30s E/W</p>
            </div>
            <div>
              <span className="atlas-tag">ATLAS SEARCH</span>
              <h2>Demand-informed timing</h2>
              <p>
                {atlas?.greens?.[0]}s N/S + {atlas?.greens?.[1]}s E/W ·{" "}
                {simulation.search.candidates} candidates
              </p>
            </div>
          </div>
          <div className="two-column comparison-scenes">
            <section className="panel">
              <Twin simFrame={a} />
              <div className="sim-live">
                {[
                  ["MEAN DELAY", `${a?.metrics.delay.toFixed(1)}s`],
                  ["QUEUE", a?.metrics.queue],
                  ["CLEARED", a?.metrics.cleared],
                  [
                    "PEDESTRIAN WAIT",
                    `${a?.metrics.pedestrian_wait.toFixed(1)}s`,
                  ],
                ].map(([k, v]) => (
                  <div key={k}>
                    <span>{k}</span>
                    <strong>{v}</strong>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel atlas-panel">
              <Twin simFrame={b} />
              <div className="sim-live">
                {[
                  ["MEAN DELAY", `${b?.metrics.delay.toFixed(1)}s`],
                  ["QUEUE", b?.metrics.queue],
                  ["CLEARED", b?.metrics.cleared],
                  [
                    "PEDESTRIAN WAIT",
                    `${b?.metrics.pedestrian_wait.toFixed(1)}s`,
                  ],
                ].map(([k, v]) => (
                  <div key={k}>
                    <span>{k}</span>
                    <strong>{v}</strong>
                  </div>
                ))}
              </div>
            </section>
          </div>
          <div className="timeline panel">
            <button
              className="play-button"
              aria-label={playing ? "Pause simulation" : "Play simulation"}
              onClick={() => setPlaying(!playing)}
            >
              {playing ? <Pause size={17} /> : <Play size={17} />}
            </button>
            <button
              className="icon-button"
              aria-label="Reset simulation"
              onClick={() => {
                clock.current = 0;
                setTime(0);
              }}
            >
              <RotateCcw size={15} />
            </button>
            <span className="mono">{time.toFixed(0)}s</span>
            <input
              aria-label="Simulation timeline"
              type="range"
              min={0}
              max={simulation.settings.duration}
              value={time}
              onChange={(e) => {
                clock.current = Number(e.target.value);
                setTime(clock.current);
              }}
            />
            <span className="mono">{simulation.settings.duration}s</span>
            <select
              aria-label="Simulation playback speed"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              {[1, 5, 10, 20].map((n) => (
                <option key={n} value={n}>
                  {n}×
                </option>
              ))}
            </select>
          </div>
          <div className="comparison-results">
            <div className="result-highlight">
              <span className="eyebrow">
                COMPLETE RUN / HELD-OUT SEED {simulation.settings.seed}
              </span>
              <strong>
                {simulation.improvement_pct.delay?.toFixed(1)}
                <span>%</span>
              </strong>
              <p>
                change in average vehicle delay
                <br />
                <small>Positive = reduction. Includes unfinished demand.</small>
              </p>
            </div>
            <section className="panel">
              <div className="panel-heading">
                ALL THREE POLICIES / FINAL METRICS
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Policy</th>
                    <th>Delay / s</th>
                    <th>Cleared</th>
                    <th>Queue</th>
                    <th>Stops</th>
                    <th>Ped wait / s</th>
                  </tr>
                </thead>
                <tbody>
                  {simulation.runs.map((r) => (
                    <tr key={r.policy}>
                      <td>{r.policy}</td>
                      <td>{r.metrics.delay.toFixed(1)}</td>
                      <td>{r.metrics.throughput}</td>
                      <td>{r.metrics.mean_queue?.toFixed(1)}</td>
                      <td>{r.metrics.stops.toFixed(2)}</td>
                      <td>{r.metrics.pedestrian_wait.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
          <section className="panel">
            <div className="panel-heading">
              DELAY ACCUMULATION / BASELINE VS ATLAS
            </div>
            <TrendChart
              data={
                baseline?.frames
                  .filter((_, i) => i % 5 === 0)
                  .map((f) => ({
                    t: f.t,
                    baseline: f.metrics.delay,
                    atlas: atlas?.frames[Math.floor(f.t)].metrics.delay || 0,
                  })) || []
              }
              keys={[
                { key: "baseline", color: "#8f9fa9", name: "Fixed baseline" },
                { key: "atlas", color: "#a8d4bc", name: "ATLAS search" },
              ]}
              height={230}
            />
          </section>
          <p className="provenance-note">
            {simulation.scope} Selection seeds:{" "}
            {simulation.search.tuning_seeds.join(", ")}. Estimated field
            benefits require validated demand and a calibrated traffic model.
          </p>
        </>
      )}
    </Shell>
  );
}
