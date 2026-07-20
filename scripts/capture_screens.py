"""実psutilデータでsysdashをヘッドレス起動し、ダッシュボード・グラフ画面をSVGとして
指定ディレクトリへ保存するツール(リポジトリにコミット対象)。

ロゴ・システム情報サイドバーの見え方をOS/ディストリ毎に確認するためのキャプチャ用途。
README用のスクリーンショット(docs/images/*.svg)とは異なり、**実データをそのまま使う**。
既定ではホスト名等の実機情報を含むため、公開するキャプチャは `--hostname sysdash-demo` 等で
サニタイズして生成すること。

## 使い方

    uv run python scripts/capture_screens.py docs/captures

出力ファイル名は `<prefix>-dashboard.svg` / `<prefix>-graph.svg`。`--prefix` を省略した場合、
OS(Windows/macOS/Linuxはディストリ名も付与。例: linux-ubuntu)から自動生成する。
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import platform
import sys
import time
from pathlib import Path

from sysdash.__main__ import build_collectors
from sysdash.ui.app import GraphScreen, SysdashApp
from sysdash.ui.widgets.system_info import _parse_os_release_id, _read_os_release

# グラフ画面への遷移待ちタイムアウト(秒)。ディスク収集が遅い環境でも十分待てる余裕を持たせる。
GRAPH_SCREEN_TIMEOUT = 5.0


def _auto_prefix() -> str:
    system = platform.system()
    if system == "Linux":
        content = _read_os_release("/etc/os-release")
        distro_id = _parse_os_release_id(content) if content else None
        return f"linux-{distro_id}" if distro_id else "linux-generic"
    if system == "Darwin":
        return "macos"
    return system.lower() or "unknown"


async def _capture(output_dir: Path, prefix: str, size: tuple[int, int], hostname: str | None) -> bool:
    """成功時True、グラフ画面への遷移に失敗した場合はFalseを返す(呼び出し側で非0終了させる)。

    ディスク収集の初回サンプルが遅れると、Enter直後はまだGraphScreenへ遷移していない
    (open_graphがデータ未着の場合はnotifyのみで遷移しない)ことがある。誤ったスクリーンショット
    (実際にはダッシュボードのまま)を成果物として保存しないよう、遷移をポーリング確認する。
    """
    app = SysdashApp(build_collectors(), interval=0.5)
    if hostname is not None:
        # 公開用キャプチャで実ホスト名を出さないための上書き(ヘッダタイトルとサイドバーの両方)
        app.title = hostname
        app._system_info = dataclasses.replace(app._system_info, hostname=hostname)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(1.2)  # サイドバー・パネルに実データが反映されるのを待つ
        app.save_screenshot(path=str(output_dir), filename=f"{prefix}-dashboard.svg")

        # ディスクパネルへ移動してEnterでグラフ画面へ(R/W専用グループの見た目も確認する)。
        # 初回サンプルが未着だとopen_graph()はnotifyのみで遷移しないため、遷移するまで
        # (またはタイムアウトまで)Enterを再試行しながらポーリングする。
        await pilot.press("down")
        await pilot.press("down")
        await pilot.pause()

        deadline = time.monotonic() + GRAPH_SCREEN_TIMEOUT
        while not isinstance(app.screen, GraphScreen) and time.monotonic() < deadline:
            await pilot.press("enter")
            await pilot.pause(0.2)

        if not isinstance(app.screen, GraphScreen):
            app.sampler.stop()
            return False

        await pilot.pause(1.2)
        app.save_screenshot(path=str(output_dir), filename=f"{prefix}-graph.svg")

        app.sampler.stop()
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_dir", type=Path, help="SVGの出力先ディレクトリ(存在しなければ作成)")
    parser.add_argument("--prefix", default=None, help="出力ファイル名の接頭辞(省略時はOS/ディストリから自動生成)")
    parser.add_argument("--width", type=int, default=120, help="キャプチャ幅(既定120、サイドバー表示に必要な120以上を推奨)")
    parser.add_argument("--height", type=int, default=40, help="キャプチャ高さ(既定40)")
    parser.add_argument(
        "--hostname",
        default=None,
        help="ヘッダ・サイドバーに表示するホスト名を上書き(公開用キャプチャのサニタイズに使用)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or _auto_prefix()

    ok = asyncio.run(_capture(args.output_dir, prefix, (args.width, args.height), args.hostname))

    print(f"saved: {args.output_dir / f'{prefix}-dashboard.svg'}")
    if not ok:
        print(
            f"error: could not reach GraphScreen within {GRAPH_SCREEN_TIMEOUT}s "
            f"({prefix}-graph.svg was not saved; disk data may not have arrived in time)",
            file=sys.stderr,
        )
        return 1
    print(f"saved: {args.output_dir / f'{prefix}-graph.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
