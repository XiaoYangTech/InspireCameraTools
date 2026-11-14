"""开机自启与后台模式支持。

自启实现：写入 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run，
值为「可执行文件路径 + --background 参数」。HKCU 写入无需管理员权限。
仅在用户主动打开「一键相机 → 开机自启」时才写注册表；读取接口只读。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:  # Windows 专有模块，非 Windows 下导入失败也不影响其它模块
    import winreg
except ImportError:  # pragma: no cover - 仅非 Windows
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "InspireCameraTools"
BACKGROUND_FLAG = "--background"

#: 记录最近一次自启命令，便于设置页展示（不持久化）
_last_command: str = ""


def is_supported() -> bool:
    """当前环境是否支持开机自启（Windows + winreg）。"""
    return sys.platform == "win32" and winreg is not None


def _app_entry_target() -> tuple[str, str]:
    """返回 (可执行文件, 需附加的脚本参数)。

    - 打包后（PyInstaller）：可执行文件即自身，无脚本参数；
    - 源码运行：用 pythonw.exe（无控制台）解释 main.py。
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.is_file():
        exe = pythonw
    # main.py 位于包根目录（core 的上一级）
    main_script = Path(__file__).resolve().parent.parent / "main.py"
    return str(exe), str(main_script)


def get_autostart_command() -> str:
    """生成写入注册表的完整命令行。"""
    exe, script = _app_entry_target()
    parts = [f'"{exe}"']
    if script:
        parts.append(f'"{script}"')
    parts.append(BACKGROUND_FLAG)
    return " ".join(parts)


def is_autostart_enabled() -> bool:
    """读取注册表判断是否已设置开机自启。"""
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:  # type: ignore[union-attr]
            try:
                value, _ = winreg.QueryValueEx(key, VALUE_NAME)  # type: ignore[union-attr]
            except FileNotFoundError:
                return False
            return bool(str(value or "").strip())
    except OSError:
        return False


def set_autostart(enabled: bool) -> tuple[bool, str]:
    """开启/关闭开机自启，返回 (是否成功, 提示信息)。"""
    global _last_command
    if not is_supported():
        return False, "当前系统不支持注册表自启（仅限 Windows）"
    command = get_autostart_command()
    try:
        with winreg.CreateKeyEx(  # type: ignore[union-attr]
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)  # type: ignore[union-attr]
                _last_command = command
                return True, "已开启开机自启（后台模式启动）"
            try:
                winreg.DeleteValue(key, VALUE_NAME)  # type: ignore[union-attr]
            except FileNotFoundError:
                pass
            _last_command = ""
            return True, "已关闭开机自启"
    except OSError as exc:
        return False, f"写入开机自启失败：{exc}"


def get_registered_command() -> str:
    """读取注册表中已登记的自启命令（只读，供设置页展示）。"""
    if not is_supported():
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:  # type: ignore[union-attr]
            try:
                value, _ = winreg.QueryValueEx(key, VALUE_NAME)  # type: ignore[union-attr]
                return str(value or "")
            except FileNotFoundError:
                return ""
    except OSError:
        return ""


def ensure_background_args(argv: list[str]) -> list[str]:
    """确保命令行带 --background（供自启命令构造/测试用）。"""
    if BACKGROUND_FLAG in argv:
        return list(argv)
    return list(argv) + [BACKGROUND_FLAG]
