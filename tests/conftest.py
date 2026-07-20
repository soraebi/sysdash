import pytest

from sysdash.core.i18n import set_language


@pytest.fixture(autouse=True)
def _default_test_language():
    """既存テストの多くは日本語UI文言をそのままassertしているため、既定言語を"ja"に固定する。

    英語UIを検証するテストは自身でset_language("en")を呼んで上書きしてよい
    (本fixtureが次のテストの前に必ず"ja"へ戻すため、テスト間で言語状態が伝染しない)。
    """
    set_language("ja")
    yield
    set_language("ja")
