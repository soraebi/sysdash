import time
from types import SimpleNamespace
from typing import Callable

import pytest
from textual.widgets import Static
from textual.widgets._footer import FooterKey, FooterLabel

from sysdash.collectors.cpu import CpuCollector
from sysdash.collectors.disk import DiskCollector
from sysdash.collectors.memory import MemoryCollector
from sysdash.collectors.network import NetworkCollector
from sysdash.core.history import SeriesKey
from sysdash.core.i18n import set_language
from sysdash.core.models import MetricSample
from sysdash.core.sampler import MIN_INTERVAL
from sysdash.ui.app import (
    GRAPH_GROUP_BUILDERS,
    GRAPH_HISTORY_POINTS,
    INTERVAL_STEP,
    DashboardScreen,
    GraphScreen,
    GraphSeriesGroup,
    SysdashApp,
)
from sysdash.ui.breakpoints import (
    SIDEBAR_FULL_MIN_HEIGHT,
    SIDEBAR_INFO_MIN_HEIGHT,
    SIDEBAR_MIN_WIDTH,
    SIDEBAR_WIDE_MIN_WIDTH,
    LayoutMode,
    layout_mode_for_width,
)
from sysdash.ui.graph_view import LineGraphView
from sysdash.ui.widgets.system_info import SystemInfo, SystemInfoPanel, blank_system_info
from tests.fakes import FakeCpuBackend, FakeDiskBackend, FakeMemoryBackend, FakeNetworkBackend


