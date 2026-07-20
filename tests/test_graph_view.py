import re

import pytest
from textual.app import App, ComposeResult

from sysdash.ui.graph_view import LineGraphView, _segments


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class _GraphOnlyApp(App):
    def compose(self) -> ComposeResult:
        yield LineGraphView(id="graph")


@pytest.mark.asyncio
async def test_plot_series_single_series_does_not_raise() -> None:
    app = _GraphOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)
        graph.plot_series([("Total", [0.0, 1.0, 2.0], [10.0, 20.0, 30.0])], "%")
        await pilot.pause()


@pytest.mark.asyncio
async def test_plot_series_multiple_series_does_not_raise() -> None:
    app = _GraphOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)
        graph.plot_series(
            [
                ("Read", [0.0, 1.0], [100.0, 200.0]),
                ("Write", [0.0, 1.0], [50.0, 80.0]),
            ],
            "bytes/s",
        )
        await pilot.pause()


@pytest.mark.asyncio
async def test_plot_series_empty_does_not_raise() -> None:
    app = _GraphOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)
        graph.plot_series([], "")
        await pilot.pause()


@pytest.mark.asyncio
async def test_plot_series_skips_series_with_no_points() -> None:
    app = _GraphOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)
        # 空のtimes(データ無し)を含む系列はスキップされ、例外にならないこと
        graph.plot_series([("Empty", [], []), ("Data", [0.0, 1.0], [1.0, 2.0])], "%")
        await pilot.pause()


@pytest.mark.asyncio
async def test_graph_view_fills_container_height() -> None:
    app = _GraphOnlyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)
        assert graph.size.height > 1


# --- _segments() の純関数テスト ---


def test_segments_no_gaps_returns_single_segment() -> None:
    assert _segments([0.0, 1.0, 2.0], [1.0, 2.0, 3.0]) == [([0.0, 1.0, 2.0], [1.0, 2.0, 3.0])]


def test_segments_splits_on_middle_none() -> None:
    result = _segments([0.0, 1.0, 2.0, 3.0], [1.0, None, 3.0, 4.0])
    assert result == [([0.0], [1.0]), ([2.0, 3.0], [3.0, 4.0])]


def test_segments_ignores_leading_and_trailing_none() -> None:
    result = _segments([0.0, 1.0, 2.0, 3.0], [None, 2.0, 3.0, None])
    assert result == [([1.0, 2.0], [2.0, 3.0])]


def test_segments_all_none_returns_no_segments() -> None:
    assert _segments([0.0, 1.0], [None, None]) == []


def test_segments_empty_input_returns_no_segments() -> None:
    assert _segments([], []) == []


def test_segments_multiple_gaps() -> None:
    result = _segments([0.0, 1.0, 2.0, 3.0, 4.0], [1.0, None, 3.0, None, 5.0])
    assert result == [([0.0], [1.0]), ([2.0], [3.0]), ([4.0], [5.0])]


# --- plot_series()がNoneで線を分割することの回帰テスト ---


@pytest.mark.asyncio
async def test_plot_series_splits_line_at_none_gaps_and_labels_only_first_segment() -> None:
    app = _GraphOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        calls: list[tuple[list[float], list[float], str | None]] = []
        original_plot = graph.plt.plot

        def spy_plot(x, y, *, label=None, color=None, **kwargs):
            calls.append((list(x), list(y), label))
            return original_plot(x, y, label=label, color=color, **kwargs)

        graph.plt.plot = spy_plot

        graph.plot_series([("CPU", [0.0, 1.0, 2.0, 3.0], [1.0, None, 3.0, 4.0])], "%")
        await pilot.pause()

        assert len(calls) == 2  # Noneで2セグメントに分割される
        assert calls[0] == ([0.0], [1.0], "CPU")  # 先頭セグメントだけラベル(凡例)を持つ
        assert calls[1] == ([2.0, 3.0], [3.0, 4.0], None)


# --- 単一点(またはNoneのみ)でX軸が負範囲にならないことの回帰テスト ---


