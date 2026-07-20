import threading
import time

from sysdash.core.models import MetricSample
from sysdash.core.sampler import MAX_INTERVAL, MIN_INTERVAL, Sampler


class _CountingCollector:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def collect(self) -> list[MetricSample]:
        self.calls += 1
        return [MetricSample(name="fake.value", timestamp=0.0, value=float(self.calls), unit="")]


def test_tick_dispatches_samples_to_all_listeners() -> None:
    collector = _CountingCollector()
    sampler = Sampler([collector])
    received: list[list[MetricSample]] = []
    sampler.add_listener(received.append)

    samples = sampler.tick()

    assert collector.calls == 1
    assert samples[0].value == 1.0
    assert received == [samples]


class _RaisingCollector:
    name = "raising"

    def collect(self) -> list[MetricSample]:
        raise RuntimeError("collector boom")


def test_one_collector_raising_does_not_block_others() -> None:
    good = _CountingCollector()
    sampler = Sampler([_RaisingCollector(), good])

    samples = sampler.tick()  # 例外を投げても tick() 全体は落ちない(=隔離されている)こと自体が検証

    assert good.calls == 1
    assert samples == [MetricSample(name="fake.value", timestamp=0.0, value=1.0, unit="")]


def test_listener_exception_is_isolated() -> None:
    sampler = Sampler([_CountingCollector()])
    calls = []

    def bad_listener(_samples: list[MetricSample]) -> None:
        raise RuntimeError("boom")

    def good_listener(samples: list[MetricSample]) -> None:
        calls.append(samples)

    sampler.add_listener(bad_listener)
    sampler.add_listener(good_listener)

    sampler.tick()  # bad_listenerが例外を投げてもテストが落ちない(=隔離されている)こと自体が検証

    assert len(calls) == 1


def test_interval_is_clamped_to_minimum() -> None:
    sampler = Sampler([_CountingCollector()], interval=0.01)
    assert sampler.interval == MIN_INTERVAL


def test_interval_is_clamped_to_maximum() -> None:
    sampler = Sampler([_CountingCollector()], interval=999.0)
    assert sampler.interval == MAX_INTERVAL


def test_set_interval_clamps_both_bounds() -> None:
    sampler = Sampler([_CountingCollector()])
    sampler.set_interval(0.1)
    assert sampler.interval == MIN_INTERVAL
    sampler.set_interval(999.0)
    assert sampler.interval == MAX_INTERVAL
    sampler.set_interval(2.0)
    assert sampler.interval == 2.0


def test_run_polls_until_stopped() -> None:
    collector = _CountingCollector()
    sampler = Sampler([collector], interval=MIN_INTERVAL)

    thread = threading.Thread(target=sampler.run, daemon=True)
    thread.start()
    time.sleep(MIN_INTERVAL * 2.5)
    sampler.stop()
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert collector.calls >= 2


def test_pause_stops_ticking_and_resume_continues() -> None:
    collector = _CountingCollector()
    sampler = Sampler([collector], interval=MIN_INTERVAL)
    assert not sampler.paused

    thread = threading.Thread(target=sampler.run, daemon=True)
    thread.start()
    time.sleep(MIN_INTERVAL * 1.5)  # 少なくとも1tickは進める
    sampler.pause()
    assert sampler.paused
    calls_at_pause = collector.calls

    time.sleep(MIN_INTERVAL * 2.5)  # pause中はtickが進まないはず
    assert collector.calls == calls_at_pause

    sampler.resume()
    assert not sampler.paused
    time.sleep(MIN_INTERVAL * 1.5)
    sampler.stop()
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert collector.calls > calls_at_pause


def test_set_interval_wakes_a_long_blocked_wait_promptly() -> None:
    """待機中(interval満了待ち)にset_interval()で間隔を大きく縮めた場合、元のintervalが
    満了するまで待たされず、短縮後の間隔で次tickが起きることを実スレッドで決定的に確認する。
    """
    collector = _CountingCollector()
    sampler = Sampler([collector], interval=5.0)  # 長い間隔で待機に入らせる

    thread = threading.Thread(target=sampler.run, daemon=True)
    thread.start()
    time.sleep(0.1)  # 1tick目が終わり、5.0秒のwaitに入るのを待つ
    calls_before = collector.calls
    assert calls_before >= 1

    sampler.set_interval(MIN_INTERVAL)  # 5.0秒待たせず、すぐ短縮後の間隔で次tickさせる
    time.sleep(MIN_INTERVAL + 0.3)

    sampler.stop()
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert collector.calls > calls_before  # 5.0秒を待たずに次tickが発生していること
