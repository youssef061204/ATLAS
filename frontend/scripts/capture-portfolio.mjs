import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const base = process.env.ATLAS_WEB_URL || "http://127.0.0.1:3100";
const signalOnly = process.argv.includes("--signal-only");
const destination = fileURLToPath(
  new URL("../../artifacts/portfolio/", import.meta.url),
);
await mkdir(destination, { recursive: true });
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const page = await browser.newPage({
  viewport: { width: 1600, height: 1050 },
  deviceScaleFactor: 1,
});
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  if (!signalOnly) {
    await page.goto(`${base}/workspace`);
    await page.getByText("ROAD USERS DETECTED").waitFor();
    await page.getByRole("button", { name: "Pause playback" }).click();
    await page.getByRole("slider", { name: "Video timeline" }).fill("3");
    await page.waitForTimeout(1000);
    await page.screenshot({
      path: destination + "digital-twin.png",
      fullPage: true,
    });
    await page.locator(".cv-overlay g").first().click();
    await page.screenshot({
      path: destination + "tracking.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "HEATMAP", exact: true }).click();
    await page.screenshot({
      path: destination + "heatmap.png",
      fullPage: true,
    });
  }
  for (const route of [
    "analytics",
    "safety",
    "forecast",
    "optimization",
    "benchmarks",
  ]) {
    if (signalOnly && !["optimization", "benchmarks"].includes(route)) continue;
    await page.goto(`${base}/${route}`);
    await page.waitForTimeout(1300);
    if (["optimization", "benchmarks"].includes(route)) {
      const control = page.getByRole("region", {
        name: "Improved signal-control study",
      });
      await control
        .getByRole("table", { name: "Held-out signal-control metrics" })
        .waitFor();
      if (route === "benchmarks") await control.scrollIntoViewIfNeeded();
    }
    await page.screenshot({
      path: destination + route + ".png",
      fullPage: !["benchmarks", "optimization"].includes(route),
    });
  }
  if (errors.length) throw new Error(errors.join("\n"));
  console.log(
    `Captured ${signalOnly ? "two signal-control" : "eight"} actual application views`,
  );
} finally {
  await browser.close();
}
