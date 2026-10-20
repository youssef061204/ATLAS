"use client";

import { Canvas, useFrame, useThree, useLoader } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import {
  ComponentRef,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  Suspense,
} from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import styles from "./reality-scene-v7.module.css";

export type SceneVehicle = {
  id: string;
  source: "observed" | "sumo";
  x: number;
  y: number;
  angle: number;
  speed: number | null;
  category: string;
  confidence?: number;
  length?: number;
  extrapolated?: boolean;
  inferred?: boolean;
};
export type SceneData = {
  orthophoto?: { file: string; bounds_m: [number, number, number, number] };
  raw_to_world: number[][];
  native_vehicle_lengths_m?: Record<string, number>;
  calibration_hull_world_m?: [number, number][];
  survey_lines: { layer: string; points: [number, number][] }[];
  provenance: Record<string, string>;
};
type Lane = { id: string; width: number; shape: [number, number][] };
type Signal = { lane: string; point: [number, number]; index: number };
type Preset = "angled" | "top" | "street" | "follow";

function HistoricalGround({
  asset,
}: {
  asset: NonNullable<SceneData["orthophoto"]>;
}) {
  const texture = useLoader(
    THREE.TextureLoader,
    "/demo/reality/v7/" + asset.file,
  );
  useEffect(() => {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 4;
    texture.needsUpdate = true;
  }, [texture]);
  const [xmin, ymin, xmax, ymax] = asset.bounds_m;
  return (
    <mesh
      position={[(xmin + xmax) / 2, -0.025, -(ymin + ymax) / 2]}
      rotation={[-Math.PI / 2, 0, 0]}
      receiveShadow
    >
      <planeGeometry args={[xmax - xmin, ymax - ymin]} />
      <meshBasicMaterial map={texture} alphaTest={0.3} toneMapped={false} />
    </mesh>
  );
}

function CalibrationSupport({ points }: { points: [number, number][] }) {
  const geometry = useMemo(
    () =>
      new THREE.ShapeGeometry(
        new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y))),
      ),
    [points],
  );
  const outline = useMemo(
    () =>
      new THREE.BufferGeometry().setFromPoints(
        points.map(([x, y]) => new THREE.Vector3(x, 0.09, -y)),
      ),
    [points],
  );
  useEffect(
    () => () => {
      geometry.dispose();
      outline.dispose();
    },
    [geometry, outline],
  );
  return (
    <>
      <mesh
        geometry={geometry}
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, 0.075, 0]}
      >
        <meshBasicMaterial
          color="#a1dcbe"
          transparent
          opacity={0.08}
          depthWrite={false}
          side={THREE.DoubleSide}
        />
      </mesh>
      <lineLoop geometry={outline}>
        <lineBasicMaterial color="#a1dcbe" transparent opacity={0.65} />
      </lineLoop>
    </>
  );
}