async def _wait_until(pilot, predicate: Callable[[], bool], timeout: float = 3.0, interval: float = 0.1) -> None:
    """resizeデバウンス等、確定的な単発waitだとテスト実行環境の負荷で稀に間に合わないことがある
    条件を、タイムアウト付きでポーリングして待つ(システム負荷に対して頑健にするため)。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await pilot.pause(interval)
    assert predicate(), f"condition not met within {timeout}s"


class _FakeCollector:
    def __init__(self, name: str) -> None:
        self.name = name

    def collect(self) -> list[MetricSample]:
        return [MetricSample(name=f"{self.name}.value", timestamp=0.0, value=1.0, unit="")]


def _make_app() -> SysdashApp:
    collectors = [_FakeCollector("cpu"), _FakeCollector("memory"), _FakeCollector("disk"), _FakeCollector("network")]
    return SysdashApp(collectors, interval=0.5)


def _make_real_app() -> SysdashApp:
    """グラフ画面のテストはROW/SERIES_BUILDERSが認識する実メトリクス名が必要なため、
    実collector+FakeBackendの組み合わせを使う(_FakeCollectorの"cpu.value"等はcpu.total等の
    命名規則に一致せず、SERIES_BUILDERSが空リストを返してグラフが開けない)。
    """
    collectors = [
        CpuCollector(backend=FakeCpuBackend(per_core=[10.0, 20.0])),
        MemoryCollector(backend=FakeMemoryBackend(percent=50.0, swap_percent=5.0)),
    ]
    return SysdashApp(collectors, interval=0.5)


@pytest.mark.asyncio
async def test_app_starts_with_all_panels() -> None:
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app._dashboard is not None
        assert set(app._dashboard.panels.keys()) == {"cpu", "memory", "disk", "network"}
        app.sampler.stop()


@pytest.mark.asyncio
async def test_teardown_without_quit_stops_sampler() -> None:
    """qを押さずにrun_testコンテキストを抜けてもサンプラーが止まりハングしないこと。

    回帰: 終了処理がaction_quit_appにしかないと、teardownがワーカースレッド待ちで
    ハングする(このテストは失敗ではなくタイムアウトとして現れる)。
    """
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
    assert app.sampler.stopped


@pytest.mark.asyncio
async def test_q_key_exits_app() -> None:
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        assert app._exit is True


@pytest.mark.asyncio
async def test_resize_switches_layout_mode_after_debounce() -> None:
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert layout_mode_for_width(120) is LayoutMode.GRID
        grid = app._dashboard.query_one("#grid")
        assert (grid.styles.grid_size_columns, grid.styles.grid_size_rows) == (2, 2)  # 4パネル

        await pilot.resize_terminal(40, 40)
        await _wait_until(pilot, lambda: grid.styles.grid_size_columns == 1)  # デバウンス(0.5秒)を待つ

        assert layout_mode_for_width(40) is LayoutMode.COMPACT
        assert (grid.styles.grid_size_columns, grid.styles.grid_size_rows) == (1, 4)
        assert all(panel.compact for panel in app._dashboard.panels.values())

        app.sampler.stop()


@pytest.mark.asyncio
async def test_enter_opens_graph_screen_and_escape_returns_to_dashboard() -> None:
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)  # 最初のtickを待つ

        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("enter")  # 初期フォーカスはcpuパネル
        await pilot.pause()
        assert isinstance(app.screen, GraphScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)

        app.sampler.stop()


def _current_series_label(graph: GraphScreen) -> str:
    index = graph._current_index()
    return graph._groups[index].title


@pytest.mark.asyncio
async def test_left_right_switches_series_within_category() -> None:
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        graph = app.screen
        assert isinstance(graph, GraphScreen)
        # cpu: Total + Core0 + Core1 の3系列(いずれも単系列グループ)
        assert len(graph._groups) == 3

        first_label = _current_series_label(graph)
        await pilot.press("right")
        await pilot.pause()
        assert _current_series_label(graph) != first_label

        await pilot.press("left")
        await pilot.pause()
        assert _current_series_label(graph) == first_label

        app.sampler.stop()


@pytest.mark.asyncio
async def test_history_wired_with_300_point_ring() -> None:
    app = _make_app()
    assert app.history.maxlen == GRAPH_HISTORY_POINTS == 300

    for i in range(305):
        app.history.record([MetricSample(name="cpu.total", timestamp=float(i), value=float(i), unit="%")])
    values = app.history.get("cpu.total")
    assert len(values) == 300
    assert values[0].value == 5.0
    assert values[-1].value == 304.0


@pytest.mark.asyncio
async def test_graph_view_fills_container_height() -> None:
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        graph_widget = app.screen.query_one("#graph", LineGraphView)
        assert graph_widget.size.height > 1

        app.sampler.stop()


class _IncrementingNetworkBackend:
    """tick毎にカウンタが一定量増える(≒安定したレート)ことを模したバックエンド。"""

    def __init__(self, sent_step: int = 5_000_000, recv_step: int = 1_000_000) -> None:
        self._sent = 0
        self._recv = 0
        self._sent_step = sent_step
        self._recv_step = recv_step

    def net_io_counters(self, pernic: bool = False) -> dict[str, SimpleNamespace]:
        self._sent += self._sent_step
        self._recv += self._recv_step
        return {"eth0": SimpleNamespace(bytes_sent=self._sent, bytes_recv=self._recv)}


@pytest.mark.asyncio
async def test_graph_stats_humanize_byte_rate_units() -> None:
    collectors = [NetworkCollector(backend=_IncrementingNetworkBackend())]
    app = SysdashApp(collectors, interval=0.5)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)  # 1tick目(レートはまだNone)
        await pilot.press("enter")
        await pilot.pause(0.6)  # 2tick目でレートが数値化するのを待つ

        stats_text = app.screen.query_one("#stats", Static).visual.plain
        assert "MB/s" in stats_text
        assert "bytes/s" not in stats_text  # 未整形の生byte単位が漏れていないこと

        app.sampler.stop()


@pytest.mark.asyncio
async def test_series_list_refreshes_and_clamps_when_nic_disappears() -> None:
    """NICのSent/Recvは1グループにまとまるため、NIC数=グループ数になる。"""
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000), "wlan0": (500, 500)})
    collectors = [NetworkCollector(backend=backend)]
    app = SysdashApp(collectors, interval=0.5)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        graph = app.screen
        assert isinstance(graph, GraphScreen)
        assert len(graph._groups) == 2  # eth0, wlan0 (それぞれSent+Recvの1グループ)

        await pilot.press("right")  # eth0 Sent/Recv -> wlan0 Sent/Recv
        await pilot.pause()
        assert _current_series_label(graph) == "wlan0 Sent/Recv"

        backend.counters = {"eth0": (1500, 2500)}  # wlan0が消える
        await pilot.pause(0.6)

        assert len(graph._groups) == 1
        assert all("wlan0" not in group.title for group in graph._groups)
        assert _current_series_label(graph) == "eth0 Sent/Recv"  # 消失した選択はクランプされ例外も出ない

        app.sampler.stop()


class _FlakyCollector:
    """1tick目のみサンプルを返し、以降は毎tick空リストを返す(収集失敗を模す)。"""

    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def collect(self) -> list[MetricSample]:
        self.calls += 1
        if self.calls == 1:
            return [MetricSample(name="flaky.value", timestamp=0.0, value=1.0, unit="")]
        return []


@pytest.mark.asyncio
async def test_latest_samples_cache_clears_when_collector_returns_nothing() -> None:
    """バックグラウンドのSamplerスレッドのタイミングに依存させず、_apply_samples()に
    手作りのサンプルを直接2回渡して「前tickの値が残らず全置換されること」を決定的に検証する。
    _FlakyCollectorは"flaky"という名前をSysdashAppに登録するためだけに使い、
    その collect() の呼び出し回数には依存しない。
    """
    app = SysdashApp([_FlakyCollector()], interval=0.5)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.sampler.stop()  # バックグラウンドの自動ポーリングは止める

        app._apply_samples([MetricSample(name="flaky.value", timestamp=0.0, value=1.0, unit="")])
        assert app._latest_samples.get("flaky") != []

        app._apply_samples([])  # このtickはサンプルなし(収集失敗を模す)
        assert app._latest_samples.get("flaky") == []


@pytest.mark.asyncio
async def test_double_enter_does_not_double_push_graph_screen() -> None:
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, GraphScreen)
        stack_depth = len(app.screen_stack)

        app.open_graph("cpu")  # 表示中に再度呼んでも二重pushされない
        await pilot.pause()
        assert len(app.screen_stack) == stack_depth

        app.sampler.stop()


@pytest.mark.asyncio
async def test_close_graph_without_open_graph_is_a_no_op() -> None:
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        stack_depth = len(app.screen_stack)

        app.close_graph()  # _graphがNoneのため何もしないはず
        await pilot.pause()

        assert len(app.screen_stack) == stack_depth
        assert isinstance(app.screen, DashboardScreen)

        app.sampler.stop()


@pytest.mark.asyncio
async def test_p_key_pauses_and_resumes_sampler_and_freezes_history() -> None:
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)  # 1tick進める
        assert not app.sampler.paused

        await pilot.press("p")
        await pilot.pause()
        assert app.sampler.paused
        assert "PAUSED" in app.sub_title

        history_len_at_pause = len(app.history.get("cpu.value"))
        await pilot.pause(1.2)  # pause中は履歴が伸びないはず
        assert len(app.history.get("cpu.value")) == history_len_at_pause

        await pilot.press("p")
        await pilot.pause()
        assert not app.sampler.paused
        assert "PAUSED" not in app.sub_title

        app.sampler.stop()


@pytest.mark.asyncio
async def test_plus_minus_keys_change_interval_and_header_reflects_it() -> None:
    app = _make_app()  # interval=0.5(=MIN_INTERVAL)で構築される
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await pilot.press("+")
        await pilot.pause()
        assert app.sampler.interval == MIN_INTERVAL + INTERVAL_STEP
        assert f"interval {app.sampler.interval:.1f}s" in app.sub_title

        await pilot.press("-")
        await pilot.pause()
        assert app.sampler.interval == MIN_INTERVAL

        await pilot.press("-")  # 下限より下げようとしてもMIN_INTERVALでクランプされる
        await pilot.pause()
        assert app.sampler.interval == MIN_INTERVAL

        app.sampler.stop()


@pytest.mark.asyncio
async def test_enter_with_no_matching_series_shows_notification() -> None:
    """_FakeCollectorはROW/SERIES_BUILDERSが認識しないメトリクス名を返すため常にデータ無し扱いになる。
    Enterを押しても無反応にならず、notify()で通知が出ることを確認する。
    """
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)

        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert len(app._notifications) > 0

        app.sampler.stop()


@pytest.mark.asyncio
async def test_column_layout_at_medium_width_is_not_compact() -> None:
    app = _make_app()
    async with app.run_test(size=(70, 40)) as pilot:
        await pilot.pause()
        assert layout_mode_for_width(70) is LayoutMode.COLUMN

        grid = app._dashboard.query_one("#grid")
        assert (grid.styles.grid_size_columns, grid.styles.grid_size_rows) == (1, 4)
        assert all(not panel.compact for panel in app._dashboard.panels.values())

        app.sampler.stop()


class _ResetThenDecreasingNetworkBackend:
    """1,2tick目は素直に増加(有効なレートが出る)。3tick目以降は際限なく減少し続け、
    以後ずっとカウンタリセット扱い(rate=None)になるようにする(タイミングに依存させないため)。
    """

    def __init__(self) -> None:
        self._tick = 0

    def net_io_counters(self, pernic: bool = False) -> dict[str, SimpleNamespace]:
        self._tick += 1
        if self._tick == 1:
            sent = 1_000_000
        elif self._tick == 2:
            sent = 3_000_000
        else:
            # 3tick目以降は際限なく減り続ける(同じ値で足踏みすると、次tickでdelta=0となり
            # 「有効なレート0.0」に化けてタイミング依存のテストになってしまうため)
            sent = 1_000_000 - self._tick * 500_000
        return {"eth0": SimpleNamespace(bytes_sent=sent, bytes_recv=sent)}


@pytest.mark.asyncio
async def test_graph_current_shows_dash_after_counter_reset_not_stale_value() -> None:
    collectors = [NetworkCollector(backend=_ResetThenDecreasingNetworkBackend())]
    app = SysdashApp(collectors, interval=0.5)
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(4):
            await pilot.pause(0.6)  # リセット後の状態に十分入り込ませる

        await pilot.press("enter")
        await pilot.pause()

        stats_text = app.screen.query_one("#stats", Static).visual.plain
        assert "現在: —" in stats_text
        assert "最小: —" not in stats_text  # tick2の有効な値が最小/最大には残っている

        app.sampler.stop()


@pytest.mark.asyncio
async def test_graph_screen_supplies_disk_read_write_pair_from_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ディスクのR/Wグループを開くと、GraphScreenがhistoryからRead/Writeそれぞれの系列を引いて
    LineGraphView.plot_series()に2系列(色分け対象)渡していることを確認する。
    """
    backend = FakeDiskBackend(mounts=["C:\\"], usage_percent={"C:\\": 50.0}, io_counters={"disk0": (1000, 2000)})
    collectors = [DiskCollector(backend=backend)]
    app = SysdashApp(collectors, interval=0.5)

    captured: list[list[tuple[str, list[float], list[float]]]] = []
    original_plot_series = LineGraphView.plot_series

    def spy_plot_series(self: LineGraphView, series, unit: str) -> None:
        captured.append(list(series))
        original_plot_series(self, series, unit)

    monkeypatch.setattr(LineGraphView, "plot_series", spy_plot_series)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)  # 1tick目(レートはNone)
        backend.io_counters = {"disk0": (2000, 4500)}
        await pilot.pause(0.6)  # 2tick目(レートが数値化)

        app.open_graph("disk")
        await pilot.pause()

        graph = app.screen
        assert isinstance(graph, GraphScreen)
        rw_index = next(i for i, group in enumerate(graph._groups) if group.title.endswith("R/W"))
        while graph._current_index() != rw_index:
            await pilot.press("right")
            await pilot.pause()

        assert captured, "plot_seriesが呼ばれていない"
        labels = [label for label, _, _ in captured[-1]]
        assert labels == ["Read", "Write"]
        assert any(values for _, _, values in captured[-1])

        app.sampler.stop()


