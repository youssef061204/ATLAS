// Capture the actual public application; benchmark values and source imagery are untouched.
import { chromium } from "@playwright/test";
import { mkdir, readFile, copyFile, writeFile } from "node:fs/promises";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3120";
const output = "../artifacts/portfolio/v3";
const golden = JSON.parse(
  await readFile("../artifacts/cities/toronto-golden-path.json", "utf8"),
);
await mkdir(output, { recursive: true });
await mkdir("../data/media-capture", { recursive: true });
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
    dir: "../data/media-capture",
    size: { width: 1440, height: 900 },
  },
});
const page = await context.newPage();
const failures = [];
page.on("pageerror", (error) => failures.push(error.message));
await page.goto(`${base}/workspace`);
await page.getByRole("heading", { level: 1 }).waitFor();
await page
  .getByText("ROAD USERS DETECTED", { exact: true })
  .waitFor({ timeout: 30000 });
await page.waitForTimeout(2000);
await page.screenshot({
  path: `${output}/vision.jpg`,
  type: "jpeg",
  quality: 85,
});
await page.waitForTimeout(6500);
await page.goto(`${base}/twin`);
await page
  .getByRole("heading", { name: "Actual completed counterfactual" })
  .waitFor();
await page.waitForTimeout(5000);
await page.goto(`${base}/studio?city=toronto&experiment=${golden.id}`);
await page.getByRole("slider", { name: "Network replay timeline" }).fill("5");
await page
  .getByRole("img", { name: "Actual simulated vehicle positions" })
  .first()
  .waitFor();
await page.evaluate(() => window.scrollTo(0, 0));
await page.screenshot({
  path: `${output}/comparison.jpg`,
  type: "jpeg",
  quality: 85,
});
await page.getByRole("button", { name: "Play recorded comparison" }).click();
await page.waitForTimeout(9000);
await page.goto(`${base}/laboratory`);
await page.getByRole("table", { name: "Forecast model evaluation" }).waitFor();
await page.screenshot({
  path: `${output}/laboratory.jpg`,
  type: "jpeg",
  quality: 85,
});
await page.waitForTimeout(7500);
await page.goto(`${base}/cities`);
await page.getByRole("button", { name: "Show OSM corridor" }).click();
await page
  .getByRole("group", {
    name: "Imported OSM corridor and simulated signal states",
  })
  .waitFor();
await page.screenshot({
  path: `${output}/cities.jpg`,
  type: "jpeg",
  quality: 85,
});
await page.waitForTimeout(4500);
const video = page.video();
await context.close();
await copyFile(await video.path(), `${output}/walkthrough.webm`);
await browser.close();
if (failures.length) throw new Error(JSON.stringify(failures));
await writeFile(
  `${output}/provenance.json`,
  JSON.stringify(
    {
      captured_at: new Date().toISOString(),
      application_mode: "precomputed_real_outputs",
      golden_experiment: golden.id,
      routes: [
        "/workspace",
        "/twin",
        `/studio?city=toronto&experiment=${golden.id}`,
        "/laboratory",
        "/cities",
      ],
      scope:
        "Actual application capture; no benchmark values altered. Official city camera images are not retained. Workspace uses the licensed original CV walkthrough source.",
      page_errors: failures,
    },
    null,
    2,
  ),
);
console.log("Captured four actual application images and current walkthrough");
