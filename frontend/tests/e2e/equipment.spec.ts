import { expect, test } from "@playwright/test";

import { ROLE_PASSWORD, login } from "./helpers";

// Начальник производства из `manage.py seed_demo`: ведёт оборудование, ТО и ремонты.
const PRODUCTION_HEAD = "morozov@npk-prod.local";
const SHOTS = process.env.E2E_SHOTS_DIR;

function localInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

test("оборудование: карточка станка и запись аварии от регистрации до закрытия", async ({ page }) => {
  await login(page, PRODUCTION_HEAD, ROLE_PASSWORD);
  await page.goto("/equipment");
  await expect(page.getByRole("heading", { name: "Оборудование", exact: true })).toBeVisible();

  const machines = page.getByTestId("machines-table");
  await expect(machines.locator("tbody tr")).toHaveCount(10);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/equipment.png` });

  // Карточка станка: 8 недель загрузки, ТО, журнал смен.
  await machines.getByText("Ленточнопильный станок полуавтомат").click();
  const card = page.getByTestId("machine-card");
  await expect(card).toBeVisible();
  await expect(card.getByText("Наработка по неделям, ч")).toBeVisible();
  await expect(card.getByRole("button", { name: "Провести ТО" }).first()).toBeVisible();
  await expect(card.getByRole("button", { name: "Записать смену" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/equipment-card.png` });
  await page.keyboard.press("Escape");
  await expect(card).toBeHidden();

  // Аварии и ремонты: новая запись → в ремонт → устранено.
  await page.getByRole("tab", { name: "Аварии и ремонты" }).click();
  await expect(page.getByTestId("repairs-table")).toBeVisible();
  await page.getByRole("button", { name: "Авария / ремонт" }).click();
  const dialog = page.getByTestId("repair-dialog");
  await expect(dialog).toBeVisible();

  const started = new Date(Date.now() - 3 * 3600_000);
  const finished = new Date(Date.now() - 1 * 3600_000);
  const text = `e2e: утечка гидравлики ${Date.now()}`;
  const machine = dialog.getByLabel("Оборудование");
  await machine.selectOption(
    (await machine.locator("option", { hasText: "Листогибочный пресс" }).getAttribute("value")) ?? "",
  );
  await dialog.getByLabel("Начало простоя").fill(localInput(started));
  await dialog.getByLabel("Категория отказа").selectOption({ label: "Гидравлика" });
  await dialog.getByLabel("Код аварии").fill("E-207");
  await dialog.getByLabel("Описание").fill(text);
  await dialog.getByRole("button", { name: "+ исполнитель" }).click();
  await dialog.getByLabel("Часы исполнителя").fill("1.5");
  await dialog.getByRole("button", { name: "Зарегистрировать" }).click();
  await expect(dialog.getByTestId("repair-status")).toHaveText("Зарегистрирована");

  await dialog.getByRole("button", { name: "В ремонт" }).click();
  await expect(dialog.getByTestId("repair-status")).toHaveText("В ремонте");

  await dialog.getByLabel("Окончание простоя").fill(localInput(finished));
  await dialog.getByLabel("Что сделано").fill("Замена уплотнений");
  await dialog.getByRole("button", { name: "Устранено — закрыть" }).click();
  await expect(dialog.getByTestId("repair-status")).toHaveText("Устранено");
  await expect(dialog.getByRole("button", { name: "Устранено — закрыть" })).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/equipment-repair-closed.png` });
  await dialog.getByRole("button", { name: "Закрыть окно" }).click();

  // Журнал перечитан: запись закрыта, простой 2 ч.
  const row = page.getByTestId("repairs-table").locator("tr", { hasText: text });
  await expect(row).toContainText("Устранено");
  await expect(row).toContainText("2 ч");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/equipment-repairs.png` });
});