@pytest.mark.asyncio
async def test_graph_screen_supplies_network_sent_recv_pair_from_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NICのSent/Recvグループを開くと、GraphScreenがhistoryからSent/Recvそれぞれの系列を引いて
    LineGraphView.plot_series()に2系列渡していることを確認する。
    """
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000)})
    collectors = [NetworkCollector(backend=backend)]
    app = SysdashApp(collectors, interval=0.5)

    captured: list[list[tuple[str, list[float], list[float]]]] = []
    original_plot_series = LineGraphView.plot_series

    def spy_plot_series(self: LineGraphView, series, unit: str) -> None:
        captured.append(list(series))
        original_plot_series(self, series, unit)

    monkeypatch.setattr(LineGraphView, "plot_series", spy_plot_series)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        backend.counters = {"eth0": (3000, 6000)}
        await pilot.pause(0.6)

        app.open_graph("network")
        await pilot.pause()

        assert captured, "plot_seriesが呼ばれていない"
        labels = [label for label, _, _ in captured[-1]]
        assert labels == ["Sent", "Recv"]
        assert any(values for _, _, values in captured[-1])

        app.sampler.stop()


@pytest.mark.asyncio
async def test_current_index_tracks_by_key_even_with_duplicate_titles() -> None:
    """titleが同名の2グループを注入しても、keyで正しく区別して追跡できることを確認する
    (titleだけで追跡すると同名の先頭グループに誤ってマッチしてしまう)。
    """
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        graph = app.screen
        assert isinstance(graph, GraphScreen)

        dup_a = GraphSeriesGroup(title="Dup", unit="%", series=(("Dup", ("metric.a", (("id", "a"),))),))
        dup_b = GraphSeriesGroup(title="Dup", unit="%", series=(("Dup", ("metric.b", (("id", "b"),))),))
        graph._groups = [dup_a, dup_b]
        graph._selected_key = dup_b.key

        assert graph._current_index() == 1  # titleが同じでもkeyで正しく2番目を特定できる

        app.sampler.stop()


@pytest.mark.asyncio
async def test_graph_screen_handles_pair_group_with_one_series_missing_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2系列ペアの片方がHistoryStoreに一度も記録されていない(空履歴)場合でも、
    例外にならず、データがある側は正しい統計を、無い側は—表示になることを確認する。

    refresh_data()は毎回GRAPH_GROUP_BUILDERSからgroupsを再構築するため、_groupsへの
    直接注入は次のtickで上書きされる。builder自体をmonkeypatchして安定させる。
    """
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        graph = app.screen
        assert isinstance(graph, GraphScreen)

        populated_key = graph._groups[0].series[0][1]  # 実在する(履歴のある)キー
        missing_key: SeriesKey = ("dummy.never_recorded", (("id", "x"),))  # 一度も記録されていないキー
        pair_group = GraphSeriesGroup(
            title="Pair", unit="%", series=(("HasData", populated_key), ("NoData", missing_key))
        )

        monkeypatch.setitem(GRAPH_GROUP_BUILDERS, "cpu", lambda samples: [pair_group])
        graph.refresh_data()
        await pilot.pause()

        stats_text = graph.query_one("#stats", Static).visual.plain
        assert "HasData" in stats_text
        assert "NoData" in stats_text
        assert "—" in stats_text  # NoData側は算出不能(データなし)表示

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_visible_only_in_grid_mode() -> None:
    """SystemInfoPanel(サイドバー)はGRIDモードでのみ表示され、COLUMN/COMPACTでは隠れる。"""
    app = _make_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert layout_mode_for_width(140) is LayoutMode.GRID
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.display is True

        await pilot.resize_terminal(90, 40)
        await _wait_until(pilot, lambda: sidebar.display is False)
        assert layout_mode_for_width(90) is LayoutMode.COLUMN

        await pilot.resize_terminal(140, 40)
        await _wait_until(pilot, lambda: sidebar.display is True)
        assert layout_mode_for_width(140) is LayoutMode.GRID

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_hidden_between_grid_min_and_sidebar_min_width() -> None:
    """GRID_MIN_WIDTH(100)以上でも、SIDEBAR_MIN_WIDTH(120)未満ではサイドバーを隠す。

    100〜119幅は「2x2グリッドだがサイドバー無し」、120以上でサイドバーも表示される
    (レビュー指摘: 閾値をGRID表示可否とサイドバー表示可否とで分離)。
    """
    assert SIDEBAR_MIN_WIDTH == 120
    app = _make_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert layout_mode_for_width(100) is LayoutMode.GRID
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.display is False  # 100幅: GRIDだがサイドバー無し

        await pilot.resize_terminal(119, 40)
        await _wait_until(pilot, lambda: layout_mode_for_width(119) is LayoutMode.GRID)
        assert sidebar.display is False  # 119幅: まだサイドバー無し

        await pilot.resize_terminal(120, 40)
        await _wait_until(pilot, lambda: sidebar.display is True)
        assert layout_mode_for_width(120) is LayoutMode.GRID  # 120幅: サイドバーも表示

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_full_display_at_sufficient_height() -> None:
    """高さがSIDEBAR_FULL_MIN_HEIGHT以上ならロゴ込みでフル表示される(120x40)。"""
    assert SIDEBAR_FULL_MIN_HEIGHT == 28
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.display is True
        assert sidebar.show_logo is True

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_omits_logo_when_height_insufficient_for_full_display() -> None:
    """高さがSIDEBAR_FULL_MIN_HEIGHT未満・SIDEBAR_INFO_MIN_HEIGHT以上ならロゴを省略し
    情報のみ表示する(120x24。ロゴ15行込みだと下部の情報がクリップされるため)。
    """
    assert SIDEBAR_INFO_MIN_HEIGHT == 14
    app = _make_app()
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.display is True  # サイドバー自体は表示される
        assert sidebar.show_logo is False  # ロゴだけ省略される

        text = sidebar.visual.plain
        assert "コア:" in text  # サイドバーラベルはja既定でP9-fixにより日本語化(Cores→コア)
        assert "Python:" in text  # 技術名は両言語とも英語のまま

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_hidden_when_height_too_small_for_info_only() -> None:
    """高さがSIDEBAR_INFO_MIN_HEIGHT未満だと、幅条件を満たしていてもサイドバー自体を隠す。"""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.display is True

        await pilot.resize_terminal(120, 10)
        await _wait_until(pilot, lambda: sidebar.display is False)

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_stays_standard_width_below_wide_threshold() -> None:
    """幅120〜139(SIDEBAR_WIDE_MIN_WIDTH未満)では、従来どおり34セル幅・30セル解像度ロゴのまま。"""
    assert SIDEBAR_WIDE_MIN_WIDTH == 140
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.wide is False
        assert sidebar.styles.width.value == 34

        await pilot.resize_terminal(139, 40)
        await _wait_until(pilot, lambda: sidebar.styles.width.value == 34)
        assert sidebar.wide is False

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_expands_to_wide_at_140_and_above() -> None:
    """幅140以上ではサイドバーが44セル幅に拡大し、40セル解像度版のロゴに切り替わる。"""
    app = _make_app()
    async with app.run_test(size=(139, 40)) as pilot:
        await pilot.pause()
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        assert sidebar.wide is False

        await pilot.resize_terminal(140, 40)
        await _wait_until(pilot, lambda: sidebar.wide is True)
        assert sidebar.styles.width.value == 44

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_shows_hostname_and_uptime() -> None:
    """SystemInfoPanelがSysdashApp起動時に収集したSystemInfoを実際に描画していることを確認する。"""
    app = _make_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause(0.6)  # uptimeが少なくとも1回更新されるのを待つ

        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        text = sidebar.visual.plain
        assert app._system_info.hostname in text
        assert "稼働時間:" in text  # サイドバーラベルはja既定でP9-fixにより日本語化(Uptime→稼働時間)

        app.sampler.stop()


