import { expect, test, type Page } from "@playwright/test";

import { HEAD_EMAIL, MANAGER_EMAIL, loginAs, openBoard } from "./production-helpers";

// Сценарии меняют демо-данные (`manage.py seed_demo`): каждый берёт первую подходящую
// карточку колонки, а не конкретный номер, — повторный прогон без пересева тоже проходит,
// пока в колонке есть карточки.

async function shot(page: Page, name: string): Promise<void> {
  if (process.env.F1_SHOTS) await page.screenshot({ path: `${process.env.F1_SHOTS}/${name}.png` });
}

test.beforeEach(async ({ page }) => {
  await loginAs(page, HEAD_EMAIL);
});

test("доска: перетаскивание заказа вперёд с визой этапа и назад с причиной", async ({ page }) => {
  await openBoard(page);
  await shot(page, "01-board");

  const launch = page.getByTestId("col-launch");
  const card = launch.getByTestId("board-card").first();
  const number = await card.getAttribute("data-number");
  expect(number).toBeTruthy();

  await card.dragTo(page.getByTestId("col-prep"));
  const visa = page.getByRole("dialog");
  await expect(visa.getByText("Виза: этап «Запуск в работу»")).toBeVisible();
  await shot(page, "02-board-visa-dialog");
  await visa.getByRole("button", { name: "Завизировать и перевести" }).click();
  await expect(page.getByTestId("col-prep").locator(`[data-number="${number}"]`)).toBeVisible();

  // Назад — только с причиной.
  await page.getByTestId("col-prep").locator(`[data-number="${number}"]`).dragTo(launch);
  const back = page.getByRole("dialog");
  await expect(back.getByText("Вернуть на этап «Запуск в работу»?")).toBeVisible();
  await back.getByRole("button", { name: "Вернуть" }).click();
  await expect(back.getByText("Поле обязательно.")).toBeVisible();
  await back.getByRole("textbox").fill("Не хватает КД от заказчика");
  await back.getByRole("button", { name: "Вернуть" }).click();
  await expect(launch.locator(`[data-number="${number}"]`)).toBeVisible();
});

test("доска: заказ нельзя вернуть в заявки — ошибка тостом", async ({ page }) => {
  await openBoard(page);
  await page.getByTestId("col-launch").getByTestId("board-card").first().dragTo(page.getByTestId("col-approval"));
  await expect(page.getByText("Заказ уже запущен — вернуть его в заявки нельзя.")).toBeVisible();
});

test("карточка заказа: вкладки и карточка операции", async ({ page }) => {
  await openBoard(page);
  await page.getByTestId("col-prod").getByTestId("board-card").first().click();
  const sheet = page.getByTestId("order-sheet");
  await expect(sheet.getByRole("tab", { name: "Основное" })).toBeVisible();
  await expect(sheet.getByText("Ответственные и визы по этапам")).toBeVisible();
  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+$/);
  await shot(page, "03-order-main");

  await sheet.getByRole("tab", { name: "Калькуляция" }).click();
  await expect(sheet.getByTestId("calc-totals")).toBeVisible();

  await sheet.getByRole("tab", { name: "План" }).click();
  await expect(sheet.getByTestId("plan-table")).toBeVisible();
  await expect(sheet.getByTestId("mini-gantt")).toBeVisible();
  await shot(page, "04-order-plan");

  await sheet.getByRole("tab", { name: "Состояние" }).click();
  await expect(sheet.getByTestId("state-table")).toBeVisible();
  await shot(page, "05-order-state");

  await sheet.getByRole("tab", { name: "Документы" }).click();
  await expect(sheet.getByTestId("order-tab-docs")).toContainText("выберите файлы");

  await sheet.getByRole("tab", { name: "Материалы" }).click();
  await expect(sheet.getByTestId("order-supply-stub")).toBeVisible();
  await sheet.getByRole("tab", { name: "Оснастка" }).click();
  await expect(sheet.getByTestId("order-supply-stub")).toBeVisible();

  await sheet.getByRole("tab", { name: "Журнал" }).click();
  await sheet.locator('textarea[name="journal-text"]').fill("e2e: проверка журнала");
  await sheet.getByRole("button", { name: "Добавить" }).click();
  await expect(sheet.getByTestId("journal-list")).toContainText("e2e: проверка журнала");
  await shot(page, "06-order-journal");

  await sheet.getByRole("tab", { name: "Состояние" }).click();
  await sheet.getByTestId("state-table").getByRole("button").first().click();
  const op = page.getByTestId("operation-dialog");
  await expect(op.getByText("Связи")).toBeVisible();
  await expect(op.getByTestId("operation-qc-stub")).toBeVisible();
  await shot(page, "07-operation");

  // Прямая ссылка открывает ту же карточку поверх доски.
  const url = page.url();
  await page.goto(url);
  await expect(page.getByTestId("order-sheet")).toBeVisible();
});

