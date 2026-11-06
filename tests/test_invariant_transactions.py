"""И3: транзакции открываются только в services/ (CLAUDE.md §3).

Ищет реальные вызовы/использования `transaction.atomic` по AST, а не по тексту —
так упоминание `transaction.atomic()` в докстроке или сообщении об ошибке (например,
в `core/events/publisher.py`, который обязан объяснить пользователю, что вызывается
вне неё) не даёт ложного срабатывания.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _open_atomic(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "atomic"):
            continue
        value = node.value
        if isinstance(value, ast.Name) and value.id == "transaction":
            return True
        if isinstance(value, ast.Attribute) and value.attr == "transaction":
            return True
    return False


def test_транзакции_открываются_только_в_сервисах() -> None:
    нарушения = []
    for path in SRC.rglob("*.py"):
        posix = path.as_posix()
        if "/services/" in posix or "/tests/" in posix or "/migrations/" in posix:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _open_atomic(tree):
            нарушения.append(posix)

    assert not нарушения, f"transaction.atomic вне services: {нарушения}"
