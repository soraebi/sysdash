import pytest

from sysdash.ui.breakpoints import (
    COLUMN_MIN_WIDTH,
    CORE_COLUMN_MIN_WIDTH,
    GRID_MIN_WIDTH,
    LayoutMode,
    chunk_into_columns,
    columns_for_width,
    grid_dimensions,
    layout_mode_for_width,
    truncate_for_grid,
)


@pytest.mark.parametrize(
    ("width", "expected"),
    [
        (GRID_MIN_WIDTH, LayoutMode.GRID),
        (GRID_MIN_WIDTH + 50, LayoutMode.GRID),
        (GRID_MIN_WIDTH - 1, LayoutMode.COLUMN),
        (COLUMN_MIN_WIDTH, LayoutMode.COLUMN),
        (COLUMN_MIN_WIDTH - 1, LayoutMode.COMPACT),
        (0, LayoutMode.COMPACT),
    ],
)
def test_layout_mode_for_width(width: int, expected: LayoutMode) -> None:
    assert layout_mode_for_width(width) is expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, (1, 1)),
        (1, (1, 1)),
        (2, (2, 1)),
        (3, (3, 1)),
        (4, (2, 2)),
        (5, (5, 1)),
    ],
)
def test_grid_dimensions_leaves_no_empty_cells(count: int, expected: tuple[int, int]) -> None:
    columns, rows = grid_dimensions(count)
    assert (columns, rows) == expected
    assert columns * rows == max(count, 1)


@pytest.mark.parametrize(
    ("width", "expected"),
    [
        (0, 1),
        (23, 1),
        (CORE_COLUMN_MIN_WIDTH, 1),
        (CORE_COLUMN_MIN_WIDTH * 2 - 1, 1),
        (CORE_COLUMN_MIN_WIDTH * 2, 2),
        (CORE_COLUMN_MIN_WIDTH * 5, 5),
    ],
)
def test_columns_for_width(width: int, expected: int) -> None:
    assert columns_for_width(width) == expected


def test_columns_for_width_respects_custom_min_column_width() -> None:
    assert columns_for_width(100, min_column_width=50) == 2


def test_chunk_into_columns_single_column_when_columns_is_one() -> None:
    assert chunk_into_columns(["a", "b", "c"], 1) == [["a", "b", "c"]]


def test_chunk_into_columns_empty_items_returns_one_empty_column() -> None:
    assert chunk_into_columns([], 3) == [[]]


def test_chunk_into_columns_splits_evenly() -> None:
    assert chunk_into_columns(list(range(6)), 3) == [[0, 1], [2, 3], [4, 5]]


def test_chunk_into_columns_uneven_split_uses_ceil_division() -> None:
    # 7件を3列に分けると各列3件+最終列1件(ceil(7/3)=3件ずつ、余りは最終列)
    assert chunk_into_columns(list(range(7)), 3) == [[0, 1, 2], [3, 4, 5], [6]]


def test_chunk_into_columns_more_columns_than_items() -> None:
    result = chunk_into_columns([0, 1], 5)
    # 空リストが混ざらないよう、実際に埋まる列数だけ返る
    assert all(column for column in result)
    assert sum(len(column) for column in result) == 2


def test_truncate_for_grid_no_truncation_when_it_fits() -> None:
    items = list(range(6))
    visible, omitted = truncate_for_grid(items, columns=2, available_height=3)  # capacity=6
    assert visible == items
    assert omitted == 0


def test_truncate_for_grid_truncates_and_reserves_last_slot_for_summary() -> None:
    # 32コア/2列/高さ14相当(Sol実測のoverflowシナリオ): capacity=28、末尾1マスを省略サマリ用に予約
    items = list(range(32))
    visible, omitted = truncate_for_grid(items, columns=2, available_height=14)
    assert len(visible) == 27  # capacity(28) - 1
    assert visible == items[:27]
    assert omitted == 32 - 27


def test_truncate_for_grid_zero_capacity_omits_everything() -> None:
    items = list(range(5))
    visible, omitted = truncate_for_grid(items, columns=1, available_height=0)
    assert visible == []
    assert omitted == 5
