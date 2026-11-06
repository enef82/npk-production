"""Обход дерева подразделений рекурсивным CTE (selectors.list_department_and_descendant_ids)."""

import pytest

from src.core.org.selectors import list_department_and_descendant_ids
from src.core.org.tests.factories import DepartmentFactory


@pytest.mark.django_db
def test_обход_дерева_подразделений_возвращает_себя_и_всех_потомков() -> None:
    root = DepartmentFactory()
    child = DepartmentFactory(parent=root, legal_entity=root.legal_entity)
    grandchild = DepartmentFactory(parent=child, legal_entity=root.legal_entity)
    сосед = DepartmentFactory(legal_entity=root.legal_entity)

    ids = set(list_department_and_descendant_ids(root.id))  # type: ignore[attr-defined]

    assert ids == {root.id, child.id, grandchild.id}  # type: ignore[attr-defined]
    assert сосед.id not in ids  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_обход_дерева_подразделений_для_листа_возвращает_только_себя() -> None:
    root = DepartmentFactory()
    leaf = DepartmentFactory(parent=root, legal_entity=root.legal_entity)

    assert list_department_and_descendant_ids(leaf.id) == [leaf.id]  # type: ignore[attr-defined]
