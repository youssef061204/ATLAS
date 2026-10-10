"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { DEMO_MODE, request } from "@/lib/api";
import {
  POLICY,
  type CityReport,
  type Observation,
  type Run,
} from "@/lib/cities";
import { Shell } from "./shell";
import { SceneEditor } from "./scene-editor";
import { readSelectedCity, selectCity } from "@/lib/city-selection";
import { CityEvidenceV4 } from "./city-evidence-v4";

type State = { mean: number; interval95: number[]; kind: string };
type Context = {
  city: string;
  camera: { id: string; name: string; image_url?: string };
  observation: Observation & {
    detections?: { class: string; score: number; box_normalized: number[] }[];
  };
  estimated_state: State;
  forecast: {
    horizon_seconds: number;
    mean: number;
    interval95: number[];
    model: string;
  }[];
  alignment: {
    status: string;
    candidates: { road_id: string; distance_m: number }[];
  };
  image_data_url?: string;
};
type Pair = Context & {
  id: string;
  seed: number;
  mode: string;
  runs: Run[];
  assumptions: { residence_seconds: number; corridor_multiplier: number };
  demand: { scheduled_vehicles: number; arrival_rate_assumed_veh_s: number };
  comparison: { mean_delay_difference_s: number; recommendation: string };
};
type Job = { id: string; state: string; result_path?: string; error?: string };
type Smoke = {
  records: {
    city: string;
    attempts: {
      camera_id: string;
      context?: Context;
      experiment?: Pair;
      state: string;
    }[];
  }[];
};

