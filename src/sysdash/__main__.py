from __future__ import annotations

import argparse
import math
import platform
import sys

from sysdash.collectors.base import Collector
from sysdash.collectors.cpu import CpuCollector
from sysdash.collectors.disk import DiskCollector
from sysdash.collectors.memory import MemoryCollector
from sysdash.collectors.network import NetworkCollector
from sysdash.core.i18n import SUPPORTED_LANGUAGES, detect_language, set_language, t
from sysdash.core.sampler import DEFAULT_INTERVAL, MAX_INTERVAL, MIN_INTERVAL, Sampler
from sysdash.ui.app import SysdashApp


def build_collectors(system: str | None = None) -> list[Collector]:
    """OS(platform.system())に応じてcollector候補を組み立てる。

    現状は cpu/memory/disk/network が全OS共通(将来OS固有collectorを追加する場合はここに分岐を足す)。
    事前probeは行わない。disk/networkはRateCalculatorベースのため、probeすると初回tickの
    基準点を消費し、本来 "—" になるべき初回レートが数値化してしまう。
    """
    del system
    return [CpuCollector(), MemoryCollector(), DiskCollector(), NetworkCollector()]


def _interval_type(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(t("cli.interval_not_a_number", value=value)) from exc
    if not math.isfinite(parsed):
        # nan/infはclampを素通りして「待機時間が常に0以下」のビジーループを引き起こすため拒否する
        raise argparse.ArgumentTypeError(t("cli.interval_not_finite", value=value))
    return parsed


def _peek_lang(argv: list[str] | None) -> str | None:
    """本パーサーを構築する前に--langの値だけを先読みする。

    argparseの--help/エラーメッセージはパーサー構築時点の言語で固定されるため、本パーサーを
    t()呼び出し込みで組み立てる前に--langを解決しておく必要がある。add_help=Falseの軽量な
    先読み専用パーサー(parse_known_args、--interval等の未知引数はエラーにせず無視する)を使う。
    """
    peek_parser = argparse.ArgumentParser(add_help=False)
    peek_parser.add_argument("--lang", choices=list(SUPPORTED_LANGUAGES), default=None)
    known, _ = peek_parser.parse_known_args(argv)
    return known.lang


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    set_language(_peek_lang(argv) or detect_language())

    parser = argparse.ArgumentParser(prog="sysdash", description=t("cli.description"))
    parser.add_argument(
        "--interval",
        type=_interval_type,
        default=DEFAULT_INTERVAL,
        help=t("cli.interval_help", min=MIN_INTERVAL, max=MAX_INTERVAL, default=DEFAULT_INTERVAL),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=t("cli.smoke_help"),
    )
    parser.add_argument(
        "--lang",
        choices=list(SUPPORTED_LANGUAGES),
        default=None,
        help=t("cli.lang_help"),
    )
    return parser.parse_args(argv)


def run_smoke_check(system: str | None = None, collectors: list[Collector] | None = None) -> int:
    """TUIを起動せずcollector組み立て→1回分の収集を行い、結果をstdoutへ出力する。

    PyInstallerでビルドした配布物のhidden import欠落等を、対話操作無しで検出するために使う。
    collectorsを渡すとbuild_collectors()をバイパスする(テスト用)。
    collectorが1つも無い、または1回分の収集で1件もサンプルが取れなかった場合は
    異常とみなし、理由をstderrへ出力してexit code 1相当の値を返す。

    出力は--langによらず常に英語固定(i18n非対応)。自動処理(CI等)での消費を想定した
    診断チャンネルであり、ロケールに依存しない一貫した出力を優先している。元々日本語版は
    存在しなかった(詳細はout/_reports/p9-fix-report.mdの判断メモ参照)。
    """
    if collectors is None:
        collectors = build_collectors(system)
    if not collectors:
        print("sysdash smoke check failed: no collectors available", file=sys.stderr)
        return 1

    sampler = Sampler(collectors, interval=MIN_INTERVAL)
    samples = sampler.tick()
    if not samples:
        print(
            f"sysdash smoke check failed: collectors={len(collectors)} samples=0",
            file=sys.stderr,
        )
        return 1

    print(f"sysdash smoke check: collectors={len(collectors)} samples={len(samples)}")
    return 0


def main() -> None:
    # parse_args()内で--langの先読み→set_language()→本パーサー構築の順に確定するため、
    # ここで改めてset_languageし直す必要は無い(--help・_interval_typeのエラーも含めて
    # 常に--lang/自動判定の言語が反映される)。
    args = parse_args()
    if args.smoke:
        raise SystemExit(run_smoke_check(platform.system()))
    app = SysdashApp(build_collectors(platform.system()), interval=args.interval)
    app.run()


if __name__ == "__main__":
    main()
