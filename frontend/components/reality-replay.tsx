"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Shell } from "./shell";
import styles from "./reality-replay.module.css";

const BASE = "/demo/reality/v6/";
type Point = [number, number];
type Box = [number, number, number, number, number, string, number];
type Vehicle = [string, number, number, number, number];
type Chunk = {
  start_frame: number;
  frames: Box[][];
  simulation: Record<string, Vehicle[]>;
};
type ErrorMetric = {
  mae: number | null;
  bias: number | null;
  pairs: number;
  coverage: number | null;
};
type Series = {
  t: number;
  observed_vehicles: number;
  simulated_vehicles: number;
  observed_sb_queue: number;
  simulated_sb_queue: number;
};
type Manifest = {
  research?: { holdout?: string; cityflow?: string; live?: string };
  title: string;
  duration_s: number;
  fps: number;
  frame_count: number;
  video: string;
  poster: string;
  lanes: { id: string; shape: Point[]; width: number }[];
  junction: Point[];
  signal_heads: { lane: string; point: Point; index: number }[];
  phases: { start: number; end: number; state: string }[];
  performance: {
    processed_frames: number;
    processed_fps: number;
    model: string;
  };
  cv: {
    identity: { IDF1: number };
    spatial_matching: { reference_coverage: number };
    speed_mps_matched_pairs: ErrorMetric;
  };
  metrics: {
    instantaneous_vehicle_count: ErrorMetric;
    sb_queue_count: ErrorMetric;
    limitations: string[];
  };
};
type Holdout = {
  source_availability: {
    scored_seconds: number;
    planned_seconds: number;
    planned_window_coverage: number;
  };
  instantaneous_vehicle_count: ErrorMetric;
  sb_queue_count: ErrorMetric;
};
type CityFlow = {
  total_decoded_and_processed_frames: number;
  before_association: { identity: { IDF1: number } };
  after_association_same_detections: { identity: { IDF1: number } };
  multicamera_filtered: { identity: { IDF1: number } };
};
type LiveTrial = {
  observed_start_utc: string;
  final_health: { decoded_frames: number; stale: boolean };
  predicted_observations: unknown[];
  media_retained: boolean;
};

