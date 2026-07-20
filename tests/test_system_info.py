from types import SimpleNamespace

import pytest

from sysdash.ui.widgets.logos import (
    ALMALINUX_LOGO,
    ALMALINUX_LOGO_LG,
    ALPINE_LOGO,
    ALPINE_LOGO_LG,
    ARCH_LOGO,
    ARCH_LOGO_LG,
    CENTOS_LOGO,
    CENTOS_LOGO_LG,
    DARWIN_LOGO_LG,
    DEBIAN_LOGO_LG,
    FEDORA_LOGO,
    FEDORA_LOGO_LG,
    GENTOO_LOGO,
    GENTOO_LOGO_LG,
    KALI_LOGO,
    KALI_LOGO_LG,
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
    UBUNTU_LOGO_LG,
    WINDOWS_LOGO_LG,
)
from sysdash.ui.widgets.system_info import (
    DARWIN_LOGO,
    DEBIAN_LOGO,
    FALLBACK_LOGO,
    LINUX_LOGO,
    SIDEBAR_CONTENT_WIDTH,
    SIDEBAR_WIDE_CONTENT_WIDTH,
    UBUNTU_LOGO,
    WINDOWS_LOGO,
    _line,
    _parse_cpuinfo_model_name,
    _parse_os_release_field,
    _parse_os_release_id,
    _parse_os_release_pretty_name,
    _truncate,
    blank_system_info,
    collect_system_info,
    logo_for_system,
)


class _FakePsutilBackend:
    def __init__(
        self,
        physical: int | None = 4,
        logical: int | None = 8,
        mem_total: int | None = 16_000_000_000,
        disk_usage_map: dict[str, tuple[int, int]] | None = None,
        raise_cpu_count: bool = False,
        raise_mem: bool = False,
        raise_disk_usage: bool = False,
    ) -> None:
        self._physical = physical
        self._logical = logical
        self._mem_total = mem_total
        # mount -> (used, total)
        self._disk_usage_map = disk_usage_map if disk_usage_map is not None else {"C:\\": (500, 1000), "/": (500, 1000)}
        self._raise_cpu_count = raise_cpu_count
        self._raise_mem = raise_mem
        self._raise_disk_usage = raise_disk_usage

    def cpu_count(self, logical: bool = True) -> int | None:
        if self._raise_cpu_count:
            raise RuntimeError("cpu_count failed")
        return self._logical if logical else self._physical

    def virtual_memory(self) -> SimpleNamespace:
        if self._raise_mem:
            raise RuntimeError("virtual_memory failed")
        return SimpleNamespace(total=self._mem_total)

    def disk_usage(self, mountpoint: str) -> SimpleNamespace:
        if self._raise_disk_usage:
            raise RuntimeError("disk_usage failed")
        used, total = self._disk_usage_map[mountpoint]  # KeyError if unknown mount (caught upstream)
        return SimpleNamespace(used=used, total=total)


class _AllRaisingPsutilBackend:
    """全メソッドが例外を送出するpsutil相当のバックエンド(全滅シナリオ用)。"""

    def cpu_count(self, logical: bool = True) -> int:
        raise RuntimeError("cpu_count failed")

    def virtual_memory(self):
        raise RuntimeError("virtual_memory failed")

    def disk_usage(self, mountpoint: str):
        raise RuntimeError("disk_usage failed")


class _FakePlatform:
    def __init__(
        self,
        system: str = "Windows",
        release: str = "11",
        version: str = "10.0.22631",
        node: str = "test-host",
        processor: str = "Intel(R) Core(TM) i7",
        machine: str = "AMD64",
        mac_ver: tuple[str, tuple, str] = ("14.1", ("", "", ""), "arm64"),
        python_version: str = "3.12.13",
    ) -> None:
        self._system = system
        self._release = release
        self._version = version
        self._node = node
        self._processor = processor
        self._machine = machine
        self._mac_ver = mac_ver
        self._python_version = python_version

    def system(self) -> str:
        return self._system

    def release(self) -> str:
        return self._release

    def version(self) -> str:
        return self._version

    def node(self) -> str:
        return self._node

    def processor(self) -> str:
        return self._processor

    def machine(self) -> str:
        return self._machine

    def mac_ver(self) -> tuple[str, tuple, str]:
        return self._mac_ver

    def python_version(self) -> str:
        return self._python_version


