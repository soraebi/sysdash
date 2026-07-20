from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Sparkline, Static

from sysdash.ui.breakpoints import chunk_into_columns, columns_for_width, truncate_for_grid

BAR_WIDTH = 20
NA_TEXT = "N/A"
SPARKLINE_POINTS = 40
SPARKLINE_AREA_HEIGHT = 2  # #sparkline の height:1 + margin-top:1


@dataclass(frozen=True)
class MetricRow:
    """パネル内の1行分の表示情報。percent が None ならバー無しの行として描画する。"""

    label: str
    text: str
    percent: float | None = None


def render_bar(percent: float | None, width: int = BAR_WIDTH) -> str:
    """0-100の値からテキストベースのバーを描画する(percent が None なら空文字)。"""
    if percent is None:
        return ""
    clamped = max(0.0, min(100.0, percent))
    filled = round(width * clamped / 100)
    return "█" * filled + "░" * (width - filled)


class MetricPanel(Vertical, can_focus=True):
    """CPU/メモリ/ディスク/ネットワーク共通のメトリクス表示パネル。

    行データは update_rows() で差し替える。compact=True の間はバーとミニSparklineを省略する。
    選択枠は Textual 標準のフォーカス(:focus)で表す。
    """

    DEFAULT_CSS = """
    MetricPanel {
        border: round $panel-lighten-2;
        padding: 0 1;
        height: 1fr;
        width: 1fr;
    }
    MetricPanel:focus {
        border: round $accent;
    }
    MetricPanel #rows {
        height: auto;
    }
    MetricPanel #sparkline {
        height: 1;
        margin-top: 1;
    }
    MetricPanel.-compact #sparkline {
        display: none;
    }
    """

    compact: reactive[bool] = reactive(False)
    rows: reactive[tuple[MetricRow, ...]] = reactive(())
    multi_column: reactive[bool] = reactive(False)

    def __init__(self, title: str, **kwargs) -> None:
        # ラベル/値はcollector由来の外部文字列(NIC名等)のため、Textualマークアップとして解釈させない。
        super().__init__(markup=False, **kwargs)
        self.border_title = title

    def compose(self) -> ComposeResult:
        yield Static(id="rows", markup=False)
        yield Sparkline(id="sparkline")

    def on_mount(self) -> None:
        # watch_rowsは#rows未生成のタイミングでも発火しうるため、マウント後に取りこぼしを防ぐ
        self._render_rows()

    def on_resize(self, event) -> None:
        # 幅変化で複数列の列数が変わりうるため、次のupdate_*_rows()呼び出しを待たずに再計算する
        self._render_rows()

    def update_rows(self, rows: list[MetricRow]) -> None:
        self.multi_column = False
        self.rows = tuple(rows)

    def update_multi_column_rows(self, header_row: MetricRow, item_rows: list[MetricRow]) -> None:
        """先頭行(バー付き、単独表示)+残りを幅に応じた複数列(バー無し)で描画する(CPUのコア別行向け)。"""
        self.multi_column = True
        self.rows = (header_row, *item_rows)

    def update_sparkline(self, values: Sequence[float]) -> None:
        try:
            sparkline = self.query_one("#sparkline", Sparkline)
        except NoMatches:
            return
        sparkline.data = list(values[-SPARKLINE_POINTS:])

    def watch_rows(self, rows: tuple[MetricRow, ...]) -> None:
        self._render_rows()

    def watch_compact(self, compact: bool) -> None:
        self.set_class(compact, "-compact")
        self._render_rows()

    def watch_multi_column(self, multi_column: bool) -> None:
        self._render_rows()

    def _render_rows(self) -> None:
        try:
            rows_widget = self.query_one("#rows", Static)
        except NoMatches:
            return
        if not self.rows:
            rows_widget.update("…")
            return
        if self.multi_column and not self.compact:
            if self.size.width == 0:
                # マウント直後等、レイアウト確定前でサイズ未確定(0)のときに列数を計算すると
                # 全コアが省略サマリ化して一瞬ちらつくため、確定後のresize/次tickに委ねる
                return
            text = self._render_multi_column()
        else:
            text = self._render_single_column(self.rows)
        rows_widget.update(text)

    def _render_single_column(self, rows: tuple[MetricRow, ...]) -> str:
        lines: list[str] = []
        for row in rows:
            lines.append(f"{row.label}: {row.text}")
            if not self.compact and row.percent is not None:
                lines.append(f"  {render_bar(row.percent)}")
        return "\n".join(lines)

    def _render_multi_column(self) -> str:
        header, *items = self.rows
        lines = [f"{header.label}: {header.text}"]
        if header.percent is not None:
            lines.append(f"  {render_bar(header.percent)}")

        item_lines = [f"{item.label}: {item.text}" for item in items]
        # self.sizeはpadding/borderを除いた実効コンテンツ幅を返す
        columns = columns_for_width(self.size.width)
        column_width = max(self.size.width // columns, 1)

        # このメソッドはcompact=False時のみ呼ばれる(_render_rows参照)ため、ミニSparkline領域
        # (height:1+margin-top:1)が常に表示分の高さを占める。差し引かないとコア表示が伸びすぎて
        # Sparklineがパネル外にクリップされる。
        available_height = max(self.size.height - len(lines) - SPARKLINE_AREA_HEIGHT, 1)
        visible_lines, omitted = truncate_for_grid(item_lines, columns, available_height)
        if omitted:
            visible_lines.append(f"+{omitted} cores")

        columns_data = chunk_into_columns(visible_lines, columns)
        row_count = max((len(column) for column in columns_data), default=0)
        for row_index in range(row_count):
            cells = [
                _fit_cell(column[row_index], column_width) if row_index < len(column) else ""
                for column in columns_data
            ]
            lines.append("".join(cells).rstrip())
        return "\n".join(lines)


def _fit_cell(text: str, width: int) -> str:
    """textを列幅ちょうどに切り詰め/パディングする(長いラベルが隣の列を侵食しないように)。"""
    return text[:width].ljust(width)
