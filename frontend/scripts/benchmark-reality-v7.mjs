import { chromium } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const base = process.env.ATLAS_WEB_URL || "http://127.0.0.1:3130";
const results = [];
for (const [profile, args] of [
  ["default-browser", []],
  [
    "software-control",
    [
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
    ],
  ],
]) {
  const browser = await chromium.launch({ args });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const started = Date.now();
    await page.goto(`${base}/reality`);
    await page.getByRole("button", { name: "Play", exact: true }).waitFor();
    await page.locator("canvas").waitFor();
    await page.waitForTimeout(2500);
    const initialReadyMs = Date.now() - started;
    const renderer = await page.locator("canvas").evaluate((canvas) => {
      const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      const extension = gl.getExtension("WEBGL_debug_renderer_info");
      return extension
        ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER);
    });
    const media = page.locator("video");
    for (const reducedGraphics of [false, true]) {
      await page
        .getByLabel("Lower graphics cost", { exact: true })
        .setChecked(reducedGraphics);
      await page
        .getByRole("slider", { name: "Shared replay timeline" })
        .fill("600");
      await page.getByRole("button", { name: "Play", exact: true }).click();
      await page.waitForTimeout(2500);
      const before = await media.evaluate((video) => video.currentTime);
      const cadence = await page.evaluate(
        () =>
          new Promise((resolve) => {
            const ticks = [];
            const start = performance.now();
            function frame(now) {
              ticks.push(now);
              if (now - start < 10000) {
                requestAnimationFrame(frame);
                return;
              }
              const gaps = ticks
                .slice(1)
                .map((v, i) => v - ticks[i])
                .sort((a, b) => a - b);
              resolve({
                frames: ticks.length,
                elapsedMs: ticks.at(-1) - ticks[0],
                fps: ((ticks.length - 1) * 1000) / (ticks.at(-1) - ticks[0]),
                frameGapP95Ms: gaps[Math.floor(gaps.length * 0.95)],
              });
            }
            requestAnimationFrame(frame);
          }),
      );
      const label = await page
        .getByLabel("Current 3D rendering performance")
        .textContent();
      const after = await media.evaluate((video) => ({
        time: video.currentTime,
        quality: {
          presented: video.getVideoPlaybackQuality().totalVideoFrames,
          dropped: video.getVideoPlaybackQuality().droppedVideoFrames,
        },
      }));
      await page.getByRole("button", { name: "Pause", exact: true }).click();
      results.push({
        profile,
        renderer,
        reducedGraphics,
        initialReadyIncluding2500msSettle: initialReadyMs,
        cadence,
        sceneCounter: label,
        actualVideoProgressS: after.time - before,
        videoPlaybackQuality: after.quality,
        errors,
      });
      console.log(JSON.stringify(results.at(-1)));
    }
  } finally {
    await browser.close();
  }
}
const digest = async (name) =>
  createHash("sha256")
    .update(await readFile(new URL(name, import.meta.url)))
    .digest("hex");
const report = {
  viewport: [1440, 1000],
  workload:
    "Production local /reality at 600 s, identical angle, CV plus native SUMO, video playing at 1x; default browser and explicit software control, each full/reduced graphics. 2.5 s settle then ~10 s cadence window. Rendering and video throughput are separate from CV inference FPS. Browser rAF and the scene's rounded wall-clock counter are both reported. No claim of physical GPU acceleration without reading the actual renderer.",
  results,
  sourceSha256: await digest("./benchmark-reality-v7.mjs"),
  sceneSourceSha256: await digest("../components/reality-scene-v7.tsx"),
};
await writeFile(
  new URL(
    "../../artifacts/reality/v7/render-performance.json",
    import.meta.url,
  ),
  JSON.stringify(report, null, 2),
);