test("Гант: перенос операции перетаскиванием полосы", async ({ page }) => {
  await page.goto("/gantt");
  const gantt = page.getByTestId("gantt");
  await expect(gantt).toBeVisible({ timeout: 30_000 });
  await shot(page, "08-gantt");

  const bar = gantt.locator('[data-testid="gantt-op-bar"][data-locked="0"]').first();
  await bar.scrollIntoViewIfNeeded();
  const box = (await bar.boundingBox())!;
  const before = await bar.evaluate((el) => (el as HTMLElement).style.left);
  await page.mouse.move(box.x + 6, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + 30, box.y + box.height / 2, { steps: 4 });
  await page.mouse.move(box.x + 6 + 26 * 3, box.y + box.height / 2, { steps: 6 });
  await expect(page.getByTestId("gantt-tip")).toHaveText("+3 раб. дн.");
  await page.mouse.up();
  await expect(page.getByText(/перенесена на/)).toBeVisible();
  const id = await bar.getAttribute("data-op");
  await expect
    .poll(async () => gantt.locator(`[data-op="${id}"]`).evaluate((el) => (el as HTMLElement).style.left))
    .not.toBe(before);
});

test("запуск заявки: диалог запуска с расчётным окончанием и созданием заказа", async ({ page }) => {
  await openBoard(page);
  const approval = page.getByTestId("col-approval");
  const card = approval.getByTestId("board-card").first();
  const number = await card.getAttribute("data-number");
  await card.dragTo(page.getByTestId("col-launch"));

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Запуск в работу")).toBeVisible();
  await expect(dialog.getByTestId("launch-preview")).toContainText("Плановое окончание", { timeout: 15_000 });
  await expect(dialog.getByTestId("launch-preview")).toContainText("Критический путь");
  await shot(page, "09-launch-dialog");
  await dialog.getByRole("button", { name: "Создать заказ" }).click();

  const sheet = page.getByTestId("order-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText(`заявка ${number}`)).toBeVisible();
  await expect(sheet.getByTestId("plan-table")).toBeVisible();
  await expect(approval.locator(`[data-number="${number}"]`)).toHaveCount(0);
});

test("заявка: карточка с калькуляцией и планом, «Мои визы» и участки", async ({ page }) => {
  await openBoard(page);
  await page.getByTestId("col-calc").getByTestId("board-card").first().click();
  const sheet = page.getByTestId("inquiry-sheet");
  await expect(sheet.getByText("Ответственные и визы по этапам")).toBeVisible();
  await sheet.getByRole("tab", { name: "Калькуляция" }).click();
  await expect(sheet.getByTestId("calc-operations")).toBeVisible();
  await shot(page, "10-inquiry-calc");
  await sheet.getByRole("tab", { name: "План" }).click();
  await expect(sheet.getByTestId("inquiry-plan-table")).toBeVisible();

  await page.goto("/my-visas");
  await expect(page.getByRole("heading", { name: "Мои визы" })).toBeVisible();
  const visaButton = page.getByTestId("my-visas-table").getByRole("button", { name: "Завизировать" }).first();
  await expect(visaButton).toBeEnabled();
  await shot(page, "11-my-visas");
  await visaButton.click();
  await expect(page.getByRole("dialog").getByText(/Виза: этап/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Отмена" }).click();

  await page.goto("/work-centers");
  await expect(page.getByTestId("work-centers-table")).toContainText("ОТК");
  await shot(page, "12-work-centers");
});

test("новая заявка менеджером: заказчик из справочника, заполнение калькуляции из шаблона", async ({ page }) => {
  await loginAs(page, MANAGER_EMAIL);
  await openBoard(page);
  await page.getByRole("button", { name: "Новая заявка" }).click();
  const dialog = page.getByTestId("new-inquiry-dialog");
  await dialog.locator('input[name="customer-search"]').fill("Водоканал");
  await dialog.locator("button", { hasText: "Водоканал" }).first().click();
  await dialog.locator('input[name="object-name"]').fill("e2e: КНС-7");
  await dialog.locator('select[name="template"]').selectOption({ index: 1 });
  await shot(page, "13-new-inquiry");
  await dialog.getByRole("button", { name: "Создать заявку" }).click();

  const sheet = page.getByTestId("inquiry-sheet");
  await expect(sheet.getByText("e2e: КНС-7")).toBeVisible();
  await sheet.getByRole("tab", { name: "Калькуляция" }).click();
  await sheet.getByRole("button", { name: "Заполнить из шаблона" }).click();
  await expect(sheet.getByTestId("calc-operations").locator("tbody tr").first()).toBeVisible();
  await sheet.getByRole("tab", { name: "План" }).click();
  await sheet.getByRole("button", { name: "Сформировать план" }).click();
  await expect(sheet.getByTestId("mini-gantt")).toBeVisible();
  await shot(page, "14-inquiry-plan");
});
