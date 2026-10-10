// Actual running application only; no image/value alteration or retained municipal imagery.
import { chromium } from "@playwright/test";
import { mkdir, copyFile, writeFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3125";
const output = "../artifacts/portfolio/v4";
await mkdir(output, { recursive: true });
await mkdir("../data/media-capture/v4", { recursive: true });
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: {
    dir: "../data/media-capture/v4",
    size: { width: 1440, height: 900 },
  },
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const captures = [];
async function capture(name, route, prepare, duration) {
  await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
  await prepare();
  await page.screenshot({
    path: `${output}/${name}.jpg`,
    type: "jpeg",
    quality: 85,
  });
  captures.push({ file: `${name}.jpg`, route });
  await page.waitForTimeout(duration);
}
await capture(
  "five-city-command",
  "/",
  async () => {
    await page
      .getByRole("group", { name: "Choose a city" })
      .getByRole("button", { name: /Seattle/ })
      .click();
    await page.evaluate(() => window.scrollTo(0, 0));
  },
  5000,
);
await capture(
  "cv-tracking",
  "/workspace",
  async () => {
    await page.getByText("ROAD USERS DETECTED").waitFor();
    await page.getByLabel("Video timeline").fill("3");
    await page.locator(".cv-overlay g").first().waitFor();
  },
  6500,
);
await capture(
  "city-forecast",
  "/twin?city=seattle",
  async () => {
    await page
      .getByText("Inspect historical city data & forecast validation", {
        exact: true,
      })
      .click();
    const table = page.getByRole("table", {
      name: "City forecasting comparison",
      exact: true,
    });
    await table.waitFor();
    await table.scrollIntoViewIfNeeded();
  },
  6500,
);
await capture(
  "optimization",
  "/studio?city=seattle&cohort=atlas-4",
  async () => {
    await page.getByLabel("Baseline controller").selectOption("fixed");
    await page.getByLabel("Network replay timeline").fill("20");
    await page
      .getByRole("heading", { name: "Fixed timing", exact: true })
      .scrollIntoViewIfNeeded();
    await page
      .getByRole("button", { name: "Play recorded comparison" })
      .click();
    await page
      .locator(".city-columns")
      .first()
      .evaluate((element) => element.scrollIntoView({ block: "start" }));
  },
  9500,
);
await capture(
  "laboratory",
  "/laboratory",
  async () => {
    const table = page.getByRole("table", {
      name: "Advanced tracking and inference comparison",
    });
    await table.waitFor();
    await table.scrollIntoViewIfNeeded();
  },
  6500,
);
const video = page.video();
await context.close();
await copyFile(await video.path(), "../data/media-capture/v4/walkthrough.webm");
await browser.close();
if (errors.length) throw new Error(JSON.stringify(errors));
const sourceSha = {};
for (const file of [
  "components/landing.tsx",
  "components/network-studio.tsx",
  "components/city-evidence-v4.tsx",
  "components/ai-laboratory.tsx",
])
  sourceSha[file] = createHash("sha256")
    .update(await readFile(file))
    .digest("hex");
await writeFile(
  `${output}/provenance.json`,
  JSON.stringify(
    {
      captured_at: new Date().toISOString(),
      application_mode: "precomputed_real_outputs",
      captures,
      measured_source_sha256: sourceSha,
      page_errors: errors,
      scope:
        "Unaltered screenshots and screen recording of the running application. Official camera imagery is not retained; workspace source uses the existing licensed real CV replay. Forecast and controller values come from published experiments.",
    },
    null,
    2,
  ),
);
console.log(
  "Captured five real application screenshots and current walkthrough source",
);
