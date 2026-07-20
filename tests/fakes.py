"""collectorテスト用のFakeBackend群。psutil相当の呼び出し形状のみを模倣する。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable


class FakeCpuBackend:
    def __init__(self, per_core: list[float] | None = None, raise_error: bool = False) -> None:
        self.per_core = [10.0, 20.0] if per_core is None else per_core
        self.raise_error = raise_error

    def cpu_percent(self, interval: float | None = None, percpu: bool = False) -> Any:
        if self.raise_error:
            raise RuntimeError("cpu_percent failed")
        if percpu:
            return list(self.per_core)
        return sum(self.per_core) / len(self.per_core) if self.per_core else 0.0


class FakeMemoryBackend:
    def __init__(
        self,
        percent: float = 50.0,
        used: int = 500,
        total: int = 1000,
        swap_percent: float = 5.0,
        raise_virtual: bool = False,
        raise_swap: bool = False,
    ) -> None:
        self.percent = percent
        self.used = used
        self.total = total
        self.swap_percent = swap_percent
        self.raise_virtual = raise_virtual
        self.raise_swap = raise_swap

    def virtual_memory(self) -> SimpleNamespace:
        if self.raise_virtual:
            raise RuntimeError("virtual_memory failed")
        return SimpleNamespace(percent=self.percent, used=self.used, total=self.total)

    def swap_memory(self) -> SimpleNamespace:
        if self.raise_swap:
            raise RuntimeError("swap_memory failed")
        return SimpleNamespace(percent=self.swap_percent)


class FakeDiskBackend:
    def __init__(
        self,
        mounts: list[str] | None = None,
        usage_percent: dict[str, float] | None = None,
        failing_mounts: set[str] | None = None,
        raise_partitions: bool = False,
        io_counters: dict[str, tuple[int, int]] | None = None,
        raise_io: bool = False,
    ) -> None:
        self.mounts = ["C:\\"] if mounts is None else mounts
        self.usage_percent = usage_percent or {mount: 42.0 for mount in self.mounts}
        self.failing_mounts = failing_mounts or set()
        self.raise_partitions = raise_partitions
        self.io_counters = io_counters or {"disk0": (1000, 2000)}
        self.raise_io = raise_io

    def disk_partitions(self, all: bool = False) -> list[SimpleNamespace]:
        if self.raise_partitions:
            raise RuntimeError("disk_partitions failed")
        return [SimpleNamespace(mountpoint=mount) for mount in self.mounts]

    def disk_usage(self, mount: str) -> SimpleNamespace:
        if mount in self.failing_mounts:
            raise RuntimeError(f"disk_usage failed for {mount}")
        return SimpleNamespace(percent=self.usage_percent.get(mount, 0.0))

    def disk_io_counters(self, perdisk: bool = False) -> dict[str, SimpleNamespace]:
        if self.raise_io:
            raise RuntimeError("disk_io_counters failed")
        return {
            name: SimpleNamespace(read_bytes=read, write_bytes=write)
            for name, (read, write) in self.io_counters.items()
        }


class FakeNetworkBackend:
    def __init__(
        self,
        counters: dict[str, tuple[int, int]] | None = None,
        raise_error: bool = False,
    ) -> None:
        self.counters = {"eth0": (1000, 2000)} if counters is None else counters
        self.raise_error = raise_error

    def net_io_counters(self, pernic: bool = False) -> dict[str, SimpleNamespace]:
        if self.raise_error:
            raise RuntimeError("net_io_counters failed")
        return {
            name: SimpleNamespace(bytes_sent=sent, bytes_recv=recv)
            for name, (sent, recv) in self.counters.items()
        }


def make_clock(start: float = 0.0) -> Callable[[], float]:
    """呼び出す度に1.0ずつ進む決定的なクロック(RateCalculatorの経過時間テスト用)。"""
    state = {"now": start}

    def clock() -> float:
        state["now"] += 1.0
        return state["now"]

    return clock
