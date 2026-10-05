"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  CirclePlay,
  FileVideo,
  LoaderCircle,
  Pause,
  Play,
  Settings2,
  Upload,
  X,
} from "lucide-react";
import { API, DEMO_MODE, post, request } from "@/lib/api";
import type { CameraConfig, Result, Video } from "@/lib/types";
import { Twin, type TwinMode } from "./twin";
import { TrendChart } from "./charts";
import { Shell } from "./shell";
import { CameraEditor } from "./camera-editor";

export function useResult() {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    request<Video[]>("/api/videos")
      .then(async (videos) => {
        const id = localStorage.getItem("atlas-video");
        const video =
          videos.find((v) => v.id === id && v.status === "complete") ||
          videos.find((v) => v.status === "complete");
        if (video) {
          const data = await request<Result>(`/api/videos/${video.id}/result`);
          if (alive) setResult(data);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  return { result, error };
}
export function Workspace() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [video, setVideo] = useState<Video | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<TwinMode>("FLOW");
  const [selected, setSelected] = useState<number>();
  const [edit, setEdit] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoId = video?.id;
  const videoStatus = video?.status;
  async function load(v: Video) {
    setVideo(v);
    localStorage.setItem("atlas-video", v.id);
    setResult(null);
    setTime(0);
    setPlaying(false);
    if (v.status === "complete") {
      const data = await request<Result>(`/api/videos/${v.id}/result`);
      setResult(data);
    }
  }
  useEffect(() => {
    request<Video[]>("/api/videos")
      .then((vs) => {
        setVideos(vs);
        const id = localStorage.getItem("atlas-video");
        const chosen = vs.find((v) => v.id === id) || vs[0];
        if (chosen) void load(chosen).catch((e) => setError(e.message));
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (
      !videoId ||
      !videoStatus ||
      !["queued", "processing"].includes(videoStatus)
    )
      return;
    const stream = new EventSource(
      `${API}/api/videos/${videoId}/events-stream`,
    );
    stream.onmessage = (e) => {
      const v: Video = JSON.parse(e.data);
      setVideo(v);
      if (v.status === "complete") {
        stream.close();
        void load(v).catch((e) => setError(e.message));
        request<Video[]>("/api/videos")
          .then(setVideos)
          .catch((e) => setError(e.message));
      }
      if (v.status === "failed") {
        stream.close();
        setError(v.error || "Processing failed");
      }
    };
    stream.onerror = () => {
      stream.close();
      setError(
        "Progress connection closed. Refresh to check processing status.",
      );
    };
    return () => stream.close();
  }, [videoId, videoStatus]);
  useEffect(() => {
    const node = videoRef.current;
    if (!node || !playing) return;
    let id: number;
    const tick = () => {
      setTime(node.currentTime);
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [playing]);
  async function demo() {
    setBusy(true);
    setError("");
    try {
      const v = await post<Video>("/api/demo");
      await load(v);
      setVideos(await request<Video[]>("/api/videos"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const v = await request<Video>("/api/videos", { method: "POST", body });
      await load(v);
      setVideos(await request<Video[]>("/api/videos"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function seek(t: number) {
    setTime(t);
    if (videoRef.current) videoRef.current.currentTime = t;
  }
  function play() {
    const node = videoRef.current;
    if (!node) return;
    if (node.paused) {
      node.play().catch((e) => setError(e.message));
    } else node.pause();
  }
  const index = result
    ? Math.max(
        0,
        Math.min(
          result.frames.length - 1,
          Math.floor(
            (time * result.metadata.fps) /
              (result.config.sample_every *
                (result.provenance.replay_stride || 1)),
          ),
        ),
      )
    : 0;
  const frame = result?.frames[index];
  const metric = result?.metrics[index];
  const object = frame?.objects.find((o) => o.id === selected);
  const activeEvent = result?.events.find((e) => Math.abs(e.t - time) < 1);
  return (
    <Shell
      title="Intersection intelligence"
      eyebrow="OBSERVE / RECONSTRUCT"
      action={
        <>
          <button
            className="button secondary"
            onClick={() => setEdit(true)}
            disabled={!result || DEMO_MODE}
          >
            <Settings2 size={15} /> Camera setup
          </button>
          <button
            className="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy || DEMO_MODE}
          >
            <Upload size={15} /> Import footage
          </button>
        </>
      }
    >
      <input
        ref={fileRef}
        type="file"
        accept="video/*,.mkv,.avi"
        hidden
        onChange={(e) => upload(e.target.files?.[0])}
      />
      {error && (
        <div role="alert" className="error-banner">
          {error}
          <button
            className="icon-button"
            aria-label="Dismiss error"
            onClick={() => setError("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
      <div className="workspace-bar">
        <div>
          <span className="status-dot" />
          <strong>{video?.filename || "Your first intersection"}</strong>
          <span className="pill">
            {DEMO_MODE
              ? "PRECOMPUTED REAL CV DEMO"
              : video?.status === "complete"
                ? video.metadata.cached
                  ? "CACHED REAL CV OUTPUT"
                  : "RECORDED OBSERVATIONS"
                : "LOCAL PROCESSING"}
          </span>
        </div>
        <div className="video-picker">
          <select
            aria-label="Select video"
            value={video?.id || ""}
            onChange={(e) => {
              const v = videos.find((v) => v.id === e.target.value);
              if (v) void load(v).catch((e) => setError(e.message));
            }}
          >
            <option value="" disabled>
              Select footage
            </option>
            {videos.map((v) => (
              <option value={v.id} key={v.id}>
                {v.filename} · {v.status}
              </option>
            ))}
          </select>
          <ChevronDown size={14} />
        </div>
      </div>
      {!video ? (
        <div className="import-empty panel">
          <div className="empty-orbit">
            <FileVideo size={38} strokeWidth={1} />
          </div>
          <div className="eyebrow">EVERY FRAME BECOMES A SIGNAL</div>
          <h2>Start with a street-level view.</h2>
          <p>
            Import traffic footage to detect, track, and reconstruct road users.
            <br />
            Processing runs locally. No API key required.
          </p>
          <div className="button-row">
            <button className="button" onClick={demo} disabled={busy}>
              {busy ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <CirclePlay size={16} />
              )}{" "}
              Process sample footage
            </button>
            <button
              className="button secondary"
              onClick={() => fileRef.current?.click()}
              disabled={busy}
            >
              <Upload size={16} /> Upload a video
            </button>
          </div>
          <small>MP4, WEBM, MOV, AVI, MKV · UP TO 250 MB</small>
        </div>
      ) : !result ? (
        <div className="processing panel">
          <div className="eyebrow">
            {video.status === "failed"
              ? "PROCESSING STOPPED"
              : "VIDEO → STRUCTURED INTELLIGENCE"}
          </div>
          <h2>
            {video.status === "failed"
              ? "This source needs attention."
              : "Reading the road."}
          </h2>
          <p>
            {video.error ||
              `Current stage: ${video.stage.replaceAll("_", " ")}`}
          </p>
          {video.metadata.live_metric && (
            <p>
              {video.metadata.live_metric.active_objects} active road users ·
              frame at {video.metadata.live_metric.t.toFixed(1)} s
            </p>
          )}
          <div className="progress">
            <span style={{ width: `${video.progress * 100}%` }} />
          </div>
          <div className="processing-stages">
            {[
              "queued",
              "preprocessing",
              "detection_tracking",
              "analytics_safety",
              "complete",
            ].map((s, i) => (
              <div key={s} className={s === video.stage ? "current" : ""}>
                <span>
                  {s === video.stage ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <Check size={15} />
                  )}
                </span>
                {String(i + 1).padStart(2, "0")} {s.replaceAll("_", " ")}
              </div>
            ))}
          </div>
          {video.status === "failed" && (
            <button
              className="button"
              onClick={() =>
                post<Video>(`/api/videos/${video.id}/reprocess`)
                  .then(load)
                  .catch((e) => setError(e.message))
              }
            >
              Retry processing
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="metric-grid">
            {[
              {
                label: "ROAD USERS DETECTED",
                value: result.summary.unique_tracks,
                unit: "unique tracks",
                detail: `${result.summary.vehicles} vehicles · ${result.summary.pedestrians} pedestrians`,
              },
              {
                label: "ACTIVE IN FRAME",
                value: metric?.active_objects || 0,
                unit: "road users",
                detail: `At ${time.toFixed(1)} seconds`,
              },
              {
                label: "STOPPED QUEUE",
                value: metric?.queue_length || 0,
                unit: "vehicles",
                detail: `Peak observed: ${result.summary.max_queue}`,
              },
              {
                label: "PIPELINE PERFORMANCE",
                value: result.performance.processed_fps.toFixed(1),
                unit: "sampled FPS",
                detail: `${result.performance.device.toUpperCase()} · ${result.performance.model}`,
              },
            ].map((m, i) => (
              <div className="stat-card" key={m.label}>
                <div className="stat-label">
                  <span className={`stat-dot dot-${i}`} />
                  {m.label}
                </div>
                <div className="stat-value">
                  {m.value}
                  <span>{m.unit}</span>
                </div>
                <div className="stat-detail">{m.detail}</div>
              </div>
            ))}
          </div>
          <div className="observation-grid">
            <section className="panel video-panel">
              <div className="panel-heading">
                <span>
                  <span className="status-dot" /> SOURCE / COMPUTER VISION
                </span>
                <span className="mono">
                  {result.metadata.width} × {result.metadata.height}
                </span>
              </div>
              <div className="source-stage">
                <video
                  ref={videoRef}
                  src={`${API}/api/videos/${video.id}/source`}
                  preload="auto"
                  muted
                  playsInline
                  autoPlay={DEMO_MODE}
                  onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                  onEnded={() => setPlaying(false)}
                />
                <svg
                  viewBox={`0 0 ${result.metadata.width} ${result.metadata.height}`}
                  className="cv-overlay"
                  aria-label="Detection overlay"
                >
                  {result.config.regions.map((r) => (
                    <polygon
                      key={r.id}
                      points={r.polygon.map((p) => p.join(",")).join(" ")}
                      fill="#91caba15"
                      pointerEvents="none"
                      stroke="#91caba"
                      strokeDasharray="8 5"
                    />
                  ))}
                  {frame?.objects.map((o) => (
                    <g
                      key={o.id}
                      onClick={() => setSelected(o.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <rect
                        x={o.bbox[0]}
                        y={o.bbox[1]}
                        width={o.bbox[2] - o.bbox[0]}
                        height={o.bbox[3] - o.bbox[1]}
                        fill={selected === o.id ? "#ffffff15" : "transparent"}
                        stroke={
                          selected === o.id
                            ? "#fff"
                            : o.class === "person"
                              ? "#ebc785"
                              : "#9bd9c4"
                        }
                        strokeWidth={1.7}
                      />
                      <rect
                        x={o.bbox[0]}
                        y={Math.max(0, o.bbox[1] - 16)}
                        width={90}
                        height={16}
                        fill="#10251ee8"
                      />
                      <text
                        x={o.bbox[0] + 3}
                        y={Math.max(12, o.bbox[1] - 4)}
                        fill="#d7f8ec"
                        fontSize={10}
                        fontFamily="monospace"
                      >
                        {o.class} #{o.id} {Math.round(o.confidence * 100)}%
                      </text>
                    </g>
                  ))}
                </svg>
                <span className="source-stamp">
                  {time.toFixed(2)}s / {result.metadata.duration.toFixed(2)}s
                </span>
              </div>
              <div className="source-legend">
                <span>
                  <i className="legend-dot" />
                  Vehicles
                </span>
                <span>
                  <i className="legend-dot amber" />
                  Pedestrians
                </span>
                <span>YOLO + {result.config.tracker.split(".")[0]}</span>
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <span>DIGITAL TWIN / RECONSTRUCTION</span>
                <span className="pill">3D</span>
              </div>
              <Twin
                result={result}
                objects={frame?.objects}
                mode={mode}
                selected={selected}
                onSelect={setSelected}
              />
              <div className="mode-tabs">
                {(["NORMAL", "FLOW", "HEATMAP", "SAFETY"] as TwinMode[]).map(
                  (m) => (
                    <button
                      key={m}
                      className={mode === m ? "selected" : ""}
                      onClick={() => setMode(m)}
                    >
                      {m}
                    </button>
                  ),
                )}
              </div>
            </section>
          </div>
          <div className="timeline panel">
            <button
              className="play-button"
              onClick={play}
              aria-label={playing ? "Pause playback" : "Play playback"}
            >
              {playing ? <Pause size={18} /> : <Play size={18} />}
            </button>
            <span className="mono">{time.toFixed(1)}s</span>
            <input
              aria-label="Video timeline"
              type="range"
              min={0}
              max={result.metadata.duration}
              step={0.01}
              value={time}
              onChange={(e) => seek(Number(e.target.value))}
            />
            <span className="mono">{result.metadata.duration.toFixed(1)}s</span>
            <select
              aria-label="Playback speed"
              defaultValue="1"
              onChange={(e) => {
                if (videoRef.current)
                  videoRef.current.playbackRate = Number(e.target.value);
              }}
            >
              {[0.5, 1, 2, 4].map((v) => (
                <option key={v} value={v}>
                  {v}×
                </option>
              ))}
            </select>
          </div>
          <div className="lower-grid">
            <section className="panel">
              <div className="panel-heading">
                <span>FLOW OVER TIME</span>
                <span className="chart-key">
                  <i /> Vehicles <i className="amber" /> Queue
                </span>
              </div>
              <TrendChart
                data={result.metrics
                  .filter((_, i) => i % 5 === 0)
                  .map((m) => ({
                    t: Number(m.t.toFixed(1)),
                    vehicles: m.vehicles,
                    queue: m.queue_length,
                  }))}
                keys={[
                  {
                    key: "vehicles",
                    name: "Active vehicles",
                    color: "#95cbbd",
                  },
                  { key: "queue", name: "Stopped queue", color: "#c9b386" },
                ]}
                area
              />
            </section>
            <section className="panel object-panel">
              <div className="panel-heading">
                <span>TRACK INSPECTOR</span>
                <span className="pill">
                  {selected ? `#${selected}` : "SELECT A ROAD USER"}
                </span>
              </div>
              {object ? (
                <div className="object-details">
                  <div className="object-title">
                    {object.class}
                    <span>{object.stopped ? "STOPPED" : "MOVING"}</span>
                  </div>
                  {[
                    ["Confidence", `${(object.confidence * 100).toFixed(1)}%`],
                    [
                      "Speed",
                      `${object.speed.toFixed(1)} ${metric?.speed_unit}`,
                    ],
                    ["Direction", object.direction],
                    [
                      "Stopped duration",
                      `${object.stopped_duration.toFixed(1)} s`,
                    ],
                    [
                      "World / image position",
                      object.world.map((v) => v.toFixed(1)).join(", "),
                    ],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <span>{k}</span>
                      <strong>{v}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="inspector-empty">
                  {selected
                    ? "This track is outside the current frame."
                    : "Select a bounding box or vehicle to inspect its trajectory."}
                </div>
              )}
              {activeEvent && (
                <button
                  className="event-inline"
                  onClick={() => seek(activeEvent.t)}
                >
                  {activeEvent.severity.toUpperCase()} ·{" "}
                  {activeEvent.explanation}
                </button>
              )}
            </section>
          </div>
          <div className="provenance-note">
            <Check size={14} /> Actual CV output ·{" "}
            {result.performance.processed_frames} sampled frames ·{" "}
            {result.summary.calibrated
              ? "Verified calibration"
              : "Image-space speed; metric distances disabled until calibration is verified"}
            <a href={`/analytics`}>
              Explore analytics <ArrowUpRight size={13} />
            </a>
          </div>
        </>
      )}
      {edit && result && video && (
        <CameraEditor
          result={result}
          onClose={() => setEdit(false)}
          onSave={async (camera: CameraConfig) => {
            await request(`/api/videos/${video.id}/camera`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(camera),
            });
            const v = await post<Video>(`/api/videos/${video.id}/reprocess`);
            setEdit(false);
            await load(v);
          }}
        />
      )}
    </Shell>
  );
}
