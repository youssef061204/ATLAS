import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { gunzipSync } from "node:zlib";

const base = process.env.ATLAS_WEB_URL || "http://127.0.0.1:3130";
const artifact = new URL("../../artifacts/reality/v7/", import.meta.url);
const destination = new URL("../../data/publication-checks/", import.meta.url);
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const errors = [],
  failures = [],
  localhostRequests = [];
const report = {
  url: base,
  pages: [],
  assets: [],
  errors,
  failures,
  localhostRequests,
};
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (r) => {
    if (r.url().startsWith(base) && r.status() >= 400)
      failures.push({ path: new URL(r.url()).pathname, status: r.status() });
  });
  page.on("request", (r) => {
    if (
      base.startsWith("https:") &&
      /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(r.url())
    )
      localhostRequests.push(new URL(r.url()).pathname);
  });
  for (const path of [
    "/",
    "/reality",
    "/benchmarks",
    "/optimization",
    "/about",
  ]) {
    const response = await page.goto(base + path);
    expect(response.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    report.pages.push({ path, status: response.status() });
  }
  for (const name of [
    "manifest.json",
    "research.json",
    "scene.json",
    "tracks.json",
    "replay-0600.json",
    "historical-ortho.webp",
  ]) {
    const compressed = name === "tracks.json" || name.startsWith("replay-");
    const local = await readFile(
      new URL(name + (compressed ? ".gz" : ""), artifact),
    );
    const expected = compressed ? gunzipSync(local) : local;
    const response = await page.request.get(`${base}/demo/reality/v7/${name}`);
    expect(response.status()).toBe(200);
    const body = await response.body();
    expect(body.equals(expected)).toBe(true);
    report.assets.push({
      name,
      bytes: body.length,
      sha256: createHash("sha256").update(body).digest("hex"),
    });
  }
  const range = await page.request.get(
    `${base}/demo/reality/v6/lankershim-camera4.mp4`,
    { headers: { Range: "bytes=0-1023" } },
  );
  expect(range.status()).toBe(206);
  report.videoRange = {
    status: range.status(),
    contentRange: range.headers()["content-range"],
  };
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  await page.goto(`${base}/reality`);
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await expect(page.locator("canvas")).toBeVisible();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect
    .poll(() => page.locator("video").evaluate((v) => v.currentTime))
    .toBeGreaterThan(600.5);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  report.renderer = await page.locator("canvas").evaluate((canvas) => {
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return ext
      ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
      : gl.getParameter(gl.RENDERER);
  });
  const metrics = (await cdp.send("Performance.getMetrics")).metrics;
  report.browserMemory = metrics.filter((m) =>
    ["JSHeapUsedSize", "JSHeapTotalSize", "Nodes", "Documents"].includes(
      m.name,
    ),
  );
  report.memoryScope =
    "One actual paused replay page after navigation/playback; JavaScript heap/DOM only, not peak browser or GPU memory.";
  expect(errors).toEqual([]);
  expect(failures).toEqual([]);
  expect(localhostRequests).toEqual([]);
  await mkdir(destination, { recursive: true });
  await writeFile(
    new URL("atlas-v7.json", destination),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
