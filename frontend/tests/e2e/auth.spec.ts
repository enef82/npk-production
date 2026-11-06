import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test("test_вход_и_выход", async ({ page }) => {
  await login(page);
  await expect(page.getByText("Администратор")).toBeVisible();

  await page.getByRole("button", { name: /Администратор/ }).click();
  await page.getByRole("menuitem", { name: "Выйти" }).click();

  await page.waitForURL(/\/login/);
  await expect(page.locator("#email")).toBeVisible();
});

test("test_неавторизованный_редиректится_на_вход", async ({ page }) => {
  await page.goto("/parties");

  await page.waitForURL(/\/login/);
  await expect(page.locator("#email")).toBeVisible();
});
