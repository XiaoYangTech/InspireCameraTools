"""高 DPI 专项自测（单缩放一次一进程）：模拟 125% / 150% 缩放遍历页面并截图。

ttkbootstrap 的 Style 为进程级单例，同一进程无法连续创建/销毁两个 Window，
因此按缩放系数在不同进程中运行：

    python ../analysis/app-shots/test_highdpi.py 1.25
    python ../analysis/app-shots/test_highdpi.py 1.5
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

PAGE_KEYS = ["home", "patch", "hid", "download", "autoupdate", "camera", "settings"]


def make_window(scale: float):
    from app import theme
    from app.app_window import MainWindow

    def setup_scaled(self) -> None:
        try:
            self.tk.call("tk", "scaling", scale)
        except Exception:  # noqa: BLE001
            pass
        theme.set_ui_scale(scale)
        theme.init_fonts(self)
        theme.configure_styles(self.style)

    MainWindow._setup_dpi_and_style = setup_scaled  # type: ignore[method-assign]
    return MainWindow(smoke_test=True)


def capture(window, name: str) -> None:
    try:
        from PIL import ImageGrab

        window.update_idletasks()
        window.update()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height()))
        image.save(OUT / name)
        print(f"  [capture] {name}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  [capture] {name} 失败：{exc}", flush=True)


def check_overflow(window, page, key: str) -> list[str]:
    """检查页面标题栏按钮是否越出窗口、页面内容是否被窗口裁剪。"""
    problems: list[str] = []
    try:
        win_width = window.winfo_width()
        win_height = window.winfo_height()
        for button in getattr(page, "_header_buttons", []):
            try:
                right = button.winfo_rootx() + button.winfo_width() - window.winfo_rootx()
                bottom = button.winfo_rooty() + button.winfo_height() - window.winfo_rooty()
                if right > win_width:
                    problems.append(f"{key}: 标题栏按钮右越界 {right}>{win_width}")
                if bottom > win_height:
                    problems.append(f"{key}: 标题栏按钮下越界")
            except Exception:  # noqa: BLE001
                pass
        if page.winfo_height() > win_height + 2:
            problems.append(f"{key}: 页面高度 {page.winfo_height()} 超出窗口 {win_height}")
    except Exception:  # noqa: BLE001
        problems.append(f"{key}: 检查异常\n{traceback.format_exc()}")
    return problems


def main() -> int:
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.25
    OUT.mkdir(parents=True, exist_ok=True)
    percent = int(round(scale * 100))
    print(f"=== 模拟缩放 {percent}%（tk scaling={scale}）===", flush=True)
    problems: list[str] = []
    try:
        # 清除其它 DPI 下保存的窗口尺寸，确保按当前模拟 DPI 计算默认窗口大小
        from core import settings

        settings.set("window_geometry", "")
        window = make_window(scale)
        window.update()
        screen = (window.winfo_screenwidth(), window.winfo_screenheight())
        work = window._get_work_area()
        print(
            f"  屏幕：{screen[0]}x{screen[1]}，可用区域：{work[2]}x{work[3]}，"
            f"窗口尺寸：{window.winfo_width()}x{window.winfo_height()}（按 DPI 自动缩放）",
            flush=True,
        )
        for key in PAGE_KEYS:
            window.show_page(key)
            window.update_idletasks()
            window.update()
            time.sleep(0.9)
            window.update_idletasks()
            window.update()
            page = window.get_page(key)
            if page is not None:
                problems.extend(check_overflow(window, page, key))
            capture(window, f"hidpi-{percent}-page-{key}.png")
            print(f"  [page] {key} OK", flush=True)
        window._on_close()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        problems.append(f"scale {scale} 执行异常")
    print("=" * 60)
    if problems:
        print(f"RESULT: FAIL（{len(problems)} 项）", flush=True)
        for problem in problems:
            print(" -", problem, flush=True)
        return 1
    print(f"RESULT: PASS {percent}% 缩放下 7 个页面正常渲染，控件未越界", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
