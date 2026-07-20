from sysdash.collectors.cpu import CpuCollector
from tests.fakes import FakeCpuBackend


def test_reports_total_and_per_core_samples() -> None:
    collector = CpuCollector(backend=FakeCpuBackend(per_core=[10.0, 30.0]))
    samples = collector.collect()

    total = next(s for s in samples if s.name == "cpu.total")
    assert total.value == 20.0

    cores = [s for s in samples if s.name == "cpu.core"]
    assert len(cores) == 2
    assert {c.labels["core"] for c in cores} == {"0", "1"}


def test_handles_differing_core_counts() -> None:
    collector = CpuCollector(backend=FakeCpuBackend(per_core=[5.0] * 8))
    samples = collector.collect()
    cores = [s for s in samples if s.name == "cpu.core"]
    assert len(cores) == 8


def test_single_core_machine() -> None:
    collector = CpuCollector(backend=FakeCpuBackend(per_core=[99.0]))
    samples = collector.collect()
    total = next(s for s in samples if s.name == "cpu.total")
    assert total.value == 99.0


def test_backend_failure_yields_na_sample_only() -> None:
    collector = CpuCollector(backend=FakeCpuBackend(raise_error=True))
    samples = collector.collect()
    assert len(samples) == 1
    assert samples[0].name == "cpu.total"
    assert samples[0].value is None
