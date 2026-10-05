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
