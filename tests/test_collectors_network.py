from sysdash.collectors.network import NetworkCollector
from sysdash.core.rate import RateCalculator
from tests.fakes import FakeNetworkBackend, make_clock


def test_reports_sent_and_recv_rate_labels_per_nic() -> None:
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000), "wlan0": (500, 500)})
    collector = NetworkCollector(backend=backend)
    samples = collector.collect()

    nics = {s.labels["nic"] for s in samples}
    assert nics == {"eth0", "wlan0"}


def test_no_nics_returns_empty_list_without_error() -> None:
    backend = FakeNetworkBackend(counters={})
    collector = NetworkCollector(backend=backend)
    samples = collector.collect()
    assert samples == []


def test_first_sample_rate_is_none_second_is_numeric() -> None:
    # make_clock は呼ぶ度に1.0ずつ進む。collect()内では now() を1回しか読まないため、
    # 1回目のcollect()で1.0、2回目のcollect()で2.0が基準時刻になる(経過1.0秒)。
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000)})
    collector = NetworkCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))

    first = collector.collect()
    sent_first = next(s for s in first if s.name == "network.sent_rate")
    assert sent_first.value is None

    backend.counters = {"eth0": (3000, 6000)}
    second = collector.collect()
    sent_second = next(s for s in second if s.name == "network.sent_rate")
    recv_second = next(s for s in second if s.name == "network.recv_rate")
    assert sent_second.value == 2000.0  # (3000-1000) / 1.0
    assert recv_second.value == 4000.0  # (6000-2000) / 1.0


def test_multiple_nics_in_one_collect_share_the_same_clock_reading() -> None:
    """1回のcollect()内で複数NICのレートを算出しても、基準時刻が1回読みで揃うことを確認する。"""
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000), "wlan0": (500, 500)})
    collector = NetworkCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))
    collector.collect()  # 基準時刻 now=1.0

    backend.counters = {"eth0": (3000, 6000), "wlan0": (2500, 2500)}
    samples = collector.collect()  # 基準時刻 now=2.0(1回読み)

    sent = {s.labels["nic"]: s.value for s in samples if s.name == "network.sent_rate"}
    assert sent["eth0"] == 2000.0  # (3000-1000) / 1.0
    assert sent["wlan0"] == 2000.0  # (2500-500) / 1.0


def test_backend_failure_yields_empty_list() -> None:
    """diskのio失敗時と形状を揃え、不完全な単一サンプルではなく空リストを返す。"""
    backend = FakeNetworkBackend(raise_error=True)
    collector = NetworkCollector(backend=backend)
    samples = collector.collect()
    assert samples == []


def test_fetch_failure_after_success_yields_na_for_previously_known_nics() -> None:
    """取得自体(net_io_counters)が失敗しても、直前まで存在したNICは行が消えず
    N/A(value=None)として継続表示されることを確認する(値欠損=N/A規約との整合)。
    """
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000)})
    collector = NetworkCollector(backend=backend)
    collector.collect()  # 1回目: 成功しeth0のキーを記憶する

    backend.raise_error = True  # 2回目: 取得自体が失敗
    samples = collector.collect()

    sent = [s for s in samples if s.name == "network.sent_rate"]
    recv = [s for s in samples if s.name == "network.recv_rate"]
    assert len(sent) == 1 and sent[0].labels["nic"] == "eth0" and sent[0].value is None
    assert len(recv) == 1 and recv[0].labels["nic"] == "eth0" and recv[0].value is None


def test_fetch_failure_before_any_success_yields_empty_list() -> None:
    backend = FakeNetworkBackend(raise_error=True)
    collector = NetworkCollector(backend=backend)
    samples = collector.collect()
    assert samples == []


def test_prune_removes_rate_baseline_for_disappeared_nic() -> None:
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000), "wlan0": (500, 500)})
    collector = NetworkCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))
    collector.collect()  # t=1.0: 両NICの基準点を確立

    backend.counters = {"eth0": (2000, 4000)}  # wlan0が消える
    collector.collect()  # t=2.0

    # wlan0が再登場。pruneされていれば初回サンプル扱いになりNoneを返す。
    # pruneされていなければ古い基準点(500, t=1.0)を使って誤ったレートを算出してしまう。
    backend.counters = {"eth0": (3000, 6000), "wlan0": (800, 800)}
    samples = collector.collect()  # t=3.0

    wlan0_sent = next(s for s in samples if s.name == "network.sent_rate" and s.labels.get("nic") == "wlan0")
    assert wlan0_sent.value is None


def test_nic_removed_between_ticks_does_not_break_remaining_nic() -> None:
    backend = FakeNetworkBackend(counters={"eth0": (1000, 2000), "wlan0": (100, 100)})
    collector = NetworkCollector(backend=backend, rate_calculator=RateCalculator(clock=make_clock()))
    collector.collect()  # 基準時刻 now=1.0

    backend.counters = {"eth0": (2000, 4000)}  # wlan0 が消える(NIC無効化等を想定)
    samples = collector.collect()  # 基準時刻 now=2.0
    nics = {s.labels["nic"] for s in samples}
    assert nics == {"eth0"}
    sent = next(s for s in samples if s.name == "network.sent_rate")
    assert sent.value == 1000.0  # (2000-1000) / 1.0
