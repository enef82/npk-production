import { expect, type Page } from "@playwright/test";

// Учётка суперпользователя — из идемпотентного `make seed`
// (src/core/accounts/management/commands/seed.py, SUPERUSER_EMAIL/SUPERUSER_PASSWORD).
export const ADMIN_EMAIL = "admin@npk-prod.local";
export const ADMIN_PASSWORD = "admin12345";

// Специалист службы без ролей — из `manage.py seed_demo_crm`
// (src/crm/management/commands/seed_demo_crm.py, SPECIALIST_EMAIL/SPECIALIST_PASSWORD).
export const SPECIALIST_EMAIL = "specialist@npk-prod.local";
export const SPECIALIST_PASSWORD = "specialist12345";

// Ролевые учётки шага 9б — из `manage.py seed_demo_crm` (ROLE_USER_PASSWORD и *_EMAIL).
// Неадмины: на суперпользователе не проверить «менеджеру форма недоступна».
export const ROLE_PASSWORD = "demo12345";
// Второй специалист — приёмник задания в мутирующем тесте (пароль ROLE_PASSWORD).
export const SPECIALIST2_EMAIL = "specialist2@npk-prod.local";
export const MANAGER_EMAIL = "manager@npk-prod.local";
export const TECHDIR_EMAIL = "techdir@npk-prod.local";
export const COMMDIR_EMAIL = "commdir@npk-prod.local";
export const PM_EMAIL = "pm@npk-prod.local";

export async function login(page: Page, email = ADMIN_EMAIL, password = ADMIN_PASSWORD): Promise<void> {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  // `useGetCsrf()` (app/login/login-form.tsx) прогревает cookie `csrftoken` после
  // гидратации. Сабмит до этого уходит без токена, и Django отклоняет POST /login
  // как межсайтовый (403) — форма при этом кнопку не блокирует. Ждём саму cookie.
  await expect
    .poll(async () => (await page.context().cookies()).some((c) => c.name === "csrftoken"), {
      timeout: 10_000,
    })
    .toBe(true);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/parties/);
  await expect(page.getByRole("heading", { name: "Контрагенты" })).toBeVisible();
}

/** Сбрасывает сессию и входит под другой учёткой — для сценариев со сменой роли. */
export async function switchUser(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await login(page, email, password);
}

/** Ответ списочного эндпоинта `pathname` содержит `paramName=value`. */
function listResponseMatches(url: string, pathname: string, paramName: string, value: string): boolean {
  if (!url.includes(pathname)) return false;
  return new URL(url).searchParams.get(paramName) === value;
}

/**
 * Ждёт ответ списочного эндпоинта, у которого query-параметр `paramName` равен
 * `value` — конец перезапроса таблицы после действия, которое ГАРАНТИРОВАННО
 * порождает запрос: `page.reload()` или клик по заголовку-сортировке. Для
 * debounce-фильтра по вводу в поле есть `filterList` — там нажатие может потеряться
 * до гидратации, и ожидание ответа надо перезапускать.
 *
 * Своё ожидание — свой таймаут и своя ошибка (правило от 09.09, роадмап): без
 * таймаута `page.waitForResponse` сжигает весь бюджет теста, если запрос не пришёл,
 * и падение читается как безликий «test timeout», а не «ответ не пришёл».
 */
export async function waitForFilteredList(
  page: Page,
  pathname: string,
  paramName: string,
  value: string,
  { timeout = 10_000 }: { timeout?: number } = {},
): Promise<void> {
  try {
    await page.waitForResponse((response) => listResponseMatches(response.url(), pathname, paramName, value), {
      timeout,
    });
  } catch {
    throw new Error(
      `Не дождались ответа ${pathname} с ${paramName}=${value} за ${timeout} мс — ` +
        "запрос не ушёл или сервер не ответил.",
    );
  }
}

/**
 * Печатает `value` в поле `label` и ждёт ответ списочного эндпоинта с этим фильтром.
 *
 * Ввод повторяется. До того как React гидратировал страницу, обработчик `onChange`
 * поля ещё не привязан — `fill` отрабатывает, но нажатие теряется вместе с
 * debounce-запросом. Одно ожидание ответа тут сожгло бы весь бюджет теста, ожидая
 * событие, которого не будет (найдено 09.09; та же дыра есть и у живого пользователя,
 * см. отчёт). `toPass` перезаполняет поле, пока debounce не отправит запрос —
 * признак этого — появившийся в URL параметр.
 *
 * Ожидание ответа регистрируется ОДИН раз, до первой попытки: оно поймает ответ на
 * запрос любой из попыток, когда бы тот ни пришёл, и не может его «проспать».
 * Ответ — основной сигнал; параметр в URL лишь подтверждает, что запрос ушёл.
 */
export async function filterList(
  page: Page,
  {
    label,
    pathname,
    paramName,
    value,
    timeout = 15_000,
  }: { label: string; pathname: string; paramName: string; value: string; timeout?: number },
): Promise<void> {
  let responded = false;
  const gotResponse = page
    .waitForResponse((r) => listResponseMatches(r.url(), pathname, paramName, value), { timeout })
    .then(() => {
      responded = true;
      return true;
    })
    .catch(() => false);

  await expect(async () => {
    if (responded) return;
    await page.getByLabel(label).fill(value);
    await expect(page).toHaveURL((url) => url.searchParams.get(paramName) === value, { timeout: 2_000 });
  }).toPass({ timeout });

  if (!(await gotResponse)) {
    throw new Error(`Фильтр ${paramName}=${value}: ответ ${pathname} не пришёл за ${timeout} мс.`);
  }
}

/** Открывает карточку заявки по фрагменту названия объекта (поиск в реестре). */
export async function openInquiryByObject(page: Page, objectText: string): Promise<void> {
  await page.goto("/crm");
  await filterList(page, {
    label: "Поиск по заявкам",
    pathname: "/api/v1/crm/inquiries",
    paramName: "search",
    value: objectText,
  });
  const row = page.locator('[role="row"]').first();
  await expect(row).toContainText(objectText);
  await row.click();
  await page.waitForURL(/\/crm\/[0-9a-f-]{36}$/);
}

/** Открывает экран расчёта заявки (последняя версия) по фрагменту названия объекта. */
export async function openQuotationByObject(page: Page, objectText: string): Promise<void> {
  await openInquiryByObject(page, objectText);
  await page.getByRole("tab", { name: /Расчёты/ }).click();
  await page.getByRole("link", { name: "Открыть" }).last().click();
  await page.waitForURL(/\/crm\/quotations\//);
  await expect(page.getByRole("heading", { name: /Расчёт КП/ })).toBeVisible();
}

/** Число из отформатированной денежной строки вида «1 234 567,89 ₽». */
export function parseMoney(text: string): number {
  return Number(text.replace(/[^\d,-]/g, "").replace(/\s/g, "").replace(",", "."));
}
