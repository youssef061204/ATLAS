"use client";
import { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { Maximize2, RotateCcw } from "lucide-react";
import type { ObjectState, Result, SimFrame } from "@/lib/types";

const colors: Record<string, string> = {
  car: "#94d5c6",
  truck: "#e2c998",
  bus: "#8eaee0",
  motorcycle: "#d2a1de",
  bicycle: "#d7b0e8",
  person: "#e8c48b",
};
export type TwinMode = "NORMAL" | "FLOW" | "HEATMAP" | "SAFETY";
export function simPosition(
  approach: number,
  position: number,
): [number, number, number] {
  if (approach === 0) return [3.5, 0.65, -position];
  if (approach === 1) return [position, 0.65, 3.5];
  if (approach === 2) return [-3.5, 0.65, position];
  return [-position, 0.65, -3.5];
}
function Roads({ frame }: { frame?: SimFrame }) {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[190, 190]} />
        <meshStandardMaterial color="#15282c" roughness={1} />
      </mesh>
      {[0, Math.PI / 2].map((r, i) => (
        <group key={i} rotation={[0, r, 0]}>
          <mesh
            position={[0, 0.02, 0]}
            rotation={[-Math.PI / 2, 0, 0]}
            receiveShadow
          >
            <planeGeometry args={[19, 180]} />
            <meshStandardMaterial color="#26383c" roughness={0.95} />
          </mesh>
          {[-10, 10].map((x) => (
            <mesh key={x} position={[x, 0.06, 0]}>
              <boxGeometry args={[0.25, 0.16, 180]} />
              <meshStandardMaterial color="#50625e" />
            </mesh>
          ))}
          {[-1, 1].map((sign) => (
            <group key={sign}>
              {Array.from({ length: 12 }, (_, j) => (
                <mesh key={j} position={[0, 0.08, sign * (16 + j * 6)]}>
                  <boxGeometry args={[0.15, 0.04, 3]} />
                  <meshBasicMaterial color="#a3a899" />
                </mesh>
              ))}
              {Array.from({ length: 9 }, (_, j) => (
                <mesh
                  key={`cross${j}`}
                  position={[-8 + j * 2, 0.09, sign * 11.5]}
                >
                  <boxGeometry args={[1, 0.04, 3]} />
                  <meshStandardMaterial color="#afb9ae" />
                </mesh>
              ))}
              <mesh position={[sign * 9, 2.1, sign * 9]}>
                <boxGeometry args={[0.3, 4.2, 0.3]} />
                <meshStandardMaterial color="#59665f" />
              </mesh>
              <mesh position={[sign * 9, 4.3, sign * 9]}>
                <boxGeometry args={[1, 1.5, 0.8]} />
                <meshStandardMaterial color="#26352e" />
              </mesh>
              <mesh position={[sign * 9, 4.3, sign * 9 + sign * 0.45]}>
                <sphereGeometry args={[0.25, 12, 12]} />
                <meshBasicMaterial
                  color={
                    frame?.signal === "yellow"
                      ? "#d9b876"
                      : frame?.signal === "all_red" || frame?.phase !== i
                        ? "#de776b"
                        : "#95dcb4"
                  }
                />
              </mesh>
            </group>
          ))}
        </group>
      ))}
      {[
        [-30, -28],
        [29, 26],
        [-32, 30],
        [28, -30],
      ].map(([x, z], i) => (
        <group key={i}>
          {Array.from({ length: 4 }, (_, j) => (
            <mesh
              key={j}
              position={[x + (j % 2) * 13, 3 + j, z + Math.floor(j / 2) * 14]}
              castShadow
            >
              <boxGeometry args={[9, 6 + 2 * j, 10]} />
              <meshStandardMaterial
                color={i % 2 ? "#344a49" : "#2b4043"}
                roughness={0.9}
              />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}
function Entity({
  position,
  angle,
  cls,
  selected,
  onClick,
  danger = false,
}: {
  position: [number, number, number];
  angle: number;
  cls: string;
  selected?: boolean;
  onClick?: () => void;
  danger?: boolean;
}) {
  const color = danger
    ? "#ee8b7b"
    : selected
      ? "#ffffff"
      : colors[cls] || "#91cec2";
  const isPerson = cls === "person";
  const narrow = ["bicycle", "motorcycle"].includes(cls);
  const dimensions: [number, number, number] = isPerson
    ? [0.55, 1.6, 0.55]
    : narrow
      ? [0.65, 0.9, 1.8]
      : cls === "bus" || cls === "truck"
        ? [2.2, 1.8, 6]
        : [1.8, 1.1, 3.8];
  return (
    <group
      position={position}
      rotation={[0, angle, 0]}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
    >
      <mesh castShadow>
        <boxGeometry args={dimensions} />
        <meshStandardMaterial color={color} roughness={0.45} metalness={0.15} />
      </mesh>
      {!isPerson && !narrow && (
        <mesh position={[0, dimensions[1] * 0.55, 0.15]}>
          <boxGeometry
            args={[dimensions[0] * 0.8, 0.45, dimensions[2] * 0.5]}
          />
          <meshStandardMaterial
            color="#314e54"
            metalness={0.45}
            roughness={0.3}
          />
        </mesh>
      )}
      {selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.55, 0]}>
          <ringGeometry args={[2.5, 2.7, 36]} />
          <meshBasicMaterial color="#e3fff8" transparent opacity={0.85} />
        </mesh>
      )}
    </group>
  );
}
function Scene({
  result,
  objects = [],
  mode,
  selected,
  onSelect,
  simFrame,
}: {
  result?: Result;
  objects?: ObjectState[];
  mode: TwinMode;
  selected?: number;
  onSelect?: (id: number) => void;
  simFrame?: SimFrame;
}) {
  const homography = result?.summary.calibrated
    ? result.scene?.homography
    : null;
  const toPlane = (p: [number, number]): [number, number] => {
    if (!homography)
      return [
        (p[0] / (result?.metadata.width || 1) - 0.5) * 100,
        (p[1] / (result?.metadata.height || 1) - 0.5) * 60,
      ];
    const h = homography;
    const w = h[2][0] * p[0] + h[2][1] * p[1] + h[2][2];
    const control = result?.config.calibration?.world || [[0, 0]];
    const cx = control.reduce((s, p) => s + p[0], 0) / control.length;
    const cy = control.reduce((s, p) => s + p[1], 0) / control.length;
    return [
      (h[0][0] * p[0] + h[0][1] * p[1] + h[0][2]) / w - cx,
      (h[1][0] * p[0] + h[1][1] * p[1] + h[1][2]) / w - cy,
    ];
  };
  const map = (image: [number, number], y = 0.65): [number, number, number] => {
    const p = toPlane(image);
    return [p[0], y, p[1]];
  };
  const regions = useMemo(
    () =>
      result?.config.regions.map((region) => {
        const shape = new THREE.Shape();
        region.polygon.forEach((p, i) => {
          const [x, planeY] = toPlane(p);
          const y = -planeY;
          if (i === 0) shape.moveTo(x, y);
          else shape.lineTo(x, y);
        });
        shape.closePath();
        return { shape, region };
      }) || [],
    // The projection depends only on this immutable processing result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [result],
  );
  const riskIds = new Set(
    result?.events
      .filter((e) => objects[0] && Math.abs(e.t - objects[0].t) < 2)
      .flatMap((e) => e.participants),
  );
  return (
    <>
      <color attach="background" args={["#112126"]} />
      <fog attach="fog" args={["#112126", 140, 280]} />
      <ambientLight intensity={1.4} />
      <directionalLight
        position={[20, 70, 10]}
        intensity={2.5}
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
      {simFrame ? (
        <Roads frame={simFrame} />
      ) : (
        <>
          <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={[130, 90]} />
            <meshStandardMaterial color="#1d3035" />
          </mesh>
          {regions.map(({ shape, region }) => (
            <mesh
              key={region.id}
              rotation={[-Math.PI / 2, 0, 0]}
              position={[0, 0.05, 0]}
            >
              <shapeGeometry args={[shape]} />
              <meshStandardMaterial
                color={region.kind === "crosswalk" ? "#d1c39b" : "#64958e"}
                transparent
                opacity={0.25}
                side={THREE.DoubleSide}
              />
            </mesh>
          ))}
        </>
      )}
      <Grid
        position={[0, 0.1, 0]}
        args={[200, 200]}
        cellSize={5}
        cellThickness={0.5}
        cellColor="#355053"
        sectionSize={25}
        sectionThickness={0.6}
        sectionColor="#456161"
        fadeDistance={170}
        infiniteGrid
      />
      {simFrame?.vehicles.map((v) => (
        <Entity
          key={v.id}
          position={simPosition(v.approach, v.position)}
          angle={v.approach % 2 ? Math.PI / 2 : 0}
          cls="car"
        />
      ))}
      {objects.map((o) => (
        <Entity
          key={o.id}
          position={map(o.image)}
          angle={Math.PI / 2 - o.heading}
          cls={o.class}
          selected={selected === o.id}
          onClick={() => onSelect?.(o.id)}
          danger={mode === "SAFETY" && riskIds.has(o.id)}
        />
      ))}
      {result &&
        (mode === "FLOW" || mode === "SAFETY") &&
        objects.map((o) => {
          const points =
            result.tracks
              .find((tr) => tr.id === o.id)
              ?.points.filter((p) => p.t <= o.t && p.t >= o.t - 3)
              .map((p) => map(p.image, 0.2)) || [];
          return points.length > 1 ? (
            <Line
              key={o.id}
              points={points}
              color={
                mode === "SAFETY" && riskIds.has(o.id)
                  ? "#ee8b7b"
                  : colors[o.class] || "#94d5c6"
              }
              lineWidth={1.5}
              transparent
              opacity={0.6}
            />
          ) : null;
        })}
      {result &&
        mode === "HEATMAP" &&
        result.tracks
          .flatMap((tr) =>
            tr.points.filter(
              (p, i) => i % 12 === 0 && p.t <= (objects[0]?.t || 0),
            ),
          )
          .slice(-1500)
          .map((p, i) => (
            <mesh
              key={i}
              rotation={[-Math.PI / 2, 0, 0]}
              position={map(p.image, 0.18)}
            >
              <circleGeometry args={[2, 16]} />
              <meshBasicMaterial
                color="#d4b784"
                transparent
                opacity={0.09}
                depthWrite={false}
              />
            </mesh>
          ))}
      <OrbitControls
        makeDefault
        minDistance={35}
        maxDistance={200}
        maxPolarAngle={Math.PI / 2.1}
        enableDamping
      />
    </>
  );
}
export function Twin({
  result,
  objects,
  mode = "NORMAL",
  selected,
  onSelect,
  simFrame,
  compact = false,
}: {
  result?: Result;
  objects?: ObjectState[];
  mode?: TwinMode;
  selected?: number;
  onSelect?: (id: number) => void;
  simFrame?: SimFrame;
  compact?: boolean;
}) {
  return (
    <div className={`twin-canvas ${compact ? "compact" : ""}`}>
      <Canvas
        shadows
        camera={{ position: [65, 85, 95], fov: 43 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
        fallback={
          <div className="empty-state">
            WebGL unavailable. Use the source overlay and analytics.
          </div>
        }
      >
        <Suspense fallback={null}>
          <Scene
            result={result}
            objects={objects}
            mode={mode}
            selected={selected}
            onSelect={onSelect}
            simFrame={simFrame}
          />
        </Suspense>
      </Canvas>
      <div className="twin-hud">
        <span className="status-dot" />{" "}
        {simFrame
          ? "MICROSCOPIC SIMULATION"
          : result?.summary.calibrated
            ? "CALIBRATED ROAD PLANE"
            : "IMAGE-PLANE RECONSTRUCTION"}
      </div>
      <div className="twin-compass">
        <span>N</span>
        <RotateCcw size={16} />
        <small>DRAG TO ORBIT</small>
      </div>
      <button
        className="twin-expand icon-button"
        title="Expand digital twin"
        onClick={(e) => e.currentTarget.parentElement?.requestFullscreen()}
      >
        <Maximize2 size={15} />
      </button>
    </div>
  );
}