export function IntelligenceWorkflow() {
  const [context, setContext] = useState<Context | null>(null);
  const [pair, setPair] = useState<Pair | null>(null);
  const [original, setOriginal] = useState<{
    context: Context;
    pair: Pair;
  } | null>(null);
  const [key, setKey] = useState("");
  const [residence, setResidence] = useState(60);
  const [baseline, setBaseline] = useState("original_mpc");
  const [seed, setSeed] = useState(21002);
  const [duration, setDuration] = useState(120);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [city, setCity] = useState("toronto");
  const [requestedCamera, setRequestedCamera] = useState<string | null>(null);
  const [catalogs, setCatalogs] = useState<CityReport[]>([]);
  const [smoke, setSmoke] = useState<Smoke | null>(null);
  const [archive, setArchive] = useState("atlas-4");
  const selectedCatalog = catalogs.find((report) => report.city === city);
  const selectedCamera = selectedCatalog?.cameras.find(
    (camera) => camera.id === requestedCamera,
  );
  const activeJob = useRef<{ id: string; key: string } | null>(null);
  const [canCancel, setCanCancel] = useState(false);
  const [regionRevision, setRegionRevision] = useState<number | null>(null);
  async function cancel() {
    const job = activeJob.current;
    if (!job) return;
    try {
      await request(`/api/operations/jobs/${job.id}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${job.key}` },
      });
      setStatus(
        "Cancellation requested; waiting for the simulation worker to stop.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancellation failed");
    }
  }
  const [counts, setCounts] = useState<{
    study: {
      latest_count_date: string;
      total_vehicle: number;
      location_name: string;
    };
    records: unknown[];
  } | null>(null);
  useEffect(() => {
    let active = true;
    const parameters = new URL(window.location.href).searchParams;
    const selectedArchive =
      parameters.get("evidence") === "atlas-3" ? "atlas-3" : "atlas-4";
    Promise.all([
      selectedArchive === "atlas-3"
        ? request<Context>("/api/operations/intelligence/context")
        : Promise.resolve(null),
      selectedArchive === "atlas-3"
        ? request<Pair>("/api/operations/intelligence")
        : Promise.resolve(null),
      selectedArchive === "atlas-3"
        ? request<NonNullable<typeof counts>>("/api/operations/counts/toronto")
        : Promise.resolve(null),
      request<{ cities: CityReport[] }>("/api/operations/cities"),
      request<Smoke>(
        selectedArchive === "atlas-3"
          ? "/api/operations/intelligence/smoke"
          : "/api/operations/intelligence/smoke-v4",
      ),
    ])
      .then(([observation, experiment, detector, sources, checked]) => {
        if (!active) return;
        const requestedCity = readSelectedCity();
        const cameraId =
          parameters.get("camera") ??
          (requestedCity === "toronto" && selectedArchive === "atlas-3"
            ? (observation?.camera.id ?? null)
            : (checked.records
                .find((record) => record.city === requestedCity)
                ?.attempts.find((attempt) => attempt.context)?.camera_id ??
              sources.cities.find((report) => report.city === requestedCity)
                ?.cameras[0]?.id ??
              null));
        const recorded =
          selectedArchive === "atlas-3" &&
          requestedCity === observation?.city &&
          cameraId === observation?.camera.id;
        const attempt = checked.records
          .find((record) => record.city === requestedCity)
          ?.attempts.find((attempt) => attempt.camera_id === cameraId);
        setContext(recorded ? observation : (attempt?.context ?? null));
        setPair(recorded ? experiment : (attempt?.experiment ?? null));
        setCounts(detector);
        setCatalogs(sources.cities);
        setSmoke(checked);
        if (observation && experiment)
          setOriginal({ context: observation, pair: experiment });
        setArchive(selectedArchive);
        setCity(requestedCity);
        setRequestedCamera(cameraId);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function observe() {
    if (!selectedCamera) return;
    const supplied = key;
    setKey("");
    setBusy(true);
    setError("");
    setStatus("Retrieving and processing an authorized official snapshot…");
    try {
      const updated = await request<Context>(
        `/api/operations/cities/${encodeURIComponent(city)}/cameras/${encodeURIComponent(selectedCamera.id)}/observe`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${supplied}` },
        },
      );
      setContext(updated);
      setRegionRevision(null);
      setPair(null);
      setAcknowledged(false);
      setStatus(
        "New snapshot processed. The image and boxes below belong to the same observation.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Observation failed");
    } finally {
      setBusy(false);
    }
  }
  function selectSource(nextCity: string, cameraId: string | null) {
    selectCity(nextCity);
    setCity(nextCity);
    setRequestedCamera(cameraId);
    const recorded = smoke?.records
      .find((record) => record.city === nextCity)
      ?.attempts.find((attempt) => attempt.camera_id === cameraId);
    const isOriginal =
      archive === "atlas-3" &&
      nextCity === original?.context.city &&
      cameraId === original?.context.camera.id;
    setContext(isOriginal ? original!.context : (recorded?.context ?? null));
    setPair(isOriginal ? original!.pair : (recorded?.experiment ?? null));
    setRegionRevision(null);
    setAcknowledged(false);
    setKey("");
    setStatus("");
    setError("");
    const url = new URL(window.location.href);
    url.searchParams.set("city", nextCity);
    if (cameraId) url.searchParams.set("camera", cameraId);
    else url.searchParams.delete("camera");
    window.history.replaceState(null, "", url);
  }
  async function optimize() {
    if (!context) return;
    const supplied = key;
    setKey("");
    setBusy(true);
    setError("");
    setStatus(
      "Preparing observation-conditioned demand and two matched SUMO simulations…",
    );
    try {
      const job = await request<Job>(
        "/api/operations/intelligence/experiments",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${supplied}`,
          },
          body: JSON.stringify({
            city: context.city,
            observation_id: context.observation.id,
            baseline,
            seed,
            duration,
            region_revision: regionRevision,
            assumptions: {
              residence_seconds: residence,
              corridor_multiplier: 1,
              acknowledge_exploratory: acknowledged,
            },
          }),
        },
      );
      let state = job;
      activeJob.current = { id: job.id, key: supplied };
      setCanCancel(true);
      const deadline = Date.now() + 120000;
      while (
        !["complete", "failed", "cancelled", "interrupted"].includes(
          state.state,
        )
      ) {
        if (Date.now() > deadline)
          throw new Error(
            `Simulation is still queued. Job ${job.id} can be inspected in the local API.`,
          );
        await new Promise((resolve) => setTimeout(resolve, 700));
        state = await request<Job>(`/api/operations/jobs/${job.id}`);
        setStatus(`Paired experiment: ${state.state}`);
      }
      if (state.state !== "complete" || !state.result_path)
        throw new Error(state.error ?? "Simulation failed");
      const output = await request<Pair>(state.result_path);
      setPair({
        ...output,
        camera: context.camera,
        alignment: context.alignment,
      });
      setStatus(
        "Both simulations completed using identical observation-conditioned demand.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Experiment failed");
    } finally {
      activeJob.current = null;
      setCanCancel(false);
      setBusy(false);
    }
  }
  function exportEvidence() {
    if (!pair) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(pair, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `atlas-intelligence-${pair.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <Shell
      title="Traffic intelligence loop"
      eyebrow="OBSERVE → ESTIMATE → SIMULATE → EXPLAIN"
      action={
        <Link className="button secondary" href="/cities">
          Explore cities
        </Link>
      }
    >
      <p className="city-notice">
        A real snapshot drives an exploratory simulation through inspectable
        demand assumptions. Independent field calibration is unavailable;
        simulated benefits are conditional.
      </p>
      <section className="workflow-guide" aria-label="Operator task guide">
        <div>
          <div className="eyebrow">YOUR NEXT DECISION</div>
          <h2>
            {pair
              ? "Compare the recorded signal strategies"
              : context
                ? "Inspect this observation’s coverage"
                : "Choose a supported observation"}
          </h2>
          <p>
            {pair
              ? "Both runs share the same input demand, seed and road network. Follow the comparison into a pilot assessment."
              : context
                ? "Visible objects are measured. Flow, physical queues and field savings require additional evidence."
                : "Start with an official city source. An unavailable observation stays unavailable."}
          </p>
        </div>
        <div className="button-row">
          {pair ? (
            <Link
              className="button"
              href={`/studio?city=${encodeURIComponent(pair.city)}&experiment=${pair.id}`}
            >
              Compare signal strategies
            </Link>
          ) : (
            <Link className="button secondary" href={`/cities?city=${city}`}>
              Inspect city coverage
            </Link>
          )}
          <span className="mode-chip">
            {DEMO_MODE
              ? "Recorded real-data replay"
              : "Authorized native processing"}
          </span>
        </div>
      </section>
      <section className="city-panel" id="choose-observation">
        <h2>Choose an official source</h2>
        <div className="city-toolbar workflow-source-controls">
          <label>
            Observation archive
            <select
              aria-label="Observation archive"
              value={archive}
              disabled={busy}
              onChange={(event) => {
                const url = new URL(window.location.href);
                url.searchParams.set("evidence", event.target.value);
                url.searchParams.delete("camera");
                window.location.assign(url.toString());
              }}
            >
              <option value="atlas-4">Newest five-city checks · ATLAS 4</option>
              <option value="atlas-3">Retained observations · ATLAS 3</option>
            </select>
          </label>
          <label>
            City
            <select
              aria-label="Intelligence city"
              disabled={busy}
              value={city}
              onChange={(event) =>
                selectSource(
                  event.target.value,
                  smoke?.records
                    .find((record) => record.city === event.target.value)
                    ?.attempts.find((attempt) => attempt.context)?.camera_id ??
                    catalogs.find(
                      (report) => report.city === event.target.value,
                    )?.cameras[0]?.id ??
                    null,
                )
              }
            >
              {catalogs.map((report) => (
                <option key={report.city} value={report.city}>
                  {report.settings.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Camera
            <select
              aria-label="Intelligence camera"
              disabled={busy}
              value={requestedCamera ?? ""}
              onChange={(event) => selectSource(city, event.target.value)}
            >
              {selectedCatalog?.cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>
                  {camera.name} · {camera.id}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p>
          Catalog coordinates identify a source; they do not establish camera
          field of view or lane alignment. Only sources near the imported
          corridor can condition its exploratory simulation.
        </p>
        {!context && (
          <p role="status">
            No processed observation is selected for this camera. No vehicle
            count, forecast or simulation result has been substituted.
          </p>
        )}
        {!context &&
          (DEMO_MODE ? (
            <p>
              Public mode offers recorded outputs.{" "}
              <a href="/twin?city=toronto&evidence=atlas-3">
                Open the real Toronto observation-conditioned replay
              </a>{" "}
              or{" "}
              <Link href={`/studio?city=${encodeURIComponent(city)}`}>
                inspect {city}’s separately prepared corridor simulation
              </Link>
              .
            </p>
          ) : (
            <div className="city-toolbar">
              <label>
                Local operator key
                <input
                  aria-label="Intelligence operator key"
                  type="password"
                  autoComplete="off"
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                />
              </label>
              <button
                className="button"
                disabled={!key || busy || !selectedCamera}
                onClick={observe}
              >
                {busy ? "Processing source…" : "Observe a new snapshot"}
              </button>
            </div>
          ))}
      </section>
      <ol className="workflow-stages" aria-label="Intelligence pipeline">
        {[
          "Official observation",
          "Perception & state",
          "Demand assumptions",
          "Matched simulation",
          "Evidence & pilot",
        ].map((step, i) => (
          <li key={step}>
            <span>{i + 1}</span>
            {step}
          </li>
        ))}
      </ol>
      {error && (
        <p role="alert" className="city-notice">
          {error}
        </p>
      )}
      {!catalogs.length && !error && (
        <p role="status">
          Loading recorded official observation and completed experiment…
        </p>
      )}
      {context && (
        <>
          <div className="city-columns">
            <section className="city-panel">
              <div className="eyebrow">1 / OBSERVE & UNDERSTAND</div>
              <h2>{context.camera.name}</h2>
              {context.image_data_url ? (
                <div className="snapshot-view">
                  {/* Authorized, ephemeral source imagery; a data URL cannot use Next image optimization. */}
                  <img
                    src={context.image_data_url}
                    alt="Official snapshot processed in this observation"
                  />
                  <svg
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    role="img"
                    aria-label="Detection boxes from this snapshot"
                  >
                    {context.observation.detections?.map((d, i) => (
                      <g key={i}>
                        <rect
                          x={d.box_normalized[0] * 100}
                          y={d.box_normalized[1] * 100}
                          width={
                            (d.box_normalized[2] - d.box_normalized[0]) * 100
                          }
                          height={
                            (d.box_normalized[3] - d.box_normalized[1]) * 100
                          }
                        />
                        <title>
                          {d.class}, model score {d.score.toFixed(2)}
                        </title>
                      </g>
                    ))}
                  </svg>
                </div>
              ) : (
                <p className="observation-empty">
                  The recorded image was processed in memory and was not
                  retained. Its real aggregate detections are available below.
                  An authorized local operator can retrieve a new image and its
                  matching overlay.
                </p>
              )}
              {context.image_data_url && (
                <SceneEditor
                  key={context.observation.id}
                  city={context.city}
                  cameraId={context.camera.id}
                  observationId={context.observation.id}
                  image={context.image_data_url}
                  roads={context.alignment.candidates}
                  onSaved={(region) => {
                    setRegionRevision(region.revision);
                    setContext({
                      ...context,
                      observation:
                        region.derived_observation as Context["observation"],
                      estimated_state: region.estimated_state as State,
                      forecast: region.forecast as Context["forecast"],
                    });
                    setPair(null);
                  }}
                />
              )}
              <div className="city-metrics">
                {Object.entries(context.observation.counts ?? {}).map(
                  ([name, count]) => (
                    <div key={name}>
                      <span>{name.toUpperCase()}</span>
                      <strong>{count}</strong>
                    </div>
                  ),
                )}
              </div>
              {regionRevision && (
                <p>
                  These counts and estimated inputs now use operator region
                  revision {regionRevision}. Road/lane calibration remains
                  unvalidated.
                </p>
              )}
              <dl className="city-details">
                <dt>Retrieved</dt>
                <dd>{context.observation.retrieved_at}</dd>
                <dt>Capture time</dt>
                <dd>Not verified</dd>
                <dt>Observation fingerprint</dt>
                <dd className="evidence-id">
                  {context.observation.id.slice(0, 16)}
                </dd>
                <dt>Model latency</dt>
                <dd>
                  {context.observation.inference_ms?.toFixed(1)} ms for this
                  image
                </dd>
              </dl>
              <p>
                Snapshot counts establish visible objects. Queues, turning flows
                and vehicle speeds remain unobserved.
              </p>
              <Link href="/workspace">
                Inspect real continuous-video tracking →
              </Link>
            </section>
            <section className="city-panel">
              <div className="eyebrow">2 / ESTIMATE & PREDICT</div>
              <h2>State with uncertainty</h2>
              <p className="state-value">
                {context.estimated_state.mean.toFixed(1)}{" "}
                <span>estimated visible motor vehicles</span>
              </p>
              <p>
                Model-based 95% interval:{" "}
                {context.estimated_state.interval95
                  .map((v) => v.toFixed(1))
                  .join("–")}
                . Gaussian count prior; field coverage unvalidated.
              </p>
              <ul>
                {context.forecast.map((f) => (
                  <li key={f.horizon_seconds}>
                    {f.horizon_seconds} s: {f.mean.toFixed(1)} vehicles;
                    interval {f.interval95.map((v) => v.toFixed(1)).join("–")}
                  </li>
                ))}
              </ul>
              <p>
                These use an unvalidated random-walk prior.{" "}
                <Link href="/laboratory">
                  Measured METR-LA forecasting models
                </Link>{" "}
                operate on highway speed sensors and are evaluated separately.
              </p>
              <h3>Camera-to-road alignment</h3>
              <p>
                Geographic candidates require field-of-view and lane
                verification.
              </p>
              <ul>
                {context.alignment.candidates.slice(0, 3).map((r) => (
                  <li key={r.road_id}>
                    {r.road_id} · {r.distance_m.toFixed(0)} m from camera
                  </li>
                ))}
              </ul>
              {context.city === "toronto" &&
                context.camera.id === "8113" &&
                counts && (
                  <p>
                    {counts.records.length} official historical fifteen-minute
                    bins / {counts.study.total_vehicle.toLocaleString()} motor
                    vehicles at {counts.study.location_name},{" "}
                    {counts.study.latest_count_date}. Historical counts are kept
                    separate from this snapshot; they were observed at different
                    times.
                  </p>
                )}
            </section>
          </div>
          <section className="city-panel">
            <div className="eyebrow">3 / CONFIGURE THE EXPLORATORY TWIN</div>
            <h2>Observed counts, explicit assumptions</h2>
            <p>
              Assumed arrivals = estimated visible count ÷ residence time.
              Origin–destination paths come from the pinned corridor’s generated
              routes. This conversion makes a conditional test possible; it is
              not measured flow or calibrated demand.
            </p>
            {DEMO_MODE ? (
              <div className="replay-choice">
                <p>
                  Public mode instantly replays the completed run below. New
                  source processing and simulations require an authorized
                  Python/SUMO worker.
                </p>
                {pair ? (
                  <Link
                    className="button"
                    href={`/studio?city=${city}&experiment=${pair.id}`}
                  >
                    Optimize Traffic · watch saved comparison
                  </Link>
                ) : (
                  <>
                    <p>
                      No observation-conditioned pair exists for this snapshot.
                      The separately prepared corridor study uses its original
                      assumed demand.
                    </p>
                    <Link
                      className="button secondary"
                      href={`/studio?city=${city}`}
                    >
                      Inspect separately prepared corridor study
                    </Link>
                  </>
                )}
              </div>
            ) : (
              <>
                <div className="city-toolbar">
                  <label>
                    Local operator key
                    <input
                      aria-label="Intelligence operator key"
                      type="password"
                      autoComplete="off"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                    />
                  </label>
                  <label>
                    Baseline controller
                    <select
                      aria-label="Experiment baseline"
                      value={baseline}
                      onChange={(event) => setBaseline(event.target.value)}
                      disabled={busy}
                    >
                      {["fixed", "max_pressure", "original_mpc"].map(
                        (policy) => (
                          <option key={policy} value={policy}>
                            {POLICY[policy]}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  <label>
                    Simulation duration (seconds)
                    <select
                      aria-label="Experiment duration"
                      value={duration}
                      onChange={(event) =>
                        setDuration(Number(event.target.value))
                      }
                      disabled={busy}
                    >
                      {[60, 120, 300].map((value) => (
                        <option key={value} value={value}>
                          {value} s
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Reproducible seed
                    <input
                      type="number"
                      aria-label="Intelligence simulation seed"
                      min={1}
                      max={2000000000}
                      value={seed}
                      onChange={(event) => setSeed(Number(event.target.value))}
                      disabled={busy}
                    />
                  </label>
                  <label>
                    Assumed residence time (seconds)
                    <input
                      aria-label="Assumed residence time"
                      type="number"
                      min={10}
                      max={600}
                      value={residence}
                      onChange={(e) => setResidence(Number(e.target.value))}
                    />
                  </label>
                  <button
                    className="button secondary"
                    disabled={!key || busy}
                    onClick={observe}
                  >
                    Observe a new snapshot
                  </button>
                  <button
                    className="button"
                    disabled={
                      !key ||
                      busy ||
                      !acknowledged ||
                      context.estimated_state.mean <= 0 ||
                      !context.alignment.candidates.length ||
                      context.alignment.candidates[0].distance_m > 1000 ||
                      residence < 10 ||
                      residence > 600 ||
                      !Number.isInteger(seed) ||
                      seed < 1 ||
                      seed > 2000000000
                    }
                    onClick={optimize}
                  >
                    {busy ? "Processing…" : "Optimize Traffic"}
                  </button>
                  {canCancel && (
                    <button className="button secondary" onClick={cancel}>
                      Cancel paired experiment
                    </button>
                  )}
                </div>
                <label className="assumption-ack">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                  />{" "}
                  I understand that demand conversion, OD paths and signal
                  timings are unvalidated assumptions.
                </label>
              </>
            )}
            <p role="status">{status}</p>
            {context.alignment.candidates[0]?.distance_m > 1000 && (
              <p role="status">
                This camera is farther than the 1 km geographic screening limit
                from the imported corridor. Its detections remain inspectable;
                this corridor cannot be simulated from them.
              </p>
            )}
            {context.estimated_state.mean <= 0 && (
              <p role="status">
                No motor vehicles were detected. This snapshot cannot support a
                demand conversion; independent flow measurements or another
                supported observation are required.
              </p>
            )}
          </section>
          {pair && (
            <section className="city-panel">
              <div className="eyebrow">4 / COMPARE & EXPLAIN</div>
              <h2>Actual completed counterfactual</h2>
              <p>
                {status ? "New simulation" : "Recorded simulation"} · paired
                seed {pair.seed} · {pair.demand.scheduled_vehicles} scheduled
                vehicles · {pair.assumptions.residence_seconds} s assumed
                residence time.
              </p>
              <div className="city-metrics">
                {pair.runs.map((r) => (
                  <div key={r.policy}>
                    <span>{POLICY[r.policy]}</span>
                    <strong>{r.metrics.mean_delay_s.toFixed(2)} s</strong>
                    <span>MEAN SIMULATED DELAY</span>
                  </div>
                ))}
              </div>
              <p>{pair.comparison.recommendation}</p>
              <p>
                Baseline minus prototype:{" "}
                {pair.comparison.mean_delay_difference_s.toFixed(2)} s per
                vehicle. A single conditional run does not establish general
                superiority; the twenty-seed city study includes prototype
                regressions.
              </p>
              <div className="button-row">
                <Link
                  className="button"
                  href={`/studio?city=${encodeURIComponent(pair.city)}&experiment=${pair.id}`}
                >
                  Watch synchronized comparison
                </Link>
                <button className="button secondary" onClick={exportEvidence}>
                  Export complete experiment
                </button>
                <Link
                  className="text-link"
                  href={`/pilot?city=${encodeURIComponent(pair.city)}&experiment=${pair.id}`}
                >
                  Build a pilot assessment →
                </Link>
              </div>
            </section>
          )}
        </>
      )}
      <CityEvidenceV4 city={city} />
    </Shell>
  );
}
