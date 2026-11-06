import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("test_создание_контрагента_показывает_предупреждение_о_дубликате", async ({ page }) => {
  await page.getByRole("button", { name: "Создать" }).click();

  // "Альфа Строй" — уже существует в сиде (core.accounts.management.commands.seed).
  // Другой ИНН — иначе сработало бы ограничение БД на точное совпадение (инн, кпп),
  // а не нечёткое совпадение по названию, которое проверяет этот тест (docs/spec/
  // 02yadroidentichnosti.md §5.1: сначала точный ИНН, затем нечёткое имя).
  await page.getByLabel("Краткое наименование").fill("Альфа Строй");
  await page.getByLabel("Полное наименование").fill("Альфа Строй, другое ООО");
  await page.getByLabel("ИНН").fill("7799112233");
  await page.getByRole("button", { name: "Создать", exact: true }).click();

  await expect(page.getByText("Найдены похожие контрагенты")).toBeVisible();
  // Форма не закрылась и не сброшена — у пользователя остаётся шанс поправить ввод.
  await expect(page.getByLabel("Краткое наименование")).toHaveValue("Альфа Строй");
});

test("test_серверная_ошибка_валидации_подсвечивает_поле", async ({ page }) => {
  // EntityForm валидирует той же zod-схемой, что сгенерирована из того же OpenAPI,
  // что и backend (задание, критерий приёмки: «типы фронтенда полностью выведены
  // из OpenAPI, ручных дублей нет») — а значит клиент и сервер физически не могут
  // разойтись в этом ограничении, и обычным пользовательским вводом 422 с backend
  // не воспроизвести. Подменяем ответ сети только для этого теста, чтобы проверить
  // реальный код EntityForm, отвечающий за отрисовку серверной ошибки поля
  // (lib/api/mutator.ts: fieldErrors → components/entity-form/entity-form.tsx:
  // form.setError), а не выдумывать несуществующее серверное правило.
  await page.route("**/api/v1/identity/parties", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        code: "validation_error",
        message: "Данные не прошли проверку.",
        errors: [{ loc: ["body", "payload", "short_name"], msg: "Уже занято другим контрагентом.", type: "value_error" }],
      }),
    });
  });

  await page.getByRole("button", { name: "Создать" }).click();
  await page.getByLabel("Краткое наименование").fill("Тестовый ввод");
  await page.getByLabel("Полное наименование").fill("Тестовый ввод ООО");
  await page.getByRole("button", { name: "Создать", exact: true }).click();

  const shortNameField = page.getByLabel("Краткое наименование");
  await expect(shortNameField).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("Уже занято другим контрагентом.")).toBeVisible();
});
