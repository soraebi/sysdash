from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass
class _LastSample:
    timestamp: float
    value: float


class RateCalculator:
    """累積カウンタ(ディスクI/O・ネットワーク送受信量など)から速度(単位/秒)を算出する。

    初回サンプル・カウンタリセット(値の減少)・巻き戻り呼び出しはいずれも None を返す
    (算出不能、UI側は"—"表示)。キー単位で独立して前回値を保持するため、ディスク/NICの
    増減にも個別に追従する。
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last: dict[str, _LastSample] = {}

    def compute(self, key: str, value: float, now: float | None = None) -> float | None:
        if now is None:
            now = self._clock()

        previous = self._last.get(key)
        if previous is None:
            self._last[key] = _LastSample(timestamp=now, value=value)
            return None

        elapsed = now - previous.timestamp
        if elapsed <= 0:
            # 巻き戻り呼び出しでは基準点を更新しない(次回以降の算出基準がずれるため)。
            return None

        self._last[key] = _LastSample(timestamp=now, value=value)

        delta = value - previous.value
        if delta < 0:
            return None

        return delta / elapsed

    def now(self) -> float:
        """collect()内で複数系列に同一時刻を使い回すための1回読み。"""
        return self._clock()

    def prune(self, active_keys: Iterable[str]) -> None:
        """active_keysに含まれないキーの基準点を捨てる(消滅したディスク/NIC分の掃除)。

        1インスタンスは1collectorが専有する前提。複数collectorで共有すると、
        互いに無関係なキー集合でpruneし合い、相手側の基準点を誤って消してしまう。
        """
        active = set(active_keys)
        for key in list(self._last):
            if key not in active:
                del self._last[key]
