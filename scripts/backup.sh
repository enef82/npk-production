#!/usr/bin/env bash
set -euo pipefail

# Бэкап прод-контура: PostgreSQL (pg_dump) + содержимое MinIO (mc mirror).
# docs/adr/0029-prod-kontur.md, п. 2; docs/vds-obkatka.md, «Бэкап».
#
# База без вложений бесполезна — в ней только ссылки на файлы в MinIO, поэтому
# оба артефакта пишутся вместе, в один каталог на снимок, и ротируются как единое
# целое: иначе можно получить дамп без соответствующего ему MinIO-снимка.
#
# Использование:
#   scripts/backup.sh [каталог-назначения]
#
# Каталог назначения — параметр, не зашитый путь: куда класть бэкап (NAS, второй
# компьютер, внешний диск, облако) решает заказчик, не эта команда.

DEST_ROOT="${1:-/opt/npk-prod/backups}"

if [ "$#" -eq 0 ]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: каталог назначения не указан явно, использую локальный ${DEST_ROOT}." >&2
  echo "Бэкап на том же диске, что и рабочие данные, защищает только от «удалили" >&2
  echo "запись» — не от отказа диска. Второй параметр — внешний каталог (NAS," >&2
  echo "внешний диск, точка монтирования облачного хранилища)." >&2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.prod.yml"

compose() { docker compose -f "${COMPOSE_FILE}" "$@"; }

# Значения читаются из уже запущенного контейнера `web` (`printenv`), не из .env
# через `source`: SECRET_KEY и подобные секреты по построению состоят из случайных
# символов, включая `(`, `)`, `&`, `*`, `%` — обычный shell-синтаксис, на котором
# наивный `source .env` падает («syntax error near unexpected token»). `web` уже
# получил все переменные через `env_file: .env` (docker-compose.prod.yml) — читаем
# готовое, а не парсим файл заново.
POSTGRES_USER="$(compose exec -T web printenv POSTGRES_USER)"
POSTGRES_DB="$(compose exec -T web printenv POSTGRES_DB)"
AWS_ACCESS_KEY_ID="$(compose exec -T web printenv AWS_ACCESS_KEY_ID)"
AWS_SECRET_ACCESS_KEY="$(compose exec -T web printenv AWS_SECRET_ACCESS_KEY)"
AWS_STORAGE_BUCKET_NAME="$(compose exec -T web printenv AWS_STORAGE_BUCKET_NAME || echo npk-prod)"

TODAY="$(date +%F)"          # 2026-09-17
MONTH="$(date +%Y-%m)"        # 2026-09
DAILY_DIR="${DEST_ROOT}/daily/${TODAY}"
MONTHLY_DIR="${DEST_ROOT}/monthly/${MONTH}"

mkdir -p "${DAILY_DIR}"

echo "==> pg_dump (custom format) -> ${DAILY_DIR}/postgres.dump"
compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER}" -Fc "${POSTGRES_DB}" > "${DAILY_DIR}/postgres.dump"

echo "==> mc mirror MinIO -> ${DAILY_DIR}/minio"
mkdir -p "${DAILY_DIR}/minio"
compose run --rm \
  -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
  -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
  -e AWS_STORAGE_BUCKET_NAME="${AWS_STORAGE_BUCKET_NAME}" \
  -v "${DAILY_DIR}/minio:/backup" \
  --entrypoint sh minio-init -c \
  'mc alias set local http://minio:9000 "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" \
   && mc mirror --overwrite "local/${AWS_STORAGE_BUCKET_NAME:-npk-prod}" /backup'

# Первый бэкап месяца становится месячным снимком — GFS-подобная схема без
# отдельного расписания: ежедневный cron решает и то, и другое.
if [ ! -d "${MONTHLY_DIR}" ]; then
  echo "==> первый бэкап месяца ${MONTH} -> копия в ${MONTHLY_DIR}"
  mkdir -p "$(dirname "${MONTHLY_DIR}")"
  cp -r "${DAILY_DIR}" "${MONTHLY_DIR}"
fi

# Ротация: 30 ежедневных, 12 ежемесячных (docs/vds-obkatka.md). Каталоги именованы
# датой/месяцем — сортировка по имени и есть сортировка по времени.
prune() {
  local dir="$1" keep="$2"
  local count
  count="$(find "${dir}" -mindepth 1 -maxdepth 1 -type d | wc -l)"
  if [ "${count}" -gt "${keep}" ]; then
    find "${dir}" -mindepth 1 -maxdepth 1 -type d | sort | head -n "$((count - keep))" \
      | while IFS= read -r old; do
          echo "==> ротация: удаляю ${old}"
          rm -rf "${old}"
        done
  fi
}

prune "${DEST_ROOT}/daily" 30
prune "${DEST_ROOT}/monthly" 12

echo "==> готово: ${DAILY_DIR}"

# Установка в cron — не этим скриптом (он делает бэкап, не администрирует cron) и не
# в этом задании (часть D — только локальная проверка контура, на сервер не
# выкатываем). Строка для crontab -e на сервере, на будущее:
#
#   0 3 * * * /opt/npk-prod/repo/scripts/backup.sh /mnt/backup-nas >> /var/log/npk-prod-backup.log 2>&1