class _AllRaisingPlatform:
    """全メソッドが例外を送出するplatform相当のオブジェクト(全滅シナリオ用)。"""

    def system(self) -> str:
        raise RuntimeError("system failed")

    def release(self) -> str:
        raise RuntimeError("release failed")

    def version(self) -> str:
        raise RuntimeError("version failed")

    def node(self) -> str:
        raise RuntimeError("node failed")

    def processor(self) -> str:
        raise RuntimeError("processor failed")

    def machine(self) -> str:
        raise RuntimeError("machine failed")

    def mac_ver(self):
        raise RuntimeError("mac_ver failed")

    def python_version(self) -> str:
        raise RuntimeError("python_version failed")


class _NoAttrsPlatform:
    """machine()/mac_ver()自体を持たない(属性アクセス自体がAttributeErrorになる)platform相当。"""

    def system(self) -> str:
        return "Windows"

    def release(self) -> str:
        return "11"

    def version(self) -> str:
        return "10.0.22631"

    def node(self) -> str:
        return "host"

    def processor(self) -> str:
        return "CPU"

    def python_version(self) -> str:
        return "3.12.13"


# --- collect_system_info: Windows分岐 ---


def test_collect_system_info_windows_happy_path() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(), plat=_FakePlatform())

    assert info.os_name == "Windows"
    assert info.os_display == "Windows 11"
    assert info.kernel == "10.0.22631"  # Windowsのkernelはversion()
    assert info.hostname == "test-host"
    assert info.cpu_model == "Intel(R) Core(TM) i7"  # Windowsはprocessor()
    assert info.cpu_physical_cores == 4
    assert info.cpu_logical_cores == 8
    assert info.memory_total == 16_000_000_000
    assert info.disk_mount == "C:\\"
    assert info.disk_used == 500
    assert info.disk_total == 1000
    assert info.python_version == "3.12.13"


def test_collect_system_info_handles_cpu_count_failure() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(raise_cpu_count=True), plat=_FakePlatform())
    assert info.cpu_physical_cores is None
    assert info.cpu_logical_cores is None


def test_collect_system_info_handles_memory_failure() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(raise_mem=True), plat=_FakePlatform())
    assert info.memory_total is None


def test_collect_system_info_handles_disk_usage_failure() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(raise_disk_usage=True), plat=_FakePlatform())
    assert info.disk_used is None
    assert info.disk_total is None


def test_collect_system_info_falls_back_to_na_for_empty_processor_on_windows() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(), plat=_FakePlatform(processor=""))
    assert info.cpu_model == "N/A"


# --- collect_system_info: Linux分岐(/etc/os-release, /proc/cpuinfoのファイル読み) ---


def test_collect_system_info_linux_reads_os_release_and_cpuinfo(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 22.04.3 LTS"\nVERSION_ID="22.04"\n', encoding="utf-8")
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor\t: 0\nmodel name\t: Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz\n", encoding="utf-8"
    )

    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (300, 900)}),
        plat=_FakePlatform(system="Linux", release="5.15.0-91-generic"),
        os_release_path=str(os_release),
        cpuinfo_path=str(cpuinfo),
    )

    assert info.os_name == "Linux"
    assert info.os_display == "Ubuntu 22.04.3 LTS"  # PRETTY_NAME優先
    assert info.kernel == "5.15.0-91-generic"  # Linuxのkernelはrelease()
    assert info.cpu_model == "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz"  # /proc/cpuinfo由来
    assert info.disk_mount == "/"
    assert info.disk_used == 300
    assert info.disk_total == 900


def test_collect_system_info_linux_falls_back_when_os_release_unreadable(tmp_path) -> None:
    missing_path = tmp_path / "does-not-exist"
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.2.0"),
        os_release_path=str(missing_path),
        cpuinfo_path=str(tmp_path / "also-missing"),
    )
    assert info.os_display == "Linux 6.2.0"  # PRETTY_NAME取得失敗時はsystem()+release()
    assert info.cpu_model == "N/A"  # /proc/cpuinfo読み取り失敗時


