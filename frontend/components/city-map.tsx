"use client";
import { useState } from "react";
import type { CityReport, Network, Run, RoadEvent } from "@/lib/cities";

export function CityMap({
  city,
  network,
  frame,
  onCamera,
  events = [],
  onEvent,
}: {
  city?: CityReport;
  network?: Network;
  frame?: Run["trace"][number];
  onCamera?: (id: string) => void;
  events?: RoadEvent[];
  onEvent?: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const points =
    network?.roads.flatMap((r) => r.coordinates) ??
    city?.cameras.map((c) => [c.lon, c.lat]) ??
    [];
  if (!points.length)
    return <div className="empty-state">No verified geometry available.</div>;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const longitudeScale = Math.cos((((minY + maxY) / 2) * Math.PI) / 180);
  const scale = Math.min(
    640 / Math.max((maxX - minX) * longitudeScale, 0.0001),
    390 / Math.max(maxY - minY, 0.0001),
  );
  const project = (lon: number, lat: number) => [
    350 + (lon - (minX + maxX) / 2) * longitudeScale * scale,
    225 - (lat - (minY + maxY) / 2) * scale,
  ];
  return (
    <div className="city-map-wrap">
      <div className="city-map-tools">
        <button
          type="button"
          onClick={() => setZoom((v) => Math.min(4, v + 0.5))}
          aria-label="Zoom map in"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => setZoom((v) => Math.max(1, v - 0.5))}
          aria-label="Zoom map out"
        >
          −
        </button>
        <button type="button" onClick={() => setZoom(1)}>
          Reset
        </button>
      </div>
      <svg
        viewBox={`${350 - 350 / zoom} ${225 - 225 / zoom} ${700 / zoom} ${450 / zoom}`}
        aria-label={
          network
            ? "Imported OSM corridor and simulated signal states"
            : "Official camera coordinates"
        }
        role="group"
      >
        <rect x="0" y="0" width="700" height="450" fill="#101c22" />
        {network?.roads.map((r) => (
          <polyline
            key={r.id}
            points={r.coordinates
              .map(([lon, lat]) => project(lon, lat).join(","))
              .join(" ")}
            fill="none"
            stroke="#526a73"
            strokeWidth="2"
          >
            <title>{r.id}</title>
          </polyline>
        ))}
        {network?.signals
          .filter((s) => s.lat !== null && s.lon !== null)
          .map((s) => {
            const [x, y] = project(s.lon!, s.lat!);
            const status = frame?.signals[s.id];
            return (
              <circle
                key={s.id}
                cx={x}
                cy={y}
                r={status ? 5 : 2.5}
                fill={
                  status?.execution === "yellow" ||
                  status?.execution === "switch"
                    ? "#edb85a"
                    : status?.execution === "all_red"
                      ? "#ee7373"
                      : status
                        ? "#70c9bc"
                        : "#718087"
                }
              >
                <title>
                  {s.id}:{" "}
                  {status
                    ? `phase ${status.phase}, queue ${status.queue}, ${status.state}`
                    : "Generated signal; not in controller trace"}
                </title>
              </circle>
            );
          })}
        {frame?.vehicles && (
          <g role="img" aria-label="Actual simulated vehicle positions">
            {frame.vehicles.map((v) => {
              const [x, y] = project(v.lon, v.lat);
              return (
                <circle
                  key={v.id}
                  cx={x}
                  cy={y}
                  r="2.2"
                  fill={v.speed_m_s < 0.1 ? "#f0bf6d" : "#c3e3ff"}
                >
                  <title>
                    {v.id} · {v.speed_m_s.toFixed(1)} m/s · simulated
                  </title>
                </circle>
              );
            })}
          </g>
        )}
        {city?.cameras
          .filter(
            (c) =>
              !network ||
              (c.lon >= minX &&
                c.lon <= maxX &&
                c.lat >= minY &&
                c.lat <= maxY),
          )
          .map((c) => {
            const [x, y] = project(c.lon, c.lat);
            const checked = city.image_checks.find((s) => s.camera_id === c.id);
            return (
              <g
                key={c.id}
                role="button"
                tabIndex={0}
                aria-label={`Inspect camera ${c.name}`}
                onClick={() => onCamera?.(c.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onCamera?.(c.id);
                  }
                }}
              >
                <circle
                  cx={x}
                  cy={y}
                  r={checked ? 4.5 : 2.5}
                  fill={
                    checked?.status === "accessible" ? "#70c9bc" : "#82959c"
                  }
                />
                <title>{c.name}</title>
              </g>
            );
          })}
        {events
          .filter(
            (e) =>
              e.lon >= minX && e.lon <= maxX && e.lat >= minY && e.lat <= maxY,
          )
          .map((event) => {
            const [x, y] = project(event.lon, event.lat);
            return (
              <g
                key={event.id}
                role="button"
                tabIndex={0}
                aria-label={`Inspect reported road event ${event.description}`}
                onClick={() => onEvent?.(event.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onEvent?.(event.id);
                  }
                }}
              >
                <path
                  d={`M ${x} ${y - 6} L ${x + 6} ${y + 5} L ${x - 6} ${y + 5} Z`}
                  fill="#f0bf6d"
                  stroke="#0c2027"
                />
                <title>{event.description}</title>
              </g>
            );
          })}
      </svg>
      <p className="city-map-caption">
        {network
          ? "© OpenStreetMap contributors · ODbL · generated research signal plans"
          : `${city?.settings.attribution} · recorded catalog coordinates · imagery not redistributed`}
      </p>
    </div>
  );
}
