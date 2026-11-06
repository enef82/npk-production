import { defineConfig, devices } from "@playwright/test";

// Backend (Django, :8000) не поднимается отсюда — предполагается уже запущенным
// (docker compose up postgres redis minio gotenberg web && make migrate && make seed
// && make seed_demo_vendor). webServer поднимает только Next.js, у которого dev-скрипт
// уже фиксирован на порту 3001 (frontend/package.json — 3000 в docker-compose.yml
// занят gotenberg, см. config/settings/local.py CSRF_TRUSTED_ORIGINS).
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false, // тесты делят один и тот же seed-набор контрагентов в БД
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3001",
    reuseExistingServer: true,
    // Холодный старт Next dev (turbopack) в CI бывает дольше 30 с.
    timeout: 120_000,
  },
});
