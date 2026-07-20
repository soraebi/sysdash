from __future__ import annotations

import platform
import time
from dataclasses import dataclass
from typing import Any

import psutil
from rich.markup import escape
from textual.reactive import reactive
from textual.widgets import Static

from sysdash.core.i18n import t
from sysdash.ui.widgets.logos import (
    ALMALINUX_LOGO,
    ALMALINUX_LOGO_LG,
    ALPINE_LOGO,
    ALPINE_LOGO_LG,
    ARCH_LOGO,
    ARCH_LOGO_LG,
    CENTOS_LOGO,
    CENTOS_LOGO_LG,
    DARWIN_LOGO,
    DARWIN_LOGO_LG,
    DEBIAN_LOGO,
    DEBIAN_LOGO_LG,
    FEDORA_LOGO,
    FEDORA_LOGO_LG,
    GENTOO_LOGO,
    GENTOO_LOGO_LG,
    KALI_LOGO,
    KALI_LOGO_LG,
    LINUX_LOGO,
    LINUX_LOGO_LG,
    LINUXMINT_LOGO,
    LINUXMINT_LOGO_LG,
    MANJARO_LOGO,
    MANJARO_LOGO_LG,
    OPENSUSE_LOGO,
    OPENSUSE_LOGO_LG,
    POP_LOGO,
    POP_LOGO_LG,
    RASPBIAN_LOGO,
    RASPBIAN_LOGO_LG,
    RHEL_LOGO,
    RHEL_LOGO_LG,
    ROCKY_LOGO,
    ROCKY_LOGO_LG,
    UBUNTU_LOGO,
    UBUNTU_LOGO_LG,
    WINDOWS_LOGO,
    WINDOWS_LOGO_LG,
)

NA_TEXT = "N/A"
OS_RELEASE_PATH = "/etc/os-release"
CPUINFO_PATH = "/proc/cpuinfo"
DEVICE_TREE_MODEL_PATH = "/proc/device-tree/model"

FALLBACK_LOGO = """[dim]┌────────────┐[/]
[dim]│[/]  [white]▁▁▁▁▁▁▁▁[/]  [dim]│[/]
[dim]│[/]  [grey62]░░░░░░░░[/]  [dim]│[/]
[dim]│[/]  [grey62]░░░░░░░░[/]  [dim]│[/]
[dim]│[/]  [white]▔▔▔▔▔▔▔▔[/]  [dim]│[/]
[dim]│[/]            [dim]│[/]
[dim]│[/]     [bright_green]>_[/]     [dim]│[/]
[dim]└────────────┘[/]"""

# ID(os-release)完全一致で選ぶディストリ専用ロゴ。openSUSEはID前方一致(leap/tumbleweed共通)。
# 幅140以上のワイドサイドバー用に、40セル解像度版(_LG)も同じキー構成で用意する。
_DISTRO_LOGOS: dict[str, str] = {
    "ubuntu": UBUNTU_LOGO,
    "debian": DEBIAN_LOGO,
    "fedora": FEDORA_LOGO,
    "arch": ARCH_LOGO,
    "linuxmint": LINUXMINT_LOGO,
    "manjaro": MANJARO_LOGO,
    "opensuse": OPENSUSE_LOGO,
    "raspbian": RASPBIAN_LOGO,
    "rhel": RHEL_LOGO,
    "centos": CENTOS_LOGO,
    "almalinux": ALMALINUX_LOGO,
    "rocky": ROCKY_LOGO,
    "kali": KALI_LOGO,
    "alpine": ALPINE_LOGO,
    "pop": POP_LOGO,
    "gentoo": GENTOO_LOGO,
}

