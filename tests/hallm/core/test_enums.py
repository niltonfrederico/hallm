"""Unit tests for hallm.core.enums."""

from hallm.core.enums import WorkTypes


def test_work_types_are_strings() -> None:
    assert WorkTypes.BOOK == "book"
    assert WorkTypes.POEM == "poem"


def test_work_types_membership() -> None:
    assert "book" in {wt.value for wt in WorkTypes}
    assert "video" in {wt.value for wt in WorkTypes}


def test_work_types_count() -> None:
    assert len(list(WorkTypes)) == 9
