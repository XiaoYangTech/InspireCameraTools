"""展台 HID 通信模块（纯 ctypes 调用 hid.dll / setupapi.dll，无第三方 HID 库）。

协议来源：``seewo-easicamera-analysis/docs/EasiCamera_分析报告.md`` §1.2、§2.1；
契约 §6。命令/应答统一以 ``AA BB CC`` 开头：

============  ==========================================================
输出帧（写）   
查询灯光状态   ``AA BB CC 02``
开灯          ``AA BB CC 02 02 02 00 01 <level>``（level: 0x19=25 / 0x32=50 / 0x46=70）
关灯          ``AA BB CC 02 02 02 00 00 00``
触摸灯开/关/闪 ``AA BB CC 03 02 01 00 01/00/02``
查询触摸灯     ``AA BB CC 03``
查询 MCU 版本  ``AA BB CC 06``
心跳应答       ``AA BB CC 04 00``
============  ==========================================================

输入帧（读，payload 以 ``BB CC`` 开头，兼容设备附带 report-ID/0xAA 前缀）：

- ``BB CC 02 …`` LED 状态应答（payload[6]=亮灭，payload[7]=亮度）
- ``BB CC 05 …`` 机身补光灯按键通知（字段同 02）
- ``BB CC 03 …`` 触摸灯状态（payload[6]=状态）
- ``BB CC 04 01 …`` 设备心跳（主机需回应 ``AA BB CC 04 00``）
- ``BB CC 01 <n> …`` 机身按键 1..5（拍照/旋转/唤起/缩小/放大）
- ``BB CC 06 …`` MCU 版本 ASCII
- ``BB CC 0C …`` 镜头盖开合
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 协议常量
# ---------------------------------------------------------------------------
CMD_QUERY_LED = bytes((0xAA, 0xBB, 0xCC, 0x02))
CMD_LED_OFF = bytes((0xAA, 0xBB, 0xCC, 0x02, 0x02, 0x02, 0x00, 0x00, 0x00))
CMD_TOUCH_ON = bytes((0xAA, 0xBB, 0xCC, 0x03, 0x02, 0x01, 0x00, 0x01))
CMD_TOUCH_OFF = bytes((0xAA, 0xBB, 0xCC, 0x03, 0x02, 0x01, 0x00, 0x00))
CMD_TOUCH_FLASH = bytes((0xAA, 0xBB, 0xCC, 0x03, 0x02, 0x01, 0x00, 0x02))
CMD_QUERY_TOUCH = bytes((0xAA, 0xBB, 0xCC, 0x03))
CMD_QUERY_MCU = bytes((0xAA, 0xBB, 0xCC, 0x06))
CMD_HEARTBEAT_REPLY = bytes((0xAA, 0xBB, 0xCC, 0x04, 0x00))

#: 亮度档位 → 协议亮度字节：0=默认50；1/2/3=三级灯 25/50/70
LEVEL_BYTES = {0: 0x32, 1: 0x19, 2: 0x32, 3: 0x46}
LEVEL_LABELS = {0: "默认(50)", 1: "25", 2: "50", 3: "70"}

#: 机身按键编号 → 名称
KEY_NAMES = {
    1: "拍照",
    2: "旋转",
    3: "启动展台",
    4: "缩小",
    5: "放大",
}

#: 希沃展台 VID 兜底白名单
SEEWO_VIDS = (0x1FF7, 0x254A)


@dataclass(frozen=True)
class ModelInfo:
    """机型信息（VID/PID 白名单，来源：分析报告 §2.1）。"""

    vid: int
    pid: int
    name: str
    has_light: bool = False
    three_level: bool = False


#: 完整机型 / VID-PID 白名单（HID 与 UVC 两侧都列出，便于机型识别）
MODELS: tuple[ModelInfo, ...] = (
    ModelInfo(0x1BCF, 0x1001, "SC01"),
    ModelInfo(0x1BCF, 0x8003, "SC02"),
    ModelInfo(0x15AA, 0x1555, "SC03", True, False),
    ModelInfo(0x1FF7, 0x0F16, "SC03(HID)", True, False),
    ModelInfo(0x1FF7, 0x0F05, "SC03C", True, False),
    ModelInfo(0x1BCF, 0x2289, "SC05", True, False),
    ModelInfo(0x1FF7, 0x0F51, "SC06", True, False),
    ModelInfo(0x1FF7, 0x0F8D, "SC06K", True, True),
    ModelInfo(0x1FF7, 0x0F18, "SC07", True, False),
    ModelInfo(0x1FF7, 0x0F6E, "SC07", True, False),
    ModelInfo(0x1FF7, 0x0F56, "SC07E"),
    ModelInfo(0x1FF7, 0x0F59, "SC07F"),
    ModelInfo(0x1FF7, 0x0F63, "SC07F"),
    ModelInfo(0x1FF7, 0x0F4E, "SC08"),
    ModelInfo(0x1FF7, 0x0F64, "SC08 USB"),
    ModelInfo(0x1FF7, 0x0F6F, "SC13", True, True),
    ModelInfo(0x1FF7, 0x0F81, "SC13 cost", True, True),
    ModelInfo(0x1BCF, 0x0002, "SC15"),
    ModelInfo(0x1FF7, 0x0509, "SC20"),
    ModelInfo(0x1FF7, 0x0500, "SC20"),
    ModelInfo(0x1FF7, 0x0F65, "SC31"),
    ModelInfo(0x0BDA, 0x5876, "F2"),
    ModelInfo(0x1BCF, 0x2650, "F3"),
    ModelInfo(0x1FF7, 0x0508, "F6"),
    ModelInfo(0x1FF7, 0x0520, "F6"),
    ModelInfo(0x1FF7, 0x051A, "F6F98"),
    ModelInfo(0x1FF7, 0x051B, "F6F98"),
    ModelInfo(0x254A, 0x0000, "视熙(VID兜底)"),
)

_MODEL_INDEX = {(m.vid, m.pid): m for m in MODELS}


def model_by_vid_pid(vid: int, pid: int) -> ModelInfo | None:
    """按 VID/PID 查机型；未登记返回 None。"""
    return _MODEL_INDEX.get((vid & 0xFFFF, pid & 0xFFFF))


def model_name(vid: int, pid: int) -> str:
    info = model_by_vid_pid(vid, pid)
    if info:
        return info.name
    if vid in SEEWO_VIDS:
        return "希沃展台(VID兜底)"
    return f"未知设备 {vid:04X}:{pid:04X}"


# ---------------------------------------------------------------------------
# Win32 结构体 / API 定义（32/64 位均兼容）
# ---------------------------------------------------------------------------
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_DIGCF_PRESENT = 0x00000002
_DIGCF_DEVICEINTERFACE = 0x00000010
_ERROR_IO_PENDING = 997
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_HIDP_STATUS_SUCCESS = 0x00110000


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
        ("_Padding", wintypes.USHORT),  # C 结构体 4 字节对齐后的尾部填充（sizeof=12）
    ]


class HIDP_CAPS(ctypes.Structure):
    """HIDP_CAPS 完整定义（含 Reserved[17] 与 10 个计数字段，共 64 字节）。

    注意：该结构体不能只声明前几个字段——HidP_GetCaps 会写入完整结构，
    声明过小会导致堆内存越界（表现为随机崩溃/段错误）。
    """

    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


def _bind_dlls() -> tuple[ctypes.WinDLL, ctypes.WinDLL, ctypes.WinDLL] | None:
    """延迟绑定系统 DLL；非 Windows / 缺库时返回 None。"""
    if not hasattr(ctypes, "WinDLL"):
        return None
    try:
        hid = ctypes.WinDLL("hid.dll", use_last_error=True)
        setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    except OSError:
        return None

    def proto(dll, name, restype, argtypes):
        fn = getattr(dll, name)
        fn.restype = restype
        fn.argtypes = argtypes

    proto(hid, "HidD_GetHidGuid", None, [ctypes.POINTER(GUID)])
    proto(hid, "HidD_GetAttributes", wintypes.BOOLEAN, [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)])
    proto(hid, "HidD_GetProductString", wintypes.BOOLEAN, [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG])
    proto(hid, "HidD_GetManufacturerString", wintypes.BOOLEAN, [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG])
    proto(hid, "HidD_GetPreparsedData", wintypes.BOOLEAN, [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)])
    proto(hid, "HidD_FreePreparsedData", wintypes.BOOLEAN, [ctypes.c_void_p])
    proto(hid, "HidP_GetCaps", ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)])

    proto(
        setupapi,
        "SetupDiGetClassDevsW",
        wintypes.HANDLE,
        [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD],
    )
    proto(
        setupapi,
        "SetupDiEnumDeviceInterfaces",
        wintypes.BOOL,
        [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)],
    )
    proto(
        setupapi,
        "SetupDiGetDeviceInterfaceDetailW",
        wintypes.BOOL,
        [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ],
    )
    proto(setupapi, "SetupDiDestroyDeviceInfoList", wintypes.BOOL, [wintypes.HANDLE])

    proto(
        kernel32,
        "CreateFileW",
        wintypes.HANDLE,
        [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ],
    )
    proto(
        kernel32,
        "ReadFile",
        wintypes.BOOL,
        [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)],
    )
    proto(
        kernel32,
        "WriteFile",
        wintypes.BOOL,
        [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)],
    )
    proto(kernel32, "CreateEventW", wintypes.HANDLE, [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR])
    proto(kernel32, "WaitForSingleObject", wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD])
    proto(
        kernel32,
        "GetOverlappedResult",
        wintypes.BOOL,
        [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL],
    )
    proto(kernel32, "CancelIoEx", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)])
    proto(kernel32, "CloseHandle", wintypes.BOOL, [wintypes.HANDLE])
    return hid, setupapi, kernel32


_DLLS = _bind_dlls()
if _DLLS is None:
    log.warning("HID 底层 DLL 绑定失败，HID 功能不可用（非 Windows 环境？）")
_hid, _setupapi, _kernel32 = _DLLS if _DLLS else (None, None, None)

#: 非 Windows 环境标记
HID_AVAILABLE = _DLLS is not None


def _last_error() -> int:
    return ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0


# ---------------------------------------------------------------------------
# 设备对象
# ---------------------------------------------------------------------------
@dataclass
class HidDeviceInfo:
    """枚举到的 HID 接口信息（不含句柄，可安全跨线程传递）。"""

    path: str
    vid: int
    pid: int
    version: int = 0
    product: str = ""
    manufacturer: str = ""
    input_len: int = 0
    output_len: int = 0
    feature_len: int = 0
    is_seewo: bool = False

    @property
    def model(self) -> str:
        return model_name(self.vid, self.pid)

    @property
    def model_info(self) -> ModelInfo | None:
        return model_by_vid_pid(self.vid, self.pid)

    @property
    def vid_pid_text(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}"

    @property
    def display_name(self) -> str:
        base = self.model
        if self.product and self.product.lower() not in base.lower():
            return f"{base} · {self.product}"
        return base


class HidDevice:
    """一个可打开的 HID 接口句柄（非线程安全，一个实例只在一个线程用）。"""

    def __init__(self, info: HidDeviceInfo) -> None:
        self.info = info
        self._handle: int | None = None
        self._access: str = ""

    # ---------- 生命周期 ----------
    @property
    def is_open(self) -> bool:
        return self._handle is not None and self._handle != _INVALID_HANDLE

    def open(self, access: str = "rw") -> bool:
        """打开设备。access: ``rw`` 读写 / ``r`` 只读 / ``w`` 只写。"""
        self.close()
        if _kernel32 is None:
            return False
        generic = 0
        if "r" in access:
            generic |= _GENERIC_READ
        if "w" in access:
            generic |= _GENERIC_WRITE
        handle = _kernel32.CreateFileW(
            self.info.path,
            generic,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_OVERLAPPED,
            None,
        )
        if handle is None or handle == _INVALID_HANDLE:
            # 部分设备被独占时降级：读写失败改只读
            if access == "rw":
                return self.open("r")
            log.debug("CreateFileW 失败 path=%s err=%s", self.info.path, _last_error())
            self._handle = None
            return False
        self._handle = int(handle)
        self._access = access
        return True

    def close(self) -> None:
        if self._handle is not None and _kernel32 is not None:
            try:
                _kernel32.CloseHandle(self._handle)
            except Exception:  # noqa: BLE001 - 关闭失败不影响后续
                pass
        self._handle = None

    def __enter__(self) -> "HidDevice":
        if not self.open():
            raise OSError(f"打开 HID 失败：{self.info.path}")
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ---------- 读写（overlapped + 超时） ----------
    def _wait_overlapped(self, event: int, ov: OVERLAPPED, handle: int, timeout_ms: int) -> tuple[bool, int]:
        wait = _kernel32.WaitForSingleObject(event, int(timeout_ms))
        if wait == _WAIT_OBJECT_0:
            transferred = wintypes.DWORD(0)
            ok = _kernel32.GetOverlappedResult(handle, ctypes.byref(ov), ctypes.byref(transferred), False)
            if not ok:
                return False, 0
            return True, int(transferred.value)
        if wait == _WAIT_TIMEOUT:
            try:
                _kernel32.CancelIoEx(handle, ctypes.byref(ov))
            except Exception:  # noqa: BLE001
                pass
            return False, 0
        return False, 0

    def write(self, data: bytes, timeout_ms: int = 800) -> bool:
        """按协议原样写入输出报告（首字节 0xAA）。"""
        if not self.is_open or _kernel32 is None:
            return False
        length = self.info.output_len or len(data)
        buf = ctypes.create_string_buffer(length)
        ctypes.memmove(buf, bytes(data), min(len(data), length))
        event = _kernel32.CreateEventW(None, True, False, None)
        if not event:
            return False
        try:
            ov = OVERLAPPED()
            ov.hEvent = event
            written = wintypes.DWORD(0)
            ok = _kernel32.WriteFile(
                self._handle, buf, length, ctypes.byref(written), ctypes.byref(ov)
            )
            if ok:
                return True
            if _last_error() != _ERROR_IO_PENDING:
                log.debug("WriteFile 失败 err=%s", _last_error())
                return False
            ok, got = self._wait_overlapped(event, ov, self._handle, timeout_ms)
            return ok and got >= 0
        finally:
            _kernel32.CloseHandle(event)

    def read(self, timeout_ms: int = 200) -> bytes:
        """读取一个输入报告（原始字节）。超时返回空 bytes。"""
        if not self.is_open or _kernel32 is None:
            return b""
        length = self.info.input_len or 64
        buf = ctypes.create_string_buffer(length)
        event = _kernel32.CreateEventW(None, True, False, None)
        if not event:
            return b""
        try:
            ov = OVERLAPPED()
            ov.hEvent = event
            read = wintypes.DWORD(0)
            ok = _kernel32.ReadFile(self._handle, buf, length, ctypes.byref(read), ctypes.byref(ov))
            if ok:
                return buf.raw[: int(read.value)]
            if _last_error() != _ERROR_IO_PENDING:
                return b""
            ok, got = self._wait_overlapped(event, ov, self._handle, timeout_ms)
            if not ok or got <= 0:
                return b""
            return buf.raw[:got]
        finally:
            _kernel32.CloseHandle(event)


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
def _device_path_from_set(set_handle: int) -> list[str]:
    """枚举 HID 设备接口路径列表。"""
    paths: list[str] = []
    if _setupapi is None or _hid is None:
        return paths
    guid = GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    did = SP_DEVICE_INTERFACE_DATA()
    did.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
    index = 0
    while True:
        ok = _setupapi.SetupDiEnumDeviceInterfaces(
            set_handle, None, ctypes.byref(guid), index, ctypes.byref(did)
        )
        if not ok:
            break
        index += 1
        needed = wintypes.DWORD(0)
        _setupapi.SetupDiGetDeviceInterfaceDetailW(
            set_handle, ctypes.byref(did), None, 0, ctypes.byref(needed), None
        )
        if needed.value == 0:
            continue
        buf = ctypes.create_string_buffer(needed.value)
        # cbSize：SP_DEVICE_INTERFACE_DETAIL_DATA_W 在 32 位下为 6、64 位下为 8
        ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        ok = _setupapi.SetupDiGetDeviceInterfaceDetailW(
            set_handle, ctypes.byref(did), buf, needed.value, None, None
        )
        if not ok:
            continue
        try:
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
        except (ValueError, OSError):
            continue
        if path:
            paths.append(path)
    return paths


def _inspect_device(path: str) -> HidDeviceInfo | None:
    """打开设备读取 VID/PID/产品名/报告长度（失败返回 None）。"""
    if _kernel32 is None or _hid is None:
        return None
    handle = _kernel32.CreateFileW(
        path, 0, _FILE_SHARE_READ | _FILE_SHARE_WRITE, None, _OPEN_EXISTING, 0, None
    )
    if handle is None or handle == _INVALID_HANDLE:
        return None
    try:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        if not _hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
            return None
        info = HidDeviceInfo(
            path=path,
            vid=int(attrs.VendorID),
            pid=int(attrs.ProductID),
            version=int(attrs.VersionNumber),
        )
        info.product = _hid_string(handle, "HidD_GetProductString") or ""
        info.manufacturer = _hid_string(handle, "HidD_GetManufacturerString") or ""
        preparsed = ctypes.c_void_p()
        if _hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)) and preparsed:
            try:
                caps = HIDP_CAPS()
                if _hid.HidP_GetCaps(preparsed, ctypes.byref(caps)) >= 0:
                    info.input_len = int(caps.InputReportByteLength)
                    info.output_len = int(caps.OutputReportByteLength)
                    info.feature_len = int(caps.FeatureReportByteLength)
            finally:
                _hid.HidD_FreePreparsedData(preparsed)
        info.is_seewo = is_seewo_device(info.vid, info.pid, path)
        return info
    finally:
        _kernel32.CloseHandle(handle)


def _hid_string(handle: int, func_name: str) -> str:
    """读取宽字符设备字符串（产品名/厂商名）。"""
    if _hid is None:
        return ""
    fn = getattr(_hid, func_name, None)
    if fn is None:
        return ""
    buf = ctypes.create_string_buffer(512 * 2)
    try:
        if fn(handle, buf, len(buf)):
            return ctypes.wstring_at(ctypes.addressof(buf)).strip("\x00 ").strip()
    except (OSError, ValueError):
        pass
    return ""


def is_seewo_device(vid: int, pid: int, path: str = "") -> bool:
    """是否希沃展台设备：VID 白名单 / 机型白名单 / 设备路径兜底规则。"""
    if vid in SEEWO_VIDS:
        return True
    if model_by_vid_pid(vid, pid) is not None:
        return True
    low = (path or "").lower()
    return "vid_1ff7" in low or "vid_254a" in low


def enumerate_devices(only_seewo: bool = False) -> list[HidDeviceInfo]:
    """枚举当前系统的 HID 接口（SetupAPI）。异常时返回空列表，不抛异常。"""
    if _setupapi is None or _hid is None:
        return []
    set_handle = None
    results: list[HidDeviceInfo] = []
    try:
        guid = GUID()
        _hid.HidD_GetHidGuid(ctypes.byref(guid))
        set_handle = _setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid), None, None, _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE
        )
        if set_handle is None or set_handle == _INVALID_HANDLE:
            return []
        for path in _device_path_from_set(int(set_handle)):
            try:
                info = _inspect_device(path)
            except Exception as exc:  # noqa: BLE001 - 单个设备异常不影响整体枚举
                log.debug("检查 HID 设备失败 %s: %s", path, exc)
                continue
            if info is None:
                continue
            if only_seewo and not info.is_seewo:
                continue
            results.append(info)
    except Exception as exc:  # noqa: BLE001
        log.warning("HID 枚举异常：%s", exc)
    finally:
        if set_handle is not None and set_handle != _INVALID_HANDLE:
            try:
                _setupapi.SetupDiDestroyDeviceInfoList(set_handle)
            except Exception:  # noqa: BLE001
                pass
    return results


def find_seewo_devices() -> list[HidDeviceInfo]:
    """只返回希沃展台相关的 HID 接口。"""
    return enumerate_devices(only_seewo=True)


# ---------------------------------------------------------------------------
# 帧构造 / 解析
# ---------------------------------------------------------------------------
def build_led_on(level: int = 0) -> bytes:
    """构造开灯帧。level: 0=默认50，1/2/3=三级灯 25/50/70。"""
    if level not in LEVEL_BYTES:
        level = 0
    return bytes((0xAA, 0xBB, 0xCC, 0x02, 0x02, 0x02, 0x00, 0x01, LEVEL_BYTES[level]))


def build_led_off() -> bytes:
    return CMD_LED_OFF


def build_touch(action: str) -> bytes:
    mapping = {"on": CMD_TOUCH_ON, "off": CMD_TOUCH_OFF, "flash": CMD_TOUCH_FLASH, "query": CMD_QUERY_TOUCH}
    return mapping.get(action, CMD_QUERY_TOUCH)


def normalize_input(raw: bytes) -> bytes | None:
    """把原始输入报告规范化为以 ``BB CC`` 开头的 payload。

    兼容三种形态：直接 ``BB CC…``、``AA BB CC…``（多 0xAA 前缀）、
    ``00 BB CC…`` / ``00 AA BB CC…``（带 report-ID 前缀）。
    """
    if not raw:
        return None
    data = bytes(raw)
    # 跳过前导的 report-ID(0x00) 或 0xAA（最多 2 个）
    for _ in range(3):
        if data[:2] == b"\xbb\xcc":
            return data
        if len(data) >= 3 and data[1:3] == b"\xbb\xcc" and data[0] in (0x00, 0xAA):
            return data[1:]
        if len(data) >= 4 and data[2:4] == b"\xbb\xcc" and data[0] in (0x00, 0xAA) and data[1] in (0x00, 0xAA):
            return data[2:]
        break
    # 兜底：在前 4 字节内搜索 BB CC
    idx = data.find(b"\xbb\xcc", 0, 5)
    if idx > 0:
        return data[idx:]
    return None


@dataclass
class FrameInfo:
    """解析后的 HID 输入帧。"""

    raw: bytes
    payload: bytes
    cmd: int = -1
    kind: str = "other"  # led / led_key / key / touch / heartbeat / mcu / cover / mode / other
    description: str = ""
    led_on: bool | None = None
    led_level: int | None = None
    key_index: int | None = None
    key_name: str = ""
    touch_state: int | None = None
    cover_open: bool | None = None
    mcu_version: str = ""
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # 来源设备 VID:PID

    @property
    def hex_raw(self) -> str:
        return " ".join(f"{b:02X}" for b in self.raw)

    @property
    def hex_payload(self) -> str:
        return " ".join(f"{b:02X}" for b in self.payload)


def parse_input_frame(raw: bytes, source: str = "") -> FrameInfo | None:
    """解析输入帧；不是有效协议帧时返回 None。"""
    payload = normalize_input(raw)
    if payload is None or len(payload) < 3:
        return None
    frame = FrameInfo(raw=bytes(raw), payload=payload, cmd=payload[2], source=source)
    cmd = frame.cmd
    if cmd in (0x02, 0x05):
        frame.kind = "led" if cmd == 0x02 else "led_key"
        if len(payload) > 8:
            frame.led_on = payload[6] == 0x01
            frame.led_level = payload[7]
            frame.description = (
                f"{'灯状态应答' if cmd == 0x02 else '机身灯按键通知'}："
                f"{'开' if frame.led_on else '关'}，亮度={payload[7]}"
            )
        else:
            frame.description = f"灯状态帧（长度不足，原始 {frame.hex_payload}）"
    elif cmd == 0x01:
        frame.kind = "key"
        frame.key_index = payload[3] if len(payload) > 3 else None
        frame.key_name = KEY_NAMES.get(frame.key_index or -1, "未知按键")
        frame.description = f"机身按键 {frame.key_index}（{frame.key_name}）"
    elif cmd == 0x03:
        frame.kind = "touch"
        frame.touch_state = payload[6] if len(payload) > 6 else None
        names = {0: "关", 1: "开", 2: "闪烁"}
        frame.description = f"触摸灯状态：{names.get(frame.touch_state, frame.touch_state)}"
    elif cmd == 0x04:
        frame.kind = "heartbeat"
        is_heartbeat = len(payload) > 3 and payload[3] == 0x01
        frame.description = "设备心跳" if is_heartbeat else f"04 帧：{frame.hex_payload}"
    elif cmd == 0x06:
        frame.kind = "mcu"
        try:
            frame.mcu_version = bytes(payload[2:]).decode("ascii", errors="ignore").strip("\x00 ")
        except Exception:  # noqa: BLE001
            frame.mcu_version = ""
        frame.description = f"MCU 版本：{frame.mcu_version or frame.hex_payload}"
    elif cmd == 0x0C:
        frame.kind = "cover"
        frame.cover_open = (payload[6] == 0x01) if len(payload) > 6 else None
        frame.description = f"镜头盖：{'打开' if frame.cover_open else '合上'}"
    elif cmd == 0x09:
        frame.kind = "mode"
        frame.description = f"SC08 模式切换：{frame.hex_payload}"
    else:
        frame.kind = "other"
        frame.description = f"未知命令 cmd=0x{cmd:02X}：{frame.hex_payload}"
    return frame


def is_led_frame(raw: bytes) -> bool:
    payload = normalize_input(raw)
    return bool(payload and len(payload) > 8 and payload[2] in (0x02, 0x05))


def is_heartbeat_frame(raw: bytes) -> bool:
    payload = normalize_input(raw)
    return bool(payload and len(payload) > 3 and payload[2] == 0x04 and payload[3] == 0x01)


# ---------------------------------------------------------------------------
# 控制器：SendAPI（写命令 + 查询）
# ---------------------------------------------------------------------------
@dataclass
class LedState:
    on: bool
    level: int = 0
    raw: bytes = b""
    source: str = ""

    @property
    def text(self) -> str:
        return f"{'已开灯' if self.on else '已关灯'}（亮度 {self.level}）"


class HidController:
    """对希沃展台 HID 发送命令的高层封装（带主接口/全部接口回退策略）。

    使用方式（每次操作独立开关句柄，避免长期占用设备）::

        ctrl = HidController()
        state = ctrl.query_led()
        ctrl.turn_on_light(level=2)
    """

    def __init__(self, prefer_all: bool = False) -> None:
        self.prefer_all = prefer_all
        self.last_message = ""
        self._lock = threading.Lock()

    # ---------- 目标选择 ----------
    def _devices(self) -> list[HidDeviceInfo]:
        devices = enumerate_devices()
        if self.prefer_all:
            return [d for d in devices if d.output_len > 0 or d.input_len > 0]
        primary = [d for d in devices if d.is_seewo]
        if primary:
            return primary
        # 兜底：没有任何希沃 VID 时尝试全部有输出报告的 HID（旧版工具行为）
        return [d for d in devices if d.output_len > 0]

    # ---------- 底层发送 ----------
    def _write_to_device(self, info: HidDeviceInfo, cmd: bytes, attempts: int = 2) -> bool:
        dev = HidDevice(info)
        try:
            if not dev.open("w"):
                dev.close()
                # 部分设备只允许读打开；再试读写
                if not dev.open("rw"):
                    return False
            for i in range(attempts):
                if dev.write(cmd, 800):
                    return True
                time.sleep(0.06)
            return False
        finally:
            dev.close()

    def _send(self, cmd: bytes, verify_led: bool = False, expect_on: bool | None = None) -> dict:
        """发送命令到目标 HID；返回统计信息。"""
        with self._lock:
            targets = self._devices()
            if not targets:
                self.last_message = "未发现可用的展台 HID 接口。请确认展台已连接，或关闭 EasiCamera/Guardian 后重试。"
                return {"ok": False, "written": 0, "confirmed": False}
            written = 0
            confirmed = False
            detail: list[str] = []
            for info in targets:
                ok = self._write_to_device(info, cmd)
                if ok:
                    written += 1
                detail.append(f"{info.vid_pid_text}{'✓' if ok else '✗'}")
                if verify_led and ok:
                    time.sleep(0.12)
                    state = self._read_led_once(info, 900)
                    if state is not None and expect_on is not None and state.on == expect_on:
                        confirmed = True
            self.last_message = "写入接口：" + " ".join(detail)
            return {"ok": written > 0, "written": written, "confirmed": confirmed, "detail": detail}

    def _read_led_once(self, info: HidDeviceInfo, timeout_ms: int = 1200) -> LedState | None:
        dev = HidDevice(info)
        try:
            if not dev.open("r"):
                return None
            deadline = time.monotonic() + timeout_ms / 1000.0
            while time.monotonic() < deadline:
                raw = dev.read(200)
                if not raw:
                    continue
                frame = parse_input_frame(raw, source=info.vid_pid_text)
                if frame and frame.kind == "led" and frame.led_on is not None:
                    return LedState(frame.led_on, frame.led_level or 0, raw, info.vid_pid_text)
            return None
        finally:
            dev.close()

    # ---------- 高层命令 ----------
    def turn_on_light(self, level: int = 0) -> dict:
        result = self._send(build_led_on(level), verify_led=True, expect_on=True)
        result["message"] = (
            f"开灯命令已发送（亮度 {LEVEL_LABELS.get(level, level)}）"
            if result["ok"]
            else self.last_message
        )
        return result

    def turn_off_light(self) -> dict:
        result = self._send(build_led_off(), verify_led=True, expect_on=False)
        result["message"] = "关灯命令已发送" if result["ok"] else self.last_message
        return result

    def query_led(self, timeout_ms: int = 1500) -> LedState | None:
        """查询灯状态：先直接读取（设备可能自动上报），再发送查询命令。"""
        with self._lock:
            targets = self._devices()
            for info in [d for d in targets if d.input_len > 0]:
                state = self._read_led_once(info, min(700, timeout_ms))
                if state is not None:
                    return state
            # 发送查询帧后再读
            self._send(CMD_QUERY_LED)
            for info in [d for d in targets if d.input_len > 0]:
                state = self._read_led_once(info, timeout_ms)
                if state is not None:
                    return state
            return None

    def _send_simple(self, cmd: bytes, message: str) -> dict:
        result = self._send(cmd)
        result["message"] = message if result["ok"] else self.last_message
        return result

    def touch_on(self) -> dict:
        return self._send_simple(CMD_TOUCH_ON, "触摸灯已点亮")

    def touch_off(self) -> dict:
        return self._send_simple(CMD_TOUCH_OFF, "触摸灯已关闭")

    def touch_flash(self) -> dict:
        return self._send_simple(CMD_TOUCH_FLASH, "触摸灯闪烁命令已发送")

    def query_touch(self) -> dict:
        return self._send_simple(CMD_QUERY_TOUCH, "触摸灯状态查询命令已发送（应答见原始帧日志）")

    def query_mcu(self) -> str | None:
        """查询 MCU 版本（阻塞读取应答）。"""
        with self._lock:
            targets = [d for d in self._devices() if d.input_len > 0]
            if not targets:
                self.last_message = "未发现可读 HID 接口"
                return None
            for info in targets:
                self._write_to_device(info, CMD_QUERY_MCU)
                dev = HidDevice(info)
                try:
                    if not dev.open("r"):
                        continue
                    deadline = time.monotonic() + 1.2
                    while time.monotonic() < deadline:
                        raw = dev.read(200)
                        if not raw:
                            continue
                        frame = parse_input_frame(raw, source=info.vid_pid_text)
                        if frame and frame.kind == "mcu" and frame.mcu_version:
                            return frame.mcu_version
                finally:
                    dev.close()
            return None

    def send_raw(self, data: bytes) -> dict:
        return self._send_simple(data, f"原始帧已发送：{data.hex(' ').upper()}")


# ---------------------------------------------------------------------------
# 监听器：后台线程读取输入帧（心跳自动应答 / 按键 / 灯态）
# ---------------------------------------------------------------------------
class HidMonitor:
    """后台 HID 监听线程。

    回调均在**监听线程**中触发，UI 侧需自行用 ``widget.after`` 切回主线程。

    参数：
        on_frame(FrameInfo)     每收到一帧有效协议帧回调
        on_log(str)             普通日志
        on_led(LedState)        灯状态变化
        on_key(int, str)        机身按键事件
        on_connection(bool, list[HidDeviceInfo]) 设备连接状态变化
        heartbeat_reply         是否自动回应设备心跳
    """

    POLL_TIMEOUT_MS = 200
    RECONNECT_INTERVAL = 2.5

    def __init__(
        self,
        on_frame: Callable[[FrameInfo], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_led: Callable[[LedState], None] | None = None,
        on_key: Callable[[int, str], None] | None = None,
        on_connection: Callable[[bool, list[HidDeviceInfo]], None] | None = None,
        heartbeat_reply: bool = True,
    ) -> None:
        self.on_frame = on_frame
        self.on_log = on_log
        self.on_led = on_led
        self.on_key = on_key
        self.on_connection = on_connection
        self.heartbeat_reply = heartbeat_reply
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._connected = False
        self._devices: list[HidDeviceInfo] = []
        self._frames = 0
        self._last_error = ""

    # ---------- 状态 ----------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def device_count(self) -> int:
        return len(self._devices)

    @property
    def frame_count(self) -> int:
        return self._frames

    @property
    def last_error(self) -> str:
        return self._last_error

    # ---------- 生命周期 ----------
    def start(self) -> bool:
        with self._lock:
            if self.running:
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="HidMonitor", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 1.5) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        self._set_connected(False, [])

    def _set_connected(self, connected: bool, devices: list[HidDeviceInfo]) -> None:
        changed = connected != self._connected
        self._connected = connected
        self._devices = devices
        if changed and self.on_connection:
            try:
                self.on_connection(connected, devices)
            except Exception:  # noqa: BLE001 - 回调异常不能打断监听
                log.exception("on_connection 回调异常")

    def _emit(self, callback, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # noqa: BLE001
            log.exception("HID 监听回调异常：%s", getattr(callback, "__name__", callback))

    # ---------- 主循环 ----------
    def _run(self) -> None:
        self._emit(self.on_log, "HID 监听线程已启动")
        opened: dict[str, HidDevice] = {}
        last_scan = 0.0
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if not opened and now - last_scan > self.RECONNECT_INTERVAL:
                    last_scan = now
                    devices = find_seewo_devices()
                    readable = [d for d in devices if d.input_len > 0]
                    if not readable:
                        if devices:
                            self._emit(self.on_log, "展台 HID 已连接但无输入报告接口（无法监听按键）")
                        self._set_connected(False, devices)
                        self._stop_event.wait(0.6)
                        continue
                    for info in readable:
                        dev = HidDevice(info)
                        if dev.open("r"):
                            opened[info.path] = dev
                            self._emit(
                                self.on_log,
                                f"已连接展台 HID：{info.model}（{info.vid_pid_text}）",
                            )
                    if opened:
                        self._set_connected(True, readable)
                        self._emit(self.on_log, f"开始监听 {len(opened)} 个 HID 接口…")
                if not opened:
                    self._stop_event.wait(0.4)
                    continue

                got_any = False
                for path, dev in list(opened.items()):
                    if self._stop_event.is_set():
                        break
                    raw = dev.read(self.POLL_TIMEOUT_MS)
                    if raw:
                        got_any = True
                        self._handle_raw(raw, dev.info)
                    elif not dev.is_open:
                        # 设备被拔出
                        dev.close()
                        opened.pop(path, None)
                if not got_any:
                    # 空闲轮询间隔，避免空转占 CPU
                    self._stop_event.wait(0.05)

                # 定期检查设备是否仍在
                if opened and time.monotonic() - last_scan > 5.0:
                    last_scan = time.monotonic()
                    current = {d.path for d in find_seewo_devices()}
                    for path in list(opened):
                        if path not in current:
                            opened[path].close()
                            opened.pop(path, None)
                    if not opened:
                        self._set_connected(False, [])
                        self._emit(self.on_log, "展台已断开，等待重新连接…")
        except Exception as exc:  # noqa: BLE001 - 线程兜底
            self._last_error = str(exc)
            log.exception("HID 监听线程异常退出")
            self._emit(self.on_log, f"HID 监听异常退出：{exc}")
        finally:
            for dev in opened.values():
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
            self._set_connected(False, [])
            self._emit(self.on_log, "HID 监听线程已停止")

    def _handle_raw(self, raw: bytes, info: HidDeviceInfo) -> None:
        frame = parse_input_frame(raw, source=info.vid_pid_text)
        if frame is None:
            return
        self._frames += 1
        if frame.kind == "heartbeat" and frame.description == "设备心跳" and self.heartbeat_reply:
            dev = HidDevice(info)
            try:
                if dev.open("w"):
                    dev.write(CMD_HEARTBEAT_REPLY, 300)
            finally:
                dev.close()
        self._emit(self.on_frame, frame)
        if frame.kind in ("led", "led_key") and frame.led_on is not None:
            self._emit(self.on_led, LedState(frame.led_on, frame.led_level or 0, raw, info.vid_pid_text))
        if frame.kind == "key" and frame.key_index is not None:
            self._emit(self.on_key, frame.key_index, frame.key_name)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------
def self_test() -> dict:
    """HID 模块自检（供测试脚本 / CLI 调用，不发任何控制命令）。"""
    result: dict = {
        "hid_available": HID_AVAILABLE,
        "models": len(MODELS),
        "devices": [],
        "seewo_devices": [],
        "frame_parse_ok": False,
    }
    try:
        devices = enumerate_devices()
        result["devices"] = [
            {
                "vid_pid": d.vid_pid_text,
                "model": d.model,
                "product": d.product,
                "in": d.input_len,
                "out": d.output_len,
                "seewo": d.is_seewo,
                "path": d.path,
            }
            for d in devices
        ]
        result["seewo_devices"] = [d.vid_pid_text for d in devices if d.is_seewo]
        # 解析自检：构造一个 LED 应答帧
        sample = bytes((0x00, 0xBB, 0xCC, 0x02, 0x02, 0x02, 0x00, 0x01, 0x32, 0x00))
        frame = parse_input_frame(sample)
        result["frame_parse_ok"] = bool(frame and frame.kind == "led" and frame.led_on is True and frame.led_level == 0x32)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result
