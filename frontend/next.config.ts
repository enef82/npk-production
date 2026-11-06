import type { NextConfig } from "next";

// Django слушает на localhost:8000 в dev (docker-compose `web`) и на `web:8000` изнутри
// docker-сети фронтенда. Проксируем /api/* через сам Next.js — браузер видит всё как
// same-origin, сессионная cookie Django работает без CORS и без ослабления SameSite.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

// Найдено отладкой 05.09: приложение файла > 10 МБ к заявке отдавало голую
// «Internal Server Error» через ~30 с, ничего не попадало ни в лог Django, ни в
// хранилище. Причина — не в Django и не в MinIO: `rewrites()` ниже проксирует
// `/api/*` через встроенный прокси Next.js (`next/dist/server/lib/router-utils/
// proxy-request.js`), а для этого Next клонирует тело запроса
// (`next-server.js::attachRequestMeta`, безусловно для любого не-GET/HEAD запроса —
// не только под middleware, хотя матчер `middleware.ts` и исключает `/api`).
// Клон режется по `experimental.middlewareClientMaxBodySize` — умолчание Next
// **10 МБ** (`server/config-shared.js`); при превышении клонированный поток обрубается
// молча (`console.warn`, без исключения), Django получает тело короче заявленного
// `Content-Length` и зависает на дочитывании, а `http-proxy` рвёт соединение своим
// умолчанием `proxyTimeout` **30000 мс** (`proxy-request.js`) — в этот момент и
// рождается «Internal Server Error», это текст самого Next, не ответ Django.
// Подтверждено эмпирически: 9 МБ через прокси проходит меньше чем за секунду, 11 МБ —
// висит ровно 30 с и падает; напрямую в Django (минуя :3001) 16 МБ проходит за 0,44 с.
//
// Оба порога — свойства прокси-слоя Next, не бизнес-правило, но обязаны быть не
// меньше объявленного предела вложения заявки (`INQUIRY_ATTACHMENT_MAX_SIZE_BYTES`,
// `src/crm/services/attachments.py`, сейчас 50 МБ) — иначе объявленный предел
// недостижим независимо от того, что скажет Django. Запас — не впритык к 50 МБ:
// multipart-конверт (границы, заголовки полей) добавляет не учтённые здесь байты.
// `proxyTimeout` поднят так же: 50 МБ по посредственному офисному каналу (~10 Мбит/с)
// сами по себе занимают около 40 с — дольше умолчания в 30 с, ещё до всякого клонирования.
const MAX_UPLOAD_BYTES = 60 * 1024 * 1024; // с запасом над лимитом вложения заявки
const PROXY_TIMEOUT_MS = 5 * 60 * 1000; // с запасом над временем загрузки 50 МБ на медленном канале

const nextConfig: NextConfig = {
  // Прод-контур (docs/adr/0029-prod-kontur.md, часть C): standalone-выход собирает
  // минимальный набор файлов и зависимостей для `node server.js` без node_modules
  // всего проекта — то, что копирует `frontend/Dockerfile` во финальный слой образа.
  output: "standalone",
  experimental: {
    middlewareClientMaxBodySize: MAX_UPLOAD_BYTES,
    proxyTimeout: PROXY_TIMEOUT_MS,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