@pytest.mark.asyncio
async def test_sidebar_uptime_shows_na_when_boot_time_unavailable() -> None:
    """psutil.boot_time()取得に失敗した(boot_time=None)場合、update_uptime()は
    例外を送出せずUptime行をN/A表示にする。"""
    from textual.app import App, ComposeResult

    class _PanelOnlyApp(App):
        def compose(self) -> ComposeResult:
            yield SystemInfoPanel(blank_system_info(), None, id="sb")

    app = _PanelOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#sb", SystemInfoPanel)
        panel.update_uptime()
        await pilot.pause()
        assert "稼働時間: N/A" in panel.visual.plain  # サイドバーラベルはja既定でP9-fixにより日本語化


@pytest.mark.asyncio
async def test_sidebar_hostname_with_markup_characters_displays_literally() -> None:
    """hostname等にRichマークアップ風の文字列("[bold]...[/]"等)が含まれても、
    escape()によって書式として解釈されず文字どおり表示されることの回帰テスト。
    """
    from textual.app import App, ComposeResult

    info = SystemInfo(
        os_name="Windows",
        os_display="Windows 11",
        kernel="10.0.22631",
        hostname="[bold]host[/bold]",
        cpu_model="Generic CPU",
        cpu_physical_cores=4,
        cpu_logical_cores=8,
        memory_total=1000,
        disk_mount="C:\\",
        disk_used=100,
        disk_total=200,
        python_version="3.12.0",
    )

    class _PanelOnlyApp(App):
        def compose(self) -> ComposeResult:
            yield SystemInfoPanel(info, None, id="sb")

    app = _PanelOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#sb", SystemInfoPanel)
        assert "[bold]host[/bold]" in panel.visual.plain


