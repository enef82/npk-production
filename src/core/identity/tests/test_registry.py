"""Реестр (`registry.py`) не должен сам импортировать функциональные модули — они
регистрируют свои профили сами через `AppConfig.ready()` (см. `test_профиль_...`
в `src/procurement/tests/`, где `VendorProfile` уже виден в реестре без единого
импорта `src.procurement` внутри `core.identity`). Здесь достаточно прогнать
`lint-imports`, который проверяет это по всему дереву импортов, а не только
по `registry.py`.

Вызывается `importlinter.cli.lint_imports()` напрямую в процессе теста, а не через
`subprocess.run(["lint-imports"])` — см. докстринг аналогичного теста в
`core.events.tests.test_registry`: бинарник ищется в `PATH`, который зависит от способа
запуска pytest, и подмена на прямой вызов делает результат от него не зависящим.
"""

from importlinter.cli import lint_imports


def test_реестр_профилей_не_нарушает_границы() -> None:
    assert lint_imports() == 0, "import-linter нашёл нарушение границ — см. вывод выше"
