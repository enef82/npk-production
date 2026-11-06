import { defineConfig } from "orval";

// Вход — openapi.json в корне репозитория, экспортируется первым шагом `make api`
// (manage.py export_openapi_schema). Пути в схеме уже содержат полный префикс
// /api/v1/..., поэтому baseUrl не задаётся — сгенерированные вызовы идут
// относительными путями, которые Next.js проксирует на Django (next.config.ts).
export default defineConfig({
  isErp: {
    input: {
      target: "../openapi.json",
    },
    output: {
      target: "./lib/api/endpoints.ts",
      client: "react-query",
      httpClient: "fetch",
      mode: "single",
      clean: false,
      override: {
        mutator: {
          path: "./lib/api/mutator.ts",
          name: "customFetch",
        },
        // Мутатор возвращает уже распарсенное тело ответа (см. mutator.ts), а не
        // {data, status, headers} — отключаем обёртку, иначе сгенерированные типы
        // не совпадают с тем, что реально возвращает customFetch в рантайме.
        fetch: {
          includeHttpResponseReturnType: false,
        },
      },
    },
  },
  isErpZod: {
    input: {
      target: "../openapi.json",
    },
    output: {
      target: "./lib/api/schemas.ts",
      client: "zod",
      mode: "single",
      clean: false,
    },
  },
});
