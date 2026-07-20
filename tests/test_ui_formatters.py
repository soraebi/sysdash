from sysdash.core.history import SeriesKey
from sysdash.core.models import MetricSample
from sysdash.ui.app import (
    GraphSeriesGroup,
    _build_cpu_rows,
    _build_disk_rows,
    _build_memory_rows,
    _build_network_rows,
    _disk_graph_groups,
    _fmt_bytes,
    _fmt_percent,
    _fmt_rate,
    _format_stat_value,
    _humanize_bytes,
)
from sysdash.ui.widgets.metric_panel import NA_TEXT, render_bar


def test_humanize_bytes_below_1024_stays_in_bytes() -> None:
    assert _humanize_bytes(1023) == "1023.0B"


def test_humanize_bytes_at_1024_boundary_rolls_over_to_kb() -> None:
    assert _humanize_bytes(1024) == "1.0KB"


def test_humanize_bytes_mb_boundary() -> None:
    assert _humanize_bytes(1024 * 1024) == "1.0MB"


def test_humanize_bytes_caps_at_tb_for_huge_values() -> None:
    huge = 1024**5  # PB相当の値でもTB表記で頭打ちにする
    result = _humanize_bytes(huge)
    assert result.endswith("TB")


def test_fmt_percent_na_on_none() -> None:
    assert _fmt_percent(None) == NA_TEXT
    assert _fmt_percent(12.34) == "12.3%"


def test_fmt_bytes_na_on_none() -> None:
    assert _fmt_bytes(None) == NA_TEXT
    assert _fmt_bytes(2048) == "2.0KB"


def test_fmt_rate_dash_on_none() -> None:
    assert _fmt_rate(None) == "—"
    assert _fmt_rate(1024) == "1.0KB/s"


def test_format_stat_value_by_unit() -> None:
    assert _format_stat_value(5.0, "%") == "5.0%"
    assert _format_stat_value(1024.0, "bytes/s") == "1.0KB/s"
    assert _format_stat_value(3.0, "") == "3.0"


def test_render_bar_clamps_out_of_range_percent() -> None:
    full_width_low = render_bar(-10.0, width=10)
    full_width_high = render_bar(150.0, width=10)
    assert full_width_low == "░" * 10
    assert full_width_high == "█" * 10


def test_render_bar_none_percent_is_empty() -> None:
    assert render_bar(None) == ""


def _sample(name: str, value: float | None, unit: str = "%", **labels: str) -> MetricSample:
    return MetricSample(name=name, timestamp=0.0, value=value, unit=unit, labels=labels)


def test_build_cpu_rows_includes_total_and_sorted_cores() -> None:
    samples = [
        _sample("cpu.total", 42.0),
        _sample("cpu.core", 10.0, core="1"),
        _sample("cpu.core", 90.0, core="0"),
    ]
    rows = _build_cpu_rows(samples)
    assert [row.label for row in rows] == ["Total", "Core 0", "Core 1"]
    assert rows[0].text == "42.0%"


def test_build_memory_rows_appends_percent_alongside_bytes() -> None:
    samples = [
        _sample("memory.percent", 55.5),
        _sample("memory.used", 4 * 1024**3, unit="bytes"),
        _sample("memory.total", 8 * 1024**3, unit="bytes"),
        _sample("memory.swap_percent", 1.2),
    ]
    rows = _build_memory_rows(samples)
    used_row = next(row for row in rows if row.label == "Used")
    assert "55.5%" in used_row.text  # percentがバーだけでなくテキストにも併記される
    assert used_row.percent == 55.5


def test_build_disk_rows_groups_usage_and_rate_by_key() -> None:
    samples = [
        _sample("disk.usage_percent", 70.0, unit="%", mount="C:\\"),
        _sample("disk.read_rate", 1024.0, unit="bytes/s", disk="disk0"),
        _sample("disk.write_rate", None, unit="bytes/s", disk="disk0"),
    ]
    rows = _build_disk_rows(samples)
    labels = [row.label for row in rows]
    assert "C:\\" in labels
    assert "disk0 R/W" in labels
    rw_row = next(row for row in rows if row.label == "disk0 R/W")
    assert "—" in rw_row.text  # write_rateがNoneなので—表示


def test_build_network_rows_groups_sent_and_recv_by_nic() -> None:
    samples = [
        _sample("network.sent_rate", 2048.0, unit="bytes/s", nic="eth0"),
        _sample("network.recv_rate", 4096.0, unit="bytes/s", nic="eth0"),
    ]
    rows = _build_network_rows(samples)
    assert len(rows) == 1
    assert rows[0].label == "eth0"
    assert "↑" in rows[0].text and "↓" in rows[0].text


def test_graph_series_group_key_differs_for_same_title_different_series() -> None:
    """titleは表示専用のラベルで一意性を保証しないため、選択追跡には系列キー由来のkeyを使う。
    同じtitleでも系列が違えばkeyは別物になることを確認する。
    """
    key_a: SeriesKey = ("disk.usage_percent", (("mount", "C:\\"),))
    key_b: SeriesKey = ("disk.usage_percent", (("mount", "D:\\"),))
    group_a = GraphSeriesGroup(title="Usage", unit="%", series=(("Usage", key_a),))
    group_b = GraphSeriesGroup(title="Usage", unit="%", series=(("Usage", key_b),))

    assert group_a.title == group_b.title
    assert group_a.key != group_b.key


def test_graph_series_group_key_reflects_all_series_in_a_pair() -> None:
    read_key: SeriesKey = ("disk.read_rate", (("disk", "disk0"),))
    write_key: SeriesKey = ("disk.write_rate", (("disk", "disk0"),))
    group = GraphSeriesGroup(
        title="disk0 R/W", unit="bytes/s", series=(("Read", read_key), ("Write", write_key))
    )
    assert group.key == (read_key, write_key)


def test_disk_graph_groups_no_longer_include_usage() -> None:
    """ディスクのグラフ画面は各ディスクのRead/Write速度のみを対象にする(使用率は非対象)。
    ダッシュボードパネルの使用率表示(_build_disk_rows)には影響しない。
    """
    samples = [
        _sample("disk.usage_percent", 50.0, unit="%", mount="C:\\"),
        _sample("disk.read_rate", 1024.0, unit="bytes/s", disk="disk0"),
        _sample("disk.write_rate", 512.0, unit="bytes/s", disk="disk0"),
    ]
    groups = _disk_graph_groups(samples)

    assert len(groups) == 1
    assert groups[0].title == "disk0 R/W"
    assert not any("Usage" in group.title for group in groups)
    assert [label for label, _ in groups[0].series] == ["Read", "Write"]

    # ダッシュボードパネルの使用率表示は現状維持
    rows = _build_disk_rows(samples)
    assert any(row.label == "C:\\" for row in rows)
