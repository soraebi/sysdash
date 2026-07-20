from sysdash.collectors.disk import DiskCollector
from sysdash.core.rate import RateCalculator
from tests.fakes import FakeDiskBackend, make_clock


def test_reports_usage_per_mount() -> None:
    backend = FakeDiskBackend(mounts=["C:\\", "D:\\"], usage_percent={"C:\\": 10.0, "D:\\": 90.0})
    collector = DiskCollector(backend=backend)
    samples = collector.collect()

    usages = {s.labels["mount"]: s.value for s in samples if s.name == "disk.usage_percent"}
    assert usages == {"C:\\": 10.0, "D:\\": 90.0}


def test_one_failing_mount_does_not_affect_others() -> None:
    backend = FakeDiskBackend(mounts=["C:\\", "D:\\"], failing_mounts={"D:\\"})
    collector = DiskCollector(backend=backend)
    samples = collector.collect()

    usages = {s.labels["mount"]: s.value for s in samples if s.name == "disk.usage_percent"}
    assert usages["C:\\"] is not None
    assert usages["D:\\"] is None


def test_partitions_enumeration_failure_yields_single_na_sample() -> None:
    backend = FakeDiskBackend(raise_partitions=True)
    collector = DiskCollector(backend=backend)
    samples = collector.collect()

    usage_samples = [s for s in samples if s.name == "disk.usage_percent"]
    assert len(usage_samples) == 1
    assert usage_samples[0].value is None


def test_io_rate_is_none_on_first_sample_then_numeric_on_second() -> None:
    # make_clock は呼ぶ度に1.0ずつ進む。collect()内では now() を1回しか読まないため、
    # 1回目のcollect()で1.0、2回目のcollect()で2.0が基準時刻になる(経過1.0秒)。
    backend = FakeDiskBackend(io_counters={"disk0": (1000, 2000)})
    collector = DiskCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))

    first = collector.collect()
    reads = [s for s in first if s.name == "disk.read_rate"]
    assert reads[0].value is None

    backend.io_counters = {"disk0": (2000, 4000)}
    second = collector.collect()
    reads2 = [s for s in second if s.name == "disk.read_rate"]
    writes2 = [s for s in second if s.name == "disk.write_rate"]
    assert reads2[0].value == 1000.0  # (2000-1000) / 1.0
    assert writes2[0].value == 2000.0  # (4000-2000) / 1.0


def test_multiple_disks_in_one_collect_share_the_same_clock_reading() -> None:
    """1回のcollect()内で複数ディスクのレートを算出しても、基準時刻が1回読みで揃うことを確認する。"""
    backend = FakeDiskBackend(io_counters={"disk0": (1000, 2000), "disk1": (500, 500)})
    collector = DiskCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))
    collector.collect()  # 基準時刻 now=1.0

    backend.io_counters = {"disk0": (3000, 6000), "disk1": (2500, 2500)}
    samples = collector.collect()  # 基準時刻 now=2.0(1回読み)

    reads = {s.labels["disk"]: s.value for s in samples if s.name == "disk.read_rate"}
    assert reads["disk0"] == 2000.0  # (3000-1000) / 1.0
    assert reads["disk1"] == 2000.0  # (2500-500) / 1.0


def test_io_counters_failure_does_not_affect_usage() -> None:
    backend = FakeDiskBackend(raise_io=True, mounts=["C:\\"])
    collector = DiskCollector(backend=backend)
    samples = collector.collect()

    assert any(s.name == "disk.usage_percent" and s.value is not None for s in samples)
    assert not any(s.name == "disk.read_rate" for s in samples)


def test_io_failure_after_success_yields_na_for_previously_known_disks() -> None:
    """取得自体(disk_io_counters)が失敗しても、直前まで存在したディスクは行が消えず
    N/A(value=None)として継続表示されることを確認する(値欠損=N/A規約との整合)。
    """
    backend = FakeDiskBackend(io_counters={"disk0": (1000, 2000)})
    collector = DiskCollector(backend=backend)
    collector.collect()  # 1回目: 成功しdisk0のキーを記憶する

    backend.raise_io = True  # 2回目: 取得自体が失敗
    samples = collector.collect()

    reads = [s for s in samples if s.name == "disk.read_rate"]
    writes = [s for s in samples if s.name == "disk.write_rate"]
    assert len(reads) == 1 and reads[0].labels["disk"] == "disk0" and reads[0].value is None
    assert len(writes) == 1 and writes[0].labels["disk"] == "disk0" and writes[0].value is None


def test_io_failure_before_any_success_yields_no_rate_samples() -> None:
    backend = FakeDiskBackend(raise_io=True)
    collector = DiskCollector(backend=backend)
    samples = collector.collect()
    assert not any(s.name in ("disk.read_rate", "disk.write_rate") for s in samples)


def test_prune_removes_rate_baseline_for_disappeared_disk() -> None:
    backend = FakeDiskBackend(io_counters={"disk0": (1000, 2000), "disk1": (500, 500)})
    collector = DiskCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))
    collector.collect()  # t=1.0: 両ディスクの基準点を確立

    backend.io_counters = {"disk0": (2000, 4000)}  # disk1が消える(io_counters圏外)
    collector.collect()  # t=2.0

    # disk1が再登場。pruneされていれば初回サンプル扱いになりNoneを返す。
    # pruneされていなければ古い基準点(500, t=1.0)を使って誤ったレートを算出してしまう。
    backend.io_counters = {"disk0": (3000, 6000), "disk1": (800, 800)}
    samples = collector.collect()  # t=3.0

    disk1_read = next(s for s in samples if s.name == "disk.read_rate" and s.labels.get("disk") == "disk1")
    assert disk1_read.value is None


def test_usage_and_io_use_independent_key_spaces() -> None:
    """マウント表記(usage側)とディスク名(io側)が別々のラベルキーで管理されることを確認する。"""
    backend = FakeDiskBackend(mounts=["/"], usage_percent={"/": 50.0}, io_counters={"nvme0": (0, 0)})
    collector = DiskCollector(backend=backend)
    samples = collector.collect()

    assert any(s.labels.get("mount") == "/" for s in samples if s.name == "disk.usage_percent")
    assert any(s.labels.get("disk") == "nvme0" for s in samples if s.name == "disk.read_rate")
