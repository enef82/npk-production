from uuid6 import uuid7


def test_uuid7_монотонно_возрастает() -> None:
    ids = [uuid7() for _ in range(50)]

    assert ids == sorted(ids)
