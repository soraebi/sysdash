from __future__ import annotations

import threading
import time
from typing import Callable, Iterable, List

from sysdash.collectors.base import Collector
from sysdash.core.models import MetricSample

MIN_INTERVAL = 0.5
MAX_INTERVAL = 10.0
DEFAULT_INTERVAL = 1.0

SampleListener = Callable[[List[MetricSample]], None]


def _clamp_interval(interval: float) -> float:
    return min(max(interval, MIN_INTERVAL), MAX_INTERVAL)


class Sampler:
    """collector群を定期的に回し、収集結果をリスナー群へ配信するポーリングループ。

    tick() は1回分の収集+配信を同期的に行う。run() は stop() が呼ばれるまで
    interval間隔でtick()を繰り返す(ワーカースレッドからの利用を想定)。
    """

    def __init__(
        self,
        collectors: Iterable[Collector],
        interval: float = DEFAULT_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._collectors = list(collectors)
        self.interval = _clamp_interval(interval)
        self._clock = clock
        self._listeners: list[SampleListener] = []
        self._stop_event = threading.Event()
        self._paused_event = threading.Event()
        self._wake_event = threading.Event()

    def add_listener(self, listener: SampleListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: SampleListener) -> None:
        self._listeners.remove(listener)

    def set_interval(self, interval: float) -> None:
        self.interval = _clamp_interval(interval)
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def pause(self) -> None:
        self._paused_event.set()
        self._wake_event.set()

    def resume(self) -> None:
        self._paused_event.clear()
        self._wake_event.set()

    @property
    def paused(self) -> bool:
        return self._paused_event.is_set()

    def tick(self) -> list[MetricSample]:
        """1回分の収集を実行し、リスナーへ配信して結果を返す。

        collector単位でtry/exceptする。1つのcollect()が例外を送出しても
        そのtickでは当該collectorをスキップし、他collectorの収集・配信は継続する。
        """
        samples: list[MetricSample] = []
        for collector in self._collectors:
            try:
                samples.extend(collector.collect())
            except Exception:
                continue
        self._dispatch(samples)
        return samples

    def _dispatch(self, samples: list[MetricSample]) -> None:
        for listener in list(self._listeners):
            try:
                listener(samples)
            except Exception:
                continue

    def run(self) -> None:
        """stop() が呼ばれるまで interval 間隔で tick() を繰り返す。pause中は tick() を呼ばない。

        待機は _wake_event で行い、stop/pause/resume/set_interval はいずれもこれをsetして
        待機中のrun()を即座に起こす(interval満了を待たせない)。
        """
        while not self._stop_event.is_set():
            start = self._clock()
            if not self._paused_event.is_set():
                self.tick()
            elapsed = self._clock() - start
            remaining = self.interval - elapsed
            if remaining > 0:
                self._wake_event.wait(remaining)
            self._wake_event.clear()