@pytest.mark.asyncio
async def test_graph_screen_left_right_bindings_appear_in_footer() -> None:
    """GraphScreenの系列切替(左右キー)はフッタに表示される(show=True)ことを確認する。
    ユーザーが矢印キーでの系列切替に気づけなかったフィードバックへの対応。
    left/rightはBinding.Groupで束ねてあるため、フッタ上ではキー2つ+共有ラベル1つ
    (「系列切替」の重複表示無し)という構成になる。
    """
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        # フルスイート実行時のシステム負荷下で、固定pause()だとGraphScreenへの遷移・フッタの
        # 再構成が間に合わないことがあったため(単体実行では常に成功)、ポーリングで待つ。
        await _wait_until(pilot, lambda: isinstance(app.screen, GraphScreen))
        await _wait_until(pilot, lambda: len(list(app.screen.query(FooterKey))) > 0)

        footer_keys = {key.key: key.description for key in app.screen.query(FooterKey)}
        assert "left" in footer_keys
        assert "right" in footer_keys

        labels = [label.content for label in app.screen.query(FooterLabel)]
        assert labels.count("系列切替") == 1  # グループ化により1エントリのみ表示される

        app.sampler.stop()


@pytest.mark.asyncio
async def test_lang_en_produces_english_panel_titles_and_footer() -> None:
    """--lang en相当(set_language("en"))でアプリを構築すると、パネルタイトルとフッタ文言が
    英語になることを確認する(P9: i18n対応)。日本語側の既存テストはtests/conftest.pyの
    `_default_test_language` fixtureが既定言語を"ja"に固定するため、本テストの影響を受けない。
    """
    set_language("en")
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_until(pilot, lambda: isinstance(app.screen, DashboardScreen))
        titles = {name: panel.border_title for name, panel in app.screen.panels.items()}
        assert titles["cpu"] == "CPU"
        assert titles["memory"] == "Memory"
        assert titles["disk"] == "Disk"
        assert titles["network"] == "Network"

        await _wait_until(pilot, lambda: len(list(app.screen.query(FooterKey))) > 0)
        footer_descriptions = {key.description for key in app.screen.query(FooterKey)}
        assert "Quit" in footer_descriptions
        assert "Pause" in footer_descriptions

        app.sampler.stop()


