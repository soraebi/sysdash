from sysdash.core.models import MetricSample


def test_series_key_distinguishes_by_labels() -> None:
    a = MetricSample(name="cpu.core", timestamp=0.0, value=1.0, unit="%", labels={"core": "0"})
    b = MetricSample(name="cpu.core", timestamp=0.0, value=2.0, unit="%", labels={"core": "1"})
    assert a.series_key != b.series_key


def test_series_key_ignores_label_insertion_order() -> None:
    a = MetricSample(name="disk.usage_percent", timestamp=0.0, value=1.0, unit="%", labels={"mount": "C:\\", "x": "1"})
    b = MetricSample(name="disk.usage_percent", timestamp=0.0, value=1.0, unit="%", labels={"x": "1", "mount": "C:\\"})
    assert a.series_key == b.series_key


def test_series_key_default_labels_is_empty() -> None:
    sample = MetricSample(name="cpu.total", timestamp=0.0, value=1.0, unit="%")
    assert sample.series_key == ("cpu.total", ())
