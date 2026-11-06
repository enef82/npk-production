"""Валидация формат-строки шаблона номера (docs/spec/03-platforma.md §4: `template`,
напр. `"ДГ-{year}-{seq:05d}"`) — чтобы опечатка ловилась при сохранении нумератора
в админке, а не при выпуске первого документа.

Чистая функция без обращений к БД и без транзакции — не `services/` (И3: services —
место транзакций, не общих утилит). Живёт на уровне модуля, а не под `models/` или
`services/`, специально: и `models.Numerator.clean()`, и `services.numerator.
create_numerator()` должны иметь возможность импортировать её напрямую, без риска
цикла через `services/__init__.py` (тот реэкспортирует всё содержимое `services/`,
а часть из этого содержимого сама импортирует `models`) — цикл здесь невозможен
по построению: этот модуль не зависит ни от `models`, ни от `services`.
"""

from __future__ import annotations

import string

from src.core.common.exceptions import ValidationError

KNOWN_PLACEHOLDERS = frozenset({"year", "month", "seq"})


def validate_numerator_template(template: str) -> None:
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValidationError(f"Некорректный шаблон номера: {exc}") from exc

    fields: set[str] = set()
    for _literal_text, field_name, _format_spec, _conversion in parsed:
        if field_name is None:
            continue
        if field_name == "":
            raise ValidationError(
                "Шаблон номера должен использовать именованные подстановки — не {}."
            )
        fields.add(field_name)

    unknown = fields - KNOWN_PLACEHOLDERS
    if unknown:
        raise ValidationError(
            f"Шаблон номера использует неизвестные подстановки: {', '.join(sorted(unknown))}. "
            f"Разрешены: {', '.join(sorted(KNOWN_PLACEHOLDERS))}."
        )

    if "seq" not in fields:
        raise ValidationError(
            "Шаблон номера обязан содержать подстановку {seq} — иначе номера не уникальны."
        )