function ribbon(points: [number, number][], width: number) {
  const vertices: number[] = [],
    indices: number[] = [];
  points.forEach(([x, y], i) => {
    const previous = points[Math.max(0, i - 1)],
      next = points[Math.min(points.length - 1, i + 1)];
    const length =
      Math.hypot(next[0] - previous[0], next[1] - previous[1]) || 1;
    const dx = ((-(next[1] - previous[1]) / length) * width) / 2;
    const dy = (((next[0] - previous[0]) / length) * width) / 2;
    vertices.push(x + dx, 0, -y - dy, x - dx, 0, -y + dy);
    if (i) {
      const k = i * 2;
      indices.push(k - 2, k - 1, k, k - 1, k + 1, k);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(vertices, 3),
  );
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function Pavement({
  lanes,
  junction,
  survey,
  showSurvey,
  photographic,
}: {
  lanes: Lane[];
  junction: [number, number][];
  survey: SceneData["survey_lines"];
  showSurvey: boolean;
  photographic: boolean;
}) {
  const roads = useMemo(
    () =>
      lanes.map((lane) => ({
        id: lane.id,
        geometry: ribbon(lane.shape, lane.width + 0.15),
      })),
    [lanes],
  );
  const polygon = useMemo(() => {
    const shape = new THREE.Shape(
      junction.map(([x, y]) => new THREE.Vector2(x, y)),
    );
    return new THREE.ShapeGeometry(shape);
  }, [junction]);
  const markings = useMemo(() => {
    const vertices: number[] = [];
    for (const line of survey)
      for (let i = 1; i < line.points.length; i++) {
        const a = line.points[i - 1],
          b = line.points[i];
        vertices.push(a[0], 0.055, -a[1], b[0], 0.055, -b[1]);
      }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(vertices, 3),
    );
    return geometry;
  }, [survey]);
  useEffect(
    () => () => {
      roads.forEach((r) => r.geometry.dispose());
      polygon.dispose();
      markings.dispose();
    },
    [roads, polygon, markings],
  );
  return (
    <>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[20, -0.12, -50]}
        receiveShadow
      >
        <planeGeometry args={[310, 350]} />
        <meshStandardMaterial color="#465648" roughness={1} />
      </mesh>
      {roads.map((road) => (
        <mesh key={road.id} geometry={road.geometry} receiveShadow>
          <meshStandardMaterial
            color="#333b40"
            roughness={0.94}
            side={THREE.DoubleSide}
            transparent={photographic}
            opacity={photographic ? 0.45 : 1}
          />
        </mesh>
      ))}
      <mesh
        geometry={polygon}
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, 0.012, 0]}
        receiveShadow
      >
        <meshStandardMaterial
          color="#333b40"
          side={THREE.DoubleSide}
          transparent={photographic}
          opacity={photographic ? 0.45 : 1}
        />
      </mesh>
      {showSurvey && (
        <lineSegments geometry={markings}>
          <lineBasicMaterial color="#e8dec2" transparent opacity={0.8} />
        </lineSegments>
      )}
    </>
  );
}

