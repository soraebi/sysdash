import pytest
from textual.app import App, ComposeResult
from textual.widgets import Sparkline, Static

from sysdash.ui.widgets.metric_panel import MetricPanel, MetricRow


class _PanelOnlyApp(App):
    def compose(self) -> ComposeResult:
        yield MetricPanel("Test", id="panel")


@pytest.mark.asyncio
async def test_panel_shows_placeholder_immediately_after_mount() -> None:
    """update_rows()を一度も呼ばない状態(起動直後・初回tick前)でも"…"のプレースホルダが
    表示されること。rowsのreactiveデフォルト(空タプル)に対するwatch_rowsはマウント前に
    発火して捨てられるため、on_mount()での再描画が効いていることの回帰確認。
    """
    app = _PanelOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)
        assert panel.query_one("#rows", Static).visual.plain == "…"


@pytest.mark.asyncio
async def test_labels_containing_markup_like_text_are_not_interpreted_as_markup() -> None:
    """collector由来のラベル(NIC名等)は環境依存の外部文字列であり、"[data]"や"[/]"
    のようなTextualマークアップに似た文字列を含んでいても、MarkupErrorにならず、
    かつブラケットの中身が消えずにそのまま表示されることを確認する。
    """
    app = _PanelOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        # 例外(MarkupError)が出ないこと自体が主眼の検証
        panel.update_rows(
            [
                MetricRow("eth0 [data]", "12.3%", 12.3),
                MetricRow("wlan0", "[/]broken", None),
            ]
        )
        await pilot.pause()

        plain_text = panel.query_one("#rows", Static).visual.plain
        assert "[data]" in plain_text
        assert "[/]broken" in plain_text


@pytest.mark.asyncio
async def test_update_sparkline_feeds_the_mini_sparkline_widget() -> None:
    app = _PanelOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        panel.update_sparkline([1.0, 2.0, 3.0])
        await pilot.pause()

        sparkline = panel.query_one("#sparkline", Sparkline)
        assert list(sparkline.data) == [1.0, 2.0, 3.0]


@pytest.mark.asyncio
async def test_multi_column_rows_lays_out_items_side_by_side_when_wide() -> None:
    app = _PanelOnlyApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        header = MetricRow("Total", "50.0%", 50.0)
        cores = [MetricRow(f"Core {i}", "10.0%", 10.0) for i in range(8)]
        panel.update_multi_column_rows(header, cores)
        await pilot.pause()

        text = panel.query_one("#rows", Static).visual.plain
        lines = text.splitlines()
        core_lines = [line for line in lines if "Core" in line]
        # 列優先で並べるため同居する組み合わせは幅依存だが、複数列になっていれば
        # 8コア分が8行より少ない行数に収まるはず
        assert 0 < len(core_lines) < len(cores)


@pytest.mark.asyncio
async def test_multi_column_rows_falls_back_to_single_column_when_compact() -> None:
    app = _PanelOnlyApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        header = MetricRow("Total", "50.0%", 50.0)
        cores = [MetricRow(f"Core {i}", "10.0%", 10.0) for i in range(8)]
        panel.update_multi_column_rows(header, cores)
        panel.compact = True
        await pilot.pause()

        text = panel.query_one("#rows", Static).visual.plain
        lines = text.splitlines()
        assert any(line.strip() == "Core 0: 10.0%" for line in lines)
        assert not any("Core 0" in line and "Core 1" in line for line in lines)


@pytest.mark.asyncio
async def test_update_rows_resets_multi_column_mode() -> None:
    """update_rows()(CPU以外のパネル用)を呼ぶと、直前がupdate_multi_column_rows()の
    状態でも単一列表示に戻ることを確認する。
    """
    app = _PanelOnlyApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        header = MetricRow("Total", "50.0%", 50.0)
        cores = [MetricRow(f"Core {i}", "10.0%", 10.0) for i in range(8)]
        panel.update_multi_column_rows(header, cores)
        await pilot.pause()
        assert panel.multi_column is True

        panel.update_rows([MetricRow("Used", "50.0%", 50.0)])
        await pilot.pause()
        assert panel.multi_column is False


@pytest.mark.asyncio
async def test_multi_column_rows_recompute_on_panel_resize() -> None:
    """update_multi_column_rows()を呼び直さなくても、パネル自体の幅が変わればon_resizeで
    列数が再計算されることを確認する(次tickのデータ更新を待たずに追従する回帰確認)。
    """
    app = _PanelOnlyApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        header = MetricRow("Total", "50.0%", 50.0)
        cores = [MetricRow(f"Core {i}", "10.0%", 10.0) for i in range(8)]
        panel.update_multi_column_rows(header, cores)
        await pilot.pause()

        text_wide = panel.query_one("#rows", Static).visual.plain
        core_lines_wide = [line for line in text_wide.splitlines() if "Core" in line]

        await pilot.resize_terminal(40, 30)  # update_multi_column_rows()は呼ばずに幅だけ変える
        await pilot.pause()

        text_narrow = panel.query_one("#rows", Static).visual.plain
        core_lines_narrow = [line for line in text_narrow.splitlines() if "Core" in line]

        # 列数が減れば行数は増えるはず(幅変化だけで再計算されている証拠)
        assert len(core_lines_narrow) > len(core_lines_wide)


@pytest.mark.asyncio
async def test_multi_column_rows_truncates_with_summary_when_too_many_for_height() -> None:
    """幅・高さともに小さいパネルに大量のコア(32個)を渡すと、パネル外へあふれず
    末尾が"+N cores"の省略サマリになることを確認する。
    """
    app = _PanelOnlyApp()
    async with app.run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        header = MetricRow("Total", "50.0%", 50.0)
        cores = [MetricRow(f"Core {i}", "10.0%", 10.0) for i in range(32)]
        panel.update_multi_column_rows(header, cores)
        await pilot.pause()

        text = panel.query_one("#rows", Static).visual.plain
        lines = text.splitlines()

        assert any("+" in line and "cores" in line for line in lines)
        # パネルの高さを超える行数にはならない(オーバーフローしない)
        assert len(lines) <= panel.size.height

        # コア表示がミニSparkline領域を侵食し、枠外にクリップしていないことも確認する
        sparkline = panel.query_one("#sparkline", Sparkline)
        panel_bottom = panel.content_region.y + panel.content_region.height
        sparkline_bottom = sparkline.region.y + sparkline.region.height
        assert sparkline_bottom <= panel_bottom


@pytest.mark.asyncio
async def test_compact_mode_hides_sparkline_via_css_class() -> None:
    app = _PanelOnlyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#panel", MetricPanel)

        panel.compact = True
        await pilot.pause()

        assert panel.has_class("-compact")
