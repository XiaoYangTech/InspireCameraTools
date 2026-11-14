"""降级与无硬件场景自测：无展台 HID 操作、补丁引擎缺失、自动更新模块缺失、断网下载。

用法（在 InspireCameraTools/ 下）：
    python ../analysis/app-shots/test_degrade.py hid
    python ../analysis/app-shots/test_degrade.py patch-degrade
    python ../analysis/app-shots/test_degrade.py update-degrade
    python ../analysis/app-shots/test_degrade.py net-degrade
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "InspireCameraTools"
OUT = ROOT / "analysis" / "app-shots"
sys.path.insert(0, str(APP_DIR))

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "hid"


def capture(window, name: str) -> None:
    try:
        from PIL import ImageGrab

        window.update_idletasks()
        window.update()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height()))
        image.save(OUT / name)
        print("[capture]", name, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("[capture] 失败", exc, flush=True)


def setup_dialogs() -> list[str]:
    """把模态对话框替换为记录调用（自动化测试不能弹窗阻塞）。"""
    from app import common

    calls: list[str] = []

    def record(kind):
        def _fn(parent, title, message):
            calls.append(f"[{kind}] {title}")
            print(f"[dialog:{kind}] {title} / {str(message)[:100]}", flush=True)
            return True
        return _fn

    common.show_warning = record("warning")  # type: ignore[assignment]
    common.show_error = record("error")  # type: ignore[assignment]
    common.show_info = record("info")  # type: ignore[assignment]
    common.ask_yes_no = lambda parent, title, message: (calls.append(f"[yesno] {title}"), True)[1]  # type: ignore[assignment]
    return calls


class Scenario:
    def __init__(self, name: str) -> None:
        self.name = name
        self.failures: list[str] = []
        self.calls: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        print(("  [OK]   " if condition else "  [FAIL] ") + message, flush=True)
        if not condition:
            self.failures.append(message)


def run_hid(scene: Scenario) -> None:
    from app.app_window import MainWindow

    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    window.show_page("hid")
    page = window.get_page("hid")

    def after_enum() -> None:
        scene.check(page._devices == [], "无展台时设备列表为空")
        scene.check(str(page._query_led_button.cget("state")) == "disabled", "无展台时灯控按钮置灰")
        # 尝试灯控操作（应给出友好提示而不是崩溃）
        page.query_led()
        page.turn_on_light()
        window.update()
        # 开始/停止监听：无设备时仍允许开启，监听线程等待接入
        page.start_listening()
        window.after(2500, after_monitor)

    def after_monitor() -> None:
        scene.check(page._monitor is not None and page._monitor.running, "无展台时监听线程仍可启动（等待接入）")
        scene.check(not page._monitor.connected, "监听线程报告未连接")
        page.stop_listening()
        window.update()
        scene.check(not (page._monitor and page._monitor.running), "停止监听后线程退出")
        capture(window, "degrade-hid-no-hardware.png")
        log_text = page._log_box.text.get("1.0", "end")
        scene.check("未发现希沃展台" in log_text or "未连接" in log_text, "日志中有未连接提示")
        scene.check(
            any("未连接展台" in call for call in scene.calls),
            "灯控操作给出友好提示（弹窗记录）",
        )
        window.after(300, window._on_close)

    window.after(1500, after_enum)
    window.mainloop()


def run_patch_degrade(scene: Scenario) -> None:
    import sys as _sys

    _sys.modules["core.patch_engine"] = None  # 模拟引擎文件缺失
    from app.app_window import MainWindow

    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    window.show_page("patch")
    page = window.get_page("patch")

    def check() -> None:
        scene.check(page._engine is None, "补丁引擎缺失时 _engine 为空")
        scene.check(bool(page._engine_error), "记录了引擎未就绪原因")
        scene.check(bool(page._engine_banner.winfo_manager()), "显示「引擎未就绪」横幅")
        scene.check(
            all(str(row["check"].cget("state")) == "disabled" for row in page._rows.values()),
            "所有功能复选框置灰",
        )
        scene.check(str(page._apply_button.cget("state")) == "disabled", "应用按钮禁用")
        log_text = page._log.text.get("1.0", "end")
        scene.check("补丁引擎未就绪" in log_text, "日志记录引擎未就绪")
        capture(window, "degrade-patch-no-engine.png")
        window.after(300, window._on_close)

    window.after(2000, check)
    window.mainloop()


def run_update_degrade(scene: Scenario) -> None:
    import sys as _sys

    _sys.modules["core.autoupdate"] = None
    from app.app_window import MainWindow

    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    window.show_page("autoupdate")
    page = window.get_page("autoupdate")

    def check() -> None:
        scene.check(page._module is None, "自动更新模块缺失时 _module 为空")
        scene.check(bool(page._module_error), "记录了模块未就绪原因")
        scene.check(bool(page._module_banner.winfo_manager()), "显示「模块未就绪」横幅")
        scene.check(str(page._apply_button.cget("state")) == "disabled", "执行防护按钮禁用")
        scene.check(str(page._restore_button.cget("state")) == "disabled", "还原按钮禁用")
        capture(window, "degrade-autoupdate-missing.png")
        window.after(300, window._on_close)

    window.after(1800, check)
    window.mainloop()


def run_net_degrade(scene: Scenario) -> None:
    from core import downloader

    downloader.API_GET_PACKAGE = "https://127.0.0.1:9/apix/get_package"
    from app.app_window import MainWindow

    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    window.show_page("download")
    page = window.get_page("download")

    def check() -> None:
        scene.check(bool(page._error_banner.winfo_manager()), "网络失败时显示错误提示条")
        label_text = str(page._count_label.cget("text"))
        scene.check("失败" in label_text, f"计数标签显示加载失败（实际：{label_text}）")
        scene.check(str(page._download_button.cget("state")) == "disabled", "下载按钮保持禁用")
        capture(window, "degrade-download-network-error.png")
        window.after(300, window._on_close)

    window.after(6000, check)
    window.mainloop()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scene = Scenario(SCENARIO)
    scene.calls = setup_dialogs()
    print(f"=== 场景：{SCENARIO} ===", flush=True)
    try:
        {"hid": run_hid, "patch-degrade": run_patch_degrade,
         "update-degrade": run_update_degrade, "net-degrade": run_net_degrade}[SCENARIO](scene)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        scene.failures.append("场景执行异常")
    print("对话框调用：", scene.calls, flush=True)
    if scene.failures:
        print(f"RESULT: FAIL（{len(scene.failures)} 项）", flush=True)
        return 1
    print("RESULT: PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