_DISTRO_LOGOS_LG: dict[str, str] = {
    "ubuntu": UBUNTU_LOGO_LG,
    "debian": DEBIAN_LOGO_LG,
    "fedora": FEDORA_LOGO_LG,
    "arch": ARCH_LOGO_LG,
    "linuxmint": LINUXMINT_LOGO_LG,
    "manjaro": MANJARO_LOGO_LG,
    "opensuse": OPENSUSE_LOGO_LG,
    "raspbian": RASPBIAN_LOGO_LG,
    "rhel": RHEL_LOGO_LG,
    "centos": CENTOS_LOGO_LG,
    "almalinux": ALMALINUX_LOGO_LG,
    "rocky": ROCKY_LOGO_LG,
    "kali": KALI_LOGO_LG,
    "alpine": ALPINE_LOGO_LG,
    "pop": POP_LOGO_LG,
    "gentoo": GENTOO_LOGO_LG,
}

_LOGOS: dict[str, str] = {
    "Windows": WINDOWS_LOGO,
    "Linux": LINUX_LOGO,
    "Darwin": DARWIN_LOGO,
}

_LOGOS_LG: dict[str, str] = {
    "Windows": WINDOWS_LOGO_LG,
    "Linux": LINUX_LOGO_LG,
    "Darwin": DARWIN_LOGO_LG,
}


def _resolve_distro_logo(token: str | None, distro_logos: dict[str, str]) -> str | None:
    """os-releaseのID(またはID_LIKEの1トークン)からディストリ専用ロゴを引く。

    openSUSEはID="opensuse-leap"/"opensuse-tumbleweed"のようにサフィックスが付くため、
    "opensuse"完全一致または"opensuse-"で始まる場合のみ共通ロゴに寄せる(単純な前方一致だと
    "opensuseful"のような無関係な文字列まで誤マッチするため、境界を区切り文字で明示している)。
    一致しなければNone(呼び出し側でTuxにフォールバック)。
    """
    if not token:
        return None
    if token == "opensuse" or token.startswith("opensuse-"):
        return distro_logos["opensuse"]
    return distro_logos.get(token)


def logo_for_system(
    system: str,
    distro_id: str | None = None,
    distro_id_like: str | None = None,
    is_raspberry_pi: bool = False,
    wide: bool = False,
) -> str:
    """OS名(platform.system()の値)に応じたASCIIロゴを返す。

    wide=Trueの場合、幅140以上のワイドサイドバー用の40セル解像度版(_LG)から選ぶ。

    system=="Linux"の場合の解決順序:
    1. distro_id=="debian"かつis_raspberry_pi(ハードウェア由来の判定。collect_system_info参照)
       がTrueならraspbian専用ロゴ(Raspberry Pi OS 64bit版はID=debianを名乗るための特例)
    2. distro_idがディストリ専用ロゴに解決できればそれを使う(openSUSEはID前方一致)
    3. 1・2で解決できなければdistro_id_like(スペース区切り)の各トークンを順に2.と同じ
       ロジックで試し、最初に解決できたファミリーのロゴを使う
    4. いずれも解決できなければTux(汎用)

    Linux以外・未知のOSは_LOGOS/FALLBACK_LOGOの通常経路(FALLBACK_LOGOは解像度版を持たない)。
    """
    distro_logos = _DISTRO_LOGOS_LG if wide else _DISTRO_LOGOS
    logos = _LOGOS_LG if wide else _LOGOS
    if system == "Linux":
        if distro_id == "debian" and is_raspberry_pi:
            return distro_logos["raspbian"]
        resolved = _resolve_distro_logo(distro_id, distro_logos)
        if resolved is not None:
            return resolved
        for token in (distro_id_like or "").split():
            resolved = _resolve_distro_logo(token, distro_logos)
            if resolved is not None:
                return resolved
        return logos["Linux"]
    return logos.get(system, FALLBACK_LOGO)


