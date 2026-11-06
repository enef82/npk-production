import { test, expect } from "@playwright/test";
import { ROLE_PASSWORD, login, switchUser } from "./helpers";

// Данные — `manage.py seed_demo` (строки потребности демо-заказов в разных статусах,
// поставщики прототипа). Снабженец — kuznetsov@, начальник склада — shilova@.
const PROCUREMENT_EMAIL = "kuznetsov@npk-prod.local";
const WAREHOUSE_EMAIL = "shilova@npk-prod.local";

test("test_снабженец_оформляет_заказ_а_склад_принимает", async ({ page }) => {
  await login(page, PROCUREMENT_EMAIL, ROLE_PASSWORD);
  await page.goto("/supply");
  await expect(page.getByRole("heading", { name: "Закупки и склад" })).toBeVisible();
  await expect(page.getByText("к заказу (снабжение)")).toBeVisible();

  // Позиции «Передано в закупку» — снабженцу доступен заказ поставщику.
  await page.getByText("к заказу (снабжение)").click();
  const lines = page.getByTestId("supply-lines");
  const row = lines.locator("tbody tr").filter({ has: page.getByRole("button", { name: "Заказано" }) }).first();
  const name = (await row.locator("td").nth(2).innerText()).split("\n")[0].split(" · ")[0];
  await row.getByRole("button", { name: "Заказано" }).click();
  await page.getByRole("combobox", { name: "Поставщик" }).click();
  await page.getByRole("option", { name: "ООО «ИнструментЦентр»" }).click();
  await page.getByRole("button", { name: "Оформить заказ" }).click();
  await expect(page.getByText(/Заказ оформлен: ЗП-/)).toBeVisible();

  // Склад видит строку заказанной и принимает её; история показывает оба действия.
  await switchUser(page, WAREHOUSE_EMAIL, ROLE_PASSWORD);
  await page.goto("/supply");
  await page.getByRole("textbox", { name: "Поиск по позициям" }).fill(name);
  const ordered = page
    .getByTestId("supply-lines")
    .locator("tbody tr")
    .filter({ hasText: name })
    .filter({ has: page.getByRole("button", { name: "Принять на склад" }) })
    .first();
  await ordered.getByRole("button", { name: "Принять на склад" }).click();
  await page.getByRole("button", { name: "Принять", exact: true }).click();
  await expect(page.getByText("Принято на склад").first()).toBeVisible();
});

test("test_наблюдатель_не_видит_действий_снабжения", async ({ page }) => {
  await login(page, "lebedev@npk-prod.local", ROLE_PASSWORD);
  await page.goto("/supply");
  await expect(page.getByRole("heading", { name: "Закупки и склад" })).toBeVisible();
  await expect(page.getByTestId("supply-lines").locator("tbody tr").first()).toBeVisible();
  await expect(page.getByTestId("supply-lines").getByRole("button", { name: "Заказано" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Заявка на закупку" })).toBeDisabled();
});
