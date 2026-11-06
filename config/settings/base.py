"""Базовые настройки Django, общие для всех окружений."""

from celery.schedules import crontab

from .env import BASE_DIR, build_database_config
from .env import env as env

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "ninja",
    "rules",
    "pgtrigger",
    "pghistory",
    "src.core.identity",
    "src.core.org",
    "src.core.accounts",
    "src.core.documents",
    "src.core.events",
    "src.core.numbering",
    "src.core.notifications",
    "src.sales",
    "src.production",
    "src.quality",
    "src.supply",
    "src.timesheet",
    "src.equipment",
    "src.energy",
    "src.analytics",
    # Ограничение частоты попыток входа (docs/adr/0030-publikatsiya-v-internet.md,
    # мера 1). Последним в INSTALLED_APPS — по образцу собственной документации axes.
    "axes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Прикрепляет пользователя текущего запроса как actor к записям истории
    # pghistory (core.audit) — должен идти после AuthenticationMiddleware,
    # чтобы request.user уже был определён.
    "pghistory.middleware.HistoryMiddleware",
    # Последним, как требует документация django-axes — должен видеть финальный
    # ответ остальных middleware, чтобы подменить его на 429 при блокировке.
    "axes.middleware.AxesMiddleware",
]

AUTH_USER_MODEL = "core_accounts.User"