@dataclass(frozen=True)
class SystemInfo:
    """起動時に1回だけ収集する静的なシステム情報(uptimeは含まない)。

    os_nameはplatform.system()の生値(ロゴ選択専用)、os_displayが実際に表示する
    OS名+バージョンの整形済み文字列(OS毎に取得方法が異なる。collect_system_info参照)。
    linux_distro_id/linux_distro_id_likeはLinuxでのみ/etc/os-releaseのID/ID_LIKEを保持し、
    logo_for_system()でのディストリ専用ロゴ選択(ID_LIKEフォールバック)に使う。
    linux_is_raspberry_piは/proc/device-tree/model・/proc/cpuinfoのハードウェア情報から
    判定したRaspberry Pi実機フラグ(os-releaseのNAME/PRETTY_NAMEはRaspberry Pi OS 64bit版でも
    単に"Debian"を名乗るため判定に使えない。collect_system_info参照)。
    いずれもLinux以外・取得失敗時はNone/False。
    """

    os_name: str
    os_display: str
    kernel: str
    hostname: str
    cpu_model: str
    cpu_physical_cores: int | None
    cpu_logical_cores: int | None
    memory_total: int | None
    disk_mount: str
    disk_used: int | None
    disk_total: int | None
    python_version: str
    linux_distro_id: str | None = None
    linux_distro_id_like: str | None = None
    linux_is_raspberry_pi: bool = False


def _safe_platform_call(plat: Any, method_name: str) -> str:
    """plat.<method_name>()を個別に保護する。

    属性が存在しない場合(getattr自体)・呼び出し時の例外・空文字はすべて空文字列にする。
    getattrをtry内に含めることで、fake実装がメソッド自体を持たないケースも保護する。
    """
    try:
        value = getattr(plat, method_name)()
    except Exception:
        return ""
    return value or ""


def _safe_platform_call_indexed(plat: Any, method_name: str, index: int) -> str:
    """plat.<method_name>()[index]を個別に保護する版(platform.mac_ver()[0]用)。"""
    try:
        value = getattr(plat, method_name)()[index]
    except Exception:
        return ""
    return value or ""


def _unquote_os_release_value(raw: str) -> str:
    """os-release(5)の値表記を1つ分解決する(シングル/ダブルクォート除去+ダブルクォート内の
    バックスラッシュエスケープ解除)。

    仕様上、値は無引用/シングルクォート/ダブルクォートのいずれかで、ダブルクォート内では
    \\, $, ", ` のみバックスラッシュエスケープが有効(シェルのダブルクォート規則に準拠)。
    シングルクォート内はエスケープ処理をしない(囲みを外すのみ)。
    """
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        inner = raw[1:-1]
        result: list[str] = []
        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner) and inner[i + 1] in "\\$\"`":
                result.append(inner[i + 1])
                i += 2
            else:
                result.append(inner[i])
                i += 1
        return "".join(result)
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    return raw


def _parse_os_release_field(content: str, key: str) -> str | None:
    """/etc/os-release形式のテキストから指定キー(例: PRETTY_NAME, ID)の値を取り出す。

    引用符除去・ダブルクォート内エスケープ解除に対応。同じキーが複数行に現れた場合は
    仕様どおり後勝ち(最後に出現した行の値を採用)にする。
    """
    prefix = f"{key}="
    value: str | None = None
    for line in content.splitlines():
        if line.startswith(prefix):
            value = _unquote_os_release_value(line[len(prefix) :].strip())
    return value


def _parse_os_release_pretty_name(content: str) -> str | None:
    """/etc/os-release形式のテキストからPRETTY_NAMEの値を取り出す(引用符除去込み)。"""
    return _parse_os_release_field(content, "PRETTY_NAME")


def _parse_os_release_id(content: str) -> str | None:
    """/etc/os-release形式のテキストからID(例: ubuntu, debian)の値を取り出す。"""
    return _parse_os_release_field(content, "ID")