@pytest.mark.asyncio
async def test_lang_en_graph_screen_shows_english_footer_and_stats() -> None:
    """--lang en相当(set_language("en"))でGraphScreenに遷移すると、フッタ(Back・左右キーの
    Switch series)とグラフ統計(Now/Min/Max)が英語になることを確認する(P9-fix item7b)。
    """
    set_language("en")
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await _wait_until(pilot, lambda: isinstance(app.screen, GraphScreen))
        await _wait_until(pilot, lambda: len(list(app.screen.query(FooterKey))) > 0)

        footer_keys = {key.key: key.description for key in app.screen.query(FooterKey)}
        assert footer_keys.get("escape") == "Back"

        labels = [label.content for label in app.screen.query(FooterLabel)]
        assert labels.count("Switch series") == 1  # left/rightがグループ化され1エントリのみ

        stats_text = app.screen.query_one("#stats", Static).visual.plain
        assert "Now:" in stats_text
        assert "Min:" in stats_text
        assert "Max:" in stats_text

        app.sampler.stop()


@pytest.mark.asyncio
async def test_lang_en_keeps_sidebar_labels_english() -> None:
    """--lang en相当でも、サイドバーラベル(Cores/Uptime/Memory/Disk)は元々英語のため
    見た目が変わらないことを確認する(P9-fix item1: 「en時は現状どおり」の回帰防止)。
    """
    set_language("en")
    app = _make_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause(0.6)
        sidebar = app._dashboard.system_info_panel
        assert sidebar is not None
        text = sidebar.visual.plain
        assert "Cores:" in text
        assert "Uptime:" in text
        assert "Memory:" in text
        assert "Disk (" in text

        app.sampler.stop()


