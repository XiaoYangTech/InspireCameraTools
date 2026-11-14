"""系统与安装环境探测，以及「一键相机」所需的键盘注入能力。

职责：
- 展台连接状态 / 机型识别（HID 优先，UVC 摄像头设备兜底）
- EasiCamera 安装目录探测（注册表卸载信息 + 常见路径 + 用户手选）
- EasiCamera / Guardian 进程检测
- 系统信息（Windows 版本、管理员权限、架构）
- ``send_key_combo``：通过 Win32 ``SendInput`` 向前台窗口发送按键
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import subprocess
import sys
import time
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

from . import hid, settings

log = logging.getLogger(__name__)

#: EasiCamera 常见安装路径（Main 目录的候选父目录）
DEFAULT_MAIN_DIRS: tuple[str, ...] = (
    r"C:\Program Files\Seewo\EasiCamera\Main",
    r"C:\Program Files (x86)\Seewo\EasiCamera\Main",
    r"C:\Program Files\CVTE\EasiCamera\Main",
    r"C:\Program Files (x86)\CVTE\EasiCamera\Main",
    r"C:\Seewo\EasiCamera\Main",
    r"D:\Program Files\Seewo\EasiCamera\Main",
    r"D:\Program Files (x86)\Seewo\EasiCamera\Main",
    r"D:\Program Files\CVTE\EasiCamera\Main",
    r"D:\Seewo\EasiCamera\Main",
    r"E:\Program Files\Seewo\EasiCamera\Main",
)

#: 进程名（用于「应用补丁前必须关闭」检查）
CAMERA_PROCESSES = ("EasiCamera.exe", "EasiCameraGuardian.exe")


# ---------------------------------------------------------------------------
# 系统信息
# ---------------------------------------------------------------------------
def is_admin() -> bool:
    """当前进程是否以管理员身份运行。"""
    try:
        import ctypes as _ct

        return bool(_ct.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - 非 Windows 或受限环境
        return False


def windows_version_text() -> str:
    """Windows 版本的可读描述。"""
    try:
        ver = sys.getwindowsversion()
        build = f"Build {ver.build}"
        edition = platform.platform(terse=True)
        return f"Windows {ver.major}.{ver.minor} {build}（{edition}）"
    except Exception:  # noqa: BLE001
        return platform.platform()


def python_arch() -> str:
    return "64 位" if sys.maxsize > 2**32 else "32 位"


def get_system_info() -> dict:
    """汇总系统信息，供「设置/关于」页展示。"""
    return {
        "windows": windows_version_text(),
        "admin": is_admin(),
        "arch": python_arch(),
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "exe": sys.executable,
        "cwd": os.getcwd(),
        "version": settings.APP_VERSION,
    }


# ---------------------------------------------------------------------------
# 展台连接状态 / 机型识别
# ---------------------------------------------------------------------------
@dataclass
class CameraStatus:
    """展台连接状态。"""

    connected: bool = False
    model: str = "未连接"
    vid: int = 0
    pid: int = 0
    source: str = ""  # HID / UVC
    hid_devices: list[hid.HidDeviceInfo] = field(default_factory=list)
    camera_devices: list[dict] = field(default_factory=list)
    error: str = ""

    @property
    def vid_pid_text(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}" if self.vid else "-"

    @property
    def has_light(self) -> bool:
        info = hid.model_by_vid_pid(self.vid, self.pid)
        return bool(info and info.has_light)

    @property
    def three_level_light(self) -> bool:
        info = hid.model_by_vid_pid(self.vid, self.pid)
        return bool(info and info.three_level)


def _pick_primary_hid(devices: list[hid.HidDeviceInfo]) -> hid.HidDeviceInfo | None:
    """从希沃 HID 设备中选出最能代表展台的一个（优先有灯光能力的机型）。"""
    if not devices:
        return None
    for dev in devices:
        info = hid.model_by_vid_pid(dev.vid, dev.pid)
        if info and info.has_light:
            return dev
    return devices[0]


def detect_camera_status() -> CameraStatus:
    """探测当前展台连接状态（不会抛异常）。"""
    status = CameraStatus()
    try:
        seewo_hids = hid.find_seewo_devices()
        status.hid_devices = seewo_hids
        primary = _pick_primary_hid(seewo_hids)
        if primary is not None:
            status.connected = True
            status.model = primary.model
            status.vid = primary.vid
            status.pid = primary.pid
            status.source = "HID"
        # UVC 摄像头兜底识别（例如 HID 接口被占用/未暴露时）
        cameras = find_camera_devices()
        status.camera_devices = cameras
        if not status.connected:
            for cam in cameras:
                if cam["is_seewo"]:
                    status.connected = True
                    status.model = cam["model"]
                    status.vid = cam["vid"]
                    status.pid = cam["pid"]
                    status.source = "UVC"
                    break
    except Exception as exc:  # noqa: BLE001 - 状态探测失败不能影响主界面
        status.error = str(exc)
        log.debug("探测展台状态失败：%s", exc)
    return status


# ---------------------------------------------------------------------------
# UVC 摄像头枚举（SetupAPI，仅用于机型识别兜底）
# ---------------------------------------------------------------------------
_CAMERA_CLASS_GUIDS = (
    "ca3e7ab9-b4c3-4ae6-8251-579ef933890f",  # Camera
    "6bdd1fc6-810f-11d0-bec7-08002be2092f",  # Image
)
_SPDRP_DEVICEDESC = 0x0
_SPDRP_FRIENDLYNAME = 0xC
_DIGCF_PRESENT = 0x2

_win_dlls_ready = False
_setupapi = None
_kernel32 = None


def _ensure_win_dlls() -> bool:
    """绑定 SetupAPI（摄像头枚举用），失败返回 False。"""
    global _win_dlls_ready, _setupapi, _kernel32
    if _win_dlls_ready:
        return _setupapi is not None
    _win_dlls_ready = True
    if not hasattr(ctypes, "WinDLL"):
        return False
    try:
        from .hid import GUID, SP_DEVINFO_DATA

        setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
        setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
        setupapi.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(GUID),
            wintypes.LPCWSTR,
            wintypes.HWND,
            wintypes.DWORD,
        ]
        setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
        setupapi.SetupDiEnumDeviceInfo.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(SP_DEVINFO_DATA),
        ]
        setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
        setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVINFO_DATA),
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
        setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVINFO_DATA),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
        setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
        _setupapi = setupapi
        _kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        return True
    except Exception as exc:  # noqa: BLE001
        log.debug("绑定 SetupAPI 失败：%s", exc)
        return False


def _read_device_property(set_handle, dev_info, prop: int) -> str:
    buf = ctypes.create_string_buffer(2048)
    needed = wintypes.DWORD(0)
    ok = _setupapi.SetupDiGetDeviceRegistryPropertyW(  # type: ignore[union-attr]
        set_handle, ctypes.byref(dev_info), prop, None, buf, len(buf), ctypes.byref(needed)
    )
    if not ok:
        return ""
    return ctypes.wstring_at(ctypes.addressof(buf)).strip("\x00 ").strip()


def _parse_vid_pid(text: str) -> tuple[int, int]:
    """从设备 InstanceId / HardwareID 中解析 VID/PID。"""
    upper = text.upper()
    vi = upper.find("VID_")
    pi = upper.find("PID_")
    if vi < 0 or pi < 0 or vi + 8 > len(upper) or pi + 8 > len(upper):
        return 0, 0
    try:
        return int(upper[vi + 4 : vi + 8], 16), int(upper[pi + 4 : pi + 8], 16)
    except ValueError:
        return 0, 0


def find_camera_devices() -> list[dict]:
    """枚举系统中的摄像头/图像设备（失败返回空列表）。"""
    if sys.platform != "win32" or not _ensure_win_dlls():
        return []
    from .hid import GUID, SP_DEVINFO_DATA

    results: list[dict] = []
    seen: set[str] = set()
    for guid_text in _CAMERA_CLASS_GUIDS:
        # 用 uuid 拆解后按 GUID 结构体（小端 Data1/2/3）构造
        import uuid

        u = uuid.UUID(guid_text)
        guid = GUID(
            u.time_low,
            u.time_mid,
            u.time_hi_version,
            (ctypes.c_ubyte * 8)(*u.bytes[8:]),
        )
        set_handle = _setupapi.SetupDiGetClassDevsW(  # type: ignore[union-attr]
            ctypes.byref(guid), None, None, _DIGCF_PRESENT
        )
        if not set_handle or set_handle == ctypes.c_void_p(-1).value:
            continue
        try:
            dev_info = SP_DEVINFO_DATA()
            dev_info.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            index = 0
            while _setupapi.SetupDiEnumDeviceInfo(set_handle, index, ctypes.byref(dev_info)):  # type: ignore[union-attr]
                index += 1
                iid_buf = ctypes.create_unicode_buffer(512)
                required = wintypes.DWORD(0)
                instance_id = ""
                if _setupapi.SetupDiGetDeviceInstanceIdW(  # type: ignore[union-attr]
                    set_handle, ctypes.byref(dev_info), iid_buf, 512, ctypes.byref(required)
                ):
                    instance_id = iid_buf.value
                name = _read_device_property(set_handle, dev_info, _SPDRP_FRIENDLYNAME) or _read_device_property(
                    set_handle, dev_info, _SPDRP_DEVICEDESC
                )
                vid, pid = _parse_vid_pid(instance_id)
                if not vid:
                    hardware_ids = _read_device_property(set_handle, dev_info, 0x1)
                    vid, pid = _parse_vid_pid(hardware_ids)
                key = instance_id or f"{vid:04X}:{pid:04X}:{name}"
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    {
                        "name": name,
                        "instance_id": instance_id,
                        "vid": vid,
                        "pid": pid,
                        "model": hid.model_name(vid, pid) if vid else "",
                        "is_seewo": hid.is_seewo_device(vid, pid, instance_id),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            log.debug("枚举摄像头设备异常：%s", exc)
        finally:
            try:
                _setupapi.SetupDiDestroyDeviceInfoList(set_handle)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
    return results


# ---------------------------------------------------------------------------
# EasiCamera 安装目录 / 进程
# ---------------------------------------------------------------------------
def _registry_install_locations() -> list[str]:
    """从注册表卸载信息中提取 EasiCamera 安装位置。"""
    locations: list[str] = []
    try:
        import winreg
    except ImportError:
        return locations
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    keywords = ("easicamera", "希沃视频展台", "希沃展台")
    for root, subkey in roots:
        try:
            with winreg.OpenKey(root, subkey) as key:
                count = winreg.QueryInfoKey(key)[0]
                for idx in range(count):
                    try:
                        name = winreg.EnumKey(key, idx)
                        with winreg.OpenKey(key, name) as entry:
                            try:
                                display, _ = winreg.QueryValueEx(entry, "DisplayName")
                            except FileNotFoundError:
                                continue
                            if not any(k in str(display).lower() for k in keywords):
                                continue
                            try:
                                loc, _ = winreg.QueryValueEx(entry, "InstallLocation")
                            except FileNotFoundError:
                                loc = ""
                            try:
                                icon, _ = winreg.QueryValueEx(entry, "DisplayIcon")
                            except FileNotFoundError:
                                icon = ""
                            for raw in (loc, icon):
                                raw = str(raw or "").strip().strip('"')
                                if raw:
                                    locations.append(os.path.dirname(raw) if raw.lower().endswith(".exe") else raw)
                    except OSError:
                        continue
        except OSError:
            continue
    return locations


def _main_dir_from_root(root: str) -> str | None:
    """从安装根目录推导出 Main 目录；兼容直接给 Main 目录的情况。"""
    if not root:
        return None
    path = Path(root)
    candidates = [path, path / "Main", path / "main"]
    if path.name.lower() == "main":
        candidates = [path]
    for cand in candidates:
        try:
            if (cand / "EasiCamera.exe").is_file():
                return str(cand)
        except OSError:
            continue
    return None


def find_easicamera_dirs() -> list[str]:
    """探测本机 EasiCamera Main 目录列表（去重）。"""
    candidates: list[str] = []
    configured = str(settings.get("install_dir") or "").strip()
    if configured:
        candidates.append(configured)

    # 注册表
    for loc in _registry_install_locations():
        candidates.append(loc)
        candidates.append(str(Path(loc) / "EasiCamera"))
        candidates.append(str(Path(loc) / "Seewo" / "EasiCamera"))
    # 常见路径
    candidates.extend(DEFAULT_MAIN_DIRS)

    # 各个盘的常见安装根
    for drive in ("C:", "D:", "E:", "F:"):
        for sub in (r"\Program Files\Seewo\EasiCamera", r"\Program Files (x86)\Seewo\EasiCamera", r"\Seewo\EasiCamera"):
            candidates.append(drive + sub)

    found: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        main_dir = _main_dir_from_root(raw)
        if not main_dir:
            continue
        key = os.path.normcase(os.path.abspath(main_dir))
        if key in seen:
            continue
        seen.add(key)
        found.append(main_dir)
    return found


def detect_install_dir() -> str | None:
    """返回首个探测到的 Main 目录；没有则 None。"""
    dirs = find_easicamera_dirs()
    return dirs[0] if dirs else None


def find_easicamera_processes() -> list[str]:
    """检测正在运行的 EasiCamera 相关进程（返回进程名列表）。"""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="ignore",
            timeout=8,
            creationflags=flags,
        )
        output = (completed.stdout or "").lower()
        running = [name for name in CAMERA_PROCESSES if name.lower() in output]
        return running
    except Exception as exc:  # noqa: BLE001 - 进程检测失败按未运行处理
        log.debug("进程检测失败：%s", exc)
        return []


def is_camera_running() -> bool:
    return bool(find_easicamera_processes())


# ---------------------------------------------------------------------------
# 键盘注入（SendInput）
# ---------------------------------------------------------------------------
_VK_NAMES: dict[str, int] = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "WIN": 0x5B,
    "LWIN": 0x5B,
    "APPS": 0x5D,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
}
for _i in range(1, 25):
    _VK_NAMES[f"F{_i}"] = 0x6F + _i  # F1=0x70
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _VK_NAMES[_ch] = ord(_ch)
for _d in "0123456789":
    _VK_NAMES[_d] = ord(_d)
# 小键盘
_VK_NAMES.update({"NUM0": 0x60, "NUM1": 0x61, "NUM2": 0x62, "NUM3": 0x63, "NUM4": 0x64,
                  "NUM5": 0x65, "NUM6": 0x66, "NUM7": 0x67, "NUM8": 0x68, "NUM9": 0x69})

#: 可选的拍照目标键（下拉框用）
TARGET_KEY_CHOICES = ["F12", "F11", "F10", "F9", "Ctrl+Enter", "Ctrl+F12", "Shift+F12", "Enter", "Space", "Ctrl+Shift+P"]

_MODIFIER_VKS = {
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "SHIFT": 0x10,
    "WIN": 0x5B,
    "LWIN": 0x5B,
}

_EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5D, 0x90,
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_EXTENDEDKEY = 0x0001


def parse_key_combo(combo: str) -> tuple[list[int], int]:
    """把 ``"Ctrl+Shift+F12"`` 解析为（修饰键 VK 列表, 主键 VK）。"""
    parts = [p.strip().upper() for p in (combo or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("按键组合为空")
    if parts[-1] not in _VK_NAMES:
        raise ValueError(f"不支持的按键：{parts[-1]}")
    main_vk = _VK_NAMES[parts[-1]]
    modifiers: list[int] = []
    for part in parts[:-1]:
        if part not in _MODIFIER_VKS:
            raise ValueError(f"不支持的修饰键：{part}")
        modifiers.append(_MODIFIER_VKS[part])
    return modifiers, main_vk


def _send_key_event(vk: int, key_up: bool) -> None:
    flags = _KEYEVENTF_KEYUP if key_up else 0
    if vk in _EXTENDED_VKS:
        flags |= _KEYEVENTF_EXTENDEDKEY
    item = _INPUT()
    item.type = _INPUT_KEYBOARD
    item.union.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
    user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    sent = user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(_INPUT))
    if sent != 1:
        raise OSError(f"SendInput 失败（错误码 {ctypes.get_last_error()}）")


def send_key_combo(combo: str, hold_ms: int = 60) -> tuple[bool, str]:
    """向前台窗口发送按键组合（如 ``F12`` / ``Ctrl+Enter``）。

    返回 ``(是否成功, 错误信息)``。不抛异常。
    """
    try:
        if sys.platform != "win32":
            return False, "仅支持 Windows"
        modifiers, main_vk = parse_key_combo(combo)
        for vk in modifiers:
            _send_key_event(vk, key_up=False)
            time.sleep(0.012)
        try:
            _send_key_event(main_vk, key_up=False)
            time.sleep(max(hold_ms, 20) / 1000.0)
            _send_key_event(main_vk, key_up=True)
        finally:
            for vk in reversed(modifiers):
                time.sleep(0.012)
                _send_key_event(vk, key_up=True)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - 注入失败不能中断监听线程
        return False, str(exc)


def get_foreground_window_title() -> str:
    """当前前台窗口标题（用于日志展示）。"""
    try:
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# 打开目录 / 链接
# ---------------------------------------------------------------------------
def open_path(path: str | Path) -> tuple[bool, str]:
    """用资源管理器打开目录或文件。"""
    target = Path(path)
    try:
        if not target.exists():
            return False, f"路径不存在：{target}"
        os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def open_url(url: str) -> tuple[bool, str]:
    """用默认浏览器打开链接。"""
    try:
        webbrowser.open(url, new=2)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
