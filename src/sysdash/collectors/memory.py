from __future__ import annotations

import time
from typing import Any

import psutil

from sysdash.core.models import MetricSample


class MemoryCollector:
    """物理メモリ・スワップ使用率を収集する。両者は別APIのため項目単位で個別にtry/exceptする。"""

    name = "memory"

    def __init__(self, backend: Any = psutil) -> None:
        self._backend = backend

    def collect(self) -> list[MetricSample]:
        now = time.time()
        samples: list[MetricSample] = []

        try:
            vm = self._backend.virtual_memory()
            samples.append(MetricSample(name="memory.percent", timestamp=now, value=vm.percent, unit="%"))
            samples.append(MetricSample(name="memory.used", timestamp=now, value=vm.used, unit="bytes"))
            samples.append(MetricSample(name="memory.total", timestamp=now, value=vm.total, unit="bytes"))
        except Exception:
            samples.append(MetricSample(name="memory.percent", timestamp=now, value=None, unit="%"))

        try:
            swap = self._backend.swap_memory()
            samples.append(
                MetricSample(name="memory.swap_percent", timestamp=now, value=swap.percent, unit="%")
            )
        except Exception:
            samples.append(MetricSample(name="memory.swap_percent", timestamp=now, value=None, unit="%"))

        return samples
