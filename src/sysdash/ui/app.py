from __future__ import annotations

import dataclasses
import platform
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import psutil
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingsMap
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from sysdash.collectors.base import Collector
from sysdash.core.history import DEFAULT_MAXLEN, HistoryStore, SeriesKey
from sysdash.core.i18n import t
from sysdash.core.models import MetricSample
from sysdash.core.sampler import Sampler
from sysdash.ui.breakpoints import (
    SIDEBAR_MIN_WIDTH,
    SIDEBAR_WIDE_MIN_WIDTH,
    LayoutMode,
    SidebarDisplayMode,
    grid_dimensions,
    layout_mode_for_width,
    sidebar_display_mode_for_height,
)
from sysdash.ui.graph_view import LineGraphView
from sysdash.ui.widgets.metric_panel import NA_TEXT, MetricPanel, MetricRow
from sysdash.ui.widgets.system_info import SystemInfo, SystemInfoPanel, blank_system_info, collect_system_info

RESIZE_DEBOUNCE = 0.5
GRAPH_HISTORY_POINTS = DEFAULT_MAXLEN  # HistoryStoreの既定件数をそのまま採用(定義を二重に持たない)
INTERVAL_STEP = 0.5

SeriesInfo = tuple[str, SeriesKey, str]  # (表示ラベル, 系列キー, 単位)

def panel_title(name: str) -> str:
    """collector名(cpu/memory/disk/network)から表示用パネルタイトルを引く。

    未知のnameはそのまま返す(以前のPANEL_TITLES.get(name, name)と同じフォールバック)。
    言語に依存するため呼び出しの都度t()経由で解決する(モジュールレベルの辞書には
    しない。BINDINGS同様、import時点の言語で固定されてしまうのを避けるため)。
    """
    key = f"panel.{name}"
    return t(key) if key in _PANEL_TITLE_KEYS else name


_PANEL_TITLE_KEYS = frozenset({"panel.cpu", "panel.memory", "panel.disk", "panel.network"})


def _localize_bindings(bindings_map: BindingsMap) -> None:
    """BINDINGSのdescription/group.descriptionに置いたi18nメッセージキーを、現在の言語の
    表示文言へ解決する。

    Textualの`Binding`はfrozen dataclassで、`BINDINGS`クラス属性はクラス定義(=モジュール
    import)時に評価されて`_merged_bindings`としてクラスにキャッシュされる。インスタンス化の
    たびに`self._bindings`へコピーされるが、コピーはdictの浅いコピーであり中の`Binding`
    オブジェクト自体はクラスキャッシュと共有されたままなので、直接書き換えるとテスト間で
    言語状態が伝染してしまう。そのため`dataclasses.replace()`で翻訳済みの新しい`Binding`
    (groupがあれば新しい`Binding.Group`も)を作り、`key_to_bindings`の値を新しいリストで
    丸ごと置き換える。呼び出し側(各Screen/Appの__init__)でインスタンス生成のたびに実行する
    ことで、翻訳が言語設定の時点(=インスタンス生成時点)を正しく反映する。
    """
    for key, bindings in list(bindings_map.key_to_bindings.items()):
        translated: list[Binding] = []
        for binding in bindings:
            new_group = (
                dataclasses.replace(binding.group, description=t(binding.group.description))
                if binding.group is not None
                else None
            )
            translated.append(dataclasses.replace(binding, description=t(binding.description), group=new_group))
        bindings_map.key_to_bindings[key] = translated

# 表示規約: 値欠損(collector側の項目単位失敗)は N/A、レート系列の初回サンプル/
# カウンタリセットで算出不能な場合は —。


def _fmt_percent(value: float | None) -> str:
    return NA_TEXT if value is None else f"{value:.1f}%"


def _humanize_bytes(value: float) -> str:
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units[:-1]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}{units[-1]}"


def _fmt_bytes(value: float | None) -> str:
    return NA_TEXT if value is None else _humanize_bytes(value)


def _fmt_rate(value: float | None) -> str:
    return "—" if value is None else f"{_humanize_bytes(value)}/s"


