from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Iterable

from sysdash.core.models import MetricSample

DEFAULT_MAXLEN = 300

SeriesKey = tuple[str, tuple[tuple[str, str], ...]]


class HistoryStore:
    """メトリクス系列(name+labels)毎に maxlen 件のリングバッファで履歴を保持する。

    Sampler の SampleListener としてそのまま登録できる(__call__ = record)。
    record() はワーカースレッドから、get() 系はUIスレッドから並行して呼ばれるため
    Lock で相互排他し、get() 系は deque のコピー(list)を返して参照漏れを避ける。
    """

    def __init__(self, maxlen: int = DEFAULT_MAXLEN) -> None:
        self._maxlen = maxlen
        self._series: dict[SeriesKey, Deque[MetricSample]] = {}
        self._lock = threading.Lock()

    @property
    def maxlen(self) -> int:
        return self._maxlen

    def __call__(self, samples: Iterable[MetricSample]) -> None:
        self.record(samples)

    def record(self, samples: Iterable[MetricSample]) -> None:
        with self._lock:
            for sample in samples:
                key = sample.series_key
                series = self._series.get(key)
                if series is None:
                    series = deque(maxlen=self._maxlen)
                    self._series[key] = series
                series.append(sample)

    def get(self, name: str, labels: dict[str, str] | None = None) -> list[MetricSample]:
        key: SeriesKey = (name, tuple(sorted((labels or {}).items())))
        return self.get_by_key(key)

    def get_by_key(self, key: SeriesKey) -> list[MetricSample]:
        with self._lock:
            series = self._series.get(key)
            return list(series) if series is not None else []

    def keys(self) -> list[SeriesKey]:
        with self._lock:
            return list(self._series.keys())
