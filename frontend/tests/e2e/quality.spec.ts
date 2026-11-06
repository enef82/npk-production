import { test, expect } from "@playwright/test";
import { ROLE_PASSWORD, login } from "./helpers";

// Данные — `manage.py seed_demo` (точки контроля прототипа, записи контроля и история
// брака за 12 недель). Инженер ОТК — orlova@npk-prod.local.
const QC_ENGINEER_EMAIL = "orlova@npk-prod.local";

test("test_экран_качества_показывает_сводку_парето_и_журнал", async ({ page }) => {
  await login(page, QC_ENGINEER_EMAIL, ROLE_PASSWORD);
  await page.goto("/quality");

  await expect(page.getByRole("heading", { name: "Качество" })).toBeVisible();
  await expect(page.getByTestId("quality-kpi")).toContainText("проверено, шт.");
  await expect(page.getByRole("img", { name: "Брак по неделям" })).toBeVisible();
  await expect(page.getByTestId("quality-by-work-center").locator("tbody tr")).toHaveCount(9);
  await expect(page.getByTestId("quality-records").locator("tbody tr").first()).toContainText(/ПЗ-/);

  await page.getByRole("combobox", { name: "Период" }).click();
  await page.getByRole("option", { name: "12 недель" }).click();
  await expect(page.getByText(/Период: /)).toBeVisible();
});
