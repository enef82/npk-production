import { expect, test } from "@playwright/test";

import { ROLE_PASSWORD, login } from "./helpers";

// Любой аутентифицированный читает энергоучёт; демо-счётчики — `manage.py seed_demo`.
const VIEWER = "morozov@npk-prod.local";
const SHOTS = process.env.E2E_SHOTS_DIR;

test("энергоучёт: дерево счётчиков с балансом и графики", async ({ page }) => {
  await login(page, VIEWER, ROLE_PASSWORD);
  await page.goto("/energy");
  await expect(page.getByRole("heading", { name: "Энергоучёт" })).toBeVisible();

  const tree = page.getByTestId("meter-tree");
  await expect(tree).toContainText("Ввод ТП-1 (коммерческий учёт)");
  await expect(tree).toContainText("Лазерный станок");
  // У ввода есть дочерние — показан баланс (потери, %).
  await expect(tree.locator("tr", { hasText: "Ввод ТП-1" })).toContainText("%");

  // Расход по дням — столбцы есть.
  await expect(page.getByTestId("daily-chart").locator("rect").first()).toBeVisible();
  // Профиль суток по выбранной точке учёта: линия из 48 точек.
  await expect(page.getByRole("heading", { name: /Получасовой профиль: Ввод ТП-1/ })).toBeVisible();
  await expect(page.getByTestId("profile-chart").locator("path").first()).toBeVisible();

  await tree.locator("tr", { hasText: "Механозаготовительный участок" }).click();
  await expect(page.getByRole("heading", { name: /Получасовой профиль: Механозаготовительный участок/ })).toBeVisible();

  await expect(page.getByTestId("specific-table")).toContainText("ИН-0012");
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/energy.png` });
    await page.getByTestId("profile-chart").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/energy-profile.png` });
    await page.getByTestId("specific-table").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/energy-specific.png` });
  }

  await page.getByLabel("Ресурс", { exact: true }).selectOption("gas");
  await expect(tree).toContainText("Газ, ввод");
  await expect(tree).toContainText("Печь полимеризации");
});
