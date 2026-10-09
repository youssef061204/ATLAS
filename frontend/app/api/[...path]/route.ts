import { readFile } from "node:fs/promises";
import path from "node:path";
import { DEMO_MODE } from "@/lib/api";

export const runtime = "nodejs";
type Context = { params: Promise<{ path: string[] }> };
async function manifest() {
  return JSON.parse(
    await readFile(
      path.join(process.cwd(), "public/demo/manifest.json"),
      "utf8",
    ),
  );
}
function asset(request: Request, filename: string, status = 307) {
  // Relative locations preserve the visitor's HTTPS origin behind deployment proxies.
  return new Response(null, {
    status,
    headers: { Location: new URL(`/demo/${filename}`, request.url).pathname },
  });
}
function unavailable() {
  return Response.json(
    {
      detail:
        "This public experience replays precomputed real ATLAS outputs. Run the local Python backend for new processing.",
    },
    { status: 409 },
  );
}
export async function GET(request: Request, context: Context) {
  if (!DEMO_MODE)
    return Response.json(
      { detail: "Use the configured Python API" },
      { status: 404 },
    );
  const route = (await context.params).path.join("/");
  const operationFiles: Record<string, string> = {
    "operations/cities": "source-health.json",
    "operations/networks": "networks.json",
    "operations/experiments": "experiments.json",
    "operations/intelligence": "toronto-golden-path.json",
    "operations/intelligence/context": "toronto-intelligence.json",
    "operations/intelligence/smoke": "city-intelligence-smoke.json",
    "operations/counts/toronto": "toronto-counts.json",
    "operations/models/forecast": "forecast-v3.json",
    "operations/models/graph": "graph-forecast.json",
    "operations/traffic-context": "traffic-context.json",
    "operations/visual-flow": "visual-flow.json",
    "operations/models/vision": "vision-v3.json",
  };
  if (operationFiles[route])
    return asset(request, `cities/${operationFiles[route]}`);
  const intelligence = /^operations\/intelligence\/([a-f0-9]{24})$/.exec(route);
  if (intelligence) {
    const recorded = JSON.parse(
      await readFile(
        path.join(process.cwd(), "public/demo/cities/toronto-golden-path.json"),
        "utf8",
      ),
    );
    if (recorded.id === intelligence[1]) return Response.json(recorded);
    const initial = JSON.parse(
      await readFile(
        path.join(
          process.cwd(),
          "public/demo/cities/toronto-golden-path-initial.json",
        ),
        "utf8",
      ),
    );
    if (initial.id === intelligence[1]) return Response.json(initial);
    const smoke = JSON.parse(
      await readFile(
        path.join(
          process.cwd(),
          "public/demo/cities/city-intelligence-smoke.json",
        ),
        "utf8",
      ),
    );
    for (const record of smoke.records) {
      for (const attempt of record.attempts) {
        if (attempt.experiment?.id === intelligence[1])
          return Response.json(attempt.experiment);
      }
    }
    return Response.json(
      { detail: "This experiment is not published in the public replay" },
      { status: 404 },
    );
  }
  const info = await manifest();
  if (route === "videos") return Response.json([info.video]);
  if (route === "benchmarks") return asset(request, "benchmarks.json");
  const benchmark = /^benchmarks\/([a-z0-9_-]+)$/.exec(route);
  if (benchmark && info.benchmarks.includes(benchmark[1]))
    return asset(request, `benchmarks/${benchmark[1]}.json`);
  if (route === `videos/${info.video.id}/result`)
    return asset(request, "result.json");
  if (route === `videos/${info.video.id}/source`)
    return asset(request, "source.webm");
  if (route === "simulations/demo") return asset(request, "simulation.json");
  return Response.json({ detail: "Demo resource not found" }, { status: 404 });
}
export async function POST(request: Request, context: Context) {
  if (!DEMO_MODE)
    return Response.json(
      { detail: "Use the configured Python API" },
      { status: 404 },
    );
  const route = (await context.params).path.join("/");
  const info = await manifest();
  if (route === "demo") return Response.json(info.video);
  if (route === "simulations") {
    const body = await request.json().catch(() => null);
    const preset = info.simulation_settings;
    if (
      body &&
      !body.video_id &&
      body.seed === preset.seed &&
      body.duration === preset.duration &&
      JSON.stringify(body.demand) === JSON.stringify(preset.demand)
    )
      return asset(request, "simulation.json", 303);
  }
  return unavailable();
}
export async function PUT() {
  return unavailable();
}