def _read_os_release(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _parse_cpuinfo_model_name(content: str) -> str | None:
    """/proc/cpuinfo形式のテキストから最初の"model name"行の値を取り出す。"""
    for line in content.splitlines():
        if line.lower().startswith("model name"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def _read_cpuinfo(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _read_device_tree_model(path: str) -> str | None:
    """/proc/device-tree/modelを読む(末尾のNUL終端を除去)。取得できなければNone。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return None
    content = content.rstrip("\x00").strip()
    return content or None


def _detect_raspberry_pi(device_tree_model: str | None, cpuinfo_content: str | None) -> bool:
    """Raspberry Pi実機かどうかを判定する。

    Raspberry Pi OS 64bit版はos-releaseのID/NAME/PRETTY_NAMEがいずれも"Debian"を名乗るため
    (Debianベースであることの表明であり機種名は含まれない)、os-release頼みでは判定できない。
    代わりにハードウェア由来の情報(/proc/device-tree/model、無ければ/proc/cpuinfoの
    Hardware/Model行等)に"Raspberry Pi"の文字列が含まれるかで判定する(いずれもファイル読みのみ)。
    """
    if device_tree_model and "raspberry pi" in device_tree_model.lower():
        return True
    if cpuinfo_content and "raspberry pi" in cpuinfo_content.lower():
        return True
    return False


def _system_disk_usage(backend: Any, mount: str) -> tuple[int | None, int | None]:
    """システムドライブ(Windows=C:\\、Unix系=/)のused/totalを取得する。失敗時は(None, None)。"""
    try:
        usage = backend.disk_usage(mount)
        return usage.used, usage.total
    except Exception:
        return None, None


def collect_system_info(
    backend: Any = psutil,
    plat: Any = platform,
    os_release_path: str = OS_RELEASE_PATH,
    cpuinfo_path: str = CPUINFO_PATH,
    device_tree_model_path: str = DEVICE_TREE_MODEL_PATH,
) -> SystemInfo:
    """psutil(backend)とplatform(plat)から静的なシステム情報を収集する。

    外部コマンドは使わない(processor()がuname -pを実行するUnix系では使わず、
    ファイル読み取り(/etc/os-release, /proc/cpuinfo)で代替する)。platform.*の
    呼び出しは個別にtry/exceptで保護し、取得できない項目はNone/N/Aにする
    (collector層と同じ規約)。全滅してもこの関数自体は例外を送出しない。
    """
    try:
        physical_cores = backend.cpu_count(logical=False)
    except Exception:
        physical_cores = None
    try:
        logical_cores = backend.cpu_count(logical=True)
    except Exception:
        logical_cores = None
    try:
        memory_total = backend.virtual_memory().total
    except Exception:
        memory_total = None

    system_name = _safe_platform_call(plat, "system")
    release = _safe_platform_call(plat, "release")
    version = _safe_platform_call(plat, "version")
    node = _safe_platform_call(plat, "node")
    processor = _safe_platform_call(plat, "processor")
    machine = _safe_platform_call(plat, "machine")
    python_version = _safe_platform_call(plat, "python_version")

    # Windows/Darwin/未知OSでは常にNone/False(Linuxのみos-release・ハードウェア情報から設定)
    distro_id: str | None = None
    distro_id_like: str | None = None
    is_raspberry_pi = False

    if system_name == "Windows":
        os_display = f"{system_name} {release}".strip() if release else (system_name or NA_TEXT)
        kernel = version or NA_TEXT
        cpu_model = processor or NA_TEXT
        disk_mount = "C:\\"
    elif system_name == "Darwin":
        mac_version = _safe_platform_call_indexed(plat, "mac_ver", 0)
        os_display = f"macOS {mac_version}".strip() if mac_version else (system_name or NA_TEXT)
        kernel = release or NA_TEXT
        cpu_model = machine or NA_TEXT
        disk_mount = "/"
    elif system_name == "Linux":
        os_release_content = _read_os_release(os_release_path)
        if os_release_content:
            pretty_name = _parse_os_release_pretty_name(os_release_content)
            distro_id = _parse_os_release_id(os_release_content)
            distro_id_like = _parse_os_release_field(os_release_content, "ID_LIKE")
        else:
            pretty_name = None
        os_display = pretty_name or (f"{system_name} {release}".strip() if release else NA_TEXT)
        kernel = release or NA_TEXT
        cpuinfo_content = _read_cpuinfo(cpuinfo_path)
        cpu_model = _parse_cpuinfo_model_name(cpuinfo_content or "") or NA_TEXT
        device_tree_model = _read_device_tree_model(device_tree_model_path)
        is_raspberry_pi = _detect_raspberry_pi(device_tree_model, cpuinfo_content)
        disk_mount = "/"
    else:
        os_display = f"{system_name} {release}".strip() or NA_TEXT
        kernel = release or version or NA_TEXT
        cpu_model = processor or NA_TEXT
        disk_mount = "/"

    disk_used, disk_total = _system_disk_usage(backend, disk_mount)

    return SystemInfo(
        os_name=system_name or NA_TEXT,
        os_display=os_display,
        kernel=kernel,
        hostname=node or NA_TEXT,
        cpu_model=cpu_model,
        cpu_physical_cores=physical_cores,
        cpu_logical_cores=logical_cores,
        memory_total=memory_total,
        disk_mount=disk_mount,
        disk_used=disk_used,
        disk_total=disk_total,
        python_version=python_version or NA_TEXT,
        linux_distro_id=distro_id,
        linux_distro_id_like=distro_id_like,
        linux_is_raspberry_pi=is_raspberry_pi,
    )


def blank_system_info() -> SystemInfo:
    """collect_system_info自体が予期せず例外を送出した場合の全項目N/Aフォールバック。"""
    return SystemInfo(
        os_name=NA_TEXT,
        os_display=NA_TEXT,
        kernel=NA_TEXT,
        hostname=NA_TEXT,
        cpu_model=NA_TEXT,
        cpu_physical_cores=None,
        cpu_logical_cores=None,
        memory_total=None,
        disk_mount=NA_TEXT,
        disk_used=None,
        disk_total=None,
        python_version=NA_TEXT,
    )


def _humanize_bytes(value: float) -> str:
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units[:-1]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}{units[-1]}"


def _fmt_bytes(value: int | None) -> str:
    return NA_TEXT if value is None else _humanize_bytes(value)


def _fmt_cores(physical: int | None, logical: int | None) -> str:
    physical_text = str(physical) if physical is not None else NA_TEXT
    logical_text = str(logical) if logical is not None else NA_TEXT
    return f"{physical_text} physical / {logical_text} logical"


# DEFAULT_CSSのwidth(34)からborder(左右各1)とpadding(左右各1)を引いた実測コンテンツ幅。
SIDEBAR_CONTENT_WIDTH = 30
# 幅140以上のワイドサイドバー用(外形44、コンテンツ44-4=40)。DashboardScreen._apply_layout参照。
SIDEBAR_STANDARD_WIDTH = 34
SIDEBAR_WIDE_WIDTH = 44
SIDEBAR_WIDE_CONTENT_WIDTH = 40


def _truncate(value: str, width: int) -> str:
    """valueを省略記号(…)付きでwidth以内に切り詰める純関数(width<=0なら空文字)。"""
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width == 1:
        return value[:1]
    return value[: width - 1] + "…"


def _line(prefix: str, raw_value: str, total_width: int = SIDEBAR_CONTENT_WIDTH) -> str:
    """prefix込みでtotal_width以内に収まるよう、生値を切り詰めてからエスケープして連結する。

    エスケープ前に切り詰めることで、エスケープシーケンス("\\[" 等)の途中で
    文字列を切ってしまうのを避ける。
    """
    available = max(total_width - len(prefix), 1)
    return f"{prefix}{escape(_truncate(raw_value, available))}"


class SystemInfoPanel(Static):
    """fastfetch風のシステム情報サイドバー。GRIDレイアウト時かつ十分な幅の時のみ表示する。

    起動時に1回収集した静的情報(SystemInfo)を保持し、update_uptime()でuptimeのみtick毎に
    更新する(psutil呼び出しはSysdashApp側で1回だけ行い、このウィジェット自体は表示に徹する)。
    """

    DEFAULT_CSS = """
    SystemInfoPanel {
        width: 34;
        height: 1fr;
        border: round $panel-lighten-2;
        padding: 0 1;
        display: none;
    }
    """

    uptime_text: reactive[str] = reactive("")
    """初期値は空文字(モジュールimport時点の言語で固定されるのを避けるため)。
    実際の文言はon_mount()がupdate_uptime()を呼んで確定する。"""
    show_logo: reactive[bool] = reactive(True)
    """低い高さの端末ではロゴを省略し情報のみ表示する(DashboardScreen._apply_layout参照)。"""
    wide: reactive[bool] = reactive(False)
    """幅140以上では44セル幅+40セル解像度ロゴに切り替える(DashboardScreen._apply_layout参照)。"""

    def __init__(self, info: SystemInfo, boot_time: float | None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._info = info
        self._boot_time = boot_time

    def on_mount(self) -> None:
        self.update_uptime()  # uptime_textの初期値(空文字)を実文言に確定させてから描画する

    def update_uptime(self) -> None:
        if self._boot_time is None:
            self.uptime_text = f"{t('sidebar.uptime')}: {NA_TEXT}"
            return
        elapsed = max(0.0, time.time() - self._boot_time)
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.uptime_text = f"{t('sidebar.uptime')}: {hours:02d}:{minutes:02d}:{seconds:02d}"

    def watch_uptime_text(self, uptime_text: str) -> None:
        self._compose_lines()

    def watch_show_logo(self, show_logo: bool) -> None:
        self._compose_lines()

    def watch_wide(self, wide: bool) -> None:
        self.styles.width = SIDEBAR_WIDE_WIDTH if wide else SIDEBAR_STANDARD_WIDTH
        self._compose_lines()

    def _compose_lines(self) -> None:
        # 注意: メソッド名を _render / _render_content にするとWidgetの内部レンダリング
        # パイプライン(Widget._render_content()が内部でWidget._render()を呼ぶ)を
        # 上書きしてしまい、コンポジタが空描画になる(export_screenshot等で顕在化)。
        # そのため衝突しない名前(_compose_lines)を使う。
        info = self._info
        content_width = SIDEBAR_WIDE_CONTENT_WIDTH if self.wide else SIDEBAR_CONTENT_WIDTH
        lines: list[str] = []
        if self.show_logo:
            logo = logo_for_system(
                info.os_name, info.linux_distro_id, info.linux_distro_id_like, info.linux_is_raspberry_pi, self.wide
            )
            lines.extend([logo, ""])
        hostname = escape(_truncate(info.hostname, content_width))
        lines.append(f"[bold]{hostname}[/bold]")
        lines.append(_line("OS: ", info.os_display, content_width))
        lines.append(_line("Kernel: ", info.kernel, content_width))
        lines.append(self.uptime_text)
        lines.append(_line("CPU: ", info.cpu_model, content_width))
        lines.append(
            _line(f"{t('sidebar.cores')}: ", _fmt_cores(info.cpu_physical_cores, info.cpu_logical_cores), content_width)
        )
        lines.append(_line(f"{t('sidebar.memory')}: ", _fmt_bytes(info.memory_total), content_width))
        disk_prefix = f"{t('sidebar.disk')} ({escape(info.disk_mount)}): "
        lines.append(_line(disk_prefix, f"{_fmt_bytes(info.disk_used)} / {_fmt_bytes(info.disk_total)}", content_width))
        lines.append(_line("Python: ", info.python_version, content_width))
        self.update("\n".join(lines))