# --- collect_system_info: Darwin(macOS)分岐 ---


def test_collect_system_info_darwin_uses_mac_ver_and_machine() -> None:
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (10, 20)}),
        plat=_FakePlatform(system="Darwin", release="23.1.0", mac_ver=("14.1", ("", "", ""), "arm64"), machine="arm64"),
    )
    assert info.os_display == "macOS 14.1"
    assert info.kernel == "23.1.0"  # Darwinのkernelはrelease()
    assert info.cpu_model == "arm64"  # Darwinはmachine()
    assert info.disk_mount == "/"
    assert info.disk_used == 10
    assert info.disk_total == 20


def test_collect_system_info_darwin_falls_back_when_mac_ver_unavailable() -> None:
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Darwin", release="23.1.0", mac_ver=("", ("", "", ""), "")),
    )
    assert info.os_display == "Darwin"


# --- collect_system_info: 未知OS分岐 ---


def test_collect_system_info_unknown_os_uses_generic_fallback() -> None:
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="FreeBSD", release="13.2", version="FreeBSD 13.2"),
    )
    assert info.os_display == "FreeBSD 13.2"
    assert info.kernel == "13.2"  # releaseが優先、なければversion
    assert info.disk_mount == "/"


# --- 属性自体が存在しないplatform(machine()/mac_ver()未定義)への耐性 ---


def test_collect_system_info_tolerates_platform_missing_machine_and_mac_ver_methods() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(), plat=_NoAttrsPlatform())
    assert info.os_display == "Windows 11"
    assert info.cpu_model == "CPU"  # Windows分岐はprocessor()のみ使うため無関係


# --- 全滅シナリオ: backend・platformともに全メソッドが例外を送出しても例外を送出しない ---


def test_collect_system_info_survives_backend_and_platform_total_failure() -> None:
    info = collect_system_info(backend=_AllRaisingPsutilBackend(), plat=_AllRaisingPlatform())

    assert info.os_name == "N/A"
    assert info.os_display == "N/A"
    assert info.kernel == "N/A"
    assert info.hostname == "N/A"
    assert info.cpu_model == "N/A"
    assert info.cpu_physical_cores is None
    assert info.cpu_logical_cores is None
    assert info.memory_total is None
    assert info.disk_used is None
    assert info.disk_total is None
    assert info.python_version == "N/A"


def test_blank_system_info_is_all_na() -> None:
    info = blank_system_info()
    assert info.os_name == "N/A"
    assert info.os_display == "N/A"
    assert info.kernel == "N/A"
    assert info.hostname == "N/A"
    assert info.cpu_model == "N/A"
    assert info.cpu_physical_cores is None
    assert info.cpu_logical_cores is None
    assert info.memory_total is None
    assert info.disk_mount == "N/A"
    assert info.disk_used is None
    assert info.disk_total is None
    assert info.python_version == "N/A"


# --- /etc/os-release, /proc/cpuinfoパーサの純関数テスト ---


def test_parse_os_release_pretty_name_extracts_quoted_value() -> None:
    content = 'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 22.04.3 LTS"\n'
    assert _parse_os_release_pretty_name(content) == "Ubuntu 22.04.3 LTS"


def test_parse_os_release_pretty_name_returns_none_when_missing() -> None:
    content = 'NAME="Ubuntu"\nVERSION_ID="22.04"\n'
    assert _parse_os_release_pretty_name(content) is None


def test_parse_cpuinfo_model_name_extracts_first_match() -> None:
    content = "processor\t: 0\nmodel name\t: AMD Ryzen 9\nprocessor\t: 1\nmodel name\t: AMD Ryzen 9\n"
    assert _parse_cpuinfo_model_name(content) == "AMD Ryzen 9"


def test_parse_cpuinfo_model_name_returns_none_when_missing() -> None:
    content = "processor\t: 0\nvendor_id\t: GenuineIntel\n"
    assert _parse_cpuinfo_model_name(content) is None


# --- OS別ロゴ選択 ---