@pytest.mark.asyncio
async def test_graph_view_is_not_focusable() -> None:
    """LineGraphView(PlotextPlot)はグラフ操作にフォーカスを必要としないため、
    can_focus=Falseであることを明示的に確認する(将来的な意図しない変更の回帰防止)。
    """
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        graph = app.screen.query_one("#graph", LineGraphView)
        assert graph.can_focus is False

        app.sampler.stop()


@pytest.mark.asyncio
async def test_footer_bindings_stay_enabled_regardless_of_focus_in_graph_screen() -> None:
    """GraphScreen表示中、フォーカスがどこにあっても(あるいは何もフォーカスされていなくても)
    Screen/Appレベルのバインド(戻る・一時停止・終了)がフッタ上で有効(enabled)であることを確認する。

    調査の結果、GraphScreen配下にはcan_focus=Trueのウィジェットが元々存在せず
    (フォーカスは常にNone)、active_bindingsは常にenabled=Trueだった。「PlotextPlotが
    フォーカスを奪いバインドが無効化される」という仮説は再現しなかったが、
    can_focus=Falseの明示化と合わせて、この不変条件を回帰テストとして残す。
    """
    app = _make_real_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("enter")
        await pilot.pause()

        assert app.focused is None  # GraphScreenには元々フォーカス可能なウィジェットが無い

        active = app.screen.active_bindings
        for key in ("escape", "left", "right", "q", "p"):
            _node, binding, enabled, _tooltip = active[key]
            assert enabled, f"{key} ({binding.action}) should stay enabled regardless of focus"

        app.sampler.stop()