AUTHENTICATION_BACKENDS = [
    # Первым — должен успеть отказать до ModelBackend/ObjectPermissionBackend,
    # иначе проверка блокировки не сработает (django-axes: AxesBackend всегда первый).
    "axes.backends.AxesBackend",
    "rules.permissions.ObjectPermissionBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Ограничение частоты попыток входа (docs/adr/0030-publikatsiya-v-internet.md, мера 1).
# Порог и окно — в настройках, не в коде: заказчик решил добавить зависимость 18.09,
# значения по умолчанию — не его решение, только разумный старт, можно поднять через env
# без правки кода.
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
# Связка «учётная запись + адрес» — вложенный список означает "И", не "ИЛИ" (axes/conf.py):
# один IP, перебирающий много логинов, не блокирует эти логины друг за друга, и наоборот.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
# `login_view` (core.accounts.api.routers) вызывает authenticate(request,
# username=data.email, ...) — то же соглашение, что и весь остальной проект
# (core.accounts.signals.log_failed_login тоже читает credentials["username"]),
# несмотря на то что реальное поле модели называется email (USERNAME_FIELD).
# Умолчание axes — AXES_USERNAME_FORM_FIELD = USERNAME_FIELD = "email" — ищет
# ключ "email" в credentials, которого там нет (Django формирует credentials из
# фактических имён kwarg'ов, не из USERNAME_FIELD), и тихо пишет username=None
# в AccessAttempt: блокировка при этом никогда не срабатывает, потому что связка
# «логин + адрес» не совпадает ни с чем. Проверено эмпирически — без этой строки
# AccessAttempt.username оставался None, и попытка после лимита проходила.
AXES_USERNAME_FORM_FIELD = "username"
AXES_COOLOFF_TIME = env.float("AXES_COOLOFF_TIME_HOURS", default=1.0)
AXES_RESET_ON_SUCCESS = True
# Умолчание django-ipware смотрит только на REMOTE_ADDR (безопасный дефолт без
# доверенного прокси) — за Caddy это всегда адрес самого Caddy, не клиента.
# Проверено эмпирически: без этой строки get_client_ip_address возвращал 127.0.0.1
# для любого X-Forwarded-For. AXES_IPWARE_PROXY_COUNT здесь не нужен — Caddy
# единственный прокси и передаёт ровно один адрес, "left-most" (умолчание
# AXES_IPWARE_PROXY_ORDER) берёт его напрямую, тот же приём, что и в
# core.accounts.signals._client_ip.
AXES_IPWARE_META_PRECEDENCE_ORDER = ("HTTP_X_FORWARDED_FOR", "REMOTE_ADDR")

# django-unfold: тема и русификация админки (шаг 9). Боковое меню намеренно не
# переопределяется через UNFOLD["SIDEBAR"]["navigation"] — дефолтная группировка
# unfold по Django-приложению (AppConfig.verbose_name) уже даёт «меню по модулям»
# бесплатно, поскольку в этой архитектуре приложение и есть модуль.
UNFOLD = {
    "SITE_TITLE": "НПК Производство",
    "SITE_HEADER": "НПК Производство",
    "DASHBOARD_CALLBACK": "config.dashboard.dashboard_callback",
}

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # config/templates/admin/index.html — переопределение дашборда unfold
        # (DASHBOARD_CALLBACK кладёт kpi_cards в контекст, шаблон их рисует).
        "DIRS": [BASE_DIR / "config" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": build_database_config(env("DATABASE_URL")),
}

REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Europe/Moscow"

# Диспетчер outbox (src.core.events) — см. docs/events.md.
EVENTS_DISPATCH_BATCH_SIZE = env.int("EVENTS_DISPATCH_BATCH_SIZE", default=100)
EVENTS_MAX_ATTEMPTS = env.int("EVENTS_MAX_ATTEMPTS", default=5)
EVENTS_RETRY_BACKOFF_BASE_SECONDS = env.int("EVENTS_RETRY_BACKOFF_BASE_SECONDS", default=30)
EVENTS_RETRY_BACKOFF_MAX_SECONDS = env.int("EVENTS_RETRY_BACKOFF_MAX_SECONDS", default=3600)
EVENTS_DISPATCH_INTERVAL_SECONDS = env.float("EVENTS_DISPATCH_INTERVAL_SECONDS", default=5.0)

# core.notifications: периодичность сборки дайджеста вместо потока однотипных уведомлений.
NOTIFICATIONS_DIGEST_INTERVAL_MINUTES = env.int("NOTIFICATIONS_DIGEST_INTERVAL_MINUTES", default=60)

# Часов в рабочей смене — единица перевода нормо-часов в дни графика.
HOURS_PER_SHIFT = 8

CELERY_BEAT_SCHEDULE = {
    "core_events-dispatch-pending": {
        "task": "core_events.dispatch_pending_events",
        "schedule": EVENTS_DISPATCH_INTERVAL_SECONDS,
        # Если пачка обрабатывается дольше интервала, Beat всё равно продолжит ставить
        # задачи каждые EVENTS_DISPATCH_INTERVAL_SECONDS. expires не чинит отставание
        # (для этого есть select_for_update(skip_locked=True) — параллельные тики
        # безопасны), но не даёт очереди копить бесполезные дубли: пришедшая с опозданием
        # задача не выполняется, а следующий тик всё равно подхватит те же необработанные
        # события — состояние в БД, а не в самой задаче.
        "options": {"expires": EVENTS_DISPATCH_INTERVAL_SECONDS},
    },
    "core_notifications-run-digest": {
        "task": "core_notifications.run_notification_digest",
        "schedule": NOTIFICATIONS_DIGEST_INTERVAL_MINUTES * 60,
    },
    # Файл вложения пишется в хранилище до транзакции,
    # откат оставляет объект без Document — осиротевшие объекты убирает эта задача.
    "core_documents-sweep-orphaned-storage": {
        "task": "core_documents.sweep_orphaned_storage_objects",
        "schedule": crontab(hour=4, minute=30),
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="npk-prod")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
# MinIO не режет поддомены по бакету — без path-style адресации запросы уходят не туда.
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")
# boto3 требует непустой регион даже для MinIO; в проде — реальный регион Yandex Object Storage.
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="ru-central1")
# Явно False: без этого django-storages по умолчанию тихо перезаписывает объект с тем же
# именем. upload_to уже исключает коллизии (ключ включает UUID документа), это подстраховка.
AWS_S3_FILE_OVERWRITE = False

# core.documents: TTL временной подписанной ссылки на файл и адрес Gotenberg для DOCX→PDF
# (см. docs/adr/0008-docxtpl-i-gotenberg-dlya-generatsii-dokumentov.md).
DOCUMENTS_URL_TTL_SECONDS = env.int("DOCUMENTS_URL_TTL_SECONDS", default=900)
GOTENBERG_URL = env("GOTENBERG_URL", default="http://gotenberg:3000")

# Порог триграммного сходства для поиска дубликатов в ядре идентичности.
# Калибруется после первой выгрузки из 1С на реальных наименованиях
# (docs/spec/02-yadro-identichnosti.md, открытый вопрос №3).
IDENTITY_DEDUP_THRESHOLD = env.float("IDENTITY_DEDUP_THRESHOLD", default=0.4)

# django-ninja: курсорная пагинация по умолчанию для всех списочных эндпоинтов —
# устойчива к вставкам между страницами (docs/adr, шаг 9), в отличие от offset-пагинации.
NINJA_PAGINATION_CLASS = "ninja.pagination.CursorPagination"

# core.common.pagination.count_capped: порог, до которого списочные эндпоинты считают
# точное количество строк по запросу клиента (`with_total=1`). Больше — total=null,
# клиент показывает «более PAGINATION_TOTAL_CAP» вместо точного числа (шаг 10).
PAGINATION_TOTAL_CAP = env.int("PAGINATION_TOTAL_CAP", default=1000)
