import { expect, type Page } from "@playwright/test";

// Ролевые учётки демо-набора приложения — `manage.py seed_demo`
// (src/analytics/management/commands/seed_demo.py, DEMO_PASSWORD).
export const DEMO_PASSWORD = "demo12345";
export const HEAD_EMAIL = "morozov@npk-prod.local"; // начальник производства
export const MANAGER_EMAIL = "ivanov@npk-prod.local"; // менеджер проекта

export async function loginAs(page: Page, email: string, password = DEMO_PASSWORD): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  // Сабмит до прогрева cookie `csrftoken` Django отклонит (см. helpers.ts::login).
  await expect
    .poll(async () => (await page.context().cookies()).some((c) => c.name === "csrftoken"), { timeout: 10_000 })
    .toBe(true);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

export async function openBoard(page: Page): Promise<void> {
  await page.goto("/board");
  await expect(page.getByTestId("board")).toBeVisible({ timeout: 30_000 });
}
