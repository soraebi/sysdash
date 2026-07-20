from sysdash.collectors.memory import MemoryCollector
from tests.fakes import FakeMemoryBackend


def test_reports_percent_used_total_and_swap() -> None:
    collector = MemoryCollector(backend=FakeMemoryBackend(percent=60.0, used=6000, total=10000, swap_percent=1.5))
    samples = collector.collect()

    by_name = {s.name: s for s in samples}
    assert by_name["memory.percent"].value == 60.0
    assert by_name["memory.used"].value == 6000
    assert by_name["memory.total"].value == 10000
    assert by_name["memory.swap_percent"].value == 1.5


def test_virtual_memory_failure_reports_na_but_swap_continues() -> None:
    collector = MemoryCollector(backend=FakeMemoryBackend(raise_virtual=True, swap_percent=2.0))
    samples = collector.collect()

    by_name = {s.name: s for s in samples}
    assert by_name["memory.percent"].value is None
    assert by_name["memory.swap_percent"].value == 2.0


def test_swap_failure_reports_na_but_virtual_memory_continues() -> None:
    collector = MemoryCollector(backend=FakeMemoryBackend(raise_swap=True, percent=40.0))
    samples = collector.collect()

    by_name = {s.name: s for s in samples}
    assert by_name["memory.percent"].value == 40.0
    assert by_name["memory.swap_percent"].value is None
