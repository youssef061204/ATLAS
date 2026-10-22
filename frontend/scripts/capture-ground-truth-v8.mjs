import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3100";
const output = resolve(process.cwd(), "../data/reality-v8/page-inspection");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
try {
  for (const [name, width, height] of [
    ["desktop", 1440, 1050],
    ["mobile", 390, 844],
  ]) {
    const page = await browser.newPage({
      viewport: { width, height },
      deviceScaleFactor: 1,
    });
    await page.goto(`${base}/ground-truth`, { waitUntil: "networkidle" });
    await page.locator("figure img").evaluate(async (image) => {
      const photo = image;
      if (!photo.complete)
        await new Promise((resolve) =>
          photo.addEventListener("load", resolve, { once: true }),
        );
    });
    await page.screenshot({
      path: resolve(output, `${name}.png`),
      fullPage: true,
    });
    await page.close();
  }
} finally {
  await browser.close();
}
