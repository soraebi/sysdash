# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller用ビルド設定(--onefile相当)。

ビルド: `uv run pyinstaller sysdash.spec`
出力  : dist/sysdash(.exe)
スモーク確認: `dist/sysdash --smoke`(uv環境の外、素のシェルから実行すること)
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

# textual/plotext/textual-plotext用の専用PyInstallerフックは存在しないため、collect_all()で
# サブモジュールに加えて同梱データファイル(.scm/.typedファイル等)まで含める。
# collect_submodules()だけだとこれらdataファイルの同梱漏れリスクがある。
textual_datas, textual_binaries, textual_hidden = collect_all("textual")
plotext_datas, plotext_binaries, plotext_hidden = collect_all("plotext")
textual_plotext_datas, textual_plotext_binaries, textual_plotext_hidden = collect_all("textual_plotext")

all_datas = textual_datas + plotext_datas + textual_plotext_datas
all_binaries = textual_binaries + plotext_binaries + textual_plotext_binaries
hidden_imports = textual_hidden + plotext_hidden + textual_plotext_hidden + collect_submodules("rich")

# サイズ抑制のため、sysdashが使わない大物ライブラリ・標準ライブラリのテスト系を除外する
# PIL(Pillow): plotextの画像出力機能(_global.py/_monitor.py内の関数ローカルimport)が
# 使っているが、sysdashのgraph_view.pyはその経路を一切呼ばない。scripts/logo_from_image.py
# (開発時専用、dev依存のみ)がPillowを使うためvenvにインストールされておりPyInstallerが
# 自動検出してしまうが、実行時未使用のため明示的に除外する(約7MBの肥大化を回避)。
excludes = [
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "test",
    "pytest",
    "PyInstaller",
    "PIL",
]

a = Analysis(
    ["src/sysdash/__main__.py"],
    pathex=["src"],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sysdash",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Defender誤検知を避けるため使用しない
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