def _format_stat_value(value: float, unit: str) -> str:
    if unit == "bytes/s":
        return f"{_humanize_bytes(value)}/s"
    if unit == "%":
        return f"{value:.1f}%"
    return f"{value:.1f}{unit}"


def _build_cpu_rows(samples: list[MetricSample]) -> list[MetricRow]:
    total = next((s for s in samples if s.name == "cpu.total"), None)
    rows = [MetricRow("Total", _fmt_percent(total.value if total else None), total.value if total else None)]
    cores = sorted(
        (s for s in samples if s.name == "cpu.core"),
        key=lambda s: int(s.labels.get("core", "0")),
    )
    for core in cores:
        rows.append(MetricRow(f"Core {core.labels.get('core')}", _fmt_percent(core.value), core.value))
    return rows


def _build_memory_rows(samples: list[MetricSample]) -> list[MetricRow]:
    percent = next((s for s in samples if s.name == "memory.percent"), None)
    swap = next((s for s in samples if s.name == "memory.swap_percent"), None)
    used = next((s for s in samples if s.name == "memory.used"), None)
    total = next((s for s in samples if s.name == "memory.total"), None)

    percent_value = percent.value if percent else None
    # バーはvm.percent基準のまま、テキストにも(percent%)を併記する。usedの定義はOSにより
    # 解釈が異なりうる(例: macOSのused)ため、バーとテキストの基準を一致させて見かけの食い違いを避ける。
    used_text = (
        f"{_fmt_bytes(used.value if used else None)} / {_fmt_bytes(total.value if total else None)}"
        f" ({_fmt_percent(percent_value)})"
    )
    return [
        MetricRow("Used", used_text, percent_value),
        MetricRow("Swap", _fmt_percent(swap.value if swap else None), swap.value if swap else None),
    ]


def _build_disk_rows(samples: list[MetricSample]) -> list[MetricRow]:
    rows: list[MetricRow] = []
    usages = sorted(
        (s for s in samples if s.name == "disk.usage_percent"),
        key=lambda s: s.labels.get("mount", ""),
    )
    for usage in usages:
        mount = usage.labels.get("mount", "?")
        rows.append(MetricRow(mount, _fmt_percent(usage.value), usage.value))

    reads = {s.labels.get("disk", "?"): s.value for s in samples if s.name == "disk.read_rate"}
    writes = {s.labels.get("disk", "?"): s.value for s in samples if s.name == "disk.write_rate"}
    for disk_name in sorted(set(reads) | set(writes)):
        rows.append(
            MetricRow(
                f"{disk_name} R/W",
                f"{_fmt_rate(reads.get(disk_name))} / {_fmt_rate(writes.get(disk_name))}",
            )
        )
    return rows


def _build_network_rows(samples: list[MetricSample]) -> list[MetricRow]:
    sent = {s.labels.get("nic", "?"): s.value for s in samples if s.name == "network.sent_rate"}
    recv = {s.labels.get("nic", "?"): s.value for s in samples if s.name == "network.recv_rate"}
    rows: list[MetricRow] = []
    for nic_name in sorted(set(sent) | set(recv)):
        rows.append(
            MetricRow(
                nic_name,
                f"↑{_fmt_rate(sent.get(nic_name))} ↓{_fmt_rate(recv.get(nic_name))}",
            )
        )
    return rows


ROW_BUILDERS = {
    "cpu": _build_cpu_rows,
    "memory": _build_memory_rows,
    "disk": _build_disk_rows,
    "network": _build_network_rows,
}


def _cpu_series(samples: list[MetricSample]) -> list[SeriesInfo]:
    series: list[SeriesInfo] = []
    total = next((s for s in samples if s.name == "cpu.total"), None)
    if total is not None:
        series.append(("Total", total.series_key, total.unit))
    cores = sorted(
        (s for s in samples if s.name == "cpu.core"),
        key=lambda s: int(s.labels.get("core", "0")),
    )
    for core in cores:
        series.append((f"Core {core.labels.get('core')}", core.series_key, core.unit))
    return series


