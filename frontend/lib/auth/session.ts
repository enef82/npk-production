import { cookies } from "next/headers";

import type { MeOut } from "@/lib/api/endpoints";

// Серверный компонент обращается к Django напрямую (не через rewrite /api/* —
// тот существует для браузера, здесь мы уже на сервере Next.js), перекладывая
// cookie входящего запроса вручную — у fetch на сервере нет доступа к cookie jar браузера.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

export async function getSession(): Promise<MeOut | null> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();
  if (!cookieHeader) return null;

  // X-Forwarded-Proto: https — без него SECURE_SSL_REDIRECT на бою отвечает 301
  // на https://web:8000/..., а `web` HTTPS не слушает вовсе: обычный fetch()
  // следует за редиректом и виснет на TLS-хендшейке с сервером, который его не
  // ведёт (UND_ERR_CONNECT_TIMEOUT). Тот же класс дефекта, что и с healthcheck
  // web-контейнера (docker-compose.prod.yml) — там это решено тем же заголовком
  // в самой команде проверки; здесь Caddy тоже не участвует и не может
  // подставить его сам, запрос идёт напрямую на web:8000.
  const response = await fetch(`${BACKEND_ORIGIN}/api/v1/accounts/me`, {
    headers: { cookie: cookieHeader, "X-Forwarded-Proto": "https" },
    cache: "no-store",
  });

  if (!response.ok) return null;
  return (await response.json()) as MeOut;
}
