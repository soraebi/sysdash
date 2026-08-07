"""表示言語判定+辞書ベースの簡易i18n。

言語はプロセス起動時に一度だけ確定する想定(set_language()を1回呼ぶ)で、実行中の
切替はサポートしない。外部コマンド・外部ライブラリは使わず、標準ライブラリの
localeモジュールのみで判定する。

Textualの`Binding`はfrozen dataclassでBINDINGSクラス属性はimport時に評価されるため、
描画文言をここで直接組み込むことはできない(先に確定した言語で固定されてしまう)。
そのためBINDINGSの`description`にはこのモジュールのメッセージキー文字列を置き、
実際の翻訳はインスタンス生成時に解決する(詳細はsysdash.ui.app._localize_bindings()を参照)。

既知の設計上の制約: BINDINGSの翻訳はインスタンス生成時点の`_current_language`で固定される
(生成後にset_language()で言語を変えても、既存インスタンスのBINDINGSは追従しない)。
実行中の言語切替を仕様上サポートしていないため許容している。
"""

from __future__ import annotations

import locale as _locale_module

SUPPORTED_LANGUAGES: tuple[str, ...] = ("ja", "en")
DEFAULT_LANGUAGE = "en"

_current_language = DEFAULT_LANGUAGE


def _is_japanese_locale_code(lang_code: str) -> bool:
    """"ja"単純前方一致だと"Javanese_Indonesia"等を誤ってjaと判定してしまうため、
    語境界を意識した判定にする。POSIX形式("ja"/"ja_JP"/"ja_JP.UTF-8")・ハイフン区切り
    ("ja-JP")・Windows形式("Japanese_Japan")のみを対象とする。
    """
    lowered = lang_code.lower()
    return (
        lowered == "ja"
        or lowered.startswith("ja_")
        or lowered.startswith("ja-")
        or lowered.startswith("ja.")
        or lowered.startswith("japanese")
    )


def detect_language(locale_module=_locale_module) -> str:
    """システムロケールから表示言語を判定する。日本語(ja系)なら"ja"、それ以外は"en"。

    POSIX形式("ja_JP"、"ja_JP.UTF-8")とWindows形式("Japanese_Japan")のいずれも判定できる
    (詳細は_is_japanese_locale_code()参照)。判定に失敗した場合(例外発生・ロケール未設定等)
    は既定の"en"にフォールバックする。

    locale.setlocale(LC_CTYPE, "")はプロセス全体のCランタイムのロケール設定を変更する
    副作用があるため、呼び出し前の設定を保存し、判定後に復元する(復元自体に失敗しても
    detect_language()の戻り値には影響させない=握りつぶす)。

    locale_moduleはテスト用の差し替え口(localeモジュール互換のsetlocale/getlocale/
    LC_CTYPEを持つオブジェクト)。省略時は標準ライブラリのlocaleモジュールを使う。
    """
    try:
        previous = locale_module.setlocale(locale_module.LC_CTYPE)  # 引数省略=現在値を文字列で問い合わせるだけ
    except Exception:
        previous = None

    try:
        locale_module.setlocale(locale_module.LC_CTYPE, "")
        result = locale_module.getlocale(locale_module.LC_CTYPE)
    except Exception:
        return DEFAULT_LANGUAGE
    finally:
        if previous is not None:
            try:
                locale_module.setlocale(locale_module.LC_CTYPE, previous)
            except Exception:
                pass

    if not result:
        return DEFAULT_LANGUAGE
    lang_code = result[0] if isinstance(result, tuple) else result
    if not lang_code:
        return DEFAULT_LANGUAGE

    return "ja" if _is_japanese_locale_code(lang_code) else DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    """現在の表示言語を確定する。未対応の値が渡された場合は既定言語にフォールバックする。"""
    global _current_language
    _current_language = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current_language