def _memory_series(samples: list[MetricSample]) -> list[SeriesInfo]:
    series: list[SeriesInfo] = []
    percent = next((s for s in samples if s.name == "memory.percent"), None)
    if percent is not None:
        series.append(("Used %", percent.series_key, percent.unit))
    swap = next((s for s in samples if s.name == "memory.swap_percent"), None)
    if swap is not None:
        series.append(("Swap %", swap.series_key, swap.unit))
    return series


def _disk_series(samples: list[MetricSample]) -> list[SeriesInfo]:
    series: list[SeriesInfo] = []
    for usage in sorted((s for s in samples if s.name == "disk.usage_percent"), key=lambda s: s.labels.get("mount", "")):
        series.append((f"{usage.labels.get('mount', '?')} Usage", usage.series_key, usage.unit))
    for read in sorted((s for s in samples if s.name == "disk.read_rate"), key=lambda s: s.labels.get("disk", "")):
        series.append((f"{read.labels.get('disk', '?')} Read", read.series_key, read.unit))
    for write in sorted((s for s in samples if s.name == "disk.write_rate"), key=lambda s: s.labels.get("disk", "")):
        series.append((f"{write.labels.get('disk', '?')} Write", write.series_key, write.unit))
    return series


def _network_series(samples: list[MetricSample]) -> list[SeriesInfo]:
    series: list[SeriesInfo] = []
    for sent in sorted((s for s in samples if s.name == "network.sent_rate"), key=lambda s: s.labels.get("nic", "")):
        series.append((f"{sent.labels.get('nic', '?')} Sent", sent.series_key, sent.unit))
    for recv in sorted((s for s in samples if s.name == "network.recv_rate"), key=lambda s: s.labels.get("nic", "")):
        series.append((f"{recv.labels.get('nic', '?')} Recv", recv.series_key, recv.unit))
    return series


SERIES_BUILDERS = {
    "cpu": _cpu_series,
    "memory": _memory_series,
    "disk": _disk_series,
    "network": _network_series,
}


@dataclass(frozen=True)
class GraphSeriesGroup:
    """グラフ画面で同時に描画する系列のまとまり。

    series は (ラベル, 系列キー) のタプルで、1件なら単系列(CPU/メモリ/ディスク使用率)、
    2件ならペア(ディスクR/W・ネットワーク送受信)として同じグラフに重ねて描画する。
    """

    title: str
    unit: str
    series: tuple[tuple[str, SeriesKey], ...]

    @property
    def key(self) -> tuple[SeriesKey, ...]:
        """選択中グループの追跡に使う一意なキー。titleは表示専用で一意性を保証しないため。"""
        return tuple(series_key for _, series_key in self.series)


def _single_group(label: str, key: SeriesKey, unit: str) -> GraphSeriesGroup:
    return GraphSeriesGroup(title=label, unit=unit, series=((label, key),))


def _cpu_graph_groups(samples: list[MetricSample]) -> list[GraphSeriesGroup]:
    return [_single_group(label, key, unit) for label, key, unit in _cpu_series(samples)]


def _memory_graph_groups(samples: list[MetricSample]) -> list[GraphSeriesGroup]:
    return [_single_group(label, key, unit) for label, key, unit in _memory_series(samples)]


def _disk_graph_groups(samples: list[MetricSample]) -> list[GraphSeriesGroup]:
    """ディスクのグラフ画面は各ディスクのRead/Write速度のみを対象にする(使用率は非対象)。

    ダッシュボードパネル内のマウント使用率表示・ミニSparkline(SERIES_BUILDERS経由)は
    このグラフ選択とは独立で、従来通り使用率を表示し続ける。
    """
    groups: list[GraphSeriesGroup] = []
    reads = {s.labels.get("disk", "?"): s for s in samples if s.name == "disk.read_rate"}
    writes = {s.labels.get("disk", "?"): s for s in samples if s.name == "disk.write_rate"}
    for disk_name in sorted(set(reads) | set(writes)):
        read = reads.get(disk_name)
        write = writes.get(disk_name)
        series: list[tuple[str, SeriesKey]] = []
        unit = "bytes/s"
        if read is not None:
            series.append(("Read", read.series_key))
            unit = read.unit
        if write is not None:
            series.append(("Write", write.series_key))
            unit = write.unit
        if series:
            groups.append(GraphSeriesGroup(title=f"{disk_name} R/W", unit=unit, series=tuple(series)))
    return groups