@pytest.mark.parametrize(
    ("system", "distro_id", "expected_logo"),
    [
        ("Windows", None, WINDOWS_LOGO),
        ("Linux", None, LINUX_LOGO),
        ("Darwin", None, DARWIN_LOGO),
        ("SomeUnknownOS", None, FALLBACK_LOGO),
        ("", None, FALLBACK_LOGO),
        ("Linux", "ubuntu", UBUNTU_LOGO),
        ("Linux", "debian", DEBIAN_LOGO),
        ("Linux", "fedora", FEDORA_LOGO),
        ("Linux", "arch", ARCH_LOGO),
        ("Linux", "linuxmint", LINUXMINT_LOGO),
        ("Linux", "manjaro", MANJARO_LOGO),
        ("Linux", "raspbian", RASPBIAN_LOGO),
        ("Linux", "rhel", RHEL_LOGO),
        ("Linux", "centos", CENTOS_LOGO),
        ("Linux", "almalinux", ALMALINUX_LOGO),
        ("Linux", "rocky", ROCKY_LOGO),
        ("Linux", "kali", KALI_LOGO),
        ("Linux", "alpine", ALPINE_LOGO),
        ("Linux", "pop", POP_LOGO),
        ("Linux", "gentoo", GENTOO_LOGO),
        ("Linux", "opensuse-leap", OPENSUSE_LOGO),  # openSUSEはID前方一致
        ("Linux", "opensuse-tumbleweed", OPENSUSE_LOGO),
        ("Linux", "slackware", LINUX_LOGO),  # 未対応ディストリはTux(汎用)にフォールバック
        ("Windows", "ubuntu", WINDOWS_LOGO),  # distro_idはsystem=="Linux"の時のみ有効
    ],
)
def test_logo_for_system(system: str, distro_id: str | None, expected_logo: str) -> None:
    assert logo_for_system(system, distro_id) == expected_logo


def test_logo_for_system_falls_back_via_id_like_chain() -> None:
    """ID完全一致が無い場合、ID_LIKEのトークンを順に試して最初に一致したファミリーへ解決する。"""
    # Nobara(Fedoraベース)相当: ID=nobara, ID_LIKE=fedora
    assert logo_for_system("Linux", "nobara", "fedora") == FEDORA_LOGO
    # Oracle Linux相当: ID=ol, ID_LIKE="rhel fedora"(先頭トークンrhelが優先)
    assert logo_for_system("Linux", "ol", "rhel fedora") == RHEL_LOGO
    # ID_LIKEも一致しなければTux
    assert logo_for_system("Linux", "unknowndistro", "alsounknown") == LINUX_LOGO


def test_logo_for_system_raspberry_pi_64bit_special_case() -> None:
    """Raspberry Pi OS 64bit版はID=debianを名乗るため(os-release自体にはRaspberry Pi関連の
    情報が出ない)、is_raspberry_pi(ハードウェア由来の別経路で判定済みのフラグ)がTrueの場合のみ
    raspbianロゴを優先する(通常のDebianとの誤判定を防ぐ)。
    """
    assert logo_for_system("Linux", "debian", None, is_raspberry_pi=True) == RASPBIAN_LOGO
    # is_raspberry_pi=Falseなら通常のDebian
    assert logo_for_system("Linux", "debian", None, is_raspberry_pi=False) == DEBIAN_LOGO
    # ID=debian以外ではこの特例は発動しない
    assert logo_for_system("Linux", "ubuntu", None, is_raspberry_pi=True) == UBUNTU_LOGO


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("opensuse", True),
        ("opensuse-leap", True),
        ("opensuse-tumbleweed", True),
        ("opensuseful", False),  # 前方一致が広すぎて誤マッチしないことの回帰テスト
        ("opensusex", False),
    ],
)
def test_opensuse_prefix_match_has_word_boundary(token: str, expected: bool) -> None:
    result = logo_for_system("Linux", token) == OPENSUSE_LOGO
    assert result is expected