MESSAGES: dict[str, dict[str, str]] = {
    "panel.cpu": {"ja": "CPU", "en": "CPU"},
    "panel.memory": {"ja": "メモリ", "en": "Memory"},
    "panel.disk": {"ja": "ディスク", "en": "Disk"},
    "panel.network": {"ja": "ネットワーク", "en": "Network"},

    "binding.next_panel": {"ja": "次のパネル", "en": "Next panel"},
    "binding.prev_panel": {"ja": "前のパネル", "en": "Previous panel"},
    "binding.open_graph": {"ja": "グラフ表示", "en": "Graph"},
    "binding.close_graph": {"ja": "戻る", "en": "Back"},
    "binding.switch_series": {"ja": "系列切替", "en": "Switch series"},
    "binding.quit": {"ja": "終了", "en": "Quit"},
    "binding.toggle_pause": {"ja": "一時停止", "en": "Pause"},
    "binding.interval_increase": {"ja": "間隔+", "en": "Interval+"},
    "binding.interval_decrease": {"ja": "間隔-", "en": "Interval-"},

    "stats.now": {"ja": "現在", "en": "Now"},
    "stats.min": {"ja": "最小", "en": "Min"},
    "stats.max": {"ja": "最大", "en": "Max"},

    "graph.xlabel": {"ja": "経過時間(秒)", "en": "Elapsed time (s)"},
    "graph.no_data": {"ja": "データなし", "en": "No data"},

    "notify.interval_clamped": {
        "ja": "指定された更新間隔 {requested}秒は範囲外のため {actual:.1f}秒に調整しました",
        "en": "Requested interval {requested}s is out of range; adjusted to {actual:.1f}s",
    },
    "notify.waiting_for_data": {
        "ja": "データ収集待ちです。しばらくしてから再度お試しください。",
        "en": "Waiting for data. Please try again shortly.",
    },

    "cli.description": {
        "ja": "クロスプラットフォームCLIシステムモニタダッシュボード",
        "en": "Cross-platform CLI system monitor dashboard",
    },
    "cli.interval_help": {
        "ja": "更新間隔(秒)。{min}〜{max}秒にクランプされる(既定: {default})",
        "en": "Update interval in seconds. Clamped to {min}-{max}s (default: {default})",
    },
    "cli.smoke_help": {
        "ja": "TUIを起動せず、collector組み立てと1回分の収集のみ行って終了する(配布物の自動スモークテスト用)",
        "en": "Exit after building collectors and collecting one sample, without starting the TUI"
        " (for automated smoke testing of built distributions)",
    },
    "cli.lang_help": {
        "ja": "表示言語(省略時はシステムロケールから自動判定)",
        "en": "Display language (auto-detected from the system locale if omitted)",
    },
    "cli.interval_not_a_number": {
        "ja": "数値として解釈できません: {value!r}",
        "en": "Could not be parsed as a number: {value!r}",
    },
    "cli.interval_not_finite": {
        "ja": "有限の数値を指定してください: {value!r}",
        "en": "Please specify a finite number: {value!r}",
    },

    "sidebar.uptime": {"ja": "稼働時間", "en": "Uptime"},
    "sidebar.cores": {"ja": "コア", "en": "Cores"},
    "sidebar.memory": {"ja": "メモリ", "en": "Memory"},
    "sidebar.disk": {"ja": "ディスク", "en": "Disk"},
    # OS/Kernel/CPU/Pythonは技術名(値そのものが英語表記のことが多い)のため、
    # 両言語とも英語ラベルのまま固定しておりMESSAGESには登録しない。
}

# --smoke出力はCI等の自動処理での言語非依存性を優先し、--langによらず常に英語固定とする
# (MESSAGES/t()は経由しない)。


def t(key: str, **kwargs: object) -> str:
    """現在の言語でメッセージキーを解決する。

    未知キーは安全側の既定動作としてキー文字列自体を返す(未翻訳の穴があっても
    クラッシュせず、画面上でキー名が見えることで気づける)。
    """
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(_current_language, entry.get(DEFAULT_LANGUAGE, key))
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template
