import fs from "node:fs";
import { test, expect } from "@playwright/test";
import { filterList, login, waitForFilteredList } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("test_список_контрагентов_фильтруется_и_сортируется", async ({ page }) => {
  const rows = page.locator('[role="row"]');

  // Фильтр по поиску — "Ostrom Trading Ltd" из сида, единственный нерезидент по имени.
  await filterList(page, {
    label: "Поиск по контрагентам",
    pathname: "/api/v1/identity/parties",
    paramName: "search",
    value: "Ostrom",
  });
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Ostrom Trading Ltd");
  await page.getByLabel("Поиск по контрагентам").fill("");

  // Фильтр по типу — ровно один нерезидент в сиде.
  await page.getByLabel("Тип").click();
  await page.getByRole("option", { name: "Нерезидент" }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Ostrom Trading Ltd");
  await page.getByLabel("Тип").click();
  await page.getByRole("option", { name: "Все типы" }).click();

  // Сортировка — обратный клик должен развернуть порядок, а не завязываться на
  // конкретную коллацию БД (латиница/кириллица сортируются в PostgreSQL не так,
  // как в JS `.sort()`).
  //
  // `waitForLoadState("networkidle")` здесь не годится (найдено 05.09 на прогоне
  // CI, PR #1: `parties-list.spec.ts` "...восстанавливается" поймал пустой Array[]
  // после `reload()`) — это тот же класс гонки, что и дебаунс-фильтр (helpers.ts,
  // `waitForFilteredList`): networkidle реагирует на сетевую тишину вообще, а не
  // на конкретный ответ таблицы, и пока запрос ещё не стартовал (или уже завершился,
  // но React ещё не перерисовал), `[role="row"]` не существует ни одного —
  // `DataTable` рендерит их только вне `isLoading` (data-table.tsx). Ждём сам ответ
  // с нужной сортировкой и появление хотя бы одной строки, а не отведённое под это время.
  const ascendingLoaded = waitForFilteredList(page, "/api/v1/identity/parties", "ordering", "short_name");
  await page.getByRole("button", { name: "Наименование" }).click();
  await ascendingLoaded;
  await expect(page.locator('[role="row"]').first()).toBeVisible();
  const ascending = await page.locator('[role="row"]').allTextContents();

  const descendingLoaded = waitForFilteredList(page, "/api/v1/identity/parties", "ordering", "-short_name");
  await page.getByRole("button", { name: "Наименование" }).click();
  await descendingLoaded;
  await expect(page.locator('[role="row"]').first()).toBeVisible();
  const descending = await page.locator('[role="row"]').allTextContents();

  expect(descending).toEqual([...ascending].reverse());
});

test("test_состояние_таблицы_сохраняется_в_url_и_восстанавливается", async ({ page }) => {
  await expect(page.locator('[role="row"]').first()).toBeVisible();
  const sorted = waitForFilteredList(page, "/api/v1/identity/parties", "ordering", "short_name");
  await page.getByRole("button", { name: "Наименование" }).click();
  await sorted;
  await expect(page).toHaveURL(/ordering=short_name/);
  await expect(page.locator('[role="row"]').first()).toBeVisible();

  const beforeReload = await page.locator('[role="row"]').allTextContents();

  // Тот же приём для `reload()`, что и для сортировки выше: ждём именно ответ
  // с сохранённой сортировкой, а не сетевую тишину вообще (см. комментарий выше).
  const reloaded = waitForFilteredList(page, "/api/v1/identity/parties", "ordering", "short_name");
  await page.reload();
  await reloaded;

  await expect(page).toHaveURL(/ordering=short_name/);
  await expect(page.locator('[role="row"]').first()).toBeVisible();
  const afterReload = await page.locator('[role="row"]').allTextContents();
  expect(afterReload).toEqual(beforeReload);
});

test("test_смена_фильтра_обновляет_счётчик_найденных", async ({ page }) => {
  // useKnownTotal (components/data-table/use-known-total.ts) держит последнее известное
  // total между страницами одного набора — риск в том, что оно застрянет и после смены
  // фильтра, молча показывая счётчик от предыдущего набора. `setFilter` сбрасывает
  // курсор (use-table-url-state.ts), что заново включает `with_total` на первой
  // странице нового набора — проверяем, что счётчик реально обновляется, а не просто
  // что механизм теоретически должен сработать.
  await expect(page.getByText(/^Найдено:/)).toBeVisible();
  const before = await page.getByText(/^Найдено:/).textContent();

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/identity/parties?") &&
      response.url().includes("with_total") &&
      response.url().includes("Ostrom"),
    { timeout: 10_000 },
  );
  await page.getByLabel("Поиск по контрагентам").fill("Ostrom");
  const response = await responsePromise;
  const body = await response.json();

  // Backend действительно пересчитал total для отфильтрованного набора (единственный
  // "Ostrom Trading Ltd" в сиде) — это не total от предыдущего запроса.
  expect(body.total).toBe(1);

  await expect(page.getByText("Найдено: 1")).toBeVisible();
  expect(before).not.toBe("Найдено: 1");
});

test("test_экспорт_списка_в_excel", async ({ page }) => {
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Экспорт в Excel" }).click(),
  ]);

  expect(download.suggestedFilename()).toBe("kontragenty.xlsx");
  const savedPath = await download.path();
  expect(savedPath).not.toBeNull();
  const stats = fs.statSync(savedPath as string);
  expect(stats.size).toBeGreaterThan(0);
});
