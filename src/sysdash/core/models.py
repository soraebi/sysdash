from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class MetricSample:
    """1回の収集で得られる単一メトリクス値。

    value が None の場合はその項目が取得できなかったことを表す(UI側はN/A表示)。
    """

    name: str
    timestamp: float
    value: float | None
    unit: str
    labels: Mapping[str, str] = field(default_factory=dict)

    @property
    def series_key(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        """name+labelsで一意な系列を識別するキー(historyの系列分けに使用)。"""
        return (self.name, tuple(sorted(self.labels.items())))
