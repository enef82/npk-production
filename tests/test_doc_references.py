"""Ссылки на документы не должны расходиться с файлами на диске.

Третий случай одного класса дефектов в проекте:

1. цель линтера не покрывала папку, о которой все думали, что покрывает
   (корневой `tests` вне `mypy config src`, см. `docs/roadmap-faza-1.md`);
2. фикстура не действовала там, где её положили
   (`conftest` в подпапке вместо корня, см. `tests/test_conftest.py`);
3. **ссылки на документы в комментариях разошлись с переехавшими файлами.**

Общее у всех трёх — расхождение между написанным и существующим, которое ничто
не проверяет. Этот тест ходит по документам и коду, вытаскивает упоминания файлов
с расширением md и требует, чтобы файл существовал. Без базы.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"

# Путь к md-файлу: не внутри URL и не в середине другого пути (lookbehind отсекает
# `схема://…` и `каталог/файл`). Только ASCII — имена документов латинские, а `\w`
# в Python подхватил бы и кириллицу из окружающей прозы.
_REF = re.compile(r"(?<![\w:/])((?:docs/)?(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md)")

# Длинную ссылку иногда переносят по дефису на следующую строку (в т.ч. с префиксом
# комментария). Склеиваем обратно перед разбором — иначе половинка выглядит как
# отдельный битый файл.
_WRAP = re.compile(r"-\s*\n\s*(?:#\s*)?(?=[A-Za-z0-9_-]*\.md)")

_SCANNED = [
    *sorted(_DOCS.glob("**/*.md")),
    *sorted(_ROOT.glob("src/**/*.py")),
    *sorted(_ROOT.glob("config/**/*.py")),
    _ROOT / "CLAUDE.md",
    _ROOT / "conftest.py",
]


def _resolves(source: Path, ref: str) -> bool:
    """Ссылка валидна, если разрешается хоть одним способом: от корня репозитория
    (полный путь от `docs`), от каталога документов (короткая запись внутри `docs`)
    или относительно самого файла-источника."""

    bases = (_ROOT, _DOCS, source.parent)
    return any((base / ref).is_file() for base in bases)


_CASES: list[tuple[str, str]] = sorted(
    {
        (path.relative_to(_ROOT).as_posix(), ref)
        for path in _SCANNED
        if path.is_file()
        for ref in _REF.findall(_WRAP.sub("-", path.read_text(encoding="utf-8")))
    }
)


@pytest.mark.parametrize(
    ("source", "ref"),
    _CASES,
    ids=[f"{source}->{ref}" for source, ref in _CASES],
)
def test_ссылка_на_документ_ведёт_на_существующий_файл(source: str, ref: str) -> None:
    assert _resolves(_ROOT / source, ref), (
        f"{source}: ссылка на «{ref}» — такого файла нет "
        f"ни от корня репозитория, ни от каталога документов, ни рядом с источником"
    )


def test_есть_что_проверять() -> None:
    # Страховка: если регэксп или обход молча перестанут что-либо находить, все
    # параметризованные кейсы исчезнут и набор «пройдёт» вхолостую.
    assert len(_CASES) > 50
