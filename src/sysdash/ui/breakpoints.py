from __future__ import annotations

from enum import Enum
from typing import Sequence, TypeVar

T = TypeVar("T")


class LayoutMode(str, Enum):
    """ターミナル幅に応じたダッシュボードのレイアウトモード。"""

    GRID = "grid"
    COLUMN = "column"
    COMPACT = "compact"


GRID_MIN_WIDTH = 100
COLUMN_MIN_WIDTH = 60
# サイドバー(幅34)をGRID_MIN_WIDTHのまま表示すると2x2グリッド領域が窮屈になるため、
# サイドバー表示にはより広い閾値を設ける(実測に基づく較正値)。
# 幅100〜119は「2x2グリッドだがサイドバー無し」、120以上でサイドバーも表示する。
SIDEBAR_MIN_WIDTH = 120
# 幅140以上ではサイドバーを44セル(コンテンツ40セル)へ拡大し、より精細なロゴを表示する。
SIDEBAR_WIDE_MIN_WIDTH = 140


def layout_mode_for_width(width: int) -> LayoutMode:
    """ターミナル幅からレイアウトモードを判定する純関数(Textualに依存しない)。

    - width >= GRID_MIN_WIDTH: 2x2グリッド(サイドバー表示可否はSIDEBAR_MIN_WIDTH別判定)
    - COLUMN_MIN_WIDTH <= width < GRID_MIN_WIDTH: 1カラム縦積み
    - width < COLUMN_MIN_WIDTH: コンパクト(数値のみ)
    """
    if width >= GRID_MIN_WIDTH:
        return LayoutMode.GRID
    if width >= COLUMN_MIN_WIDTH:
        return LayoutMode.COLUMN
    return LayoutMode.COMPACT


class SidebarDisplayMode(str, Enum):
    """ターミナル高さに応じたサイドバー(SystemInfoPanel)の表示段階。"""

    FULL = "full"  # ロゴ込みでフル表示
    INFO_ONLY = "info_only"  # ロゴを省略し情報のみ表示
    HIDDEN = "hidden"  # サイドバー自体を隠す


# ロゴ込みでクリップしない最小高さ(実測に基づく較正値)。
SIDEBAR_FULL_MIN_HEIGHT = 28
# ロゴを省略した場合の最小高さ(実測に基づく較正値)。
SIDEBAR_INFO_MIN_HEIGHT = 14


def sidebar_display_mode_for_height(height: int) -> SidebarDisplayMode:
    """ターミナル高さからサイドバーの表示段階を判定する純関数(Textualに依存しない)。

    - height >= SIDEBAR_FULL_MIN_HEIGHT: ロゴ込みフル表示
    - SIDEBAR_INFO_MIN_HEIGHT <= height < SIDEBAR_FULL_MIN_HEIGHT: ロゴ省略・情報のみ表示
    - height < SIDEBAR_INFO_MIN_HEIGHT: サイドバー自体を非表示
    """
    if height >= SIDEBAR_FULL_MIN_HEIGHT:
        return SidebarDisplayMode.FULL
    if height >= SIDEBAR_INFO_MIN_HEIGHT:
        return SidebarDisplayMode.INFO_ONLY
    return SidebarDisplayMode.HIDDEN


def grid_dimensions(count: int) -> tuple[int, int]:
    """パネル数から空セルの出ないgrid-size(列数, 行数)を算出する純関数。"""
    if count <= 1:
        return (1, 1)
    if count == 2:
        return (2, 1)
    if count == 3:
        return (3, 1)
    if count == 4:
        return (2, 2)
    return (count, 1)


CORE_COLUMN_MIN_WIDTH = 24


def columns_for_width(width: int, min_column_width: int = CORE_COLUMN_MIN_WIDTH) -> int:
    """幅からCPUコア別バー等を並べる列数を算出する純関数(最低1列)。"""
    return max(1, width // min_column_width)


def chunk_into_columns(items: Sequence[T], columns: int) -> list[list[T]]:
    """itemsをcolumns個の列(列優先、各列は連続した範囲)に分配する純関数。"""
    if columns <= 1 or not items:
        return [list(items)]
    per_column = -(-len(items) // columns)  # ceil division
    return [list(items[i : i + per_column]) for i in range(0, len(items), per_column)]


def truncate_for_grid(items: Sequence[T], columns: int, available_height: int) -> tuple[list[T], int]:
    """columns列×available_height行の枠に収まるようitemsを切り詰める純関数。

    枠に収まらない場合は、最後の1マスを省略サマリ表示用に空けて切り詰める。
    戻り値は (表示するitems, 省略した件数) で、省略件数>0のときだけ切り詰めが発生している。
    """
    capacity = max(columns, 0) * max(available_height, 0)
    if len(items) <= capacity:
        return list(items), 0
    visible_capacity = max(capacity - 1, 0)  # 省略サマリ用に1マス予約
    return list(items[:visible_capacity]), len(items) - visible_capacity
