import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const base = process.env.ATLAS_WEB_URL || "http://127.0.0.1:3100";
const output = new URL("../../artifacts/portfolio/v8/", import.meta.url);
const scratch = new URL("../../data/reality-v8/media/", import.meta.url);
await mkdir(output, { recursive: true });
await mkdir(scratch, { recursive: true });

const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const errors = [];
const failures = [];
function watch(page) {
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400 && response.url().startsWith(base))
      failures.push({
        status: response.status(),
        path: new URL(response.url()).pathname,
      });
  });
}
async function ready(page) {
  await page.goto(`${base}/reality`);
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await expect(page.locator("canvas")).toBeVisible();
  await page.waitForTimeout(1000);
}
async function chooseTrack(page) {
  const packet = await (
    await page.request.get(`${base}/demo/reality/v7/replay-0600.json`)
  ).json();
  const tracks = await (
    await page.request.get(`${base}/demo/reality/v7/tracks.json`)
  ).json();
  const native = new Set(packet.simulation["600"].map((row) => row[0]));
  const candidates = packet.frames[0]
    .filter(
      (row) =>
        !row[7] &&
        native.has(`cv_${row[0]}`) &&
        tracks[`cv_${row[0]}`]?.last_frame >= 6040,
    )
    .sort(
      (a, b) => (b[3] - b[1]) * (b[4] - b[2]) - (a[3] - a[1]) * (a[4] - a[2]),
    );
  if (!candidates.length)
    throw new Error("No source-observed/native vehicle correspondence");
  await page
    .getByLabel("Select tracked vehicle", { exact: true })
    .selectOption(`cv_${candidates[0][0]}`);
}

try {
  const still = await browser.newPage({
    viewport: { width: 1600, height: 1200 },
  });
  watch(still);
  await still.goto(`${base}/ground-truth`, { waitUntil: "networkidle" });
  await expect(
    still.getByRole("heading", {
      name: "The Main Street crossing is the weak link.",
    }),
  ).toBeVisible();
  await still.locator("figure img").evaluate(async (image) => {
    if (!image.complete)
      await new Promise((resolve) =>
        image.addEventListener("load", resolve, { once: true }),
      );
  });
  await still.evaluate(() => scrollTo(0, 600));
  await still.screenshot({
    path: fileURLToPath(new URL("ground-truth-v8.jpg", output)),
    type: "jpeg",
    quality: 84,
  });
  await still.close();

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
  await film.waitForTimeout(7500);
  await film.getByRole("button", { name: "Pause", exact: true }).click();
  await film
    .getByRole("slider", { name: "Shared replay timeline" })
    .fill("600");
  await expect
    .poll(() =>
      film.locator("video").evaluate((element) => element.currentTime),
    )
    .toBeCloseTo(600, 1);
  await chooseTrack(film);
  await film.getByRole("button", { name: "Follow", exact: true }).click();
  await film.getByRole("button", { name: "Play", exact: true }).click();
  await film.evaluate(() => scrollTo(0, 205));
  await film.waitForTimeout(5500);

  await film.goto(`${base}/ground-truth`, { waitUntil: "networkidle" });
  await expect(
    film.getByRole("heading", {
      name: "The Main Street crossing is the weak link.",
    }),
  ).toBeVisible();
  await film.evaluate(() => scrollTo(0, 375));
  await film.waitForTimeout(4200);
  await film
    .getByRole("heading", { name: "See the real geometry behind the numbers." })
    .scrollIntoViewIfNeeded();
  await film.waitForTimeout(4200);

  await film.goto(`${base}/benchmarks`);
  const benchmarks = film.getByRole("region", {
    name: "Real-world results",
    exact: true,
  });
  await expect(benchmarks.getByText("0.898", { exact: true })).toBeVisible();
  await benchmarks.evaluate((element) =>
    element.scrollIntoView({ block: "start" }),
  );
  await film.waitForTimeout(3800);

  await film.goto(`${base}/optimization`);
  const control = film.getByRole("heading", {
    name: "Feedback replaces the failed timing schedule",
  });
  await expect(control).toBeVisible();
  await control.evaluate((element) =>
    element.scrollIntoView({ block: "start" }),
  );
  await film.waitForTimeout(4100);
  await film
    .getByRole("button", { name: "Play RESCO replay", exact: true })
    .click();
  await film.waitForTimeout(3500);

  const flowSeconds = (Date.now() - recordingStart) / 1000 - trimStartSeconds;
  await context.close();
  const capture = {
    recording: await video.path(),
    trimStartSeconds,
    flowSeconds,
    errors,
    failures,
    source:
      "Actual production Next.js application with licensed historical FHWA footage, real precomputed CV/native SUMO outputs, verified benchmark displays and controlled development diagnostics. No fabricated screenshots or edited values.",
    sourceSha256: createHash("sha256")
      .update(
        await readFile(new URL("capture-reality-v8.mjs", import.meta.url)),
      )
      .digest("hex"),
  };
  await writeFile(
    new URL("capture.json", scratch),
    `${JSON.stringify(capture, null, 2)}\n`,
  );
  if (errors.length || failures.length)
    throw new Error(JSON.stringify({ errors, failures }));
  console.log(JSON.stringify(capture));
} finally {
  await browser.close();
}