@pytest.mark.parametrize(
    ("name", "logo"),
    [
        ("WINDOWS_LOGO", WINDOWS_LOGO),
        ("UBUNTU_LOGO", UBUNTU_LOGO),
        ("DEBIAN_LOGO", DEBIAN_LOGO),
        ("FEDORA_LOGO", FEDORA_LOGO),
        ("ARCH_LOGO", ARCH_LOGO),
        ("LINUXMINT_LOGO", LINUXMINT_LOGO),
        ("MANJARO_LOGO", MANJARO_LOGO),
        ("OPENSUSE_LOGO", OPENSUSE_LOGO),
        ("RASPBIAN_LOGO", RASPBIAN_LOGO),
        ("RHEL_LOGO", RHEL_LOGO),
        ("CENTOS_LOGO", CENTOS_LOGO),
        ("ALMALINUX_LOGO", ALMALINUX_LOGO),
        ("ROCKY_LOGO", ROCKY_LOGO),
        ("KALI_LOGO", KALI_LOGO),
        ("ALPINE_LOGO", ALPINE_LOGO),
        ("POP_LOGO", POP_LOGO),
        ("GENTOO_LOGO", GENTOO_LOGO),
        ("LINUX_LOGO", LINUX_LOGO),
        ("DARWIN_LOGO", DARWIN_LOGO),
        ("FALLBACK_LOGO", FALLBACK_LOGO),
    ],
)
def test_logo_fits_within_sidebar_content_width(name: str, logo: str) -> None:
    """各ロゴはRichマークアップを解決した実表示幅(cell_len。全角・半ブロックは幅1)が
    サイドバー内寸(SIDEBAR_CONTENT_WIDTH)以内に収まっていること(最長行長チェック)。
    はみ出すとサイドバーの罫線を突き破って崩れて表示される。
    """
    from rich.cells import cell_len
    from rich.text import Text

    plain = Text.from_markup(logo).plain
    longest = max((cell_len(line) for line in plain.splitlines()), default=0)
    assert longest <= SIDEBAR_CONTENT_WIDTH, f"{name}: longest line is {longest} (limit {SIDEBAR_CONTENT_WIDTH})"


@pytest.mark.parametrize(
    ("name", "logo"),
    [
        ("WINDOWS_LOGO_LG", WINDOWS_LOGO_LG),
        ("UBUNTU_LOGO_LG", UBUNTU_LOGO_LG),
        ("DEBIAN_LOGO_LG", DEBIAN_LOGO_LG),
        ("FEDORA_LOGO_LG", FEDORA_LOGO_LG),
        ("ARCH_LOGO_LG", ARCH_LOGO_LG),
        ("LINUXMINT_LOGO_LG", LINUXMINT_LOGO_LG),
        ("MANJARO_LOGO_LG", MANJARO_LOGO_LG),
        ("OPENSUSE_LOGO_LG", OPENSUSE_LOGO_LG),
        ("RASPBIAN_LOGO_LG", RASPBIAN_LOGO_LG),
        ("RHEL_LOGO_LG", RHEL_LOGO_LG),
        ("CENTOS_LOGO_LG", CENTOS_LOGO_LG),
        ("ALMALINUX_LOGO_LG", ALMALINUX_LOGO_LG),
        ("ROCKY_LOGO_LG", ROCKY_LOGO_LG),
        ("KALI_LOGO_LG", KALI_LOGO_LG),
        ("ALPINE_LOGO_LG", ALPINE_LOGO_LG),
        ("POP_LOGO_LG", POP_LOGO_LG),
        ("GENTOO_LOGO_LG", GENTOO_LOGO_LG),
        ("LINUX_LOGO_LG", LINUX_LOGO_LG),
        ("DARWIN_LOGO_LG", DARWIN_LOGO_LG),
    ],
)
def test_wide_logo_fits_within_sidebar_wide_content_width(name: str, logo: str) -> None:
    """幅140以上のワイドサイドバー用ロゴ(_LG)は、実表示幅がSIDEBAR_WIDE_CONTENT_WIDTH(40)
    以内に収まっていること。
    """
    from rich.cells import cell_len
    from rich.text import Text

    plain = Text.from_markup(logo).plain
    longest = max((cell_len(line) for line in plain.splitlines()), default=0)
    assert longest <= SIDEBAR_WIDE_CONTENT_WIDTH, (
        f"{name}: longest line is {longest} (limit {SIDEBAR_WIDE_CONTENT_WIDTH})"
    )


