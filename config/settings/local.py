"""Настройки для локальной разработки."""

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, env

DEBUG = env.bool("DEBUG", default=True)

INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]

# Next.js в dev проксирует /api/* на этот сервер (frontend/next.config.ts, порт фиксирован
# в frontend/package.json на 3001 — 3000 в этом docker-compose.yml уже занят gotenberg) —
# браузер думает, что говорит с localhost:3001, а Django видит запрос на localhost:8000
# (порт, на котором реально принято соединение после прокси). Origin и Host расходятся.
# django-ninja сам глобально помечает свои эндпоинты `csrf_exempt` на уровне Django и
# проверяет CSRF вручную только для эндпоинтов с cookie-based auth (`ninja.security.
# apikey.APIKeyCookie.authenticate` → `check_csrf` → тот же `CsrfViewMiddleware`,
# просто вызванный не автоматически всем стеком, а точечно) — именно поэтому
# `/accounts/login` (auth=None) проходит без этой настройки, а `POST /identity/parties`
# (auth=django_auth) без неё отклоняется как межсайтовый запрос. CORS тут ни при чём,
# cookie остаётся видна фронтенду как same-origin именно благодаря прокси.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:3001"])