function clock(time: number) {
  return `${Math.floor(time / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(time % 60)
    .toString()
    .padStart(2, "0")}`;
}
function display(value: number | null | undefined, digits = 2) {
  return value == null ? "Unavailable" : value.toFixed(digits);
}
async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Replay asset failed (${response.status})`);
  return response.json() as Promise<T>;
}
function screen([x, y]: Point): Point {
  return [0.5 * x + 0.8660254 * y, 0.8660254 * x - 0.5 * y];
}
function Plot({
  rows,
  observed,
  simulated,
  label,
  time,
}: {
  rows: Series[];
  observed: keyof Series;
  simulated: keyof Series;
  label: string;
  time: number;
}) {
  const maximum = Math.max(
    1,
    ...rows.flatMap((row) => [row[observed], row[simulated]]),
  );
  const points = (key: keyof Series) =>
    rows
      .map(
        (row) =>
          `${40 + ((row.t - 600) / 400) * 520},${155 - (row[key] / maximum) * 125}`,
      )
      .join(" ");
  return (
    <figure className={styles.plot}>
      <figcaption>
        {label} <span>Independent observations / CV-driven SUMO</span>
      </figcaption>
      <svg
        viewBox="0 0 600 190"
        role="img"
        aria-label={`${label} from 10:00 to 16:40 of the historical recording. Observed values are green; simulated values are blue.`}
      >
        <path d="M40 25V155H560" fill="none" stroke="#526671" />
        <polyline
          points={points(observed)}
          fill="none"
          stroke="#a8d6bc"
          strokeWidth="2"
        />
        <polyline
          points={points(simulated)}
          fill="none"
          stroke="#91afcc"
          strokeWidth="2"
        />
        {time >= 600 && time < 1000 ? (
          <line
            x1={40 + ((time - 600) / 400) * 520}
            x2={40 + ((time - 600) / 400) * 520}
            y1="25"
            y2="155"
            stroke="#d7b985"
          />
        ) : null}
        <g fill="#b9c9d1" fontSize="11">
          <text x="9" y="32">
            {maximum}
          </text>
          <text x="22" y="158">
            0
          </text>
          <text x="40" y="178">
            10:00
          </text>
          <text x="520" y="178">
            16:40
          </text>
        </g>
      </svg>
    </figure>
  );
}

export function RealityReplay() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [holdout, setHoldout] = useState<Holdout | null>(null);
  const [cityflow, setCityflow] = useState<CityFlow | null>(null);
  const [liveTrial, setLiveTrial] = useState<LiveTrial | null>(null);
  const [series, setSeries] = useState<Series[]>([]);
  const [time, setTime] = useState(600);
  const [playing, setPlaying] = useState(false);
  const [chunk, setChunk] = useState<Chunk | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const cache = useRef(new Map<number, Chunk>());
  const resume = useRef(false);
  const chunkStart = Math.floor(time / 60) * 60;

  useEffect(() => {
    let active = true;
    Promise.all([
      json<Manifest>(BASE + "manifest.json"),
      json<{ series: Series[] }>(BASE + "cv-driven-validation.json"),
    ])
      .then(([data, metrics]) => {
        if (active) {
          setManifest(data);
          setSeries(metrics.series);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (active)
          setError(
            reason instanceof Error ? reason.message : "Replay could not load",
          );
      });
    return () => {
      active = false;
    };
  }, [retry]);

  useEffect(() => {
    let active = true;
    const research = manifest?.research;
    if (research?.holdout)
      json<Holdout>(BASE + research.holdout)
        .then((data) => {
          if (active) setHoldout(data);
        })
        .catch(() => {
          if (active) setError("Qualified holdout evidence could not load.");
        });
    if (research?.cityflow)
      json<CityFlow>(BASE + research.cityflow)
        .then((data) => {
          if (active) setCityflow(data);
        })
        .catch(() => {
          if (active) setError("CityFlow research evidence could not load.");
        });
    if (research?.live)
      json<LiveTrial>(BASE + research.live)
        .then((data) => {
          if (active) setLiveTrial(data);
        })
        .catch(() => {
          if (active)
            setError("Archived native stream evidence could not load.");
        });
    return () => {
      active = false;
    };
  }, [manifest, retry]);

  useEffect(() => {
    if (!manifest) return;
    let active = true;
    const load = async (start: number) => {
      if (!cache.current.has(start)) {
        const data = await json<Chunk>(
          BASE + `replay-${start.toString().padStart(4, "0")}.json`,
        );
        cache.current.set(start, data);
      }
      return cache.current.get(start)!;
    };
    const existing = cache.current.get(chunkStart);
    if (!existing && video.current && !video.current.paused) {
      resume.current = true;
      video.current.pause();
    }
    load(chunkStart)
      .then((data) => {
        if (!active) return;
        setChunk(data);
        setError("");
        if (resume.current && video.current) {
          resume.current = false;
          video.current.play().catch(() => setPlaying(false));
        }
        if (chunkStart + 60 < manifest.duration_s)
          void load(chunkStart + 60).catch(() => undefined);
      })
      .catch((reason: unknown) => {
        if (active)
          setError(
            reason instanceof Error
              ? reason.message
              : "Synchronized data could not load",
          );
      });
    return () => {
      active = false;
    };
  }, [chunkStart, manifest, retry]);

  useEffect(() => {
    let animation = 0,
      lastFrame = -1;
    const tick = () => {
      if (video.current && !video.current.paused) {
        const next = Math.floor(video.current.currentTime * 10);
        if (next !== lastFrame) {
          lastFrame = next;
          setTime(video.current.currentTime);
        }
      }
      animation = requestAnimationFrame(tick);
    };
    animation = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animation);
  }, []);

  const viewport = useMemo(() => {
    if (!manifest) return "-20 -80 180 135";
    const points = manifest.lanes.flatMap((lane) => lane.shape.map(screen));
    const xs = points.map(([x]) => x),
      ys = points.map(([, y]) => y);
    const width = Math.max(...xs) - Math.min(...xs) + 24;
    const height = Math.max(
      width * 0.75,
      Math.max(...ys) - Math.min(...ys) + 24,
    );
    return `${(Math.max(...xs) + Math.min(...xs)) / 2 - (height * 2) / 3} ${(Math.max(...ys) + Math.min(...ys)) / 2 - height / 2} ${(height * 4) / 3} ${height}`;
  }, [manifest]);
  const frameIndex = Math.min(
    (manifest?.frame_count ?? 11220) - 1,
    Math.floor(time * 10),
  );
  const synchronized = chunk?.start_frame === chunkStart * 10;
  const boxes = synchronized
    ? (chunk.frames[frameIndex - chunk.start_frame] ?? [])
    : [];
  const native = synchronized
    ? (chunk.simulation[Math.floor(time).toString()] ?? [])
    : [];
  const nextNative = new Map(
    (synchronized
      ? (chunk.simulation[(Math.floor(time) + 1).toString()] ?? [])
      : []
    ).map((vehicle) => [vehicle[0], vehicle]),
  );
  const phase = manifest?.phases.find(
    (phase) => phase.start <= time && time < phase.end,
  );
  const seek = (target: number) => {
    if (video.current) {
      video.current.currentTime = target;
      setTime(target);
    }
  };
  const toggle = () => {
    if (!video.current) return;
    if (video.current.paused)
      video.current
        .play()
        .catch(() =>
          setError("Playback could not start. Retry after the video loads."),
        );
    else {
      resume.current = false;
      video.current.pause();
    }
  };

  return (
    <Shell
      title="Real video. Measured reconstruction."
      eyebrow="NGSIM / LANKERSHIM / JUNE 16, 2005"
      action={
        <Link className="button secondary" href="/benchmarks">
          Historical benchmarks
        </Link>
      }
    >
      <div className={styles.intro}>
        <span className={styles.badge}>
          HISTORICAL VIDEO · PRECOMPUTED REAL PROCESSING
        </span>
        <h2>Watch the traffic. Inspect where the twin falls short.</h2>
        <p>
          A complete 18:42 raw recording processed through ATLAS, alongside an
          actual SUMO run driven by its CV track crossings. The baseline misses
          substantial traffic. This is a reproducible experiment, with
          independent observations and visible errors.
        </p>
      </div>
      {error ? (
        <div className={styles.error} role="alert">
          {error}{" "}
          <button onClick={() => setRetry((value) => value + 1)}>
            Retry loading
          </button>
        </div>
      ) : null}
      {!manifest ? (
        <div className={styles.loading}>
          Loading the verified video experiment…
        </div>
      ) : (
        <>
          <div className={styles.panels}>
            <section className={styles.panel} aria-label="Real traffic video">
              <div className={styles.panelHead}>
                <h2>Observed traffic / ATLAS CV</h2>
                <span>Raw footage → detection → ByteTrack</span>
              </div>
              <div className={styles.scene}>
                <video
                  ref={video}
                  src={BASE + manifest.video}
                  poster={BASE + manifest.poster}
                  muted
                  playsInline
                  preload="metadata"
                  onLoadedMetadata={() => {
                    if (
                      video.current &&
                      Math.abs(video.current.duration - manifest.duration_s) >
                        0.2
                    )
                      setError(
                        "Video duration does not match the verified replay.",
                      );
                    else seek(600);
                  }}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                  onSeeked={() => {
                    if (video.current) setTime(video.current.currentTime);
                  }}
                  onEnded={() => setPlaying(false)}
                  onError={() =>
                    setError("Historical video asset could not be decoded.")
                  }
                  aria-label="Complete historical Lankershim traffic video with ATLAS tracking overlay"
                >
                  <track
                    kind="captions"
                    src={BASE + "description.vtt"}
                    srcLang="en"
                    label="Silent footage description"
                  />
                </video>
                <svg
                  className={styles.overlay}
                  viewBox="0 0 640 480"
                  aria-hidden="true"
                >
                  {boxes.map(([id, x1, y1, x2, y2, category]) => (
                    <g key={id}>
                      <rect
                        x={x1}
                        y={y1}
                        width={x2 - x1}
                        height={y2 - y1}
                        fill="none"
                        stroke={category === "person" ? "#ffd080" : "#9ff5c0"}
                        strokeWidth="1.3"
                      />
                      <text
                        x={x1}
                        y={Math.max(13, y1 - 3)}
                        fill="#c6ffdc"
                        stroke="#10251c"
                        strokeWidth="2.3"
                        paintOrder="stroke"
                        fontSize="11"
                        fontWeight="600"
                      >
                        CV {id}
                      </text>
                    </g>
                  ))}
                </svg>
              </div>
              <div className={styles.panelFoot}>
                {synchronized
                  ? `${boxes.length} visible model tracks`
                  : "Loading timestamp-matched boxes…"}{" "}
                <span>10 frames/s source · all 11,220 frames processed</span>
              </div>
            </section>
            <section
              className={styles.panel}
              aria-label="Synchronized SUMO reconstruction"
            >
              <div className={styles.panelHead}>
                <h2>CV-driven SUMO reconstruction</h2>
                <span>
                  Free-running baseline · no interior position forcing
                </span>
              </div>
              <svg
                className={styles.scene}
                viewBox={viewport}
                role="img"
                aria-label={`Actual SUMO reconstruction at ${clock(time)}, with ${native.length} simulated vehicles. Signal states use an approximate RSM-derived phase model.`}
              >
                <rect
                  x="-300"
                  y="-300"
                  width="700"
                  height="700"
                  fill="#14272b"
                />
                {manifest.lanes.map((lane) => (
                  <polyline
                    key={lane.id}
                    points={lane.shape
                      .map((point) => screen(point).join(","))
                      .join(" ")}
                    fill="none"
                    stroke="#344850"
                    strokeWidth={lane.width}
                  />
                ))}
                <polygon
                  points={manifest.junction
                    .map((point) => screen(point).join(","))
                    .join(" ")}
                  fill="#344850"
                />
                {manifest.lanes.map((lane) => (
                  <polyline
                    key={lane.id}
                    points={lane.shape
                      .map((point) => screen(point).join(","))
                      .join(" ")}
                    fill="none"
                    stroke="#8a9d9f"
                    strokeOpacity="0.35"
                    strokeWidth="0.15"
                    strokeDasharray="1.8 2.2"
                  />
                ))}
                {manifest.signal_heads.map((signal) => {
                  const [x, y] = screen(signal.point);
                  const state = phase?.state[signal.index]?.toLowerCase();
                  return (
                    <circle
                      key={signal.lane}
                      cx={x}
                      cy={y}
                      r="0.7"
                      fill={
                        state === "g"
                          ? "#94e9af"
                          : state === "y"
                            ? "#efcf85"
                            : "#f09a8b"
                      }
                      stroke="#14272b"
                      strokeWidth="0.3"
                    />
                  );
                })}
                {native.map(([id, x, y, speed, angle]) => {
                  const next = nextNative.get(id),
                    fraction = time % 1;
                  const [u, v] = screen(
                    next
                      ? [
                          x + (next[1] - x) * fraction,
                          y + (next[2] - y) * fraction,
                        ]
                      : [x, y],
                  );
                  const radians = (angle * Math.PI) / 180;
                  const direction = screen([
                    Math.sin(radians),
                    Math.cos(radians),
                  ]);
                  const rotation =
                    (Math.atan2(direction[1], direction[0]) * 180) / Math.PI;
                  return (
                    <g key={id}>
                      <rect
                        x={u - 3.4}
                        y={v - 0.75}
                        width="3.4"
                        height="1.5"
                        rx="0.3"
                        fill="#a8d6bc"
                        transform={`rotate(${rotation} ${u} ${v})`}
                      />
                      <text x={u + 2} y={v - 1.2} fill="#e6f3f5" fontSize="2.2">
                        {id.replace("cv_", "CV ")} · {speed.toFixed(1)} m/s
                      </text>
                    </g>
                  );
                })}
              </svg>
              <div className={styles.panelFoot}>
                {synchronized
                  ? `${native.length} actual SUMO vehicles`
                  : "Buffering synchronized simulation…"}
                <span>
                  Modeled signals · 1 Hz output, interpolated for display
                </span>
              </div>
            </section>
          </div>
          <div className={styles.transport}>
            <button
              className="button"
              onClick={toggle}
              disabled={!synchronized}
            >
              {playing ? "Pause" : "Play"}
            </button>
            <output aria-label="Playback time">
              {clock(time)} / {clock(manifest.duration_s)}
            </output>
            <label className={styles.timeline}>
              Shared video / simulation time
              <input
                aria-label="Shared replay timeline"
                type="range"
                min="0"
                max={manifest.duration_s - 0.1}
                step="0.1"
                value={Math.min(time, manifest.duration_s - 0.1)}
                onChange={(event) => seek(Number(event.target.value))}
              />
            </label>
            <label>
              Speed
              <select
                aria-label="Playback speed"
                defaultValue="1"
                onChange={(event) => {
                  if (video.current)
                    video.current.playbackRate = Number(event.target.value);
                }}
              >
                <option value="0.5">0.5×</option>
                <option value="1">1×</option>
                <option value="2">2×</option>
              </select>
            </label>
            <button className="button secondary" onClick={() => seek(600)}>
              Validation interval
            </button>
          </div>
          <div className={styles.metrics}>
            <div>
              <span>COMPLETE CPU PIPELINE</span>
              <strong>{display(manifest.performance.processed_fps)} FPS</strong>
              <small>
                Complete 11,220-frame verification run; shared CPU, 960 px
              </small>
            </div>
            <div>
              <span>CV POINT-TRAJECTORY IDF1</span>
              <strong>{display(manifest.cv.identity.IDF1, 3)}</strong>
              <small>4 m distance gate; validation only, not box IDF1</small>
            </div>
            <div>
              <span>CV MATCH COVERAGE</span>
              <strong>
                {display(
                  manifest.cv.spatial_matching.reference_coverage * 100,
                  1,
                )}
                %
              </strong>
              <small>
                Independent vehicle observations in the measured region
              </small>
            </div>
            <div>
              <span>SIMULATION COUNT MAE</span>
              <strong>
                {display(manifest.metrics.instantaneous_vehicle_count.mae)}{" "}
                vehicles
              </strong>
              <small>Instantaneous visible count; substantial undercount</small>
            </div>
            <div>
              <span>MATCHED CV SPEED MAE</span>
              <strong>
                {display(manifest.cv.speed_mps_matched_pairs.mae)} m/s
              </strong>
              <small>
                Matched pairs only; read alongside reference coverage
              </small>
            </div>
            <div>
              <span>SIMULATED QUEUE COUNT MAE</span>
              <strong>
                {display(manifest.metrics.sb_queue_count.mae)} vehicles
              </strong>
              <small>
                Fixed southbound stopped-vehicle region, validation only
              </small>
            </div>
          </div>
          <section className={styles.evaluation}>
            <div>
              <span className={styles.badge}>
                INDEPENDENT OBSERVATIONS / VALIDATION, NOT FINAL HOLDOUT
              </span>
              <h2>The discrepancies are part of the result.</h2>
              <p>
                Green is independently transcribed FHWA traffic. Blue is the
                actual video-driven SUMO output. Position updates from observed
                interior trajectories are never used to force the simulation.
              </p>
            </div>
            <div className={styles.plots}>
              <Plot
                rows={series}
                observed="observed_vehicles"
                simulated="simulated_vehicles"
                label="Visible vehicles"
                time={time}
              />
              <Plot
                rows={series}
                observed="observed_sb_queue"
                simulated="simulated_sb_queue"
                label="Southbound stopped queue (vehicles)"
                time={time}
              />
            </div>
            <p>
              Queue: below 0.5 m/s for at least 2 seconds in a fixed upstream
              region. Geometry omits turn bays, the bus layby and midblock
              driveways; the signal program reduces the source RSM timing to two
              stages. Individual vehicle travel times and exact observed lamp
              states are not validated.
            </p>
            <div className={styles.links}>
              <a
                href={BASE + "cv-driven-validation.json"}
                target="_blank"
                rel="noopener noreferrer"
              >
                Inspect simulation errors ↗
              </a>
              <a
                href={BASE + "cv-validation.json"}
                target="_blank"
                rel="noopener noreferrer"
              >
                Inspect independent CV evaluation ↗
              </a>
              <a
                href="https://github.com/youssef061204/ATLAS/blob/main/docs/reality-v6-implementation-plan.md"
                target="_blank"
                rel="noopener noreferrer"
              >
                Implementation plan ↗
              </a>
            </div>
          </section>
          {holdout ? (
            <section className={styles.evaluation}>
              <span className={styles.badge}>
                QUALIFIED SECOND-RECORDING HOLDOUT / INCOMPLETE SOURCE
              </span>
              <h2>Coverage limits the conclusion.</h2>
              <p>
                {holdout.source_availability.scored_seconds} of{" "}
                {holdout.source_availability.planned_seconds} planned seconds
                are scoreable (
                {display(
                  100 * holdout.source_availability.planned_window_coverage,
                  1,
                )}
                %). With frozen parameters, the CV-driven twin has{" "}
                {display(holdout.instantaneous_vehicle_count.mae)} vehicles of
                instantaneous count MAE and{" "}
                {display(holdout.sb_queue_count.mae)} vehicles of stopped-queue
                MAE. The full planned holdout is incomplete, and reconstruction
                remains unvalidated.
              </p>
              <div className={styles.links}>
                <a
                  href={BASE + manifest.research?.holdout}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Inspect qualified holdout and missing coverage ↗
                </a>
              </div>
            </section>
          ) : null}
          {cityflow ? (
            <section className={styles.evaluation}>
              <span className={styles.badge}>
                CITYFLOWV2 / FOUR COMPLETE CAMERAS / ZERO-SHOT RESEARCH
              </span>
              <h2>Test the frozen pipeline across cameras.</h2>
              <p>
                {cityflow.total_decoded_and_processed_frames.toLocaleString(
                  "en-US",
                )}{" "}
                consecutive frames across all four S02 videos. With the same
                candidate detections, global IDF1 is{" "}
                {display(cityflow.before_association.identity.IDF1, 3)} before
                cross-camera association and{" "}
                {display(
                  cityflow.after_association_same_detections.identity.IDF1,
                  3,
                )}{" "}
                afterward. The separate multi-camera-filtered result is{" "}
                {display(cityflow.multicamera_filtered.identity.IDF1, 3)}.{" "}
                Association regressed and is not promoted.
              </p>
              <p>
                This is one annotation-scoped transfer experiment, not the full
                CityFlowV2 benchmark or a leaderboard submission. Only
                multi-camera vehicles are annotated. CityFlow videos, crops and
                appearance embeddings remain local under its noncommercial
                research license.
              </p>
              <div className={styles.links}>
                <a
                  href={BASE + manifest.research?.cityflow}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Inspect CityFlow protocol, ablation and limitations ↗
                </a>
              </div>
            </section>
          ) : null}
          <section className={styles.limitations}>
            <h2>Reconstruction first. Controller claims later.</h2>
            <p>
              This baseline has not established acceptable physical fidelity.
              New controller comparisons are deferred until reconstruction
              validation passes. Historical ATLAS 5 controller results remain
              separate simulation studies.
            </p>
            <p>
              The second official raw file is internally truncated. A ZIP
              checksum does not establish that its video is complete. The
              complete first recording is shown here; final holdout coverage and
              source failures must be reported separately.
            </p>
            <p>
              No field-live processing runs on this public deployment. This view
              replays real historical video and precomputed processing; it is
              never labelled live processing. A separate native Caltrans HLS
              trial checks stream ingestion; its nighttime tracking accuracy is
              unvalidated.
            </p>
            {liveTrial ? (
              <p>
                Archived native stream trial ({liveTrial.observed_start_utc}):{" "}
                {liveTrial.final_health.decoded_frames.toLocaleString("en-US")}{" "}
                consecutive frames decoded,{" "}
                {liveTrial.predicted_observations.length} frames with predicted
                tracks. Temporary media was deleted. This is past execution
                telemetry, not current live traffic.{" "}
                <a
                  href={BASE + manifest.research?.live}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Inspect stream health and source conditions ↗
                </a>
              </p>
            ) : null}
          </section>
          <p className={styles.credit}>
            Video: FHWA NGSIM, Lankershim Boulevard, June 16, 2005.{" "}
            <a
              href={BASE + "source-license.txt"}
              target="_blank"
              rel="noopener noreferrer"
            >
              Source, changes and CC BY-SA licensing ↗
            </a>
          </p>
        </>
      )}
    </Shell>
  );
}
