from __future__ import annotations

import time
from typing import Any

import psutil

from sysdash.core.models import MetricSample
from sysdash.core.rate import RateCalculator


class DiskCollector:
    """マウント毎の使用率と、ディスク毎のR/W速度を収集する。

    使用率(disk_usage)はマウント単位、速度(disk_io_counters)はディスク単位で
    それぞれ独立に項目単位try/exceptする。速度は累積カウンタの差分のため RateCalculator に委譲する。
    """

    name = "disk"

    def __init__(self, backend: Any = psutil, rate_calculator: RateCalculator | None = None) -> None:
        self._backend = backend
        self._rates = rate_calculator or RateCalculator()
        self._last_disk_keys: set[str] = set()

    def collect(self) -> list[MetricSample]:
        now = time.time()
        return self._collect_usage(now) + self._collect_io(now)

    def _collect_usage(self, now: float) -> list[MetricSample]:
        try:
            partitions = self._backend.disk_partitions(all=False)
        except Exception:
            return [MetricSample(name="disk.usage_percent", timestamp=now, value=None, unit="%")]

        samples: list[MetricSample] = []
        for partition in partitions:
            mount = partition.mountpoint
            try:
                usage = self._backend.disk_usage(mount)
                value: float | None = usage.percent
            except Exception:
                value = None
            samples.append(
                MetricSample(
                    name="disk.usage_percent",
                    timestamp=now,
                    value=value,
                    unit="%",
                    labels={"mount": mount},
                )
            )
        return samples

    def _collect_io(self, now: float) -> list[MetricSample]:
        try:
            io_counters = self._backend.disk_io_counters(perdisk=True) or {}
        except Exception:
            # 直前まで存在したディスクはN/Aサンプルとして継続表示する(値欠損=N/A規約)。
            # 一度も成功していなければ_last_disk_keysは空のままなので、従来通り何も返さない。
            return [
                MetricSample(name=metric_name, timestamp=now, value=None, unit="bytes/s", labels={"disk": disk_name})
                for disk_name in sorted(self._last_disk_keys)
                for metric_name in ("disk.read_rate", "disk.write_rate")
            ]

        self._last_disk_keys = set(io_counters)
        self._rates.prune(f"{disk_name}:{kind}" for disk_name in io_counters for kind in ("read", "write"))

        # 全ディスクで同一時刻を使い、系列間で速度計算の基準がずれないようにする
        rate_now = self._rates.now()
        samples: list[MetricSample] = []
        for disk_name, counters in io_counters.items():
            read_rate = self._rates.compute(f"{disk_name}:read", counters.read_bytes, now=rate_now)
            write_rate = self._rates.compute(f"{disk_name}:write", counters.write_bytes, now=rate_now)
            samples.append(
                MetricSample(
                    name="disk.read_rate",
                    timestamp=now,
                    value=read_rate,
                    unit="bytes/s",
                    labels={"disk": disk_name},
                )
            )
            samples.append(
                MetricSample(
                    name="disk.write_rate",
                    timestamp=now,
                    value=write_rate,
                    unit="bytes/s",
                    labels={"disk": disk_name},
                )
            )
        return samples
