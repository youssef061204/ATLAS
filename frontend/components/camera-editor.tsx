"use client";
import { useState } from "react";
import { Save, X } from "lucide-react";
import { API } from "@/lib/api";
import type { CameraConfig, Result, Vec } from "@/lib/types";

export function CameraEditor({
  result,
  onClose,
  onSave,
}: {
  result: Result;
  onClose: () => void;
  onSave: (config: CameraConfig) => Promise<void>;
}) {
  const [points, setPoints] = useState<Vec[]>(
    result.config.calibration?.image || [],
  );
  const [world, setWorld] = useState<Vec[]>(
    result.config.calibration?.world || [
      [0, 0],
      [30, 0],
      [30, 30],
      [0, 30],
    ],
  );
  const [verified, setVerified] = useState(
    result.config.calibration?.verified || false,
  );
  const [regions, setRegions] = useState(
    JSON.stringify(result.config.regions, null, 2),
  );
  const [settings, setSettings] = useState(result.config);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (points.length > 0 && points.length !== 4)
        throw new Error("Select all four calibration points or clear them.");
      await onSave({
        ...settings,
        calibration: points.length
          ? {
              image: points,
              world,
              verified,
              note: "Four control points entered in camera editor",
            }
          : null,
        regions: JSON.parse(regions),
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="camera-title"
      >
        <div className="panel-heading">
          <span id="camera-title">CAMERA / ROAD-PLANE CALIBRATION</span>
          <button
            className="icon-button"
            aria-label="Close camera setup"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">
          <p>
            Click four known points on the road plane in order. Enter their
            surveyed coordinates in meters. Only verify calibration if those
            distances are known.
          </p>
          <div
            className="calibration-source"
            onClick={(e) => {
              if (points.length >= 4) return;
              const box = e.currentTarget.getBoundingClientRect();
              setPoints([
                ...points,
                [
                  ((e.clientX - box.left) / box.width) * result.metadata.width,
                  ((e.clientY - box.top) / box.height) * result.metadata.height,
                ],
              ]);
            }}
          >
            <video
              src={`${API}/api/videos/${result.video_id}/source#t=0.1`}
              muted
              preload="auto"
            />
            <svg
              viewBox={`0 0 ${result.metadata.width} ${result.metadata.height}`}
            >
              {points.length > 2 && (
                <polygon
                  points={points.map((p) => p.join(",")).join(" ")}
                  fill="#8fccbe25"
                  stroke="#8fccbe"
                />
              )}
              {points.map((p, i) => (
                <g key={i}>
                  <circle cx={p[0]} cy={p[1]} r={8} fill="#aedfca" />
                  <text x={p[0] + 12} y={p[1] + 5} fill="white" fontSize={16}>
                    {i + 1}
                  </text>
                </g>
              ))}
            </svg>
          </div>
          <button
            className="text-button"
            onClick={() => {
              setPoints([]);
              setVerified(false);
            }}
          >
            Clear points
          </button>
          <div className="coordinate-grid">
            {world.map((p, i) => (
              <label key={i}>
                POINT {i + 1} · WORLD METERS
                <div>
                  {p.map((v, axis) => (
                    <input
                      key={axis}
                      aria-label={`Point ${i + 1} ${axis ? "y" : "x"}`}
                      type="number"
                      value={v}
                      onChange={(e) =>
                        setWorld(
                          world.map((point, j) =>
                            j === i
                              ? (point.map((v, a) =>
                                  a === axis ? Number(e.target.value) : v,
                                ) as Vec)
                              : point,
                          ),
                        )
                      }
                    />
                  ))}
                </div>
              </label>
            ))}
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={verified}
              onChange={(e) => setVerified(e.target.checked)}
            />{" "}
            Coordinates are measured on the road plane; enable physical speeds
            and safety screens.
          </label>
          <div className="form-grid">
            <label>
              Detector profile
              <select
                value={settings.detector_profile || "coco"}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    detector_profile: e.target
                      .value as CameraConfig["detector_profile"],
                  })
                }
              >
                <option value="coco">COCO · street-level</option>
                <option value="aerial">VisDrone · overhead</option>
              </select>
            </label>
            <label>
              Confidence
              <input
                type="number"
                min="0.05"
                max="0.95"
                step="0.05"
                value={settings.confidence}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    confidence: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Resolution
              <select
                value={settings.resolution}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    resolution: Number(e.target.value),
                  })
                }
              >
                {[320, 480, 640, 960, 1280].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Sample every N frames
              <input
                type="number"
                min="1"
                max="30"
                value={settings.sample_every}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    sample_every: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Tracker
              <select
                value={settings.tracker}
                onChange={(e) =>
                  setSettings({ ...settings, tracker: e.target.value })
                }
              >
                <option>bytetrack.yaml</option>
                <option>botsort.yaml</option>
              </select>
            </label>
          </div>
          <label className="region-label">
            REGIONS · IMAGE-PIXEL POLYGONS
            <textarea
              aria-label="Region configuration"
              value={regions}
              onChange={(e) => setRegions(e.target.value)}
              rows={6}
              spellCheck={false}
            />
            <small>
              Schema:{" "}
              {`[{"id":"box","kind":"intersection","polygon":[[x,y],...],"direction":null}]`}
              . Kinds: inbound, outbound, crosswalk, intersection, waiting,
              stop_line.
            </small>
          </label>
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <div className="button-row">
            <button className="button" onClick={save} disabled={busy}>
              <Save size={16} />
              {busy ? "Saving…" : "Save & reprocess"}
            </button>
            <button className="button secondary" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
