from __future__ import annotations

from typing import Sequence

from textual_plotext import PlotextPlot

from sysdash.core.i18n import t

# ダークテーマでも視認しやすい2系列用の配色(Read/Sent, Write/Recv)
SERIES_COLORS: tuple[str, ...] = ("cyan", "orange")


def _segments(
    times: Sequence[float], values: Sequence[float | None]
) -> list[tuple[list[float], list[float]]]:
    """valuesの連続したNoneでない区間ごとに(times, values)のセグメントへ分割する純関数。

    Noneを挟むと別セグメントになり、折れ線として繋がらない(観測していない期間を線で
    跨がないようにするため)。
    """
    segments: list[tuple[list[float], list[float]]] = []
    current_times: list[float] = []
    current_values: list[float] = []
    for t, v in zip(times, values):
        if v is None:
            if current_times:
                segments.append((current_times, current_values))
                current_times, current_values = [], []
            continue
        current_times.append(t)
        current_values.append(v)
    if current_times:
        segments.append((current_times, current_values))
    return segments


class LineGraphView(PlotextPlot):
    """textual-plotextベースの折れ線グラフ。複数系列(色分け+凡例)に対応する。"""

    # グラフの操作はGraphScreenのキーバインド(escape/left/right)で完結し、
    # このウィジェット自体にフォーカスは不要なため明示的にFalseにする
    # (PlotextPlotの基底Widgetクラスの既定値もFalseだが、意図を明文化するため)。
    can_focus = False

    def plot_series(self, series: Sequence[tuple[str, Sequence[float], Sequence[float | None]]], unit: str) -> None:
        """seriesは(ラベル, 経過秒(右端が現在), 値)のリスト。

        値にNoneを含めると、その時点で線を分割して描画する(一時停止・カウンタリセット等で
        観測できていない期間を折れ線で繋がないようにするため)。系列毎に独立した点数を許容する。
        """
        self.plt.clear_data()
        all_times: list[float] = []
        for index, (label, times, values) in enumerate(series):
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            first_segment = True
            for seg_times, seg_values in _segments(times, values):
                self.plt.plot(seg_times, seg_values, label=label if first_segment else None, color=color)
                first_segment = False
                all_times.extend(seg_times)

        if len(set(all_times)) <= 1:
            # 点が1つ(またはゼロ)だと、plotextが経過秒の負範囲を自動生成することがあるため固定する
            self.plt.xlim(0, 1)

        # sysdashの系列はすべて%かbytes/sで負値を取らないため、Y軸下限を0に固定する
        # (上限はNoneのままにしてplotextの自動スケールに任せる)。
        self.plt.ylim(0, None)

        self.plt.xlabel(t("graph.xlabel"))
        self.plt.ylabel(unit)
        self.refresh()