@pytest.mark.asyncio
async def test_plot_series_single_point_does_not_produce_negative_xlim() -> None:
    app = _GraphOnlyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        graph.plot_series([("Total", [0.0], [42.0])], "%")
        await pilot.pause()

        graph.plt.plotsize(80, 20)
        built = _strip_ansi(graph.plt.build())
        assert "-1.00" not in built
        assert "-0.5" not in built


# --- item7: 描画結果(凡例ラベル・軸範囲)がplt.build()の出力に反映されることのassert ---


@pytest.mark.asyncio
async def test_plot_series_build_output_contains_legend_label_and_value_range() -> None:
    app = _GraphOnlyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        graph.plot_series([("MyLabel", [0.0, 1.0, 2.0], [10.0, 20.0, 30.0])], "percent-unit")
        await pilot.pause()

        graph.plt.plotsize(80, 20)
        built = _strip_ansi(graph.plt.build())

        assert "MyLabel" in built  # 凡例ラベル
        assert "30" in built  # Y軸目盛りに最大値付近が現れる(0始まりのため整数刻み表記になる)
        assert "percent-unit" in built  # 単位ラベル


@pytest.mark.asyncio
async def test_plot_series_y_axis_starts_at_zero_even_when_data_does_not() -> None:
    """全系列が%かbytes/sで負値を取らない前提のもと、Y軸下限を0に固定する
    (データが10〜30のように0から離れていても、目盛りの下端が0になること)。
    """
    app = _GraphOnlyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        graph.plot_series([("MyLabel", [0.0, 1.0, 2.0], [40.0, 50.0, 60.0])], "%")
        await pilot.pause()

        graph.plt.plotsize(80, 20)
        built = _strip_ansi(graph.plt.build())
        lines = built.splitlines()

        # Y軸目盛りに"0┤"の行が現れる(データが40〜60でも下限が0に固定されていること)
        assert any(line.lstrip().startswith("0┤") for line in lines)


@pytest.mark.asyncio
async def test_plot_series_calls_ylim_with_zero_lower_bound_and_auto_upper() -> None:
    """plot_series()がplt.ylim(0, None)を呼んでいることを、build()の見た目ではなく
    実際の呼び出し引数で直接確認する(表示経路のテストとは独立した回帰チェック)。
    """
    app = _GraphOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        calls: list[tuple] = []
        original_ylim = graph.plt.ylim

        def spy_ylim(*args, **kwargs):
            calls.append(args)
            return original_ylim(*args, **kwargs)

        graph.plt.ylim = spy_ylim

        graph.plot_series([("MyLabel", [0.0, 1.0, 2.0], [10.0, 20.0, 30.0])], "%")
        await pilot.pause()

        assert calls == [(0, None)]


@pytest.mark.asyncio
async def test_plot_series_all_none_values_does_not_raise_with_ylim_fixed() -> None:
    """全点がNone(観測データ無し)の系列でも、ylim(0, None)呼び出し込みでplot_series()と
    build()が例外にならないことの回帰テスト(_segments()が空リストを返すケース)。
    """
    app = _GraphOnlyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        graph.plot_series([("Empty", [0.0, 1.0, 2.0], [None, None, None])], "%")
        await pilot.pause()

        graph.plt.plotsize(80, 20)
        built = graph.plt.build()  # 例外にならないことが本体
        assert isinstance(built, str)


@pytest.mark.asyncio
async def test_plot_series_build_output_contains_both_series_labels() -> None:
    app = _GraphOnlyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        graph = app.query_one("#graph", LineGraphView)

        graph.plot_series(
            [
                ("Read", [0.0, 1.0], [100.0, 200.0]),
                ("Write", [0.0, 1.0], [10.0, 20.0]),
            ],
            "bytes/s",
        )
        await pilot.pause()

        graph.plt.plotsize(80, 20)
        built = _strip_ansi(graph.plt.build())

        assert "Read" in built
        assert "Write" in built
        assert "bytes/s" in built
