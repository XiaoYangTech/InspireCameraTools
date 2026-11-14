"""拍照触发模块：不依赖键盘快捷键，直接驱动希沃视频展台（EasiCamera）拍照。

## 为什么不用键盘快捷键
EasiCamera 没有拍照快捷键，“一键相机”早期实现是向前台窗口 SendInput 发送 F12；
实际使用中拍照界面收不到该按键，且热键可能被其它进程占用，因此改为**主动触发 EasiCamera
自己的拍照动作**：

1. **UIA（首选，运行期可靠）**：通过 Windows UI Automation 找到 EasiCamera 界面上的
   「拍照」工具栏按钮并 Invoke。该按钮绑定的是 ``ECCommands.CaptureImage``，与用户点击
   按钮 / 按下机身拍照键最终执行的是同一个命令；不需要 EasiCamera 前台焦点，也**不写入
   HID、不与希沃进程抢设备**。
2. **Remoting（备用/诊断）**：EasiCamera 主进程通过 .NET Remoting IPC 注册了
   ``Ipc://e3950283-80cf-4a97-a569-e6110b6e9b82/RemotingNotifyCamera`` 单例；
   Guardian 用它转发机身按键（``Notify(pid, vid, "Key5")`` 即拍照键）。
   但该对象内置 25 秒 ``_needNotify`` 定时器，启动约 25 秒后不再处理通知，
   因此只能作早期窗口/诊断用途，运行期以 UIA 为准。
3. **兜底**：可选的热键注入（旧行为），仅当 UI 自动化失败且用户配置了兜底按键时使用。

所有外部动作都由随包的 ``assets/bin/EasiCameraTrigger.exe`` 完成（.NET Framework 4.x 编译），
本模块只负责定位/编译助手、调用与结果解析。

证据来源：``analysis/capture-trigger/README.md``（REA 静态分析 + 运行期 UIA 探测）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

#: 助手可执行文件与依赖（随 assets/bin 分发）
HELPER_EXE = "EasiCameraTrigger.exe"
PROXY_DLL = "EasiCameraRemotingProxy.dll"
HELPER_SRC = "EasiCameraTrigger.cs"
PROXY_SRC = "EasiCameraRemotingProxy.cs"

#: Remoting 通道（EasiCamera.Communication.dll 内硬编码常量，3816/4087/4229/4419 一致）
REMOTING_PORT = "e3950283-80cf-4a97-a569-e6110b6e9b82"
REMOTING_OBJECT = "RemotingNotifyCamera"

#: 默认超时（毫秒→秒）
DEFAULT_TIMEOUT = 5.0

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class CaptureTriggerError(RuntimeError):
    """触发助手缺失/无法编译/无法启动。"""


@dataclass
class TriggerResult:
    """一次拍照触发的结果。"""

    ok: bool
    method: str = ""
    message: str = ""
    element: dict = field(default_factory=dict)
    candidates: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def describe(self) -> str:
        if self.ok:
            name = (self.element or {}).get("name") or (self.element or {}).get("automationId") or "拍照按钮"
            return f"已通过 {self.method or 'UIA'} 触发拍照（{name}）"
        return self.message or "触发失败"


# ---------------------------------------------------------------------------
# 助手定位 / 编译
# ---------------------------------------------------------------------------
def _app_root() -> Path:
    base = getattr(sys, "_MEIPASS", "") or ""
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


def bundled_bin_dir() -> Path:
    return _app_root() / "assets" / "bin"


def local_bin_dir() -> Path:
    """源码模式/懒编译输出目录（用户可写）。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "InspireCameraTools" / "bin"


def helper_path() -> Path:
    return bundled_bin_dir() / HELPER_EXE


def proxy_path() -> Path:
    return bundled_bin_dir() / PROXY_DLL


def _csc_candidates() -> list[Path]:
    roots = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework" / "v4.0.30319",
    ]
    return [root / "csc.exe" for root in roots]


def find_csc() -> Path | None:
    for candidate in _csc_candidates():
        if candidate.is_file():
            return candidate
    return None


def _compile_to(target_dir: Path) -> Path:
    """用系统自带 csc 从随包 .cs 源码编译助手到 target_dir。"""
    csc = find_csc()
    src_dir = bundled_bin_dir()
    if csc is None:
        raise CaptureTriggerError("未找到 .NET Framework csc.exe，无法编译拍照触发助手")
    if not (src_dir / HELPER_SRC).is_file() or not (src_dir / PROXY_SRC).is_file():
        raise CaptureTriggerError("拍照触发助手源码缺失（assets/bin/*.cs）")
    wpf = csc.parent / "WPF"
    target_dir.mkdir(parents=True, exist_ok=True)
    proxy_dll = target_dir / PROXY_DLL
    helper_exe = target_dir / HELPER_EXE
    _run_compile(
        [
            str(csc), "/nologo", "/target:library", "/platform:anycpu", "/optimize+",
            f"/out:{proxy_dll}", str(src_dir / PROXY_SRC),
        ]
    )
    _run_compile(
        [
            str(csc), "/nologo", "/target:exe", "/platform:anycpu", "/optimize+",
            f"/r:{wpf / 'UIAutomationClient.dll'}",
            f"/r:{wpf / 'UIAutomationTypes.dll'}",
            f"/r:{wpf / 'WindowsBase.dll'}",
            f"/r:{proxy_dll}",
            f"/out:{helper_exe}",
            str(src_dir / HELPER_SRC),
        ]
    )
    return helper_exe


