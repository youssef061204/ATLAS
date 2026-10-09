"use client";
import { useState } from "react";
import { request } from "@/lib/api";

export function SceneEditor({
  city,
  cameraId,
  observationId,
  image,
  roads,
  onSaved,
}: {
  city: string;
  cameraId: string;
  observationId: string;
  image: string;
  roads: { road_id: string; distance_m: number }[];
  onSaved: (region: {
    revision: number;
    derived_observation: unknown;
    estimated_state: unknown;
    forecast: unknown;
  }) => void;
}) {
  const [points, setPoints] = useState<[number, number][]>([]);
  const [road, setRoad] = useState(roads[0]?.road_id ?? "");
  const [name, setName] = useState("Observed road region");
  const [kind, setKind] = useState("road_region");
  const [x, setX] = useState(0.5),
    [y, setY] = useState(0.5);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false),
    [status, setStatus] = useState("");
  const [error, setError] = useState("");
  function addPoint(point: [number, number]) {
    if (points.length < 12) setPoints([...points, point]);
  }
  async function save() {
    const supplied = key;
    setKey("");
    setBusy(true);
    setError("");
    try {
      const region = await request<{
        revision: number;
        visible_detections_in_region: number;
        derived_observation: unknown;
        estimated_state: unknown;
        forecast: unknown;
      }>("/api/operations/scenes", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${supplied}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          city,
          camera_id: cameraId,
          observation_id: observationId,
          road_id: road,
          name,
          kind,
          polygon: points,
        }),
      });
      setStatus(
        `Saved revision ${region.revision}: ${region.visible_detections_in_region} detections inside your region. This is an operator correction; independent lane validation and physical calibration remain unavailable.`,
      );
      onSaved(region);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Region could not be saved");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="scene-editor">
      <summary>Correct the camera’s road region</summary>
      <p>
        Click the matching source image to outline an observed region, or add
        normalized vertices with the keyboard. Link it to an imported road. Your
        annotation never establishes motion, a physical queue, or surveyed lane
        accuracy.
      </p>
      <button
        type="button"
        className="scene-canvas"
        aria-label="Add region vertex on the actual camera image"
        onClick={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          addPoint(
            event.detail === 0
              ? [x, y]
              : [
                  Math.min(
                    1,
                    Math.max(0, (event.clientX - bounds.left) / bounds.width),
                  ),
                  Math.min(
                    1,
                    Math.max(0, (event.clientY - bounds.top) / bounds.height),
                  ),
                ],
          );
        }}
      >
        {/* Ephemeral authenticated source image; intentionally never written into web assets. */}
        <img
          src={image}
          alt="Actual permitted camera observation for manual region annotation"
        />
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <polygon
            points={points.map(([a, b]) => `${a * 100},${b * 100}`).join(" ")}
          />
          {points.map(([a, b], i) => (
            <circle key={i} cx={a * 100} cy={b * 100} r="1" />
          ))}
        </svg>
      </button>
      <div className="city-toolbar">
        <label>
          Vertex x{" "}
          <input
            aria-label="Region vertex x"
            type="number"
            min="0"
            max="1"
            step=".01"
            value={x}
            onChange={(e) =>
              setX(Math.min(1, Math.max(0, Number(e.target.value))))
            }
          />
        </label>
        <label>
          Vertex y{" "}
          <input
            aria-label="Region vertex y"
            type="number"
            min="0"
            max="1"
            step=".01"
            value={y}
            onChange={(e) =>
              setY(Math.min(1, Math.max(0, Number(e.target.value))))
            }
          />
        </label>
        <button
          type="button"
          className="button secondary"
          onClick={() => addPoint([x, y])}
          disabled={points.length >= 12}
        >
          Add vertex
        </button>
        <button
          type="button"
          className="button secondary"
          onClick={() => setPoints(points.slice(0, -1))}
          disabled={!points.length}
        >
          Undo vertex
        </button>
      </div>
      <p>
        {points.length} vertices ·{" "}
        {points
          .map(([a, b]) => `(${a.toFixed(2)}, ${b.toFixed(2)})`)
          .join(" → ")}
      </p>
      <label>
        Region name{" "}
        <input
          aria-label="Region name"
          maxLength={64}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Region type{" "}
        <select
          aria-label="Region type"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="road_region">Road region</option>
          <option value="approach_lane">Approach lane</option>
          <option value="crosswalk">Crosswalk</option>
        </select>
      </label>
      <label>
        Road alignment{" "}
        <select
          aria-label="Corrected road alignment"
          value={road}
          onChange={(e) => setRoad(e.target.value)}
        >
          {roads.map((r) => (
            <option key={r.road_id} value={r.road_id}>
              {r.road_id} · {r.distance_m.toFixed(1)} m from camera coordinate
            </option>
          ))}
        </select>
      </label>
      <label>
        Operator key{" "}
        <input
          aria-label="Scene operator key"
          type="password"
          autoComplete="off"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </label>
      <button
        type="button"
        className="button"
        onClick={save}
        disabled={busy || points.length < 3 || !key || !road || !name.trim()}
      >
        {busy ? "Saving region…" : "Save corrected region"}
      </button>
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
