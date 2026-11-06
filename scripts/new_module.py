#!/usr/bin/env python3
"""Генератор скелета нового функционального модуля по шаблону раздела 4 CLAUDE.md.

Обычный скрипт, не management-команда Django: `core.common`, куда его изначально
предполагалось положить как `manage.py new_module`, не зарегистрирован в
`INSTALLED_APPS` (в нём нет `apps.py` — это пакет общих утилит, а не Django-приложение),
поэтому Django не нашёл бы команду там. Заводить `core.common` полноценным приложением
ради одной команды, которая не трогает ORM, избыточно (см.
`docs/adr/0001-shablon-modulya.md`, «Отвергнутая альтернатива»).

Использование:

    uv run python scripts/new_module.py crm "CRM"

Создаёт файловую структуру `src/<name>/` с докстрингами-заглушками — тем же составом,
что был у `procurement` до шага 11 (см. `docs/checklist-novyy-modul.md` для того, что
делать дальше руками: `INSTALLED_APPS`, `.importlinter`, модели, миграции и всё
остальное по чек-листу).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _docstring_file(text: str) -> str:
    return f'"""{text}"""\n'


def generate(name: str, verbose_name: str) -> Path:
    module_dir = SRC_ROOT / name

    _write(module_dir / "__init__.py", "")

    _write(
        module_dir / "apps.py",
        f'''from django.apps import AppConfig


class {name.title().replace("_", "")}Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.{name}"
    verbose_name = "{verbose_name}"
''',
    )

    _write(module_dir / "models" / "__init__.py", "")
    _write(module_dir / "migrations" / "__init__.py", "")

    _write(
        module_dir / "admin" / "__init__.py",
        _docstring_file(f"Админка модуля «{verbose_name}»."),
    )

    _write(module_dir / "api" / "__init__.py", "")
    _write(
        module_dir / "api" / "routers.py",
        _docstring_file(f"Эндпоинты django-ninja модуля «{verbose_name}»."),
    )
    _write(
        module_dir / "api" / "schemas.py",
        _docstring_file(f"Pydantic-схемы входа и выхода API модуля «{verbose_name}»."),
    )
    _write(
        module_dir / "api" / "filters.py",
        _docstring_file(f"Query-фильтры списочных эндпоинтов модуля «{verbose_name}»."),
    )

    _write(module_dir / "services" / "__init__.py", "")

    _write(
        module_dir / "selectors.py",
        _docstring_file(f"Запросы на чтение и агрегаты модуля «{verbose_name}»."),
    )
    _write(
        module_dir / "facade.py",
        _docstring_file(f"Публичный интерфейс модуля «{verbose_name}» для других модулей."),
    )
    _write(
        module_dir / "events.py",
        _docstring_file(
            f"События, которые публикует модуль «{verbose_name}». Каталог — `docs/events.md`."
        ),
    )
    _write(
        module_dir / "handlers.py",
        _docstring_file(f"Обработчики событий других модулей в «{verbose_name}»."),
    )
    _write(
        module_dir / "rules.py",
        _docstring_file(f"Предикаты прав доступа модуля «{verbose_name}» (django-rules)."),
    )
    _write(
        module_dir / "tasks.py",
        _docstring_file(
            f"Celery-задачи модуля «{verbose_name}»: только оркестрация, логика — в services."
        ),
    )

    _write(module_dir / "tests" / "__init__.py", "")
    _write(module_dir / "tests" / "factories.py", "")

    return module_dir


def _print_next_steps(name: str) -> None:
    print(f"\nСкелет src/{name}/ готов. Дальше — руками (docs/checklist-novyy-modul.md):\n")
    print(f'  1. Добавить "src.{name}" в INSTALLED_APPS (config/settings/base.py).')
    print(
        f"  2. Добавить контракт facade-{name} в .importlinter "
        "(скопировать блок facade-procurement, переименовать)."
    )
    print("  3. Прочитать спецификацию модуля в docs/spec/ и начать с моделей.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "name", help="Имя модуля: строчные латинские буквы, цифры, _ (например crm)"
    )
    parser.add_argument(
        "verbose_name", help="Человекочитаемое имя модуля по-русски (например «CRM»)"
    )
    args = parser.parse_args()

    if not NAME_RE.match(args.name):
        print(
            f"Ошибка: имя модуля {args.name!r} должно быть snake_case латиницей.",
            file=sys.stderr,
        )
        return 1

    module_dir = SRC_ROOT / args.name
    if module_dir.exists():
        print(f"Ошибка: {module_dir} уже существует.", file=sys.stderr)
        return 1

    generate(args.name, args.verbose_name)
    _print_next_steps(args.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
