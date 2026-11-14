"""一键相机开机自启/后台模式流程自测（不写注册表：只验证命令生成与 --background 行为）。

验证：
1. startup.get_autostart_command() 生成的命令包含 --background、可执行文件与脚本路径均被引号包裹
2. 配置 camera_enabled=True 时，--background 启动会自动恢复 HID 监听（等待展台接入）
3. background 模式下窗口在 ~1 秒后最小化（iconify）
4. 测试结束恢复 camera_enabled=False，且注册表未被写入

运行（在 InspireCameraTools/ 下）：
    python ../analysis/app-shots/test_background.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "InspireCameraTools"
sys.path.insert(0, str(APP_DIR))

from core import settings, startup  # noqa: E402


def main() -> int:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        print(("  [OK]   " if condition else "  [FAIL] ") + message, flush=True)
        if not condition:
            failures.append(message)

    print("[1] 开机自启命令生成（不写注册表）", flush=True)
    command = startup.get_autostart_command()
    print("    命令：", command, flush=True)
    check(command.endswith("--background"), "命令以 --background 结尾")
    check(command.count('"') >= 2, "可执行文件/脚本路径带引号")
    check("main.py" in command or getattr(sys, "frozen", False), "源码模式下包含 main.py")
    check(startup.is_autostart_enabled() is False, "当前注册表没有自启项（测试前状态）")

    print("[2] 模拟用户开启一键相机（仅写应用配置，不写注册表）", flush=True)
    settings.set("camera_enabled", True)
    from app.app_window import MainWindow

    window = MainWindow(background=True, smoke_test=False)
    window.geometry("1200x800+80+40")
    window.update()

    result = {"camera": False, "iconified": False}

    def check_after_1500() -> None:
        # 窗口是否最小化（--background 行为）
        state = window.state()
        result["iconified"] = state == "iconic"
        check(result["iconified"], f"后台模式启动后窗口最小化（state={state}）")
        page = window.get_page("camera")
        monitor = getattr(page, "_monitor", None)
        running = bool(monitor is not None and monitor.running)
        result["camera"] = running
        check(running, "配置中 camera_enabled=True 时自动恢复一键相机监听")
        check(bool(settings.get("camera_enabled")), "camera_enabled 配置保持为 True")
        # 通过状态栏指示器确认
        indicator = window._camera_indicator.cget("text")
        check("一键相机运行中" in str(indicator), f"状态栏显示相机运行指示（{indicator!r}）")
        window.after(300, finish)

    def finish() -> None:
        # 清理：关闭相机并恢复配置，不写注册表
        page = window.get_page("camera")
        if page is not None:
            page.stop_camera()
        settings.set("camera_enabled", False)
        check(startup.is_autostart_enabled() is False, "测试结束后注册表仍无自启项")
        check(settings.get("camera_enabled") is False, "测试结束后 camera_enabled 已恢复 False")
        window.after(200, window._on_close)

    window.after(1600, check_after_1500)
    window.mainloop()
    print("=" * 60)
    if failures:
        print(f"RESULT: FAIL（{len(failures)} 项）", flush=True)
        return 1
    print("RESULT: PASS 开机自启命令/后台恢复监听/最小化行为验证通过", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
