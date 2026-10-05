import { chromium } from "@playwright/test";
import { mkdir, rename, unlink } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const destination = fileURLToPath(
  new URL("../../artifacts/demo/", import.meta.url),
);
await mkdir(destination, { recursive: true });
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: destination, size: { width: 1440, height: 1000 } },
});
const page = await context.newPage();
const errors = [];
let completed = false;
page.on("pageerror", (error) => errors.push(error.message));
const base = process.env.ATLAS_WEB_URL || "http://127.0.0.1:3000";
try {
  await page.goto(base);
  await page.waitForTimeout(3500);
  await page
    .getByRole("link", { name: /Launch (workspace|Demo)/ })
    .first()
    .click();
  await page.getByText("ROAD USERS DETECTED").waitFor();
  if (await page.getByRole("button", { name: "Pause playback" }).isVisible())
    await page.getByRole("button", { name: "Pause playback" }).click();
  await page.getByRole("slider", { name: "Video timeline" }).fill("3");
  await page.locator(".cv-overlay g").first().click();
  await page.waitForTimeout(2000);
  await page.getByRole("button", { name: "Play playback" }).click();
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Pause playback" }).click();
  await page.getByRole("button", { name: "HEATMAP", exact: true }).click();
  await page.getByRole("slider", { name: "Video timeline" }).fill("10");
  await page.waitForTimeout(4500);
  await page.goto(`${base}/analytics`);
  await page.waitForTimeout(5500);
  await page.goto(`${base}/safety`);
  await page.waitForTimeout(3500);
  await page.goto(`${base}/forecast`);
  await page.waitForTimeout(3500);
  await page.goto(`${base}/optimization`);
  await page
    .getByRole("button", {
      name: /Optimize intersection|Replay precomputed comparison/,
    })
    .first()
    .click();
  await page
    .getByText("ALL THREE POLICIES / FINAL METRICS")
    .waitFor({ timeout: 60000 });
  await page.waitForTimeout(3500);
  await page.getByRole("button", { name: "Pause simulation" }).click();
  await page.getByRole("slider", { name: "Simulation timeline" }).fill("120");
  await page.waitForTimeout(5500);
  await page.goto(`${base}/benchmarks`);
  await page.waitForTimeout(2500);
  await page
    .getByText("METR-LA / CHRONOLOGICAL FORECASTING", { exact: false })
    .scrollIntoViewIfNeeded();
  await page.waitForTimeout(2500);
  await page
    .getByText("RESCO COLOGNE / HELD-OUT DEMAND PERIOD", { exact: false })
    .scrollIntoViewIfNeeded();
  await page.waitForTimeout(2500);
  if (errors.length) throw new Error(errors.join("\n"));
  completed = true;
} finally {
  const video = page.video();
  await context.close();
  await browser.close();
  if (video && completed) {
    await rename(await video.path(), `${destination}/atlas-walkthrough.webm`);
    process.stdout.write(`Recorded ${destination}/atlas-walkthrough.webm\n`);
  } else if (video) await unlink(await video.path());
}
