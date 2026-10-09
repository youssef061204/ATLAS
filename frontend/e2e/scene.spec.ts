import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("actual official image supports a persisted observation-bound region correction", async ({
  page,
}) => {
  test.skip(
    !process.env.ATLAS_TEST_OPERATOR_KEY,
    "Requires an authorized native worker and official source access",
  );
  await page.goto("/twin?city=toronto&camera=8018");
  await page
    .getByLabel("Intelligence operator key")
    .fill(process.env.ATLAS_TEST_OPERATOR_KEY!);
  await page.getByRole("button", { name: "Observe a new snapshot" }).click();
  await expect(
    page.getByAltText("Official snapshot processed in this observation"),
  ).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel("Intelligence operator key")).toHaveValue("");
  await page
    .getByText("Correct the camera’s road region", { exact: true })
    .click();
  for (const [x, y] of [
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1],
  ]) {
    await page.getByLabel("Region vertex x").fill(String(x));
    await page.getByLabel("Region vertex y").fill(String(y));
    await page.getByRole("button", { name: "Add vertex", exact: true }).click();
  }
  await page
    .getByLabel("Scene operator key")
    .fill(process.env.ATLAS_TEST_OPERATOR_KEY!);
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/operations/scenes") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save corrected region" }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  const result = await response.json();
  await expect(
    page.getByText(
      `These counts and estimated inputs now use operator region revision ${result.revision}. Road/lane calibration remains unvalidated.`,
    ),
  ).toBeVisible();
  await expect(page.getByLabel("Scene operator key")).toHaveValue("");
  await expect(
    page.getByRole("heading", { name: "Actual completed counterfactual" }),
  ).toHaveCount(0);
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});