def _network_graph_groups(samples: list[MetricSample]) -> list[GraphSeriesGroup]:
    groups: list[GraphSeriesGroup] = []
    sent = {s.labels.get("nic", "?"): s for s in samples if s.name == "network.sent_rate"}
    recv = {s.labels.get("nic", "?"): s for s in samples if s.name == "network.recv_rate"}
    for nic_name in sorted(set(sent) | set(recv)):
        sent_sample = sent.get(nic_name)
        recv_sample = recv.get(nic_name)
        series: list[tuple[str, SeriesKey]] = []
        unit = "bytes/s"
        if sent_sample is not None:
            series.append(("Sent", sent_sample.series_key))
            unit = sent_sample.unit
        if recv_sample is not None:
            series.append(("Recv", recv_sample.series_key))
            unit = recv_sample.unit
        if series:
            groups.append(GraphSeriesGroup(title=f"{nic_name} Sent/Recv", unit=unit, series=tuple(series)))
    return groups


GRAPH_GROUP_BUILDERS: dict[str, Callable[[list[MetricSample]], list[GraphSeriesGroup]]] = {
    "cpu": _cpu_graph_groups,
    "memory": _memory_graph_groups,
    "disk": _disk_graph_groups,
    "network": _network_graph_groups,
}


class DashboardScreen(Screen):
    """CPU/メモリ/ディスク/ネットワークをグリッド表示するメイン画面。"""

    BINDINGS = [
        Binding("down,right", "app.focus_next", "binding.next_panel", show=False),
        Binding("up,left", "app.focus_previous", "binding.prev_panel", show=False),
        Binding("enter", "open_graph", "binding.open_graph"),
    ]

    DEFAULT_CSS = """
    #grid {
        width: 1fr;
        height: 1fr;
        layout: grid;
        grid-gutter: 1;
    }
    """

    def __init__(
        self, panel_names: list[str], history: HistoryStore, system_info: SystemInfo, boot_time: float | None
    ) -> None:
        super().__init__()
        _localize_bindings(self._bindings)
        self._panel_names = panel_names
        self._history = history
        self._system_info = system_info
        self._boot_time = boot_time
        self.panels: dict[str, MetricPanel] = {}
        self.system_info_panel: SystemInfoPanel | None = None
        self._resize_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="dashboard-body"):
            self.system_info_panel = SystemInfoPanel(self._system_info, self._boot_time, id="system-info")
            yield self.system_info_panel
            with Container(id="grid"):
                for name in self._panel_names:
                    panel = MetricPanel(panel_title(name), id=f"panel-{name}")
                    self.panels[name] = panel
                    yield panel
        yield Footer()

    def on_mount(self) -> None:
        self._apply_layout(self.size.width, self.size.height)
        first_panel = next(iter(self.panels.values()), None)
        if first_panel is not None:
            self.set_focus(first_panel)

    def on_resize(self, event) -> None:
        if self._resize_timer is not None:
            self._resize_timer.stop()
        width = event.size.width
        height = event.size.height
        self._resize_timer = self.set_timer(RESIZE_DEBOUNCE, lambda: self._apply_layout(width, height))

    def _apply_layout(self, width: int, height: int) -> None:
        mode = layout_mode_for_width(width)
        grid = self.query_one("#grid", Container)
        count = len(self.panels)
        columns, rows = grid_dimensions(count) if mode is LayoutMode.GRID else (1, max(count, 1))
        grid.styles.grid_size_columns = columns
        grid.styles.grid_size_rows = rows
        for panel in self.panels.values():
            panel.compact = mode is LayoutMode.COMPACT
        if self.system_info_panel is not None:
            # サイドバーはGRIDモードかつSIDEBAR_MIN_WIDTH以上の幅がある時のみ表示する。
            # 100〜119幅は2x2グリッドではあるがサイドバー分の余裕が無いため隠す。
            width_ok = mode is LayoutMode.GRID and width >= SIDEBAR_MIN_WIDTH
            # 高さが足りない端末ではロゴを省略(INFO_ONLY)、さらに足りなければ非表示(HIDDEN)にする
            # (ロゴ15行込みのコンテンツが端末高さでクリップされるのを防ぐ)。
            sidebar_mode = sidebar_display_mode_for_height(height)
            self.system_info_panel.display = width_ok and sidebar_mode is not SidebarDisplayMode.HIDDEN
            self.system_info_panel.show_logo = sidebar_mode is SidebarDisplayMode.FULL
            # 幅140以上ではサイドバーを44セルへ拡大し、40セル解像度版のロゴを表示する。
            self.system_info_panel.wide = width >= SIDEBAR_WIDE_MIN_WIDTH

    def action_open_graph(self) -> None:
        focused = self.focused
        for name, panel in self.panels.items():
            if panel is focused:
                self.app.open_graph(name)
                return

    def apply_samples(self, collector_name: str, samples: list[MetricSample]) -> None:
        panel = self.panels.get(collector_name)
        if panel is None:
            return

        row_builder = ROW_BUILDERS.get(collector_name)
        if row_builder is not None:
            rows = row_builder(samples)
            if collector_name == "cpu" and rows:
                # Total(先頭行)は単独表示、コア別行は幅に応じて複数列に並べる
                panel.update_multi_column_rows(rows[0], rows[1:])
            else:
                panel.update_rows(rows)

        series_builder = SERIES_BUILDERS.get(collector_name)
        if series_builder is not None:
            series = series_builder(samples)
            if series:
                _, primary_key, _ = series[0]
                values = [s.value for s in self._history.get_by_key(primary_key) if s.value is not None]
                panel.update_sparkline(values)


