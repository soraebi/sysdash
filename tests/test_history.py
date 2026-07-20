import threading
import time

from sysdash.core.history import HistoryStore
from sysdash.core.models import MetricSample


def make_sample(value: float, labels: dict[str, str] | None = None) -> MetricSample:
    return MetricSample(name="cpu.total", timestamp=0.0, value=value, unit="%", labels=labels or {})


def test_ring_buffer_respects_maxlen() -> None:
    history = HistoryStore(maxlen=3)
    for i in range(5):
        history.record([make_sample(float(i))])

    values = [s.value for s in history.get("cpu.total")]
    assert values == [2.0, 3.0, 4.0]


def test_different_labels_are_independent_series() -> None:
    history = HistoryStore(maxlen=10)
    history.record([make_sample(1.0, labels={"core": "0"})])
    history.record([make_sample(2.0, labels={"core": "1"})])

    assert [s.value for s in history.get("cpu.total", {"core": "0"})] == [1.0]
    assert [s.value for s in history.get("cpu.total", {"core": "1"})] == [2.0]


def test_unknown_series_returns_empty_list() -> None:
    history = HistoryStore()
    assert history.get("does.not.exist") == []


def test_usable_as_sampler_listener_via_call() -> None:
    history = HistoryStore()
    history([make_sample(1.0)])
    assert [s.value for s in history.get("cpu.total")] == [1.0]


def test_get_returns_a_copy_not_the_live_deque() -> None:
    history = HistoryStore()
    history.record([make_sample(1.0)])
    snapshot = history.get("cpu.total")
    snapshot.append(make_sample(999.0))
    assert [s.value for s in history.get("cpu.total")] == [1.0]


def test_concurrent_record_from_multiple_threads_does_not_lose_samples() -> None:
    """recordはSamplerのワーカースレッドから、getはUIスレッドから呼ばれる想定のため、
    Lockで保護されており並行呼び出しでもサンプルを取りこぼさないことを簡易に確認する。
    """
    history = HistoryStore(maxlen=1000)
    threads_count = 8
    samples_per_thread = 50

    def worker(worker_id: int) -> None:
        for i in range(samples_per_thread):
            history.record([make_sample(float(i), labels={"worker": str(worker_id)})])

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    for worker_id in range(threads_count):
        values = [s.value for s in history.get("cpu.total", {"worker": str(worker_id)})]
        assert len(values) == samples_per_thread


def test_concurrent_writer_and_readers_do_not_raise_or_corrupt() -> None:
    """1本のwriterスレッド(Samplerを模す)と複数のreaderスレッド(UI表示を模す)を
    同時に走らせ、例外を出さず、常にmaxlen以内の正しい型のリストが返ることを回帰確認する。
    """
    history = HistoryStore(maxlen=50)
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        i = 0
        while not stop.is_set():
            history.record([make_sample(float(i))])
            i += 1

    def reader() -> None:
        while not stop.is_set():
            try:
                values = history.get("cpu.total")
                assert len(values) <= history.maxlen
                assert all(isinstance(v, MetricSample) for v in values)
            except BaseException as exc:  # noqa: BLE001 - スレッド内例外を握って後段でassertする
                errors.append(exc)

    writer_thread = threading.Thread(target=writer)
    reader_threads = [threading.Thread(target=reader) for _ in range(3)]
    writer_thread.start()
    for t in reader_threads:
        t.start()

    time.sleep(0.3)
    stop.set()
    writer_thread.join(timeout=2.0)
    for t in reader_threads:
        t.join(timeout=2.0)

    assert errors == []
