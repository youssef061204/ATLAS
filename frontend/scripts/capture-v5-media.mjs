// Real running application pixels only. No benchmark edits or municipal image retention.
import { chromium } from "@playwright/test";
import { mkdir, copyFile, writeFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3130";
const output = "../artifacts/portfolio/v5";
const clips = "../data/media-capture/v5";
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
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: clips, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
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
    "command-center",
    "/",
    async (page) => {
      await page
        .getByRole("group", { name: "Supported cities" })
        .getByRole("button", { name: "Seattle", exact: true })
        .click();
    },
    5,
  );
  await capture(
    "real-cv",
    "/workspace",
    async (page) => {
      await page.getByText("ROAD USERS DETECTED").waitFor();
      await page.getByLabel("Video timeline").fill("3");
      await page.locator(".cv-overlay g").first().waitFor();
    },
    7,
  );
  await capture(
    "calibration",
    "/calibration?city=seattle",
    async (page) => {
      await page
        .getByRole("table", { name: "ATLAS 5 forecast regression results" })
        .waitFor();
      await page
        .getByRole("heading", {
          name: "Seattle: observed counts & estimated demand",
        })
        .evaluate((element) => element.scrollIntoView({ block: "start" }));
    },
    7,
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
    10,
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
    "components/landing.tsx",
    "components/calibration-dashboard.tsx",
    "components/research-evidence-v5.tsx",
    "components/control-study-v5.tsx",
    "components/video-workspace.tsx",
    "app/layout.tsx",
    "app/globals.css",
    "public/fonts/sources.json",
  ])
    sources[file] = createHash("sha256")
      .update(await readFile(file))
      .digest("hex");
  await writeFile(
    `${output}/provenance.json`,
    JSON.stringify(
      {
        captured_at: new Date().toISOString(),
        application_mode: "precomputed_real_outputs",
        captures,
        measured_source_sha256: sources,
        page_errors: errors,
        scope:
          "Unaltered actual screenshots and stable screen-recording clips. Native licensed CV output and real benchmark/simulation artifacts; no retained municipal imagery or fabricated values. Video encoding/trimming excludes loading footage only.",
      },
      null,
      2,
    ),
  );
  console.log(
    "Captured five current ATLAS screenshots and stable walkthrough clips",
  );
} finally {
  await browser.close();
}
