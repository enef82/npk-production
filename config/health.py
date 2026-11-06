import redis
from django.conf import settings
from django.db import connections
from django.http import HttpRequest, HttpResponse, JsonResponse


def healthz(request: HttpRequest) -> HttpResponse:
    """Healthcheck для Caddy/compose (`depends_on: condition: service_healthy`),
    не для мониторинга (docs/adr/0029-prod-kontur.md, п. 4). Не обращается ни к БД,
    ни к Redis: проверяет только, что процесс gunicorn жив и отвечает. Готовность
    PostgreSQL и Redis проверяют их собственные healthcheck'и в docker-compose —
    дублировать её здесь означало бы, что временная просадка БД валит web из ротации
    вместе с ней, хотя сам процесс исправен. `/health/` (ниже) остаётся отдельным,
    более строгим эндпоинтом для ручной диагностики и внешнего мониторинга."""

    return HttpResponse("ok")


def _check_db() -> bool:
    try:
        connections["default"].ensure_connection()
    except Exception:
        return False
    return True


def _check_redis() -> bool:
    try:
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception:
        return False


def health_check(request: HttpRequest) -> JsonResponse:
    db_ok = _check_db()
    redis_ok = _check_redis()
    healthy = db_ok and redis_ok
    payload = {"status": "ok" if healthy else "error", "db": db_ok, "redis": redis_ok}
    return JsonResponse(payload, status=200 if healthy else 503)