def _series_stat_text(label: str, history: list[MetricSample], unit: str, *, prefix_label: bool) -> str:
    """1系列分の現在/最小/最大テキストを作る。

    現在値は履歴の最新の生ポイントを見る(Noneならカウンタリセット等で算出不能=—)。
    最小/最大はNoneを除いた値のみから計算するため、リセット直後でも過去の有効値を示せる。
    """
    numeric_values = [s.value for s in history if s.value is not None]
    current_value = history[-1].value if history else None
    current_text = "—" if current_value is None else _format_stat_value(current_value, unit)

    if numeric_values:
        stat = (
            f"{t('stats.now')}: {current_text}  {t('stats.min')}: {_format_stat_value(min(numeric_values), unit)}  "
            f"{t('stats.max')}: {_format_stat_value(max(numeric_values), unit)}"
        )
    else:
        stat = f"{t('stats.now')}: {current_text}  {t('stats.min')}: —  {t('stats.max')}: —"
    return f"{label} {stat}" if prefix_label else stat


class GraphScreen(Screen):
    """1つの収集器の系列(単系列 or 2系列ペア)を全画面折れ線グラフで表示する画面。

    左右キーで同カテゴリ内の系列グループ(コア別・マウント別・NIC別等)を切り替える。
    """

    # left/rightは別アクション(前/次)だがBinding.Groupで束ね、フッタには
    # "← → 系列切替"のように1エントリで表示する(2つの"系列切替"が重複表示されるのを防ぐ)。
    _SERIES_SWITCH_GROUP = Binding.Group(description="binding.switch_series")

    BINDINGS = [
        Binding("escape", "close_graph", "binding.close_graph"),
        Binding("left", "prev_series", "binding.switch_series", group=_SERIES_SWITCH_GROUP),
        Binding("right", "next_series", "binding.switch_series", group=_SERIES_SWITCH_GROUP),
    ]

    DEFAULT_CSS = """
    GraphScreen #stats {
        height: 1;
        padding: 0 1;
    }
    GraphScreen #graph-container {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(
        self, collector_name: str, title: str, initial_samples: list[MetricSample], history: HistoryStore
    ) -> None:
        super().__init__()
        _localize_bindings(self._bindings)
        self.collector_name = collector_name
        self._panel_title = title
        self._history = history
        self._latest_samples = initial_samples
        self._groups: list[GraphSeriesGroup] = []
        self._selected_key: tuple[SeriesKey, ...] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="stats", markup=False)
        with Container(id="graph-container"):
            yield LineGraphView(id="graph")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self._panel_title
        self.refresh_data()

    def action_close_graph(self) -> None:
        self.app.close_graph()

    def action_prev_series(self) -> None:
        self._move_selection(-1)

    def action_next_series(self) -> None:
        self._move_selection(1)

    def update_samples(self, samples: list[MetricSample]) -> None:
        """Appからtick毎に呼ばれ、直近サンプルを更新してから再描画する(系列一覧の陳腐化対策)。"""
        self._latest_samples = samples
        self.refresh_data()

    def refresh_data(self) -> None:
        builder = GRAPH_GROUP_BUILDERS.get(self.collector_name)
        self._groups = builder(self._latest_samples) if builder is not None else []

        stats = self.query_one("#stats", Static)
        graph = self.query_one("#graph", LineGraphView)

        if not self._groups:
            self._selected_key = None
            graph.plot_series([], "")
            stats.update(f"{self._panel_title} | {t('graph.no_data')}")
            return

        index = self._current_index()
        group = self._groups[index]
        self._selected_key = group.key

        histories = [(label, self._history.get_by_key(key)) for label, key in group.series]
        if not any(history for _, history in histories):
            graph.plot_series([], group.unit)
            stats.update(f"{group.title} | {t('graph.no_data')}")
            return

        all_timestamps = [s.timestamp for _, history in histories for s in history]
        start = min(all_timestamps) if all_timestamps else 0.0

        # Noneを除外せずそのまま渡す。LineGraphView側でNoneの箇所を線で繋がずに分割描画する。
        plot_series: list[tuple[str, list[float], list[float | None]]] = []
        for label, history in histories:
            times = [s.timestamp - start for s in history]
            values: list[float | None] = [s.value for s in history]
            plot_series.append((label, times, values))
        graph.plot_series(plot_series, group.unit)

        multi = len(histories) > 1
        stat_texts = [
            _series_stat_text(label, history, group.unit, prefix_label=multi) for label, history in histories
        ]
        stats.update(f"{group.title} | " + "  ".join(stat_texts))

    def _move_selection(self, delta: int) -> None:
        if len(self._groups) <= 1:
            return
        index = (self._current_index() + delta) % len(self._groups)
        self._selected_key = self._groups[index].key
        self.refresh_data()

    def _current_index(self) -> int:
        """選択中のグループの現在位置を返す。グループが消失していれば0(先頭)にクランプする。

        titleではなくkey(系列キーのタプル)で追跡する。titleは表示用ラベルで一意性の
        保証が無く、同名グループが複数存在しうるため。
        """
        if self._selected_key is not None:
            for index, group in enumerate(self._groups):
                if group.key == self._selected_key:
                    return index
        return 0


class SysdashApp(App):
    """sysdash TUIアプリ本体。collector群を組み立ててワーカースレッドでポーリングする。"""

    TITLE = platform.node() or "sysdash"

    BINDINGS = [
        Binding("q", "quit_app", "binding.quit"),
        Binding("p", "toggle_pause", "binding.toggle_pause"),
        Binding("plus", "increase_interval", "binding.interval_increase", show=False),
        Binding("minus", "decrease_interval", "binding.interval_decrease", show=False),
    ]

    def __init__(self, collectors: Iterable[Collector], interval: float = 1.0) -> None:
        super().__init__()
        _localize_bindings(self._bindings)
        self._collectors = list(collectors)
        self._collector_names = [c.name for c in self._collectors]
        self.history = HistoryStore(maxlen=GRAPH_HISTORY_POINTS)
        self.sampler = Sampler(self._collectors, interval=interval)
        self.sampler.add_listener(self.history)
        self.sampler.add_listener(self._on_samples)
        self._requested_interval = interval
        self._dashboard: DashboardScreen | None = None
        self._graph: GraphScreen | None = None
        self._latest_samples: dict[str, list[MetricSample]] = {name: [] for name in self._collector_names}
        try:
            self._boot_time: float | None = psutil.boot_time()
        except Exception:
            self._boot_time = None
        try:
            self._system_info = collect_system_info()
        except Exception:
            # collect_system_info自体は項目単位で保護済みだが、万一ここで予期せぬ例外が
            # 出ても起動自体は継続する(全項目N/Aのサイドバーを表示するだけにする)。
            self._system_info = blank_system_info()

    def on_mount(self) -> None:
        self._dashboard = DashboardScreen(self._collector_names, self.history, self._system_info, self._boot_time)
        self.push_screen(self._dashboard)
        self._update_header()
        if self.sampler.interval != self._requested_interval:
            self.notify(
                t("notify.interval_clamped", requested=self._requested_interval, actual=self.sampler.interval),
                severity="warning",
            )
        self._run_sampler()

    @work(thread=True, exclusive=True)
    def _run_sampler(self) -> None:
        self.sampler.run()

    def _on_samples(self, samples: list[MetricSample]) -> None:
        # Samplerのワーカースレッドから呼ばれるため、UI反映はcall_from_thread経由にする
        self.call_from_thread(self._apply_samples, samples)

    def _apply_samples(self, samples: list[MetricSample]) -> None:
        if self._dashboard is None or not self._dashboard.is_mounted:
            return
        grouped: dict[str, list[MetricSample]] = {}
        for sample in samples:
            collector_name = sample.name.split(".", 1)[0]
            grouped.setdefault(collector_name, []).append(sample)
        # 登録collector全名について毎tick全置換する。空リストを返した(=collect()が失敗した)
        # collectorのキャッシュも同時に空になる。ダッシュボードのパネル自体は実際にサンプルが
        # 来たcollectorのみ更新し、1tickの収集失敗でパネル全体がN/Aに落ちるのを避ける。
        self._latest_samples = {name: grouped.get(name, []) for name in self._collector_names}
        for collector_name, collector_samples in grouped.items():
            self._dashboard.apply_samples(collector_name, collector_samples)
        if self._graph is not None and self._graph.is_mounted:
            self._graph.update_samples(self._latest_samples.get(self._graph.collector_name, []))
        self._update_header()

    def open_graph(self, collector_name: str) -> None:
        if isinstance(self.screen, GraphScreen):
            return
        group_builder = GRAPH_GROUP_BUILDERS.get(collector_name)
        initial_samples = self._latest_samples.get(collector_name, [])
        if group_builder is None or not group_builder(initial_samples):
            self.notify(
                t("notify.waiting_for_data"),
                title=panel_title(collector_name),
                severity="warning",
            )
            return
        self._graph = GraphScreen(collector_name, panel_title(collector_name), initial_samples, self.history)
        self.push_screen(self._graph)

    def close_graph(self) -> None:
        if self._graph is None:
            return
        self.pop_screen()
        self._graph = None

    def action_toggle_pause(self) -> None:
        if self.sampler.paused:
            self.sampler.resume()
        else:
            self.sampler.pause()
        self._update_header()

    def action_increase_interval(self) -> None:
        self.sampler.set_interval(self.sampler.interval + INTERVAL_STEP)
        self._update_header()

    def action_decrease_interval(self) -> None:
        self.sampler.set_interval(self.sampler.interval - INTERVAL_STEP)
        self._update_header()

    def _update_header(self) -> None:
        uptime_seconds = None if self._boot_time is None else max(0.0, time.time() - self._boot_time)

        parts = [f"{platform.system()} {platform.release()}".strip()]
        if uptime_seconds is not None:
            hours, remainder = divmod(int(uptime_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            parts.append(f"uptime {hours:02d}:{minutes:02d}:{seconds:02d}")
        parts.append(f"interval {self.sampler.interval:.1f}s")
        if self.sampler.paused:
            parts.append("PAUSED")

        if self._dashboard is not None and self._dashboard.system_info_panel is not None:
            self._dashboard.system_info_panel.update_uptime()
        self.sub_title = " | ".join(parts)

    def exit(self, *args, **kwargs) -> None:
        # q以外の終了経路(Ctrl+C・テストharnessのteardown等)でもワーカースレッド待ちで
        # ハングしないよう、ここでもsampler.stop()を確実に呼ぶ
        self.sampler.stop()
        super().exit(*args, **kwargs)

    def on_unmount(self) -> None:
        self.sampler.stop()

    def action_quit_app(self) -> None:
        self.exit()