// Original procedural vehicle geometry, shared across instances. Dimensions are
// class-based illustrations, never a claim that the video measured the car mesh.
function Fleet({
  vehicles,
  selected,
  onSelect,
  time,
  lightweight,
}: {
  vehicles: SceneVehicle[];
  selected: string | null;
  onSelect: (id: string) => void;
  time: number;
  lightweight: boolean;
}) {
  const body = useRef<THREE.InstancedMesh>(null),
    cabin = useRef<THREE.InstancedMesh>(null);
  const wheels = useRef<THREE.InstancedMesh>(null),
    lights = useRef<THREE.InstancedMesh>(null);
  const geometry = useMemo(() => new RoundedBoxGeometry(1, 1, 1, 2, 0.13), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const capacity = 512;
  const wheelMotion = useRef(
    new Map<string, { x: number; y: number; t: number; phase: number }>(),
  );
  const rows = vehicles.slice(0, capacity);
  useLayoutEffect(() => {
    if (!body.current || !cabin.current || !wheels.current || !lights.current)
      return;
    const parent = new THREE.Object3D(),
      part = new THREE.Object3D(),
      matrix = new THREE.Matrix4();
    rows.forEach((v, i) => {
      const length =
        v.length ??
        (v.category === "bus"
          ? 10
          : v.category === "truck"
            ? 6.5
            : v.category === "motorcycle"
              ? 2
              : 4.2);
      const width =
        v.category === "motorcycle" ? 0.75 : v.category === "bus" ? 2.4 : 1.8;
      const height =
        v.category === "bus" || v.category === "truck" ? 2.1 : 0.95;
      parent.position.set(v.x, 0.46, -v.y);
      parent.rotation.set(0, Math.PI - (v.angle * Math.PI) / 180, 0);
      parent.updateMatrix();
      const set = (
        mesh: THREE.InstancedMesh,
        index: number,
        position: [number, number, number],
        scale: [number, number, number],
        rotation: [number, number, number] = [0, 0, 0],
        spin = 0,
      ) => {
        part.position.set(...position);
        part.scale.set(...scale);
        part.rotation.set(...rotation);
        part.rotateY(spin);
        part.updateMatrix();
        matrix.multiplyMatrices(parent.matrix, part.matrix);
        mesh.setMatrixAt(index, matrix);
      };
      set(body.current!, i, [0, height / 2, 0], [width, height, length]);
      set(
        cabin.current!,
        i,
        [0, height + 0.18, -0.12],
        [width * 0.86, 0.65, length * 0.49],
      );
      const tint =
        v.id === selected
          ? "#ffdc7d"
          : v.inferred
            ? "#e8bc70"
            : v.extrapolated
              ? "#b9afb1"
              : v.source === "observed"
                ? "#79d8ba"
                : "#93b9fa";
      body.current!.setColorAt(i, new THREE.Color(tint));
      const wheelKey = `${v.source}:${v.id}`,
        prior = wheelMotion.current.get(wheelKey);
      const distance = prior ? Math.hypot(v.x - prior.x, v.y - prior.y) : 0;
      const wheelPhase =
        prior && Math.abs(time - prior.t) <= 0.5 && distance < 10
          ? prior.phase + (distance / 0.34) * Math.sign(time - prior.t)
          : 0;
      wheelMotion.current.set(wheelKey, {
        x: v.x,
        y: v.y,
        t: time,
        phase: wheelPhase,
      });
      for (let w = 0; w < 4; w++) {
        set(
          wheels.current!,
          i * 4 + w,
          [
            (w % 2 ? 1 : -1) * width * 0.47,
            -0.12,
            (w < 2 ? 1 : -1) * length * 0.3,
          ],
          [0.34, 0.23, 0.34],
          [0, 0, Math.PI / 2],
          wheelPhase,
        );
        set(
          lights.current!,
          i * 4 + w,
          [
            (w % 2 ? 1 : -1) * width * 0.33,
            0.27,
            (w < 2 ? 1 : -1) * length * 0.505,
          ],
          [width * 0.19, 0.14, 0.05],
        );
        lights.current!.setColorAt(
          i * 4 + w,
          new THREE.Color(w < 2 ? "#fff5c6" : "#ef7468"),
        );
      }
    });
    for (const [mesh, n] of [
      [body.current, rows.length],
      [cabin.current, rows.length],
      [wheels.current, rows.length * 4],
      [lights.current, rows.length * 4],
    ] as const) {
      mesh.count = n;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
    }
  }, [rows, selected, time]);
  return (
    <>
      <instancedMesh
        ref={body}
        args={[geometry, undefined, capacity]}
        castShadow
        onClick={(e) => {
          e.stopPropagation();
          if (e.instanceId !== undefined) onSelect(rows[e.instanceId].id);
        }}
      >
        {lightweight ? (
          <meshLambertMaterial />
        ) : (
          <meshStandardMaterial roughness={0.36} metalness={0.24} />
        )}
      </instancedMesh>
      <instancedMesh ref={cabin} args={[geometry, undefined, capacity]}>
        {lightweight ? (
          <meshLambertMaterial color="#23424c" />
        ) : (
          <meshStandardMaterial
            color="#23424c"
            roughness={0.18}
            metalness={0.5}
          />
        )}
      </instancedMesh>
      <instancedMesh ref={wheels} args={[undefined, undefined, capacity * 4]}>
        <cylinderGeometry args={[1, 1, 1, 10]} />
        <meshLambertMaterial color="#172028" />
      </instancedMesh>
      <instancedMesh ref={lights} args={[undefined, undefined, capacity * 4]}>
        <boxGeometry />
        <meshBasicMaterial />
      </instancedMesh>
    </>
  );
}

function SignalHeads({
  signals,
  phase,
}: {
  signals: Signal[];
  phase?: string;
}) {
  const poles = useRef<THREE.InstancedMesh>(null);
  const housings = useRef<THREE.InstancedMesh>(null);
  const lamps = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    if (!poles.current || !housings.current || !lamps.current) return;
    const transform = new THREE.Object3D();
    const color = new THREE.Color();
    signals.forEach((signal, index) => {
      const [x, y] = signal.point;
      transform.position.set(x, 2, -y);
      transform.updateMatrix();
      poles.current!.setMatrixAt(index, transform.matrix);
      transform.position.set(x, 4, -y);
      transform.updateMatrix();
      housings.current!.setMatrixAt(index, transform.matrix);
      ["r", "y", "g"].forEach((lamp, offset) => {
        transform.position.set(x, 4.3 - offset * 0.28, -y + 0.19);
        transform.updateMatrix();
        lamps.current!.setMatrixAt(index * 3 + offset, transform.matrix);
        const active = phase?.[signal.index]?.toLowerCase() === lamp;
        color.set(
          active
            ? lamp === "g"
              ? "#8df9b1"
              : lamp === "y"
                ? "#ffe48a"
                : "#ff7e6b"
            : "#35413c",
        );
        lamps.current!.setColorAt(index * 3 + offset, color);
      });
    });
    for (const mesh of [poles.current, housings.current, lamps.current]) {
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
    }
  }, [signals, phase]);
  return (
    <>
      <instancedMesh
        ref={poles}
        args={[undefined, undefined, signals.length]}
        castShadow
      >
        <cylinderGeometry args={[0.055, 0.07, 4, 6]} />
        <meshLambertMaterial color="#495358" />
      </instancedMesh>
      <instancedMesh
        ref={housings}
        args={[undefined, undefined, signals.length]}
      >
        <boxGeometry args={[0.4, 1, 0.35]} />
        <meshLambertMaterial color="#1d272b" />
      </instancedMesh>
      <instancedMesh
        ref={lamps}
        args={[undefined, undefined, signals.length * 3]}
      >
        <sphereGeometry args={[0.1, 8, 8]} />
        <meshBasicMaterial />
      </instancedMesh>
    </>
  );
}

