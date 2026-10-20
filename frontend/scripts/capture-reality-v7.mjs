import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const base = process.env.ATLAS_WEB_URL || "http://127.0.0.1:3130";
const out = new URL("../../artifacts/portfolio/v7/", import.meta.url);
const scratch = new URL("../../data/reality-v7/media/", import.meta.url);
await mkdir(out, { recursive: true });
await mkdir(scratch, { recursive: true });
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const errors = [],
  failures = [];
const watch = (page) => {
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400 && response.url().startsWith(base))
      failures.push({
        status: response.status(),
        path: new URL(response.url()).pathname,
      });
  });
};
const shot = async (page, name) =>
  page.screenshot({
    path: fileURLToPath(new URL(name, out)),
    type: "jpeg",
    quality: 84,
  });
async function ready(page) {
  await page.goto(`${base}/reality`);
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await expect(page.locator("canvas")).toBeVisible();
  await page.waitForTimeout(1200);
}
async function chooseTrack(page) {
  const packet = await (
    await page.request.get(`${base}/demo/reality/v7/replay-0600.json`)
  ).json();
  const index = await (
    await page.request.get(`${base}/demo/reality/v7/tracks.json`)
  ).json();
  const native = new Set(packet.simulation["600"].map((row) => row[0]));
  const choices = packet.frames[0].filter(
    (row) =>
      !row[7] &&
      native.has(`cv_${row[0]}`) &&
      index[`cv_${row[0]}`]?.last_frame >= 6040,
  );
  choices.sort(
    (a, b) => (b[3] - b[1]) * (b[4] - b[2]) - (a[3] - a[1]) * (a[4] - a[2]),
  );
  if (!choices.length)
    throw new Error(
      "No observed/native vehicle correspondence for this capture",
    );
  const identity = `cv_${choices[0][0]}`;
  await page
    .getByLabel("Select tracked vehicle", { exact: true })
    .selectOption(identity);
  return identity;
}
try {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1080 },
  });
  watch(page);
  await ready(page);
  await page.evaluate(() => scrollTo(0, 205));
  await shot(page, "video-twin-v7.jpg");
  const selected = await chooseTrack(page);
  await page.getByRole("button", { name: "Follow", exact: true }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await page.waitForTimeout(1800);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.evaluate(() => scrollTo(0, 345));
  await shot(page, "vehicle-inspector-v7.jpg");
  const report = page.getByRole("region", {
    name: "Inspect the evidence behind the reconstruction.",
  });
  await report.scrollIntoViewIfNeeded();
  await report.screenshot({
    path: fileURLToPath(new URL("physical-evidence-v7.jpg", out)),
    type: "jpeg",
    quality: 84,
  });
  await page.goto(`${base}/workspace`);
  await expect(
    page.getByText("ROAD USERS DETECTED", { exact: true }),
  ).toBeVisible();
  await page.getByRole("slider", { name: "Video timeline" }).fill("3");
  await page.waitForTimeout(400);
  await shot(page, "real-cv-v7.jpg");
  await page.goto(`${base}/benchmarks`);
  const benchmarks = page.getByRole("region", {
    name: "Real-world results",
    exact: true,
  });
  await expect(benchmarks.getByText("0.898", { exact: true })).toBeVisible();
  await benchmarks.evaluate((element) =>
    element.scrollIntoView({ block: "start" }),
  );
  await page.evaluate(() => scrollBy(0, -35));
  await shot(page, "benchmarks-v7.jpg");
  await page.close();

  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    recordVideo: {
      dir: fileURLToPath(scratch),
      size: { width: 1440, height: 1000 },
    },
  });
  const film = await context.newPage();
  watch(film);
  const video = film.video();
  const recordingStart = Date.now();
  await ready(film);
  await film.evaluate(() => scrollTo(0, 205));
  const trimStartSeconds = (Date.now() - recordingStart) / 1000;
  await film.getByRole("button", { name: "Play", exact: true }).click();
  await film.evaluate(() => scrollTo(0, 205));
  await film.waitForTimeout(9000);
  await chooseTrackAfterRewind(film);
  await film.getByRole("button", { name: "Follow", exact: true }).click();
  await film.getByRole("button", { name: "Play", exact: true }).click();
  await film.evaluate(() => scrollTo(0, 205));
  await film.waitForTimeout(6000);
  await film.getByRole("button", { name: "Top down", exact: true }).click();
  await film.evaluate(() => scrollTo(0, 205));
  await film.waitForTimeout(4000);
  await film.getByRole("button", { name: "Pause", exact: true }).click();
  const evidence = film.getByRole("region", {
    name: "Inspect the evidence behind the reconstruction.",
  });
  await evidence.scrollIntoViewIfNeeded();
  await film.waitForTimeout(4500);
  await evidence
    .getByRole("button", { name: "Cross-camera", exact: true })
    .click();
  await film.waitForTimeout(4000);
  await evidence
    .getByRole("button", { name: "Independent site", exact: true })
    .click();
  await film.waitForTimeout(4000);
  await film.goto(`${base}/optimization`);
  const controlHeading = film.getByRole("heading", {
    name: "Feedback replaces the failed timing schedule",
  });
  await expect(controlHeading).toBeVisible();
  await controlHeading.evaluate((element) =>
    element.scrollIntoView({ block: "start" }),
  );
  await film.waitForTimeout(3500);
  await film
    .getByRole("button", { name: "Play RESCO replay", exact: true })
    .click();
  await film.waitForTimeout(3500);
  const flowSeconds = (Date.now() - recordingStart) / 1000 - trimStartSeconds;
  await context.close();
  const recording = await video.path();
  const record = {
    recording,
    trimStartSeconds,
    flowSeconds,
    selectedVehicleForStill: selected,
    errors,
    failures,
    source:
      "Actual production Next.js application, actual historical video and native SUMO outputs. No synthetic screenshots or edited metric values. Recording trim removes initial loading only; final movie is a web transcode.",
    sourceSha256: createHash("sha256")
      .update(
        await readFile(new URL("capture-reality-v7.mjs", import.meta.url)),
      )
      .digest("hex"),
  };
  await writeFile(
    new URL("capture.json", scratch),
    JSON.stringify(record, null, 2),
  );
  if (errors.length || failures.length)
    throw new Error(JSON.stringify({ errors, failures }));
  console.log(JSON.stringify(record));
} finally {
  await browser.close();
}

async function chooseTrackAfterRewind(page) {
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page
    .getByRole("slider", { name: "Shared replay timeline" })
    .fill("600");
  await expect
    .poll(() => page.locator("video").evaluate((video) => video.currentTime))
    .toBeCloseTo(600, 1);
  await chooseTrack(page);
}
