"""Роли — это Django Group, отдельной модели Role нет. Заводятся в сиде.

`SEED_GROUP_PERMISSIONS` ниже — единственный источник правды о том, какие прикладные
права (`has_perm`) привязаны к роли, а не один из нескольких. Членство в роли проверяют
`is_*`-предикаты чистым запросом по `groups`, а вот `can_*`-предикаты
спрашивают `user.has_perm(...)`.

Применяет карту `post_migrate`-приёмник (`signals.sync_group_permissions`, подключён
в `apps.AccountsConfig.ready`) через `group.permissions.set(...)` — **перезатирает**,
не дополняет: на каждом `manage.py migrate` состав прав группы становится ровно тем,
что здесь написано, независимо от того, что было в базе. Ручная правка через
Django Admin не переживает деплой, и виджет прав на странице группы поэтому только
для чтения (`core.accounts.admin.GroupAdmin`) — иначе он принимал бы клик, который
на следующем деплое молча откатится.

**Карта обязана называть каждую роль из `SEED_GROUP_NAMES`, даже пустым набором.**
Не назвать роль — не «оставить как решит админ», а дать `sync_group_permissions`
не знать о ней вовсе и не тронуть то, что накопилось в базе снаружи карты. Пустой
набор — явное «прав нет», а не отсутствие мнения.

Отвергнутая альтернатива — реестр уже выданных пар (роль, право), синхронизация
только для новых. Отклонено: состояние прав перестало бы быть определимым из
репозитория — часть источника жила бы только в базе конкретного окружения, уезжала
бы с ней при переносе на новый сервер и восстановлении из бэкапа, и правки прав было
бы не видно в ревью, потому что они происходят кликом, а не коммитом."""

ADMINISTRATOR = "администратор"
PROJECT_MANAGER = "менеджер проекта"
ESTIMATOR = "экономист-сметчик"
DESIGNER = "конструктор"
TECHNOLOGIST = "технолог"
PROCUREMENT_OFFICER = "снабженец"
PRODUCTION_HEAD = "начальник производства"
WAREHOUSE_HEAD = "начальник склада"
FOREMAN = "мастер участка"
QC_ENGINEER = "инженер ОТК"
POWER_ENGINEER = "энергетик"
OBSERVER = "наблюдатель"

SEED_GROUP_NAMES = (
    ADMINISTRATOR,
    PROJECT_MANAGER,
    ESTIMATOR,
    DESIGNER,
    TECHNOLOGIST,
    PROCUREMENT_OFFICER,
    PRODUCTION_HEAD,
    WAREHOUSE_HEAD,
    FOREMAN,
    QC_ENGINEER,
    POWER_ENGINEER,
    OBSERVER,
)

# {роль: (`<app_label>.<codename>`, …)}. Строки, а не импорт моделей: `core.accounts`
# лежит выше прикладных модулей по слоевому контракту. Состав — матрица прав
# `docs/spec/00-prilozhenie-proizvodstvo.md` §4.
#
# Каждая роль из `SEED_GROUP_NAMES` названа явно, даже пустым набором — карта
# перезатирает (`group.permissions.set(...)`), и роль, не упомянутая здесь вовсе,
# осталась бы вне синхронизации (см. докстринг модуля).
SEED_GROUP_PERMISSIONS: dict[str, tuple[str, ...]] = {
    ADMINISTRATOR: (),
    PROJECT_MANAGER: (),
    ESTIMATOR: ("timesheet.approve_period",),
    DESIGNER: (),
    TECHNOLOGIST: (),
    PROCUREMENT_OFFICER: (),
    PRODUCTION_HEAD: ("equipment.manage_equipment", "timesheet.edit_any"),
    WAREHOUSE_HEAD: (),
    FOREMAN: ("equipment.log_runtime", "timesheet.edit_department"),
    QC_ENGINEER: (),
    POWER_ENGINEER: ("energy.manage_meters",),
    OBSERVER: (),
}