function Context({ night }: { night: boolean }) {
  const blocks = useMemo(
    () => [
      // Approximate massing aligned to visible orthophoto roof bounds.
      // Heights and facades are decorative, not an architectural survey.
      [84, 120, 37, 46, 5],
      [87, 40, 29, 34, 8],
      [52, -40, 40, 50, 7],
    ],
    [],
  );
  return (
    <group>
      {blocks.map(([x, y, width, depth, height], i) => (
        <group key={i} position={[x, 0, -y]}>
          <mesh position={[0, height / 2, 0]} castShadow receiveShadow>
            <boxGeometry args={[width, height, depth]} />
            <meshStandardMaterial
              color={i % 2 ? "#b6afa1" : "#929c9d"}
              roughness={0.84}
            />
          </mesh>
          <mesh position={[0, height + 0.3, 0]}>
            <boxGeometry args={[width + 1, 0.6, depth + 1]} />
            <meshStandardMaterial color="#515e61" />
          </mesh>
          {Array.from({ length: Math.floor(height / 3) }, (_, floor) => (
            <mesh key={floor} position={[0, 2 + floor * 3, depth / 2 + 0.02]}>
              <boxGeometry args={[width * 0.86, 0.85, 0.04]} />
              <meshStandardMaterial
                color={night ? "#e8c994" : "#42585f"}
                emissive={night ? "#b68c4e" : "#000000"}
                emissiveIntensity={0.6}
              />
            </mesh>
          ))}
        </group>
      ))}
      {[
        [54, 70],
        [58, 85],
        [56, 100],
        [65, 15],
        [61, 5],
        [52, -8],
        [43, -35],
      ].map(([x, y], i) => (
        <group key={i} position={[x, 0, -y]}>
          <mesh position={[0, 1.5, 0]} castShadow>
            <cylinderGeometry args={[0.18, 0.3, 3, 6]} />
            <meshStandardMaterial color="#625140" />
          </mesh>
          <mesh position={[0, 4.2, 0]} castShadow>
            <icosahedronGeometry args={[2.8, 1]} />
            <meshStandardMaterial
              color={i % 2 ? "#426b55" : "#648068"}
              roughness={1}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function Camera({
  preset,
  vehicles,
  selected,
  onFps,
  playing,
}: {
  preset: Preset;
  vehicles: SceneVehicle[];
  selected: string | null;
  onFps: (n: number) => void;
  playing: boolean;
}) {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);
  const { camera } = useThree();
  const timer = useRef({ seconds: 0, frames: 0 });
  const previousTick = useRef(0);
  useEffect(() => {
    timer.current = { seconds: 0, frames: 0 };
    previousTick.current = performance.now();
  }, [playing]);
  useEffect(() => {
    const positions = {
      angled: [140, 115, 70],
      top: [26, 175, -52],
      street: [70, 8, 22],
      follow: [45, 16, -22],
    };
    camera.position.set(...(positions[preset] as [number, number, number]));
    controls.current?.target.set(25, 0, -52);
    controls.current?.update();
  }, [preset, camera]);
  useFrame(() => {
    const state = timer.current;
    const now = performance.now();
    if (playing) {
      state.seconds += (now - previousTick.current) / 1000;
      state.frames++;
      if (state.seconds >= 2) {
        onFps(Math.round(state.frames / state.seconds));
        state.frames = 0;
        state.seconds = 0;
      }
    }
    previousTick.current = now;
    if (preset === "follow") {
      const vehicle = vehicles.find((v) => v.id === selected);
      if (vehicle && controls.current) {
        const target = new THREE.Vector3(vehicle.x, 1, -vehicle.y);
        controls.current.target.lerp(target, 0.1);
        camera.position.lerp(
          target.clone().add(new THREE.Vector3(14, 12, 16)),
          0.04,
        );
        controls.current.update();
      }
    }
  });
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      minDistance={6}
      maxDistance={330}
      maxPolarAngle={Math.PI * 0.49}
      enableDamping
      dampingFactor={0.09}
    />
  );
}

export default function RealityScene({
  lanes,
  junction,
  signals,
  phase,
  vehicles,
  selected,
  onSelect,
  scene,
  time,
  playing,
}: {
  lanes: Lane[];
  junction: [number, number][];
  signals: Signal[];
  phase?: string;
  vehicles: SceneVehicle[];
  selected: string | null;
  onSelect: (id: string) => void;
  scene: SceneData;
  time: number;
  playing: boolean;
}) {
  const [preset, setPreset] = useState<Preset>("angled"),
    [night, setNight] = useState(false),
    [context, setContext] = useState(true),
    [photo, setPhoto] = useState(true),
    [survey, setSurvey] = useState(true),
    [calibration, setCalibration] = useState(true),
    [fps, setFps] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const [lightweight, setLightweight] = useState(false);
  return (
    <div className={styles.scene}>
      <div className={styles.tools} aria-label="3D camera controls">
        {(["angled", "top", "street", "follow"] as Preset[]).map((mode) => (
          <button
            key={mode}
            aria-pressed={preset === mode}
            disabled={mode === "follow" && !selected}
            onClick={() => setPreset(mode)}
          >
            {mode === "top"
              ? "Top down"
              : mode[0].toUpperCase() + mode.slice(1)}
          </button>
        ))}
        <button
          onClick={() => {
            setPreset("angled");
            setRevision((v) => v + 1);
          }}
        >
          Fit / reset
        </button>
      </div>
      <div
        className={styles.canvas}
        role="img"
        aria-label="Three dimensional Lankershim traffic reconstruction with real survey linework and synchronized source vehicles"
      >
        <Canvas
          gl={{ antialias: false, powerPreference: "high-performance" }}
          shadows={!lightweight}
          dpr={lightweight ? 1 : [1, 1.5]}
          frameloop={playing ? "always" : "demand"}
          onCreated={({ gl }) => {
            const context = gl.getContext();
            const info = context.getExtension("WEBGL_debug_renderer_info");
            const renderer = info
              ? String(context.getParameter(info.UNMASKED_RENDERER_WEBGL))
              : "";
            if (/swiftshader|llvmpipe|software/i.test(renderer))
              setLightweight(true);
          }}
          camera={{ position: [140, 115, 70], fov: 40, near: 0.5, far: 700 }}
          fallback={
            <p>3D requires WebGL. Use the 2D map view on this device.</p>
          }
        >
          <color attach="background" args={[night ? "#111d2a" : "#c1cecc"]} />
          <fog attach="fog" args={[night ? "#111d2a" : "#c1cecc", 190, 470]} />
          <ambientLight intensity={night ? 0.55 : 1.25} />
          <hemisphereLight
            args={[night ? "#8daada" : "#deece9", "#48533c", night ? 0.5 : 1.2]}
          />
          <directionalLight
            castShadow={!lightweight}
            position={[55, 100, 15]}
            intensity={night ? 0.45 : 2.5}
            color={night ? "#a8c2f0" : "#fff0d5"}
            shadow-mapSize={[1024, 1024]}
            shadow-camera-left={-150}
            shadow-camera-right={150}
            shadow-camera-top={150}
            shadow-camera-bottom={-150}
            shadow-bias={-0.001}
          />
          <Pavement
            lanes={lanes}
            junction={junction}
            survey={scene.survey_lines}
            showSurvey={survey}
            photographic={photo}
          />
          {photo && scene.orthophoto ? (
            <Suspense fallback={null}>
              <HistoricalGround asset={scene.orthophoto} />
            </Suspense>
          ) : null}
          {context && <Context night={night} />}
          {calibration && scene.calibration_hull_world_m ? (
            <CalibrationSupport points={scene.calibration_hull_world_m} />
          ) : null}
          <SignalHeads signals={signals} phase={phase} />
          <Fleet
            vehicles={vehicles}
            selected={selected}
            onSelect={onSelect}
            time={time}
            lightweight={lightweight}
          />
          {selected &&
            vehicles
              .filter((v) => v.id === selected)
              .map((v) => (
                <Html
                  key={`${v.source}:${v.id}`}
                  position={[v.x, 4, -v.y]}
                  center
                  style={{ pointerEvents: "none" }}
                >
                  <span className={styles.tag}>
                    {v.id} · {v.source === "observed" ? "CV" : "SUMO"}
                  </span>
                </Html>
              ))}
          <Camera
            key={revision}
            preset={preset}
            vehicles={vehicles}
            selected={selected}
            onFps={setFps}
            playing={playing}
          />
        </Canvas>
      </div>
      <div className={styles.layers}>
        {scene.calibration_hull_world_m ? (
          <label>
            <input
              type="checkbox"
              checked={calibration}
              onChange={(e) => setCalibration(e.target.checked)}
            />{" "}
            Calibration support
          </label>
        ) : null}
        {scene.orthophoto ? (
          <label>
            <input
              type="checkbox"
              checked={photo}
              onChange={(e) => setPhoto(e.target.checked)}
            />{" "}
            2005 orthophoto
          </label>
        ) : null}
        <label>
          <input
            type="checkbox"
            checked={lightweight}
            onChange={(e) => setLightweight(e.target.checked)}
          />
          Lower graphics cost
        </label>
        <label>
          <input
            type="checkbox"
            checked={survey}
            onChange={(e) => setSurvey(e.target.checked)}
          />{" "}
          Survey markings
        </label>
        <label>
          <input
            type="checkbox"
            checked={context}
            onChange={(e) => setContext(e.target.checked)}
          />{" "}
          Illustrative context
        </label>
        <label>
          <input
            type="checkbox"
            checked={night}
            onChange={(e) => setNight(e.target.checked)}
          />{" "}
          Night illustration
        </label>
        <output aria-label="Current 3D rendering performance">
          {!playing
            ? "Paused / render on interaction"
            : fps === null
              ? "Measuring render FPS…"
              : `${fps} render FPS`}
        </output>
      </div>
      <p className={styles.note}>
        Drag to orbit · scroll / pinch to zoom · right drag to pan. Survey
        paint: FHWA GIS. Lanes and signals: estimated. Buildings, heights, trees
        and lighting: illustrative. Orthophoto vehicles are static background
        imagery, not current tracks.
      </p>
    </div>
  );
}
