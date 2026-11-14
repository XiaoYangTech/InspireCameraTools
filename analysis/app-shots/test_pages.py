"""页面遍历自测：创建主窗口，依次进入 7 个页面并截图。

运行（在 InspireCameraTools/ 下）：
    D:/Software/python314/python.exe ../analysis/app-shots/test_pages.py
产物：analysis/app-shots/page-<key>.png、控制台输出。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # D:\开发\SeewoCamera
APP_DIR = ROOT / "InspireCameraTools"
OUT = ROOT / "analysis" / "app-shots"
sys.path.insert(0, str(APP_DIR))

from app.app_window import MainWindow  # noqa: E402

PAGE_KEYS = ["home", "patch", "hid", "download", "autoupdate", "camera", "settings"]
errors: list[tuple[str, str]] = []
state = {"index": 0}
window: MainWindow | None = None


def capture(key: str) -> None:
    try:
        from PIL import ImageGrab

        window.update_idletasks()
        window.update()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        w, h = window.winfo_width(), window.winfo_height()
        # 把鼠标移到窗口左下角，避免截图时停在功能卡片上触发悬停高亮
        try:
            import ctypes

            ctypes.windll.user32.SetCursorPos(x + 8, y + h - 8)
            window.update()
            window.after(80)
            window.update()
        except Exception:  # noqa: BLE001
            pass
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        image.save(OUT / f"page-{key}.png")
        print(f"[capture] page-{key}.png {image.size}")
    except Exception as exc:  # noqa: BLE001
        errors.append((key, f"截图失败：{exc}"))
        print(f"[capture] {key} 截图失败：{exc}")


def step() -> None:
    index = state["index"]
    if index >= len(PAGE_KEYS):
        window.after(300, window._on_close)
        return
    key = PAGE_KEYS[index]
    try:
        window.show_page(key)
        window.update_idletasks()
        window.update()
        print(f"[page] 进入 {key} 成功")
        window.after(1800, lambda k=key: (capture(k), advance()))
    except Exception:  # noqa: BLE001
        errors.append((key, traceback.format_exc()))
        print(f"[page] 进入 {key} 失败\n{traceback.format_exc()}")
        advance()


def advance() -> None:
    state["index"] += 1
    window.after(250, step)


def main() -> int:
    global window
    OUT.mkdir(parents=True, exist_ok=True)
    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    window.after(1200, step)
    window.mainloop()
    print("=" * 60)
    if errors:
        print(f"存在 {len(errors)} 个错误：")
        for key, error in errors:
            print(f"--- {key} ---\n{error}")
        return 1
    print("全部页面创建/切换/截图成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
