import sys

import pytest

from sysdash.__main__ import main, parse_args, run_smoke_check
from sysdash.core.sampler import DEFAULT_INTERVAL


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "not-a-number"])
def test_parse_args_rejects_non_finite_or_invalid_interval(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--interval", value])


def test_parse_args_accepts_finite_out_of_range_value_for_later_clamping() -> None:
    # -1のような有限だが範囲外の値はargparseレベルでは拒否せず、Sampler側のclampに委ねる
    args = parse_args(["--interval", "-1"])
    assert args.interval == -1.0


def test_parse_args_default_interval() -> None:
    args = parse_args([])
    assert args.interval == DEFAULT_INTERVAL


def test_parse_args_accepts_normal_value() -> None:
    args = parse_args(["--interval", "2.5"])
    assert args.interval == 2.5


def test_parse_args_smoke_flag_default_is_false() -> None:
    args = parse_args([])
    assert args.smoke is False


def test_parse_args_smoke_flag_true() -> None:
    args = parse_args(["--smoke"])
    assert args.smoke is True


def test_run_smoke_check_returns_zero_and_reports_sample_count(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_smoke_check("Windows")
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "collectors=4" in captured.out
    assert "samples=" in captured.out


class _AlwaysFailingCollector:
    name = "failing"

    def collect(self) -> list:
        raise RuntimeError("boom")


def test_run_smoke_check_returns_nonzero_when_all_collectors_fail(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """全collectorのcollect()が例外を送出するとSampler.tick()はsamples=[]を返す
    (collector単位でtry/exceptされ隔離されるため)。この場合smokeは失敗扱いにする。
    """
    exit_code = run_smoke_check(collectors=[_AlwaysFailingCollector()])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "failed" in captured.err


def test_run_smoke_check_returns_nonzero_when_no_collectors(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_smoke_check(collectors=[])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "failed" in captured.err


def test_main_with_smoke_flag_exits_zero_without_launching_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    """--smoke指定時はTUI(SysdashApp.run())を起動せず、run_smoke_check()の結果でexitすることを確認する。
    もしTUI起動経路に落ちるとPilot無しのrun_test()相当が無いためテストがハングする。
    """
    monkeypatch.setattr(sys, "argv", ["sysdash", "--smoke"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


def test_main_with_smoke_flag_does_not_construct_sysdash_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """--smoke経路でSysdashAppのコンストラクタが一切呼ばれないことを直接確認する。"""
    monkeypatch.setattr(sys, "argv", ["sysdash", "--smoke"])

    def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("SysdashApp should not be constructed in --smoke mode")

    monkeypatch.setattr("sysdash.__main__.SysdashApp", _fail_if_called)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


def test_main_with_lang_en_shows_english_help_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--lang enを--help付きで指定すると、argparseの--help文言自体も英語になることを確認する
    (--lang先読み→set_language→本パーサー構築、の順で処理している)。
    """
    monkeypatch.setattr(sys, "argv", ["sysdash", "--lang", "en", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Cross-platform CLI system monitor dashboard" in captured.out
    assert "クロスプラットフォーム" not in captured.out


def test_main_with_lang_en_shows_english_interval_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--lang en指定時は--intervalの値エラー(_interval_type)も英語で出ることを確認する。"""
    monkeypatch.setattr(sys, "argv", ["sysdash", "--lang", "en", "--interval", "nope"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Could not be parsed as a number" in captured.err
    assert "数値として解釈できません" not in captured.err
