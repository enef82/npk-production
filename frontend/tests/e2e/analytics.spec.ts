import { expect, test, type Page } from "@playwright/test";

import { HEAD_EMAIL, loginAs, openBoard } from "./production-helpers";

// Данные — `manage.py seed_demo`: закрытые отсечки 8 прошлых недель (`analytics`),
// заказы, заявки, табель и контроль остальных модулей. Начальник производства —
// morozov@ (право закрытия отсечки), наблюдатель — lebedev@, инженер ОТК — orlova@.
const OBSERVER_EMAIL = "lebedev@npk-prod.local";
const QC_EMAIL = "orlova@npk-prod.local";

async function shot(page: Page, name: string): Promise<void> {
  if (process.env.G_SHOTS) await page.screenshot({ path: `${process.env.G_SHOTS}/${name}.png`, fullPage: true });
}

test("отсечки: матрица истории, закрытие текущей недели и переоткрытие с причиной", async ({ page }) => {
  await loginAs(page, HEAD_EMAIL);
  await page.goto("/cutoffs");
  await expect(page.getByRole("heading", { name: "Недельные отсечки по участкам" })).toBeVisible();
  const matrix = page.getByTestId("cutoff-matrix");
  await expect(matrix.locator("tbody tr")).toHaveCount(11);
  await expect(matrix.locator("thead")).toContainText("отсечка");
  await shot(page, "01-cutoffs");

  // Текущая неделя открыта: закрываем с правкой часов и комментарием.
  const week = page.getByTestId("cutoff-week");
  await expect(week).toContainText("открыта — данные текущие");
  await week.getByRole("button", { name: "Закрыть отсечку недели" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("spinbutton").first()).toBeVisible();
  await dialog.getByLabel("Комментарий").fill("e2e: проверка отсечки");
  await shot(page, "02-cutoff-close-dialog");
  await dialog.getByRole("button", { name: "Закрыть отсечку" }).click();
  await expect(week.getByTestId("cutoff-closed")).toBeVisible();
  await expect(week).toContainText("e2e: проверка отсечки");

  // Переоткрытие — только с причиной; причина остаётся в журнале.
  await week.getByRole("button", { name: "Переоткрыть" }).click();
  const reopen = page.getByRole("dialog");
  await expect(reopen.getByRole("button", { name: "Переоткрыть" })).toBeDisabled();
  await reopen.getByLabel("Причина").fill("e2e: возврат недели");
  await reopen.getByRole("button", { name: "Переоткрыть" }).click();
  await expect(week).toContainText("открыта — данные текущие");
  await expect(page.getByTestId("cutoff-events")).toContainText("e2e: возврат недели");

  // Клик по закрытой неделе в матрице — её снимок.
  await matrix.locator("tbody tr").first().locator("td").nth(1).click();
  await expect(week.getByTestId("cutoff-closed")).toBeVisible();
  await shot(page, "03-cutoff-closed-week");
});

test("отсечки: наблюдатель видит данные, но закрыть не может", async ({ page }) => {
  await loginAs(page, OBSERVER_EMAIL);
  await page.goto("/cutoffs");
  await expect(page.getByTestId("cutoff-matrix").locator("tbody tr").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Закрыть отсечку недели" })).toBeDisabled();
});

test("загрузка участков: 10 недель с процентами и заявками", async ({ page }) => {
  await loginAs(page, HEAD_EMAIL);
  await page.goto("/load");
  const grid = page.getByTestId("load-grid");
  await expect(grid.locator("thead th")).toHaveCount(12);
  await expect(grid.locator("tbody tr")).toHaveCount(11);
  await expect(grid.locator("tbody td").filter({ hasText: /%/ }).first()).toBeVisible();
  await shot(page, "04-load");
});

test("портфель: выручка и загрузка по месяцам, вероятности этапов, карточка из списка", async ({ page }) => {
  await loginAs(page, HEAD_EMAIL);
  await page.goto("/portfolio");
  await expect(page.getByTestId("portfolio-probabilities")).toContainText("Просчёт: 30%");
  await expect(page.getByTestId("portfolio-revenue").locator("svg rect").first()).toBeVisible();
  await expect(page.getByTestId("portfolio-load")).toContainText("Мощность");
  await expect(page.getByTestId("portfolio-centers").locator("tbody tr")).toHaveCount(11);
  await shot(page, "05-portfolio");

  const items = page.getByTestId("portfolio-items").locator("tbody tr");
  await items.filter({ hasText: /ПЗ-/ }).first().click();
  await expect(page.getByTestId("order-sheet")).toBeVisible();
});

test("сотрудники: часы и рубли, сортировка, карточка сотрудника", async ({ page }) => {
  await loginAs(page, HEAD_EMAIL);
  await page.goto("/employees");
  const table = page.getByTestId("employees-table");
  await expect(table.getByTestId("employee-row").first()).toBeVisible();
  await shot(page, "06-employees-hours");

  await table.getByRole("columnheader", { name: /Освоено, н-ч/ }).click();
  await expect(table.getByRole("columnheader", { name: /Освоено, н-ч ▾/ })).toBeVisible();

  await page.getByRole("button", { name: "В рублях" }).click();
  await expect(table.getByRole("columnheader", { name: /Выработка, ₽/ })).toBeVisible();
  await expect(page.getByTestId("employees-months")).toBeVisible();
  await shot(page, "07-employees-rub");

  await page.getByRole("combobox", { name: "Период" }).click();
  await page.getByRole("option", { name: "прошлый месяц" }).click();
  await expect(table.getByTestId("employee-row").first()).toBeVisible();

  await table.getByTestId("employee-row").filter({ hasText: "Захаров" }).click();
  const card = page.getByTestId("employee-card");
  await expect(card).toContainText("Структура времени");
  await expect(card).toContainText("Операции");
  await shot(page, "08-employee-card");
});

test("карточка операции: запись контроля по праву из abilities, вкладки снабжения заказа", async ({ page }) => {
  // Право записи контроля приходит в `abilities` блока операции: инженер ОТК видит форму,
  // наблюдатель — только записи.
  await loginAs(page, QC_EMAIL);
  await openBoard(page);
  await page.getByTestId("col-prod").getByTestId("board-card").first().click();
  const sheet = page.getByTestId("order-sheet");
  await sheet.getByRole("tab", { name: "Материалы" }).click();
  await expect(sheet.getByTestId("order-supply-mat").locator("tbody tr").first()).toBeVisible();
  await sheet.getByRole("tab", { name: "Оснастка" }).click();
  await expect(sheet.getByTestId("order-supply-tool").locator("tbody tr").first()).toBeVisible();
  await shot(page, "09-order-tools");

  await sheet.getByRole("tab", { name: "Состояние" }).click();
  // Операция с точкой контроля (метка «контроль»): инженер ОТК видит форму записи.
  const controlled = sheet
    .getByTestId("state-table")
    .locator("tr")
    .filter({ hasText: "контроль" })
    .filter({ hasText: "В работе" })
    .first();
  const name = await controlled.locator("button.text-left").first().innerText();
  await controlled.locator("button.text-left").first().click();
  const qcForm = page.getByTestId("operation-dialog").getByTestId("operation-qc");
  await expect(qcForm.getByRole("button", { name: "Записать" })).toBeVisible();
  await shot(page, "10-operation-qc-form");

  // Наблюдатель — та же операция без формы записи.
  await loginAs(page, OBSERVER_EMAIL);
  await openBoard(page);
  await page.getByTestId("col-prod").getByTestId("board-card").first().click();
  await page.getByTestId("order-sheet").getByRole("tab", { name: "Состояние" }).click();
  await page
    .getByTestId("order-sheet")
    .getByTestId("state-table")
    .getByRole("button", { name, exact: true })
    .click();
  const qc = page.getByTestId("operation-dialog").getByTestId("operation-qc");
  await expect(qc.getByTestId("operation-qc-readonly")).toBeVisible();
  await expect(qc.getByRole("button", { name: "Записать" })).toHaveCount(0);
});
