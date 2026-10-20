import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";

const out = new URL("../../data/reality-v7/browser/", import.meta.url);
await mkdir(out, { recursive: true });
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1100 },
  });
  const errors = [],
    failures = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400)
      failures.push({ status: response.status(), url: response.url() });
  });
  await page.goto(process.env.ATLAS_WEB_URL || "http://127.0.0.1:3130/reality");
  await page.getByRole("button", { name: "Play", exact: true }).waitFor();
  await page.locator("canvas").waitFor();
  await page.waitForTimeout(3500);
  await page.screenshot({
    path: new URL("desktop.png", out).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
    fullPage: true,
  });
  const performance = await page
    .getByLabel("Current 3D rendering performance")
    .textContent();
  await page.getByRole("button", { name: "Top down", exact: true }).click();
  await page.waitForTimeout(500);
  await page
    .getByRole("region", { name: "Synchronized SUMO reconstruction" })
    .screenshot({
      path: new URL("top.png", out).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
    });
  await writeFile(
    new URL("inspection.json", out),
    JSON.stringify(
      {
        errors,
        failures,
        performance,
        scope:
          "Development page, headless Chromium SwiftShader software rendering; not physical GPU or production performance",
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ errors, failures, performance }));
} finally {
  await browser.close();
}
