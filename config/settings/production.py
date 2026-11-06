"""Настройки для продакшена."""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

# Полный список того, кто обращается к `web` и под каким Host — составлен один
# раз и целиком (чек-лист прод-перехода ИС, К2), а не по мере отказов:
#
#   Браузер снаружи                          ee3.kt96.ru (из .env, уже в ALLOWED_HOSTS)
#   Caddy → web (reverse_proxy)               исходный Host клиента, не переписывается
#                                              Caddy — всегда ee3.kt96.ru для настоящих
#                                              запросов, отдельной записи не требует
#   Next.js при SSR → web (lib/auth/session.ts, BACKEND_ORIGIN)   web:8000
#   Docker healthcheck внутри контейнера `web`                     localhost:8000
#   Celery/cron/скрипты внутри сети                     нет HTTP-вызовов к web
#                                                         на 18.09 (проверено grep’ом
#                                                         по src/**/tasks.py) — если
#                                                         появятся, добавить сюда
#                                                         и в тест ниже
#
# ALLOWED_HOSTS из .env на бою содержит только ee3.kt96.ru — без "localhost" и "web"
# оба внутренних вызова получали 400 DisallowedHost (оба воспроизвелись на бою
# 18.09: healthcheck и, отдельно, «страница входа виснет» — вход на бэкенде
# проходил, но серверная проверка сессии после него молча проваливалась). Порт
# 8000 наружу не публикуется (только Caddy выходит из docker-сети) — оба
# внутренних имени здесь недостижимы снаружи, расширение не ослабляет защиту.
#
# Тест на точный состав — tests/test_env.py — иначе следующая правка настроек
# молча выкинет одно из имён, и это найдётся не в тесте, а на боевом сервере.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "localhost", "web"]  # noqa: F405

# CSRF_TRUSTED_ORIGINS обязателен отдельно от ALLOWED_HOSTS — Django с Django 4+
# требует схему (https://), а не просто имя хоста; без него POST/login с формы
# на ee3.kt96.ru отклоняется CSRF-проверкой ещё до входа в view.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Caddy — единственный обратный прокси перед Django (ADR 0029) и уже передаёт
# X-Forwarded-Proto на всех запросах через reverse_proxy. SECURE_SSL_REDIRECT здесь
# не создаёт второй редирект поверх Caddy (который уже отвечает на :80 только
# редиректом на :443) — Django видит request.is_secure() == True благодаря
# SECURE_PROXY_SSL_HEADER ниже и просто не редиректит повторно. Без этого заголовка
# SECURE_SSL_REDIRECT=True за прокси даёт бесконечный редирект (Django считает
# соединение по HTTP и шлёт на HTTPS снова и снова).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# HSTS начинается с малого значения и поднимается только после того, как всё
# заработало на бою — час, не год (docs/adr/0030-publikatsiya-v-internet.md).
# `preload` не включается вовсе: это часовой список браузеров, откатить из него
# нельзя месяцами. `includeSubDomains` не включается: `kt96.ru` — не наш домен
# целиком, у него могут быть другие поддомены не под этой системой.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Ограничение частоты попыток входа (docs/adr/0030-publikatsiya-v-internet.md,
# мера 1) — реализовано в `base.py` (действует и в dev: перебор пароля стоит ловить
# тестами тоже, не только на бою). Разрешение на зависимость `django-axes` дано
# заказчиком 18.09.