def _run_compile(args: list[str]) -> None:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=_CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        detail = (completed.stdout or "") + (completed.stderr or "")
        raise CaptureTriggerError(f"编译拍照触发助手失败：{detail.strip()[:500]}")


def ensure_helper(force: bool = False) -> Path:
    """返回可用的助手 exe 路径；缺失时尝试用 csc 现场编译（缓存到 LOCALAPPDATA）。"""
    exe = helper_path()
    dll = proxy_path()
    if exe.is_file() and dll.is_file() and not force:
        return exe
    cached_dir = local_bin_dir()
    cached_exe = cached_dir / HELPER_EXE
    cached_dll = cached_dir / PROXY_DLL
    if cached_exe.is_file() and cached_dll.is_file() and not force:
        return cached_exe
    return _compile_to(cached_dir)


# ---------------------------------------------------------------------------
# 调用助手
# ---------------------------------------------------------------------------
def _run_helper(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> dict:
    exe = ensure_helper()
    try:
        completed = subprocess.run(
            [str(exe)] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"拍照触发助手超时（{timeout:.1f}s）"}
    except OSError as exc:
        return {"ok": False, "error": f"无法启动拍照触发助手：{exc}"}
    payload = (completed.stdout or "").strip()
    if not payload:
        err = (completed.stderr or "").strip()
        return {"ok": False, "error": err or f"助手无输出（退出码 {completed.returncode}）"}
    line = payload.splitlines()[-1]
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"助手输出无法解析：{line[:300]}"}


def probe_capture_button(timeout: float = DEFAULT_TIMEOUT) -> dict:
    """检测 EasiCamera 拍照按钮（不实际点击），返回助手原始 JSON。"""
    return _run_helper(["capture", "--dry-run"], timeout=timeout)


def trigger_capture(wait_ms: int = 0, timeout: float = DEFAULT_TIMEOUT) -> TriggerResult:
    """通过 UI Automation 触发 EasiCamera 拍照按钮（模拟机身拍照键的同一命令）。"""
    args = ["capture"]
    if wait_ms > 0:
        args += ["--wait-ms", str(int(wait_ms))]
    data = _run_helper(args, timeout=timeout)
    return _to_result(data)


def _to_result(data: dict) -> TriggerResult:
    if not isinstance(data, dict):
        return TriggerResult(ok=False, message="拍照触发助手返回异常")
    ok = bool(data.get("ok"))
    error = data.get("error") or ""
    element = data.get("element") or {}
    candidates = data.get("candidates") or []
    message = "" if ok else _friendly_error(error, candidates)
    return TriggerResult(
        ok=ok,
        method=str(data.get("method") or ""),
        message=message,
        element=element,
        candidates=candidates,
        raw=data,
    )


def _friendly_error(error: str, candidates: list) -> str:
    text = str(error or "")
    lowered = text.lower()
    if "window not found" in lowered:
        return "未找到 EasiCamera 窗口：请先打开希沃视频展台（EasiCamera）"
    if "capture button not found" in lowered:
        hint = "拍照按钮未出现：请确认已连接展台并处于拍照/展台界面"
        if candidates:
            names = "、".join(str((c or {}).get("name") or (c or {}).get("automationId") or "") for c in candidates[:3])
            hint += f"；已发现候选：{names}"
        return hint
    return text or "拍照触发失败"


def remoting_notify(pid: int, vid: int, message: str = "Key5", timeout: float = DEFAULT_TIMEOUT) -> dict:
    """备用/诊断：调用 EasiCamera 的 RemotingNotifyCamera（Guardian 转发机身按键的入口）。

    注意：EasiCamera 启动约 25 秒后该对象不再处理通知（_needNotify 定时器），
    因此运行期不要依赖此通道，仅供早期窗口/诊断验证。
    """
    return _run_helper(
        ["remoting", "--pid", str(int(pid)), "--vid", str(int(vid)), "--message", message],
        timeout=timeout,
    )


def remoting_available() -> bool:
    """助手/代理 DLL 是否可用（不实际连接 EasiCamera）。"""
    try:
        ensure_helper()
        return True
    except CaptureTriggerError:
        return False


def helper_info() -> dict:
    """给「设置/诊断」用的助手信息。"""
    exe = helper_path()
    cached = local_bin_dir() / HELPER_EXE
    return {
        "bundled_exe": str(exe),
        "bundled_present": exe.is_file() and proxy_path().is_file(),
        "cached_exe": str(cached),
        "cached_present": cached.is_file(),
        "csc": str(find_csc() or ""),
        "remoting_port": REMOTING_PORT,
        "remoting_object": REMOTING_OBJECT,
    }
