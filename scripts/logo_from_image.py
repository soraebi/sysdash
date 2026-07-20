"""OSロゴ画像をサイドバー用の半ブロック(▀)ピクセルアートに変換する開発時専用ツール。

sysdashのfastfetch風サイドバー(src/sysdash/ui/widgets/system_info.py)のロゴ定数は、
このスクリプトで画像から生成したRichマークアップ文字列を**実行時に画像処理せず**ソースへ
焼き込む方式を採る(配布物にPillow・画像ファイルとも不要にするため)。Pillowはdev依存にのみ
追加している(`uv add --dev pillow`)。

## 変換方式

1文字セル=横1px×縦2px として扱い、Unicodeの上半ブロック文字 "▀" を使う:
- 前景色(文字色)   = そのセルの「上side」のピクセル色
- 背景色(bgcolor)  = そのセルの「下side」のピクセル色

これにより1つの文字グリフで実質2ピクセル分の色情報を表現できる(neofetch/fastfetch系ツールで
広く使われる手法と同じ原理)。透明ピクセル・ほぼ白のピクセルは「色なし」として扱い、
前景/背景いずれかが色なしの場合は ▀ の代わりに ▄(下半ブロック、色ありの側だけ塗る)を使うか、
両方色なしならスペース(サイドバー自体の背景を透過させる)を出力する。

## 使い方

    uv run python scripts/logo_from_image.py <入力画像> --width 30 --height 30 --name WINDOWS_LOGO

`--width`/`--height` はピクセル単位(高さは偶数推奨。文字行数 = height // 2)。
出力はそのまま `system_info.py` のロゴ定数に貼れるPython文字列リテラル(標準出力、
`--out` 指定でファイルへも書き出せる)。

## 元画像の取得元・再現性の記録(開発時のみ、大半はWikimedia CommonsのSpecial:FilePath経由)

対応OS・ディストリと元画像(計19種。個別のURLは生成物である src/sysdash/ui/widgets/logos.py
冒頭にも同じ一覧を記載している。FALLBACK_LOGOのみ変換対象の画像を用意せず手描き)。

再現に必要な情報(取得URL・ダウンロード幅・SHA256・クロップ座標・変換コマンド)をロゴ毎に記載する。
SHA256はダウンロード直後のPNGファイル(=変換スクリプトへの実際の入力)に対するもの。
Wikimedia CommonsのSpecial:FilePathは同一URLでも将来的にコンテンツが変わりうるため、
差異が出た場合はこのSHA256を基準に元ファイルの再取得可否を判断すること。

- **Windows**: https://commons.wikimedia.org/wiki/File:Windows_11_logo.svg (幅1000で取得。
  平面・軸平行な4スクエア。旧4色フラッグ版(Windows_logo_-_2012_derivative.svg)はパース歪みが
  ありレビュー指摘で差し替え済み)
  sha256:30f62d5929e48e2b6f1297c4e96251b1efa979b2e6bafb6919aae8953c7adc97 (crop後: windows11_icon_hires.png)
  crop座標: `(0, 0, 237, 236)`(ワードマーク"Windows 11"部分を除去)
  変換: `--width 30 --height 30 --name WINDOWS_LOGO --crop 0,0,237,236`
- **Ubuntu**(circle of friends): https://commons.wikimedia.org/wiki/File:UbuntuCoF.svg (幅200)
  sha256:669721740033908b72a134469a4c97e5b6d0ad964578f197389b2d8189778235・クロップ無し
- **Debian**(渦巻き): https://commons.wikimedia.org/wiki/File:Debian-OpenLogo.svg (幅1000で取得。
  線が細く縮小で途切れるため`--dilate`で膨張させてから変換。標準版(30セル)は初回`--dilate 25`
  で変換したがSolレビューで「渦の付け根が細い」との指摘があり`--dilate 45`に強化して再変換した
  (35でも改善は見られたが、付け根の連続性は45の方がより安定していたため採用)。40セル版(_LG)は
  出力解像度に余裕があるため`--dilate 25`のままで問題なし)
  sha256:a82ee311f3779ea5848eb51fa1c410a3b9a2c23d55d9235c7972b758187e9545 (debian_hires.png)
  crop座標: `(0, 0, 1280, 1265)`(下部の"debian"ワードマークを除去)
  変換(標準・30セル): `--width 30 --height 30 --name DEBIAN_LOGO --dilate 45 --crop 0,0,1280,1265`
  変換(ワイド・40セル): `--width 40 --height 40 --name DEBIAN_LOGO_LG --dilate 25 --crop 0,0,1280,1265`
- **Fedora**: https://commons.wikimedia.org/wiki/File:Fedora_icon_(2021).svg (幅200)
  sha256:b26b6a55802db71d1342be0b19e3502b17bbff4568a889a3b719d60e8bc86670・クロップ無し
- **Arch Linux**: https://commons.wikimedia.org/wiki/File:Arch_Linux_%22Crystal%22_icon.svg (幅200)
  sha256:6e43d22411acd3fc55a6051e2d6aa096c098cf76e3d8d02ddfef98ec970b3fd7・クロップ無し
- **Linux Mint**: https://commons.wikimedia.org/wiki/File:Linux_Mint_logo_without_wordmark.svg (幅200)
  sha256:245dd724e19c867d8f2a3d4390de332790c89bb4c869ea993d04bd141363004a・クロップ無し
- **Manjaro**: https://commons.wikimedia.org/wiki/File:Manjaro-logo.svg (幅200)
  sha256:871f3c50dcd2ae2ffc4740f03b307a957530b7692324fcc1293cc85b638b5112・クロップ無し
- **openSUSE**(Leap/Tumbleweed共通): https://commons.wikimedia.org/wiki/File:OpenSUSE_Geeko_button.svg (幅200)
  sha256:3a2685a7cb7d271a9c8921ae5a2ffc7148a7e87e1e6dc6dfdc220750eb95ed98・クロップ無し
- **Raspberry Pi OS**(raspbian): https://commons.wikimedia.org/wiki/File:Raspberry_Pi_OS_Logo.png (幅200)
  sha256:00f80cb0c1be50626e97e743f28dcf53109d85196ec14eb69875782fcc73b310 (raspbian.png)
  crop座標: `(0, 0, 78, 83)`(右側の"Raspberry Pi OS"ワードマークを除去)
  変換: `--width 30 --height 30 --name RASPBIAN_LOGO --crop 0,0,78,83`
- **RHEL**: https://commons.wikimedia.org/wiki/File:Red_Hat_logo.svg (幅200)
  sha256:5e3b12728b2b583a74c3a619d512e105bbdfa52aea260fdc6d9c4e2a6e810133・クロップ無し
- **CentOS**: https://commons.wikimedia.org/wiki/File:CentOS_Graphical_Symbol.svg (幅200)
  sha256:f6bd8ebdf0bbabdaebf670c188653d80ad2bc3b9359e7670ca6f8c0fb3d7d1ca・クロップ無し
- **AlmaLinux**: https://commons.wikimedia.org/wiki/File:AlmaLinux_Icon_Logo.svg (公式の6色アイコン、幅200)。
  当初は30セルでの判別性を懸念しSimple Icons単色版(`cdn.jsdelivr.net/npm/simple-icons`、ブランド
  カラー`#9F2936`付与、`resvg-py`でラスタライズ)に差し替えていたが、40セル版(ワイドサイドバー用)で
  6色版の方が花弁の境界を視認しやすいとの司令塔+Solの最終視認レビュー結果を受け、標準版(30セル)・
  ワイド版(40セル)とも本来の公式6色アイコンに統一した(Simple Icons単色版は不採用)
  sha256:dcb3a883c1ec6a275f7a44c55b42360dc30685e5aa1de6f704b2180931b585d8 (almalinux.png)
  クロップ無し
  変換(標準・30セル): `--width 30 --height 30 --name ALMALINUX_LOGO`
  変換(ワイド・40セル): `--width 40 --height 40 --name ALMALINUX_LOGO_LG`
- **Rocky Linux**: https://commons.wikimedia.org/wiki/File:Rocky_Linux_logo.svg (幅200)
  sha256:dffae4ccf51c594fce3ae44b039dad0f6a60a8bdfcbda334be35a0c085ebbddf・クロップ無し
- **Kali Linux**: https://commons.wikimedia.org/wiki/File:Kali-dragon-icon.svg (幅200)
  sha256:54828b7d38b31a24ba86f19c88579630e424b2f6a63c1d5210a0134abae81dcb・クロップ無し
- **Alpine Linux**: https://commons.wikimedia.org/wiki/File:New_Logo_Alpine_Linux.svg (幅200)
  sha256:688dcc3e2b0899d13e786dce4d6d22d36fc11c0bf0f1634a1cac382e3055c32b (alpine.png)
  crop座標: `(0, 0, 250, 190)`(下部の"alpine Linux"ワードマークを除去)
  変換: `--width 30 --height 30 --name ALPINE_LOGO --crop 0,0,250,190`
- **Pop!_OS**: https://commons.wikimedia.org/wiki/File:Pop!_OS_Icon.svg (幅200)
  sha256:2a91cd47925eecf55edd3879b507f0d11941647384de2910506af3b97fff395b・クロップ無し
- **Gentoo**: https://commons.wikimedia.org/wiki/File:Gentoo_Linux_Signet.svg (幅200)
  sha256:7054db477589b1aed657fa58168d38d2fd93bde6b8ad64153bc5fa5cf19e42ca・クロップ無し
- **Linux**(Tux、汎用フォールバック): https://commons.wikimedia.org/wiki/File:Tux.svg (幅200)
  sha256:aab9e45ed96116076d29f5508f85e615677cead3563c5e3db0384fd022aab0b3・クロップ無し
- **Darwin**(Apple): https://commons.wikimedia.org/wiki/File:Apple_logo_grey.svg (幅200)
  sha256:ba164b4e408f8c7860d65918ec0cde8632ed2c6a970640b7422bf02c89a31c41・クロップ無し

取得コマンド例(PNGサムネイルとして取得):

    curl -sL -o out/logo_src/windows11_icon_hires.png \
        "https://commons.wikimedia.org/wiki/Special:FilePath/Windows_11_logo.svg?width=1000"

クロップが必要なロゴは `--crop x0,y0,x1,y1` を変換コマンドに追加する(上記の各項目に記載の
座標・コマンド例を参照)。クロップ座標は元画像を実際に開いて確認したものであり、Wikimedia側の
画像更新でレイアウトが変わった場合は座標の再確認が必要。

`out/logo_src/` は .gitignore 対象(開発時のみのダウンロード物で、リポジトリにはコミットしない)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFilter

# ほぼ白(R,G,B全てこの値以上)は背景として透過扱いにする閾値
WHITE_THRESHOLD = 235
# アルファ値がこの値未満なら透明として透過扱いにする閾値
ALPHA_THRESHOLD = 40


def _is_blank(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a < ALPHA_THRESHOLD:
        return True
    return r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD


def _hex(pixel: tuple[int, int, int, int]) -> str:
    r, g, b, _a = pixel
    return f"#{r:02x}{g:02x}{b:02x}"


def load_and_fit(
    path: Path, width: int, height: int, dilate: int = 0, crop: tuple[int, int, int, int] | None = None
) -> Image.Image:
    """画像を読み込み、アスペクト比を保ったまま(width, height)の透明キャンバスへ中央配置する。

    crop指定時は(x0, y0, x1, y1)でワードマーク等を除いたアイコン部分のみを事前に切り出す
    (Debian/Alpine/Raspberry Pi OS等、公式配布画像にワードマークが同梱されている場合に使う)。
    dilate>0の場合、縮小前(クロップ後の元解像度)にMaxFilterで線を膨張させる(dilateは奇数の
    ウィンドウ幅)。渦巻き等の細い線が30x30への縮小で途切れて見えるのを防ぐ(Debianロゴの
    レビュー指摘対応)。
    """
    src = Image.open(path).convert("RGBA")
    if crop is not None:
        src = src.crop(crop)
    if dilate > 0:
        window = dilate if dilate % 2 == 1 else dilate + 1
        src = src.filter(ImageFilter.MaxFilter(window))
    src.thumbnail((width, height), Image.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    offset = ((width - src.width) // 2, (height - src.height) // 2)
    canvas.paste(src, offset, src)
    return canvas


def image_to_halfblock_markup(image: Image.Image) -> str:
    """(width, height)のRGBA画像を、1行=2px分を表す半ブロック文字のRichマークアップに変換する。

    heightが奇数の場合は最後の1行分の下sideを透明(色なし)として扱う。
    """
    width, height = image.size
    pixels = image.load()
    lines: list[str] = []
    for y in range(0, height, 2):
        cells: list[str] = []
        for x in range(width):
            top = pixels[x, y]
            bottom = pixels[x, y + 1] if y + 1 < height else (0, 0, 0, 0)
            top_blank = _is_blank(top)
            bottom_blank = _is_blank(bottom)
            if top_blank and bottom_blank:
                cells.append(" ")
            elif not top_blank and not bottom_blank:
                cells.append(f"[{_hex(top)} on {_hex(bottom)}]▀[/]")
            elif not top_blank:
                cells.append(f"[{_hex(top)}]▀[/]")
            else:
                cells.append(f"[{_hex(bottom)}]▄[/]")
        lines.append("".join(cells).rstrip())
    return "\n".join(lines)


def to_python_literal(name: str, markup: str) -> str:
    lines = markup.split("\n")
    body = "\n".join(lines)
    return f'{name} = """\\\n{body}\\\n"""\n'


def main() -> int:
    # description に半ブロック文字(▀)等を含むモジュールdocstring(__doc__)をそのまま渡すと、
    # cp932既定のWindowsコンソールで--help実行時にUnicodeEncodeErrorでクラッシュする。
    # argparseへはASCII安全な短い説明のみ渡し、詳細はモジュールdocstring(ソース読解)に譲る。
    parser = argparse.ArgumentParser(
        description="Convert an OS logo image into half-block (upper-half-block) pixel art "
        "Rich markup for sysdash's sidebar. See this script's module docstring for details."
    )
    parser.add_argument("image", type=Path, help="入力画像ファイル(PNG等、PillowがOpenできる形式)")
    parser.add_argument("--width", type=int, default=30, help="出力の文字幅(=ピクセル幅、既定30)")
    parser.add_argument("--height", type=int, default=30, help="変換対象のピクセル高さ(既定30、文字行数はheight//2)")
    parser.add_argument("--name", default="LOGO", help="出力するPython変数名(既定LOGO)")
    parser.add_argument("--out", type=Path, default=None, help="出力先ファイル(省略時は標準出力)")
    parser.add_argument(
        "--dilate",
        type=int,
        default=0,
        help="縮小前に線をこの幅(奇数、例:5)で膨張させる(細い線が縮小で途切れるのを防ぐ。既定0=無効)",
    )
    parser.add_argument(
        "--crop",
        default=None,
        help="変換前に'x0,y0,x1,y1'でアイコン部分のみ切り出す(ワードマーク同梱画像用。既定None=切り出さない)",
    )
    args = parser.parse_args()

    crop: tuple[int, int, int, int] | None = None
    if args.crop is not None:
        try:
            parts = tuple(int(v.strip()) for v in args.crop.split(","))
        except ValueError:
            parts = ()
        if len(parts) != 4:
            print(f"error: --crop must be 'x0,y0,x1,y1', got: {args.crop!r}", file=sys.stderr)
            return 1
        crop = parts  # type: ignore[assignment]

    if not args.image.exists():
        print(f"error: image not found: {args.image}", file=sys.stderr)
        return 1

    image = load_and_fit(args.image, args.width, args.height, args.dilate, crop)
    markup = image_to_halfblock_markup(image)
    literal = to_python_literal(args.name, markup)

    if args.out is not None:
        args.out.write_text(literal, encoding="utf-8")
    else:
        sys.stdout.buffer.write(literal.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
