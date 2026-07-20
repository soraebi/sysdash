from __future__ import annotations

from typing import Protocol, runtime_checkable

from sysdash.core.models import MetricSample


@runtime_checkable
class Collector(Protocol):
    """メトリクス収集器の共通インターフェース。OS差分・バックエンド差分は実装側に隔離する。

    collect() は例外を外へ投げない契約とする。項目単位で失敗した場合は
    value=None の MetricSample を返し、他項目は継続する。
    """

    name: str

    def collect(self) -> list[MetricSample]: ...
