"""破坏自动更新页 UI 集成自测：检测 → 执行防护 → 还原（本机未安装 EasiCamera，应安全空操作）。

运行（在 InspireCameraTools/ 下）：
    python ../analysis/app-shots/test_autoupdate_ui.py
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


def main() -> int:
    from core import settings

    # 本机没有安装 EasiCamera：清空此前测试写入的安装目录，验证「未安装」分支
    settings.set("install_dir", "")
    from app import common
    from app.app_window import MainWindow

    confirmations: list[str] = []
    common.ask_yes_no = lambda parent, title, message: (confirmations.append(title), True)[1]  # type: ignore[assignment]
    common.show_warning = lambda parent, title, message: confirmations.append(f"warn:{title}")  # type: ignore[assignment]
    common.show_error = lambda parent, title, message: confirmations.append(f"error:{title}")  # type: ignore[assignment]
    common.show_info = lambda parent, title, message: confirmations.append(f"info:{title}")  # type: ignore[assignment]

    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    window.show_page("autoupdate")
    page = window.get_page("autoupdate")
    failures: list[str] = []

    def log_text() -> str:
        try:
            return page._log.text.get("1.0", "end")
        except Exception:  # noqa: BLE001
            return ""

    def check(condition: bool, message: str) -> None:
        print(("  [OK]   " if condition else "  [FAIL] ") + message, flush=True)
        if not condition:
            failures.append(message)

    def wait(condition, timeout: float, on_ok, label: str):
        deadline = time.time() + timeout

        def tick():
            if condition():
                on_ok()
                return
            if time.time() > deadline:
                failures.append(f"{label} 超时")
                print(f"  [FAIL] {label} 超时（日志：{log_text()[-300:]}）", flush=True)
                window.after(200, window._on_close)
                return
            window.after(150, tick)

        window.after(200, tick)

    def phase_detect() -> None:
        check(page._module is not None, "自动更新模块加载成功")
        check(str(page._apply_button.cget("state")) == "normal", "执行防护按钮可用")
        check("检测完成" in log_text(), "检测完成日志存在")
        check("未检测到 EasiCamera 安装" in log_text(), "识别出本机未安装 EasiCamera")
        check(page._admin_badge.cget("text") == "已获得", "管理员权限徽标正确")
        capture(window, "autoupdate-detected.png")
        print("  → 执行防护（未安装时为空操作）", flush=True)
        page.apply_protection()
        wait(lambda: "执行防护完成" in log_text(), 25, phase_apply_done, "执行防护")

    def phase_apply_done() -> None:
        check("执行防护完成" in log_text(), "执行防护返回结果并渲染")
        capture(window, "autoupdate-applied.png")
        print("  → 还原防护（未安装时为空操作）", flush=True)
        page.restore_protection()
        wait(lambda: "还原防护完成" in log_text(), 25, phase_restore_done, "还原防护")

    def phase_restore_done() -> None:
        check("还原防护完成" in log_text(), "还原防护返回结果并渲染")
        capture(window, "autoupdate-restored.png")
        check(not any(item.startswith("error:") for item in confirmations), "过程中没有错误弹窗")
        window.after(200, window._on_close)

    wait(lambda: "检测完成" in log_text(), 20, phase_detect, "状态检测")
    window.mainloop()
    print("确认/提示弹窗：", confirmations, flush=True)
    if failures:
        print(f"RESULT: FAIL（{len(failures)} 项）", flush=True)
        return 1
    print("RESULT: PASS 检测/执行/还原 全链路通过", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
