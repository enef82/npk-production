import { expect, test } from "@playwright/test";

import { ROLE_PASSWORD, login } from "./helpers";

// Демо-набор `manage.py seed_demo` (src/analytics/management/commands/seed_demo.py):
// начальник производства правит разноску любого подразделения, текущий месяц — «Заполняется».
const PRODUCTION_HEAD = "morozov@npk-prod.local";
const SHOTS = process.env.E2E_SHOTS_DIR;

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Первый будний день текущего месяца раньше сегодняшнего (закрытый день табеля). */
function closedWorkday(): string | null {
  const now = new Date();
  for (let d = 1; d < now.getDate(); d++) {
    const day = new Date(now.getFullYear(), now.getMonth(), d);
    if (day.getDay() !== 0 && day.getDay() !== 6) return iso(day);
  }
  return null;
}

test("табель: проверки периода и диалог дня с разноской", async ({ page }) => {
  const day = closedWorkday();
  test.skip(day === null, "в текущем месяце ещё нет закрытых рабочих дней");

  await login(page, PRODUCTION_HEAD, ROLE_PASSWORD);
  await page.goto("/timesheet");
  await expect(page.getByRole("heading", { name: "Табель" })).toBeVisible();

  const now = new Date();
  await page.getByLabel("Месяц").selectOption(iso(new Date(now.getFullYear(), now.getMonth(), 1)));
  const department = page.getByLabel("Подразделение");
  await expect(department.locator("option", { hasText: "Сборочно-монтажный участок" })).toHaveCount(1);
  await department.selectOption(
    (await department.locator("option", { hasText: "Сборочно-монтажный участок" }).getAttribute("value")) ?? "",
  );
  await expect(page.getByTestId("period-status")).toHaveText(/Заполняется|Открыт для корректировки/);

  // Текущий месяц не закончен — блокирующая проверка, подать нельзя.
  await expect(page.getByTestId("timesheet-checks")).toContainText("Месяц не закончен");
  await expect(page.getByRole("button", { name: "Подать на согласование" })).toBeDisabled();

  const cell = page.getByTestId("timesheet-grid").locator(`td[data-day="${day}"]`).first();
  await cell.click();
  const dialog = page.getByTestId("day-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Сохранить" })).toBeVisible();

  // Быстрое заполнение: 6 ч накладные + 2 ч обучение = 8 ч.
  await dialog.getByRole("button", { name: "8 ч накладные" }).click();
  await expect(dialog.getByTestId("day-row")).toHaveCount(1);
  await dialog.getByLabel("Часы").first().fill("6");
  await dialog.getByRole("button", { name: "+ строка" }).click();
  await expect(dialog.getByTestId("day-row")).toHaveCount(2);
  const second = dialog.getByTestId("day-row").nth(1);
  await second.getByLabel("Объект разноски").selectOption("training");
  await second.getByLabel("Часы").fill("2");
  await expect(dialog.getByTestId("day-total")).toHaveText("8 ч");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/timesheet-day-dialog.png` });
  await dialog.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Разноска дня сохранена")).toBeVisible();
  await expect(dialog).toBeHidden();

  // Сетка перечитана: в ячейке 8 ч и пометка «есть накладные».
  await expect(cell).toHaveText("8");
  await expect(cell).toHaveClass(/bg-amber-50/);

  // Разворот по объектам показывает строку «Обучение и аттестация».
  await page.getByLabel("показать разноску по объектам").check();
  await expect(page.getByTestId("timesheet-grid")).toContainText("Обучение и аттестация");

  // Повторное открытие — строки сохранены.
  await cell.click();
  await expect(dialog.getByTestId("day-row")).toHaveCount(2);
  await dialog.getByRole("button", { name: "Отмена" }).click();

  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/timesheet.png` });
    await page.getByTestId("timesheet-checks").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}/timesheet-panels.png` });
  }
});