# --- ディストリID(os-release ID)によるロゴ選択の統合(collect_system_info経由) ---


def test_collect_system_info_ubuntu_selects_ubuntu_logo_via_distro_id(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=ubuntu\nPRETTY_NAME="Ubuntu 22.04.3 LTS"\n', encoding="utf-8")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="5.15.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(tmp_path / "missing-cpuinfo"),
    )
    assert info.linux_distro_id == "ubuntu"
    assert logo_for_system(info.os_name, info.linux_distro_id) == UBUNTU_LOGO


def test_collect_system_info_debian_selects_debian_logo_via_distro_id(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=debian\nPRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n', encoding="utf-8")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.1.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(tmp_path / "missing-cpuinfo"),
    )
    assert info.linux_distro_id == "debian"
    assert logo_for_system(info.os_name, info.linux_distro_id) == DEBIAN_LOGO


def test_collect_system_info_known_distro_id_selects_dedicated_logo(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=fedora\nPRETTY_NAME="Fedora Linux 40"\n', encoding="utf-8")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.8.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(tmp_path / "missing-cpuinfo"),
    )
    assert info.linux_distro_id == "fedora"
    assert logo_for_system(info.os_name, info.linux_distro_id) == FEDORA_LOGO


def test_collect_system_info_unsupported_distro_id_falls_back_to_tux(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=slackware\nPRETTY_NAME="Slackware Linux"\n', encoding="utf-8")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.8.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(tmp_path / "missing-cpuinfo"),
    )
    assert info.linux_distro_id == "slackware"
    assert logo_for_system(info.os_name, info.linux_distro_id) == LINUX_LOGO


def test_collect_system_info_captures_id_like(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text(
        'ID=nobara\nID_LIKE=fedora\nNAME="Nobara Linux"\nPRETTY_NAME="Nobara Linux 40"\n', encoding="utf-8"
    )
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.8.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(tmp_path / "missing-cpuinfo"),
        device_tree_model_path=str(tmp_path / "missing-device-tree-model"),
    )
    assert info.linux_distro_id == "nobara"
    assert info.linux_distro_id_like == "fedora"
    assert info.linux_is_raspberry_pi is False
    assert logo_for_system(info.os_name, info.linux_distro_id, info.linux_distro_id_like) == FEDORA_LOGO


def test_collect_system_info_raspberry_pi_64bit_integration_via_device_tree(tmp_path) -> None:
    """実際のRaspberry Pi OS 64bit相当のos-release(ID=debian、NAME/PRETTY_NAMEもDebianを名乗る)
    から、/proc/device-tree/model相当のハードウェア情報経由でraspbianロゴが選ばれることを
    collect_system_info〜logo_for_systemの通しで確認する。
    """
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=debian\nNAME="Debian GNU/Linux"\nPRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n', encoding="utf-8")
    device_tree_model = tmp_path / "device-tree-model"
    device_tree_model.write_bytes(b"Raspberry Pi 4 Model B Rev 1.4\x00")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.6.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(tmp_path / "missing-cpuinfo"),
        device_tree_model_path=str(device_tree_model),
    )
    assert info.linux_distro_id == "debian"
    assert info.linux_is_raspberry_pi is True
    logo = logo_for_system(info.os_name, info.linux_distro_id, info.linux_distro_id_like, info.linux_is_raspberry_pi)
    assert logo == RASPBIAN_LOGO


def test_collect_system_info_raspberry_pi_detected_via_cpuinfo_fallback(tmp_path) -> None:
    """device-tree/modelが存在しない環境でも、/proc/cpuinfoにRaspberry Piの記載があれば
    検出できることを確認する(32bit版Raspberry Pi OS等、環境差のフォールバック経路)。
    """
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=debian\nNAME="Debian GNU/Linux"\n', encoding="utf-8")
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("Hardware\t: BCM2835\nModel\t\t: Raspberry Pi 3 Model B Rev 1.2\n", encoding="utf-8")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="5.10.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(cpuinfo),
        device_tree_model_path=str(tmp_path / "missing-device-tree-model"),
    )
    assert info.linux_is_raspberry_pi is True


