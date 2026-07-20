import pytest

from sysdash.core.i18n import MESSAGES, detect_language, get_language, set_language, t


class _FakeLocale:
    """localeモジュール互換のフェイク(setlocale/getlocale/LC_CTYPEのみ持つ)。

    detect_language()はsetlocale()を最大3回呼ぶ想定: (1)値省略で現在値を問い合わせ、
    (2)""で判定用に設定、(3)問い合わせた値で復元。呼び出し履歴をcallsに記録する。
    """

    LC_CTYPE = object()

    def __init__(
        self,
        getlocale_result,
        raise_on_setlocale: bool = False,
        raise_on_restore: bool = False,
        query_result: str = "C",
    ) -> None:
        self._getlocale_result = getlocale_result
        self._raise_on_setlocale = raise_on_setlocale
        self._raise_on_restore = raise_on_restore
        self._query_result = query_result
        self.calls: list[tuple] = []

    def setlocale(self, category, value=None):
        self.calls.append((category, value))
        if self._raise_on_setlocale:
            raise ValueError("unsupported locale setting")
        if len(self.calls) >= 3 and self._raise_on_restore:
            raise ValueError("restore failed")
        return self._query_result if value is None else value

    def getlocale(self, category):
        return self._getlocale_result


@pytest.mark.parametrize(
    ("getlocale_result", "expected"),
    [
        (("ja_JP", "UTF-8"), "ja"),
        (("ja_JP", None), "ja"),
        (("Japanese_Japan", "932"), "ja"),
        (("en_US", "UTF-8"), "en"),
        (("C", None), "en"),
        ((None, None), "en"),
        (None, "en"),
        # 境界ケース(P9-fix: startswith("ja")単純一致だと誤判定していたもの)
        (("ja", None), "ja"),  # 単独の"ja"
        (("ja-JP", "UTF-8"), "ja"),  # ハイフン区切り
        (("JAPANESE_JAPAN", "932"), "ja"),  # 大文字表記
        (("Javanese_Indonesia", "UTF-8"), "en"),  # "ja"前方一致だが別言語(誤判定の回帰防止)
        (("jam_JM", "UTF-8"), "en"),  # ジャマイカ系クレオール語相当の架空コード、誤判定回帰防止
    ],
)
def test_detect_language_from_locale_result(getlocale_result, expected) -> None:
    assert detect_language(_FakeLocale(getlocale_result)) == expected


def test_detect_language_falls_back_to_english_on_setlocale_failure() -> None:
    assert detect_language(_FakeLocale(("ja_JP", "UTF-8"), raise_on_setlocale=True)) == "en"


def test_detect_language_restores_previous_locale_setting() -> None:
    """detect_language()はsetlocale(LC_CTYPE, "")の前の設定を判定後に復元する
    (プロセス全体のCランタイムのロケール設定を変更したままにしない)。"""
    fake = _FakeLocale(("ja_JP", "UTF-8"))
    detect_language(fake)
    assert fake.calls[0] == (fake.LC_CTYPE, None)  # 1回目: 現在値の問い合わせ(値省略)
    assert fake.calls[1] == (fake.LC_CTYPE, "")  # 2回目: 判定用にOS既定へ設定
    assert fake.calls[2] == (fake.LC_CTYPE, fake._query_result)  # 3回目: 問い合わせた値で復元


def test_detect_language_restore_failure_does_not_affect_result() -> None:
    """復元(2回目以降のsetlocale)が失敗しても、判定結果自体はそのまま返す(握りつぶす)。"""
    fake = _FakeLocale(("ja_JP", "UTF-8"), raise_on_restore=True)
    assert detect_language(fake) == "ja"


def test_set_language_rejects_unsupported_value_and_falls_back_to_default() -> None:
    set_language("fr")
    assert get_language() == "en"
    set_language("ja")  # 後続テストへ影響しないよう既知の値に戻す


def test_t_returns_correct_language_text() -> None:
    set_language("ja")
    assert t("binding.quit") == "終了"
    set_language("en")
    assert t("binding.quit") == "Quit"
    set_language("ja")  # 後続テストへ影響しないよう既知の値に戻す


def test_t_unknown_key_returns_key_itself() -> None:
    assert t("no.such.key") == "no.such.key"


def test_t_formats_kwargs() -> None:
    set_language("en")
    text = t("notify.interval_clamped", requested=3, actual=2.5)
    assert text == "Requested interval 3s is out of range; adjusted to 2.5s"
    set_language("ja")


def test_t_falls_back_to_template_on_missing_format_kwargs() -> None:
    # format()に必要なキーが足りない場合でも、未翻訳キー表示と同様に例外を出さず
    # テンプレート文字列をそのまま返す(安全側フォールバック)。
    set_language("en")
    text = t("notify.interval_clamped")
    assert "{requested}" in text
    set_language("ja")


def test_messages_have_both_languages_for_every_key() -> None:
    for key, entry in MESSAGES.items():
        assert "ja" in entry, f"{key} missing ja"
        assert "en" in entry, f"{key} missing en"
