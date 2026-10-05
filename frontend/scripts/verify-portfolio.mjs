import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const base = process.env.PORTFOLIO_URL || "http://127.0.0.1:3200";
const live = process.env.ATLAS_LIVE_URL;
const destination = fileURLToPath(
  new URL("../../data/publication-checks/", import.meta.url),
);
await mkdir(destination, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
const failed = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400 && response.url().startsWith(base))
    failed.push(`${response.status()} ${new URL(response.url()).pathname}`);
});
try {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto(base);
    const project = page.locator(".project-row").first();
    await expect(project.getByRole("heading", { name: "ATLAS" })).toBeVisible();
    await expect(page.locator(".project-row")).toHaveCount(5);
    for (const value of ["0.898", "0.793", "29.4 FPS", "2.490 mph"])
      await expect(project.getByText(value, { exact: true })).toBeVisible();
    const link = project.getByRole("link", { name: "Live demo" });
    if (live) await expect(link).toHaveAttribute("href", live);
    await expect(
      project.getByRole("link", { name: "Source code" }),
    ).toHaveAttribute("href", "https://github.com/youssef061204/ATLAS");
    await expect
      .poll(() =>
        project
          .locator("img")
          .evaluate((image) => image.complete && image.naturalWidth > 0),
      )
      .toBe(true);
    await project.screenshot({ path: `${destination}/portfolio-${width}.png` });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await project.getByRole("link", { name: "Read case study" }).click();
    await expect(page.getByRole("heading", { name: "ATLAS." })).toBeVisible();
    await expect(page.locator(".gallery-grid img")).toHaveCount(4);
    for (const image of await page.locator(".gallery-grid img").all()) {
      await image.scrollIntoViewIfNeeded();
      await expect
        .poll(() =>
          image.evaluate((node) => node.complete && node.naturalWidth > 0),
        )
        .toBe(true);
    }
    const video = page.locator("video");
    await video.scrollIntoViewIfNeeded();
    await video.evaluate((element) => element.play());
    await expect
      .poll(() => video.evaluate((element) => element.currentTime))
      .toBeGreaterThan(0.5);
    await video.evaluate((element) => element.pause());
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  }
  for (const file of [
    "digital-twin.webp",
    "analytics.webp",
    "optimization.webp",
    "benchmarks.webp",
    "demo.mp4",
  ]) {
    const response = await page.request.get(`${base}/projects/atlas/${file}`);
    expect(response.status()).toBe(200);
  }
  expect(errors).toEqual([]);
  expect(failed).toEqual([]);
  console.log(
    JSON.stringify({
      url: base,
      desktop: "passed",
      mobile: "passed",
      optimized_images: 4,
      video_playback: "passed",
      errors: 0,
    }),
  );
} finally {
  await browser.close();
}
