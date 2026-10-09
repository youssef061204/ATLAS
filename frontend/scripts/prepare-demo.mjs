// Build a read-only presentation from genuine processing/evaluation outputs.
import { createHash } from "node:crypto";
import {
  mkdir,
  readFile,
  writeFile,
  copyFile,
  readdir,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

export async function prepareDemo() {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const out = path.join(root, "frontend/public/demo");
  await mkdir(path.join(out, "cities"), { recursive: true });
  for (const filename of [
    "source-health.json",
    "networks.json",
    "experiments.json",
    "toronto-intelligence.json",
    "toronto-counts.json",
    "toronto-golden-path.json",
    "toronto-golden-path-initial.json",
    "city-intelligence-smoke.json",
    "forecast-v3.json",
    "graph-forecast.json",
    "traffic-context.json",
    "visual-flow.json",
    "vision-v3.json",
  ]) {
    await copyFile(
      path.join(root, "artifacts/cities", filename),
      path.join(out, "cities", filename),
    ).catch((error) => {
      if (error.code !== "ENOENT") throw error;
    });
  }
  await mkdir(path.join(out, "benchmarks"), { recursive: true });
  const input = await readFile(
    path.join(root, "artifacts/demo/result.json.gz"),
  );
  const original = JSON.parse(
    await readFile(path.join(root, "artifacts/demo/manifest.json"), "utf8"),
  );
  if (
    createHash("sha256").update(input).digest("hex") !==
    original.artifact_sha256
  )
    throw new Error("Real processing cache checksum mismatch");
  const result = JSON.parse(gunzipSync(input));
  // Decimation changes replay bandwidth only; model settings and measured scores stay intact.
  result.frames = result.frames.filter((_, i) => i % 2 === 0);
  result.metrics = result.metrics.filter((_, i) => i % 2 === 0);
  result.tracks = result.tracks.map((track) => ({
    ...track,
    points: track.points.filter((_, i) => i % 2 === 0),
  }));
  result.provenance = {
    ...result.provenance,
    cached: true,
    replay_stride: 2,
    sample_scope:
      "Precomputed real CV replay; image-space time-lapse observations. Replay decimated 2x for bandwidth; processing metrics unchanged.",
  };
  await writeFile(path.join(out, "result.json"), JSON.stringify(result));
  await copyFile(
    path.join(root, "artifacts/demo/annotated-preview.webm"),
    path.join(out, "source.webm"),
  );
  const simulation = JSON.parse(
    gunzipSync(
      await readFile(path.join(root, "artifacts/demo/simulation.json.gz")),
    ),
  );
  await writeFile(
    path.join(out, "simulation.json"),
    JSON.stringify(simulation),
  );
  const benchmarks = {};
  for (const name of await readdir(path.join(root, "artifacts"))) {
    if (name.endsWith(".json"))
      benchmarks[name.slice(0, -5)] = JSON.parse(
        (await readFile(path.join(root, "artifacts", name), "utf8")).replace(
          /^\uFEFF/,
          "",
        ),
      );
  }
  benchmarks.real_world = {};
  for (const name of await readdir(path.join(root, "artifacts/benchmarks"))) {
    if (!name.endsWith(".json")) continue;
    const content = await readFile(
      path.join(root, "artifacts/benchmarks", name),
    );
    benchmarks.real_world[name.slice(0, -5)] = JSON.parse(content);
    await writeFile(path.join(out, "benchmarks", name), content);
  }
  await writeFile(
    path.join(out, "benchmarks.json"),
    JSON.stringify(benchmarks),
  );
  await writeFile(
    path.join(out, "manifest.json"),
    JSON.stringify({
      mode: "precomputed",
      source_sha256: createHash("sha256").update(input).digest("hex"),
      video: {
        id: result.video_id,
        filename: "Guadalajara / real CV replay",
        status: "complete",
        stage: "complete",
        progress: 100,
        error: null,
        intersection_id: "demo",
        metadata: { ...result.metadata, cached: true },
      },
      benchmarks: Object.keys(benchmarks.real_world),
      simulation_settings: simulation.settings,
      attribution:
        "Processed/composited Mixkit #1755, Stock Video Free License; native source is time-lapse. No raw UA-DETRAC/METR-LA/RESCO data redistributed.",
    }),
  );
  console.log(
    `Prepared real CV replay and ${Object.keys(benchmarks.real_world).length} measured artifacts`,
  );
}
if (
  process.env.NEXT_PUBLIC_DEMO_MODE === "true" ||
  process.argv.includes("--force")
)
  await prepareDemo();
