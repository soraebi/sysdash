from __future__ import annotations

import time
from typing import Any

import psutil

from sysdash.core.models import MetricSample


class CpuCollector:
    """CPU使用率(合計・コア別)を収集する。psutil.cpu_percent(percpu=True) を1回呼び、
    合計値はコア別値の平均として算出する(合計とコア別で別々に呼ぶと瞬間値がずれるため)。
    """

    name = "cpu"

    def __init__(self, backend: Any = psutil) -> None:
        self._backend = backend

    def collect(self) -> list[MetricSample]:
        now = time.time()
        try:
            per_core = list(self._backend.cpu_percent(interval=None, percpu=True))
        except Exception:
            return [MetricSample(name="cpu.total", timestamp=now, value=None, unit="%")]

        samples: list[MetricSample] = []
        overall = sum(per_core) / len(per_core) if per_core else None
        samples.append(MetricSample(name="cpu.total", timestamp=now, value=overall, unit="%"))
        for index, value in enumerate(per_core):
            samples.append(
                MetricSample(
                    name="cpu.core",
                    timestamp=now,
                    value=value,
                    unit="%",
                    labels={"core": str(index)},
                )
            )
        return samples
