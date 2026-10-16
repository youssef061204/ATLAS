// Actual application pixels and actual playback; no edited benchmark values.
import { chromium } from "@playwright/test";
import { mkdir, copyFile, writeFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3130";
const output = "../artifacts/portfolio/v6";
const clips = "../data/media-capture/v6";
await mkdir(output, { recursive: true });
await mkdir(clips, { recursive: true });
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const errors = [];
const captures = [];
async function capture(name, route, prepare, duration) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    recordVideo: { dir: clips, size: { width: 1440, height: 1000 } },
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base + route, { waitUntil: "networkidle" });
  await prepare(page);
  await page.screenshot({
    path: `${output}/${name}.jpg`,
    type: "jpeg",
    quality: 85,
  });
  await page.waitForTimeout(duration * 1000);
  const video = page.video();
  await context.close();
  await copyFile(await video.path(), `${clips}/${name}.webm`);
  captures.push({
    file: `${name}.jpg`,
    route,
    source_clip: `${name}.webm`,
    stable_tail_seconds: duration,
  });
}
try {
  await capture(
    "video-twin",
    "/reality",
    async (page) => {
      await page.getByRole("button", { name: "Play", exact: true }).click();
      await page.waitForFunction(
        () => document.querySelector("video")?.currentTime > 601,
      );
      await page
        .getByRole("region", { name: "Real traffic video" })
        .scrollIntoViewIfNeeded();
    },
    16,
  );
  await capture(
    "independent-errors",
    "/reality",
    async (page) => {
      await page.getByRole("button", { name: "Play", exact: true }).waitFor();
      await page
        .getByRole("heading", {
          name: "The discrepancies are part of the result.",
        })
        .evaluate((e) => e.scrollIntoView({ block: "start" }));
    },
    9,
  );
  await capture(
    "robust-control",
    "/studio?city=seattle&cohort=atlas-5&case=high",
    async (page) => {
      await page.getByLabel("Network replay timeline").fill("20");
      await page.getByRole("button", { name: "Play recorded replay" }).click();
      await page
        .locator(".city-columns")
        .first()
        .evaluate((e) => e.scrollIntoView({ block: "start" }));
    },
    9,
  );
  await capture(
    "benchmarks",
    "/benchmarks",
    async (page) => {
      await page
        .getByText("METR-LA / CHRONOLOGICAL FORECASTING", { exact: false })
        .scrollIntoViewIfNeeded();
    },
    7,
  );
  if (errors.length) throw new Error(JSON.stringify(errors));
  const sources = {};
  for (const file of [
    "components/reality-replay.tsx",
    "components/reality-replay.module.css",
    "components/landing.tsx",
    "components/control-study-v5.tsx",
    "components/real-benchmarks.tsx",
  ]) {
    sources[file] = createHash("sha256")
      .update(await readFile(file))
      .digest("hex");
  }
  await writeFile(
    `${output}/provenance.json`,
    JSON.stringify(
      {
        captured_at: new Date().toISOString(),
        application_mode:
          "historical_video_precomputed_actual_cv_and_native_sumo",
        captures,
        measured_source_sha256: sources,
        page_errors: errors,
        scope:
          "Unaltered actual application screenshots and screen-recording clips. Encoding and stable-tail trimming remove loading footage only. Native simulator output and source video are real; physical fidelity fails and historical controller studies remain separately labelled.",
      },
      null,
      2,
    ),
  );
  console.log("Captured four actual application views and 41 stable seconds");
} finally {
  await browser.close();
}