def test_collect_system_info_non_raspberry_pi_debian_stays_false(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=debian\nNAME="Debian GNU/Linux"\n', encoding="utf-8")
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("model name\t: Intel(R) Core(TM) i7\n", encoding="utf-8")
    info = collect_system_info(
        backend=_FakePsutilBackend(disk_usage_map={"/": (1, 2)}),
        plat=_FakePlatform(system="Linux", release="6.6.0"),
        os_release_path=str(os_release),
        cpuinfo_path=str(cpuinfo),
        device_tree_model_path=str(tmp_path / "missing-device-tree-model"),
    )
    assert info.linux_is_raspberry_pi is False


def test_parse_os_release_field_extracts_id_like() -> None:
    assert _parse_os_release_field('ID=nobara\nID_LIKE=fedora\n', "ID_LIKE") == "fedora"


def test_collect_system_info_windows_has_no_distro_id() -> None:
    info = collect_system_info(backend=_FakePsutilBackend(), plat=_FakePlatform())
    assert info.linux_distro_id is None


def test_parse_os_release_id_extracts_value() -> None:
    assert _parse_os_release_id('ID=ubuntu\nID_LIKE=debian\n') == "ubuntu"


def test_parse_os_release_id_returns_none_when_missing() -> None:
    assert _parse_os_release_id('NAME="Some Linux"\n') is None


# --- os-release(5)仕様準拠(引用符・エスケープ・重複キー) ---


def test_parse_os_release_field_strips_single_quotes() -> None:
    assert _parse_os_release_field("ID='ubuntu'\n", "ID") == "ubuntu"


def test_parse_os_release_field_strips_double_quotes() -> None:
    assert _parse_os_release_field('ID="ubuntu"\n', "ID") == "ubuntu"


def test_parse_os_release_field_unescapes_double_quoted_value() -> None:
    # ダブルクォート内では \\, $, ", ` がエスケープ対象(シェルのダブルクォート規則)
    content = 'PRETTY_NAME="Say \\"Hi\\" for $5 \\\\ \\`ok\\`"\n'
    assert _parse_os_release_field(content, "PRETTY_NAME") == 'Say "Hi" for $5 \\ `ok`'


def test_parse_os_release_field_does_not_unescape_single_quoted_value() -> None:
    # シングルクォート内はエスケープ処理をしない(シェル同様、バックスラッシュはそのまま)
    assert _parse_os_release_field("ID='foo\\bar'\n", "ID") == "foo\\bar"


def test_parse_os_release_field_unquoted_value_is_used_as_is() -> None:
    assert _parse_os_release_field("ID=ubuntu\n", "ID") == "ubuntu"


def test_parse_os_release_field_duplicate_key_last_one_wins() -> None:
    # os-release(5)は重複キーの扱いを規定していないが、shellのsource的挙動(後勝ち)に合わせる
    assert _parse_os_release_field("ID=first\nID=second\n", "ID") == "second"


# --- サイドバー幅切り詰め(_truncate/_line) ---


def test_truncate_returns_value_unchanged_when_within_width() -> None:
    assert _truncate("short", 10) == "short"


def test_truncate_adds_ellipsis_when_over_width() -> None:
    result = _truncate("a very long cpu model name indeed", 10)
    assert result == "a very lo…"
    assert len(result) == 10


def test_truncate_width_zero_or_less_returns_empty() -> None:
    assert _truncate("anything", 0) == ""


def test_line_truncates_long_value_so_prefix_plus_value_fits_total_width() -> None:
    long_value = "x" * 50
    result = _line("CPU: ", long_value, total_width=20)
    assert len(result) == 20
    assert result.startswith("CPU: ")


def test_line_escapes_markup_in_value_after_truncation() -> None:
    result = _line("Info: ", "[bold]evil[/bold]", total_width=SIDEBAR_CONTENT_WIDTH)
    # rich.markup.escape()によりリテラル表示され、太字マークアップとして解釈されない
    assert "\\[bold]" in result
