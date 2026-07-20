from __future__ import annotations

import time
from typing import Any

import psutil

from sysdash.core.models import MetricSample
from sysdash.core.rate import RateCalculator


class NetworkCollector:
    """NIC毎の送受信レートを収集する。速度は累積カウンタの差分のため RateCalculator に委譲する。"""

    name = "network"

    def __init__(self, backend: Any = psutil, rate_calculator: RateCalculator | None = None) -> None:
        self._backend = backend
        self._rates = rate_calculator or RateCalculator()
        self._last_nic_keys: set[str] = set()

    def collect(self) -> list[MetricSample]:
        now = time.time()
        try:
            io_counters = self._backend.net_io_counters(pernic=True) or {}
        except Exception:
            # 直前まで存在したNICはN/Aサンプルとして継続表示する(値欠損=N/A規約)。
            # 一度も成功していなければ_last_nic_keysは空のままなので、従来通り何も返さない。
            return [
                MetricSample(name=metric_name, timestamp=now, value=None, unit="bytes/s", labels={"nic": nic_name})
                for nic_name in sorted(self._last_nic_keys)
                for metric_name in ("network.sent_rate", "network.recv_rate")
            ]

        self._last_nic_keys = set(io_counters)
        self._rates.prune(f"{nic_name}:{kind}" for nic_name in io_counters for kind in ("sent", "recv"))

        # 全NICで同一時刻を使い、系列間で速度計算の基準がずれないようにする
        rate_now = self._rates.now()
        samples: list[MetricSample] = []
        for nic_name, counters in io_counters.items():
            sent_rate = self._rates.compute(f"{nic_name}:sent", counters.bytes_sent, now=rate_now)
            recv_rate = self._rates.compute(f"{nic_name}:recv", counters.bytes_recv, now=rate_now)
            samples.append(
                MetricSample(
                    name="network.sent_rate",
                    timestamp=now,
                    value=sent_rate,
                    unit="bytes/s",
                    labels={"nic": nic_name},
                )
            )
            samples.append(
                MetricSample(
                    name="network.recv_rate",
                    timestamp=now,
                    value=recv_rate,
                    unit="bytes/s",
                    labels={"nic": nic_name},
                )
            )
        return samples
