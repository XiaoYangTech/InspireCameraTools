"""PyInstaller 打包脚本：生成 Windows 单目录分发版 dist/InspireCameraTools/。

用法（任选其一）：:

    # 1. 在 InspireCameraTools/ 目录下
    D:/Software/python314/python.exe build/build.py

    # 2. 任意目录
    D:/Software/python314/python.exe D:/开发/SeewoCamera/InspireCameraTools/build/build.py

参数：
    --onefile   打成单文件（默认单目录，启动更快、便于更新规则文件）
    --console   保留控制台窗口（默认 --windowed，无控制台）
    --clean     打包前清理 build 缓存（默认启用）
    --no-verify 跳过打包后的产物自检

首次打包前请先安装 PyInstaller：:

    D:/Software/python314/python.exe -m pip install pyinstaller

产物：``dist/InspireCameraTools/InspireCameraTools.exe``（单目录模式）。
注意：``core/rules`` 与 ``app`` 下的页面模块是动态导入的，必须用
``--collect-submodules`` 收集，否则运行时会出现「补丁引擎未就绪 / 页面加载失败」。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
APP_NAME = "InspireCameraTools"
ENTRY = APP_DIR / "main.py"
ICON = APP_DIR / "assets" / "app.ico"
DIST_DIR = APP_DIR / "dist"
BUILD_DIR = APP_DIR / "build" / "_pyinstaller"
SPEC_DIR = APP_DIR / "build"


def ensure_assets() -> None:
    """图标资源缺失时用 Pillow 脚本重新生成。"""
    logo = APP_DIR / "assets" / "icons" / "logo.png"
    if ICON.is_file() and logo.is_file():
        return
    print("[build] 图标资源缺失，正在生成 assets/…")
    script = APP_DIR / "assets" / "gen_assets.py"
    subprocess.run([sys.executable, str(script)], check=True, cwd=str(APP_DIR))


def ensure_trigger_helper() -> None:
    """确保一键相机的拍照触发助手（UIA）已编译且可随包分发。

    助手源码在 ``assets/bin/EasiCameraTrigger.cs`` / ``EasiCameraRemotingProxy.cs``，
    正常随仓库/分发提供已编译的 exe+dll；若缺失则用系统自带 csc 现场编译。
    """
    bin_dir = APP_DIR / "assets" / "bin"
    exe = bin_dir / "EasiCameraTrigger.exe"
    dll = bin_dir / "EasiCameraRemotingProxy.dll"
    if exe.is_file() and dll.is_file():
        return
    print("[build] 拍照触发助手缺失，正在用系统 csc 编译…")
    sys.path.insert(0, str(APP_DIR))
    try:
        from core import capture_trigger

        capture_trigger._compile_to(bin_dir)  # noqa: SLF001 - 构建脚本复用同一编译逻辑
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[build] 拍照触发助手编译失败：{exc}") from exc


def check_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        return False
    return True


def print_install_hint() -> None:
    print("=" * 70)
    print("未检测到 PyInstaller，无法打包。请先安装（只需一次）：")
    print()
    print(f'    "{sys.executable}" -m pip install pyinstaller')
    print()
    print("如使用代理：")
    print(f'    set https_proxy=http://127.0.0.1:7897 && "{sys.executable}" -m pip install pyinstaller')
    print("=" * 70)


def build(onefile: bool = False, console: bool = False) -> int:
    if not ENTRY.is_file():
        print(f"[build] 找不到入口文件：{ENTRY}")
        return 2
    ensure_assets()
    ensure_trigger_helper()

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        APP_NAME,
        "--icon",
        str(ICON),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(SPEC_DIR),
        # 资源文件（图标、ico）
        "--add-data",
        f"{APP_DIR / 'assets'}{os.pathsep}assets",
        # 动态导入的模块：页面与规则包必须显式收集
        "--collect-submodules",
        "app",
        "--collect-submodules",
        "core",
        "--collect-submodules",
        "core.rules",
        # ttkbootstrap 部分主题/资源为动态加载
        "--collect-data",
        "ttkbootstrap",
        # Pillow 在 Tk 场景下的隐藏依赖
        "--hidden-import",
        "PIL._tkinter_finder",
    ]
    args.append("--console" if console else "--windowed")
    if onefile:
        args.append("--onefile")
    args.append(str(ENTRY))

    print("[build] 执行：")
    print("  " + " ".join(args))
    print()
    completed = subprocess.run(args, cwd=str(APP_DIR))
    if completed.returncode != 0:
        print(f"[build] 打包失败，退出码 {completed.returncode}")
        return completed.returncode

    if onefile:
        exe = DIST_DIR / f"{APP_NAME}.exe"
    else:
        exe = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    if not exe.is_file():
        print(f"[build] 打包完成但未找到产物：{exe}")
        return 3
    size_mb = exe.stat().st_size / (1024 * 1024)
    print()
    print("=" * 70)
    print(f"打包成功：{exe}（{size_mb:.1f} MB）")
    print(f"分发方式：将 {exe.parent} 整个目录复制给用户即可运行 {exe.name}。")
    print("=" * 70)
    return 0


def verify(exe: Path | None = None) -> int:
    """对打包产物做最小自检：--version / --smoke-test。"""
    if exe is None:
        candidate = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
        if not candidate.is_file():
            candidate = DIST_DIR / f"{APP_NAME}.exe"
        exe = candidate
    if not exe.is_file():
        print(f"[verify] 未找到打包产物：{exe}")
        return 3
    print(f"[verify] 启动 {exe} --version …")
    completed = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=120)
    print(f"[verify] 退出码 {completed.returncode}，输出：{(completed.stdout or '').strip()}")
    if completed.returncode != 0:
        return 1
    print(f"[verify] 启动 {exe} --self-check（资源/主题/补丁规则/HID）…")
    completed = subprocess.run([str(exe), "--self-check"], capture_output=True, text=True, timeout=180)
    output = (completed.stdout or "").strip()
    print(f"[verify] 退出码 {completed.returncode}")
    for line in output.splitlines()[-40:]:
        print("  " + line)
    if completed.returncode != 0:
        print("[verify] 自检失败，请检查上面的 FAIL 项")
        return 1
    print(f"[verify] 启动 {exe} --smoke-test（约 5 秒）…")
    completed = subprocess.run([str(exe), "--smoke-test"], capture_output=True, text=True, timeout=60)
    print(f"[verify] 退出码 {completed.returncode}，输出：{(completed.stdout or '').strip()[:500]}")
    if completed.returncode != 0:
        return 1
    print("[verify] 打包产物自检通过")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="亿方展台管家 PyInstaller 打包脚本")
    parser.add_argument("--onefile", action="store_true", help="打包为单文件 exe（默认单目录）")
    parser.add_argument("--console", action="store_true", help="保留控制台窗口（调试用）")
    parser.add_argument("--no-verify", action="store_true", help="跳过打包产物自检")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("[build] 本打包脚本仅支持 Windows。")
        return 2
    if not check_pyinstaller():
        print_install_hint()
        return 1
    code = build(onefile=args.onefile, console=args.console)
    if code != 0:
        return code
    if not args.no_verify:
        return verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
