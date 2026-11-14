"""UI 主题、字体、配色与图标资源。

- 统一 Bootstrap 5 配色（主题色 #0d6efd / 中性灰 #6c757d）
- 若当前 ttkbootstrap 版本没有内置 ``bootstrap-light`` 主题，则动态注册一个等价主题，
  保证契约要求的 ``themename="bootstrap-light"`` 在任何 ttkbootstrap 版本下都可用
- 图标全部由 ``assets/gen_assets.py`` 本地生成，不依赖网络素材
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = APP_DIR / "assets"


def resource_path(relative: str) -> Path:
    """兼容 PyInstaller 打包后的资源路径（one-folder 模式下 _MEIPASS 存在）。"""
    base = Path(getattr(sys, "_MEIPASS", "") or APP_DIR)
    return base / relative


def icon_path(name: str) -> Path:
    """图标文件路径（name 不含扩展名，如 ``patch``）。"""
    return resource_path("assets/icons") / f"{name}.png"


def ico_path() -> Path:
    return resource_path("assets/app.ico")


# ---------------------------------------------------------------------------
# 配色（Bootstrap 5 调色板）
# ---------------------------------------------------------------------------
PRIMARY = "#0d6efd"
PRIMARY_DARK = "#0b5ed7"
SECONDARY = "#6c757d"
SUCCESS = "#198754"
SUCCESS_BG = "#d1e7dd"
DANGER = "#dc3545"
DANGER_BG = "#f8d7da"
WARNING = "#b8860b"  # 文字用深金色，比 #ffc107 更易读
WARNING_BG = "#fff3cd"
INFO = "#0dcaf0"
INFO_BG = "#cff4fc"
LIGHT = "#f8f9fa"
WHITE = "#ffffff"
BORDER = "#dee2e6"
TEXT = "#212529"
MUTED = "#6c757d"
HOVER_BG = "#eef5ff"
PAGE_BG = "#f5f7fa"
DISABLED_BG = "#e9ecef"
DISABLED_FG = "#adb5bd"

#: 状态色映射：kind -> (前景, 背景)
BADGE_STYLES = {
    "success": (SUCCESS, SUCCESS_BG),
    "danger": (DANGER, DANGER_BG),
    "warning": (WARNING, WARNING_BG),
    "info": (PRIMARY_DARK, INFO_BG),
    "secondary": (MUTED, DISABLED_BG),
    "primary": (WHITE, PRIMARY),
}

# ---------------------------------------------------------------------------
# 字体 / 缩放
# ---------------------------------------------------------------------------
FONT_FAMILY = "Microsoft YaHei UI"
_ui_scale = 1.0
_fonts_initialized = False


def _pick_font_family(root: tk.Misc) -> str:
    """选择可用中文字体（优先微软雅黑 UI）。"""
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        families = set()
    for candidate in (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Segoe UI",
        "Arial",
    ):
        if candidate in families:
            return candidate
    return "TkDefaultFont"


def set_ui_scale(scale: float) -> None:
    """设置 UI 缩放系数（= winfo_fpixels('1i')/96）。"""
    global _ui_scale
    _ui_scale = max(0.75, min(float(scale or 1.0), 4.0))


def ui_scale() -> float:
    """当前缩放宽高比（100% DPI 时为 1.0）。"""
    return _ui_scale


def px(value: float) -> int:
    """把设计稿像素值按当前 DPI 缩放。"""
    return max(1, int(round(value * _ui_scale)))


def font(size: int = 12, weight: str = "normal", family: str | None = None) -> tuple:
    """返回 tk 字体元组（size 单位为 pt，随 tk scaling 缩放）。"""
    return (family or FONT_FAMILY, size, weight)


def init_fonts(root: tk.Misc) -> None:
    """初始化全局字体族（在 tk scaling 设置后调用）。"""
    global FONT_FAMILY, _fonts_initialized
    if _fonts_initialized:
        return
    FONT_FAMILY = _pick_font_family(root)
    # 统一默认命名字体，让 messagebox 等原生对话框风格一致
    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(name).configure(family=FONT_FAMILY, size=12)
        except (tk.TclError, ValueError):
            continue
    _fonts_initialized = True


# ---------------------------------------------------------------------------
# 图标加载（Pillow 缩放 + 缓存）
# ---------------------------------------------------------------------------
_icon_cache: dict[tuple[str, int], tk.PhotoImage] = {}


def load_icon(name: str, size: int = 56, master: tk.Misc | None = None) -> tk.PhotoImage:
    """加载并缩放 PNG 图标（带缓存，同一尺寸只创建一次）。"""
    size = max(8, int(size))
    key = (name, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    path = icon_path(name)
    photo: tk.PhotoImage
    try:
        image = Image.open(path).convert("RGBA")
        image = image.resize((size, size), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image, master=master)
    except Exception:  # noqa: BLE001 - PIL 不可用时退回 Tk 原生 PNG 加载
        try:
            photo = tk.PhotoImage(file=str(path), master=master)
            if photo.width() != size:
                photo = photo.subsample(max(1, round(photo.width() / size)))
        except tk.TclError:
            # 最后兜底：生成一张占位透明图，避免 UI 崩溃
            photo = tk.PhotoImage(width=size, height=size, master=master)
    _icon_cache[key] = photo
    return photo


# ---------------------------------------------------------------------------
# 主题注册 / 样式
# ---------------------------------------------------------------------------
#: Bootstrap 5 默认配色的 light 主题定义
_BOOTSTRAP_LIGHT = {
    "type": "light",
    "colors": {
        "primary": "#0d6efd",
        "secondary": "#6c757d",
        "success": "#198754",
        "info": "#0dcaf0",
        "warning": "#ffc107",
        "danger": "#dc3545",
        "light": "#f8f9fa",
        "dark": "#212529",
        "bg": "#ffffff",
        "fg": "#212529",
        "selectbg": "#0d6efd",
        "selectfg": "#ffffff",
        "border": "#dee2e6",
        "inputfg": "#212529",
        "inputbg": "#ffffff",
        "active": "#e9ecef",
    },
}


def ensure_bootstrap_light_theme() -> bool:
    """确保 ttkbootstrap 能使用 ``bootstrap-light`` 主题。

    某些 ttkbootstrap 发行版只内置经典主题名（litera/flatly/...），这里在创建窗口前
    向标准主题表注册一个 Bootstrap 5 配色的 light 主题，保证 ``themename`` 参数始终有效。
    返回是否执行了注册（已内置时返回 False）。
    """
    try:
        from ttkbootstrap.themes.standard import STANDARD_THEMES

        if "bootstrap-light" not in STANDARD_THEMES:
            STANDARD_THEMES["bootstrap-light"] = _BOOTSTRAP_LIGHT
            return True
    except Exception:  # noqa: BLE001 - 主题注册失败时由调用方回退其它主题
        return False
    return False


def configure_styles(style) -> None:
    """微调 ttk 样式：字体、行高、按钮内边距。"""
    base = 12
    style.configure("TLabel", font=font(base))
    style.configure("TButton", font=font(base), padding=(px(14), px(7)))
    style.configure("TEntry", font=font(base), padding=(px(6), px(5)))
    style.configure("TCombobox", font=font(base), padding=(px(6), px(4)))
    style.configure("TCheckbutton", font=font(base))
    style.configure("TNotebook.Tab", font=font(base))
    style.configure("TLabelframe.Label", font=font(base, "bold"))
    style.configure("Treeview", font=font(11), rowheight=px(30))
    style.configure("Treeview.Heading", font=font(11, "bold"))
    style.configure("TProgressbar", thickness=px(10))
    # ttkbootstrap 自定义样式类
    style.configure("Page.TFrame", background=PAGE_BG)
    style.configure("Card.TFrame", background=WHITE)
    try:
        style.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", WHITE)])
    except tk.TclError:
        pass


# ---------------------------------------------------------------------------
# 通用颜色常量导出
# ---------------------------------------------------------------------------
__all__ = [
    "APP_DIR",
    "ASSETS_DIR",
    "resource_path",
    "icon_path",
    "ico_path",
    "PRIMARY",
    "PRIMARY_DARK",
    "SECONDARY",
    "SUCCESS",
    "SUCCESS_BG",
    "DANGER",
    "DANGER_BG",
    "WARNING",
    "WARNING_BG",
    "INFO",
    "INFO_BG",
    "LIGHT",
    "WHITE",
    "BORDER",
    "TEXT",
    "MUTED",
    "HOVER_BG",
    "PAGE_BG",
    "DISABLED_BG",
    "DISABLED_FG",
    "BADGE_STYLES",
    "FONT_FAMILY",
    "set_ui_scale",
    "ui_scale",
    "px",
    "font",
    "init_fonts",
    "load_icon",
    "ensure_bootstrap_light_theme",
    "configure_styles",
]
