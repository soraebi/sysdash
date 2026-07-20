from sysdash.core.rate import RateCalculator


def test_first_sample_returns_none() -> None:
    rate = RateCalculator()
    assert rate.compute("k", 100.0, now=0.0) is None


def test_known_counter_sequence_computes_rate_per_second() -> None:
    rate = RateCalculator()
    rate.compute("k", 1000.0, now=0.0)
    result = rate.compute("k", 2000.0, now=1.0)
    assert result == 1000.0


def test_variable_interval_is_reflected_in_rate() -> None:
    rate = RateCalculator()
    rate.compute("k", 0.0, now=0.0)
    result = rate.compute("k", 1000.0, now=2.0)
    assert result == 500.0


def test_negative_delta_counter_reset_returns_none() -> None:
    rate = RateCalculator()
    rate.compute("k", 5000.0, now=0.0)
    result = rate.compute("k", 100.0, now=1.0)
    assert result is None


def test_zero_or_negative_elapsed_returns_none() -> None:
    rate = RateCalculator()
    rate.compute("k", 100.0, now=1.0)
    assert rate.compute("k", 200.0, now=1.0) is None
    assert rate.compute("k", 200.0, now=0.5) is None


def test_invalid_elapsed_does_not_corrupt_baseline_for_next_valid_call() -> None:
    rate = RateCalculator()
    rate.compute("k", 100.0, now=1.0)
    assert rate.compute("k", 200.0, now=0.5) is None  # 巻き戻り呼び出し: 基準点は更新されない
    # 巻き戻り呼び出しを無視して、直前の正常な基準点(t=1, v=100)からレートが算出される
    assert rate.compute("k", 300.0, now=2.0) == 200.0


def test_keys_are_tracked_independently() -> None:
    rate = RateCalculator()
    rate.compute("nic0", 100.0, now=0.0)
    # nic1が初出でも nic0 の追跡には影響しない
    assert rate.compute("nic1", 0.0, now=0.0) is None
    assert rate.compute("nic0", 300.0, now=1.0) == 200.0


def test_new_key_after_interface_added_starts_fresh() -> None:
    rate = RateCalculator()
    rate.compute("nic0", 100.0, now=0.0)
    rate.compute("nic0", 200.0, now=1.0)
    # NIC増設で新しいキーが現れても、既存キーの履歴には影響せず、新キーは初回None扱いになる
    assert rate.compute("nic1", 50.0, now=1.0) is None
    assert rate.compute("nic1", 150.0, now=2.0) == 100.0


def test_prune_removes_keys_not_in_active_set() -> None:
    rate = RateCalculator()
    rate.compute("nic0", 100.0, now=0.0)
    rate.compute("nic1", 100.0, now=0.0)

    rate.prune(["nic0"])  # nic1が消滅したとみなす

    # nic0は基準点が残っているので継続してレートが算出できる
    assert rate.compute("nic0", 200.0, now=1.0) == 100.0
    # nic1は基準点が捨てられているので、再登場すれば初回サンプル扱いに戻る
    assert rate.compute("nic1", 999.0, now=1.0) is None


def test_default_clock_used_when_now_omitted() -> None:
    ticks = iter([10.0, 11.0])
    rate = RateCalculator(clock=lambda: next(ticks))
    assert rate.compute("k", 100.0) is None
    assert rate.compute("k", 300.0) == 200.0
