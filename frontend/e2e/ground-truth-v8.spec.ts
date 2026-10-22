import { expect, test } from "@playwright/test";

test("ground-truth page keeps oracle claims and source geometry inspectable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/ground-truth");
  await expect(
    page.getByRole("heading", {
      name: "The Main Street crossing is the weak link.",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Oracle diagnostic · not deployable"),
  ).toBeVisible();
  const northbound = page.getByText("Northbound position error").locator("..");
  await expect(northbound).toContainText("33.58");
  await expect(northbound).toContainText("6.56");
  await expect(page.getByText("1,441 observed states")).toBeVisible();
  const source = page.getByRole("img", {
    name: /Actual Lankershim traffic video frame/,
  });
  await expect(source).toBeVisible();
  await expect
    .poll(() =>
      source.evaluate((image) => (image as HTMLImageElement).naturalWidth),
    )
    .toBeGreaterThan(0);
  await expect(
    page.getByRole("link", { name: "Watch video + 3D twin" }),
  ).toHaveAttribute("href", "/reality");
  expect(errors).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(source).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
});
