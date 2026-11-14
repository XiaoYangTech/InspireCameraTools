"""主窗口：标题栏、页面容器、状态栏与导航。

使用 ttkbootstrap ``bootstrap-light`` 主题；页面全部内嵌在同一窗口内切换
（不弹新窗口），每个子页面自带「返回」按钮。
"""

from __future__ import annotations

import importlib
import logging
import re
import tkinter as tk
from pathlib import Path

import ttkbootstrap as tb

from core import settings, sysinfo

from . import common, theme

log = logging.getLogger(__name__)

APP_TITLE = "亿方展台管家"

#: 页面 key -> (模块名, 类名, 标题)
PAGES: dict[str, tuple[str, str, str]] = {
    "home": ("app.home", "HomePage", "主页"),
    "patch": ("app.patch_page", "PatchPage", "一键补丁"),
    "hid": ("app.hid_page", "HidPage", "状态调试"),
    "download": ("app.download_page", "DownloadPage", "历史版本下载"),
    "autoupdate": ("app.autoupdate_page", "AutoUpdatePage", "破坏自动更新"),
    "camera": ("app.camera_page", "CameraPage", "一键相机"),
    "settings": ("app.settings_page", "SettingsPage", "设置与关于"),
}

_GEOMETRY_RE = re.compile(r"^\d+x\d+[+-]-?\d+[+-]-?\d+$")


class _ErrorPage(tk.Frame):
    """页面构建失败时的兜底页，保证应用不崩溃。"""

    title = "页面加载失败"
    subtitle = ""
    icon = ""

    def __init__(self, master, app, error: str) -> None:
        super().__init__(master, bg=theme.PAGE_BG)
        self.app = app
        header = tk.Frame(self, bg=theme.PAGE_BG)
        header.pack(fill="x")
        tb.Button(
            header,
            text="← 返回",
            bootstyle="secondary-outline",
            command=app.go_home,
            cursor="hand2",
            width=7,
        ).pack(side="left", padx=(0, theme.px(14)))
        tk.Label(
            header,
            text="页面加载失败",
            font=theme.font(17, "bold"),
            bg=theme.PAGE_BG,
            fg=theme.DANGER,
        ).pack(side="left")
        card = common.Card(self, title="错误详情", icon="settings")
        card.pack(fill="both", expand=True, pady=(theme.px(16), 0))
        common.label(card.body, error, size=11, fg=theme.DANGER, justify="left").pack(fill="x")

    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass

    def on_close(self) -> None:
        pass


class MainWindow(tb.Window):
    """应用主窗口。"""

    def __init__(self, background: bool = False, smoke_test: bool = False, initial_page: str = "home") -> None:
        # 确保 bootstrap-light 主题存在（部分 ttkbootstrap 版本未内置）
        theme.ensure_bootstrap_light_theme()
        super().__init__(
            themename="bootstrap-light",
            hdpi=False,
            title=APP_TITLE,
        )
        self.app_version = settings.APP_VERSION
        self._background = background
        self._smoke_test = smoke_test
        self._initial_page = initial_page if initial_page in PAGES else "home"
        self._pages: dict[str, object] = {}
        self._current_key: str | None = None
        self._closing = False
        self._status_reset_job: str | None = None
        self._window_icon = None

        self._setup_dpi_and_style()
        self._setup_window()
        self._build_ui()
        self._resume_camera_if_needed()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def _setup_dpi_and_style(self) -> None:
        try:
            scale = float(self.winfo_fpixels("1i")) / 96.0
        except tk.TclError:
            scale = 1.0
        try:
            self.tk.call("tk", "scaling", scale)
        except tk.TclError:
            pass
        theme.set_ui_scale(scale)
        theme.init_fonts(self)
        try:
            theme.configure_styles(self.style)
        except Exception:  # noqa: BLE001 - 样式微调失败不影响功能
            log.exception("样式配置失败")

    # ------------------------------------------------------------------
    # 窗口尺寸 / 居中（按 DPI 缩放，且不超出屏幕可用区域）
    # ------------------------------------------------------------------
    def _get_work_area(self) -> tuple[int, int, int, int]:
        """返回 Windows 桌面可用区域（排除任务栏）：(left, top, width, height)。"""
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width > 0 and height > 0:
                    return int(rect.left), int(rect.top), width, height
        except Exception:  # noqa: BLE001
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _setup_window(self) -> None:
        scale = theme.ui_scale()
        work_x, work_y, work_w, work_h = self._get_work_area()
        # 100% DPI 下即契约要求的 1200x800 / 最小 1000x680；高 DPI 下按比例放大，
        # 但不超过屏幕可用区域（避免窗口超出屏幕），保证布局有足够空间。
        width = min(int(round(1200 * scale)), int(work_w * 0.96))
        height = min(int(round(800 * scale)), int(work_h * 0.96))
        min_width = min(int(round(1000 * scale)), int(work_w * 0.80))
        min_height = min(int(round(680 * scale)), int(work_h * 0.80))
        self.minsize(min_width, min_height)

        geometry = str(settings.get("window_geometry") or "")
        saved = None
        if _GEOMETRY_RE.match(geometry):
            match = re.match(r"^(\d+)x(\d+)", geometry)
            if match:
                saved_w, saved_h = int(match.group(1)), int(match.group(2))
                # 记忆尺寸太小（例如切换过 DPI）时忽略，用当前 DPI 的默认尺寸
                if saved_w >= min_width and saved_h >= min_height:
                    saved = geometry
        if saved:
            self.geometry(saved)
        else:
            self.geometry(f"{width}x{height}")
            self.after(50, self._center_window)
        # 图标：优先 ico（任务栏），退而用 PNG
        try:
            ico = theme.ico_path()
            if ico.is_file():
                self.iconbitmap(default=str(ico))
        except Exception:  # noqa: BLE001
            pass
        try:
            self._window_icon = theme.load_icon("logo", 64, master=self)
            self.iconphoto(True, self._window_icon)
        except Exception:  # noqa: BLE001
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._on_tk_exception

    def _center_window(self) -> None:
        try:
            self.update_idletasks()
            width = self.winfo_width() or 1200
            height = self.winfo_height() or 800
            work_x, work_y, work_w, work_h = self._get_work_area()
            x = work_x + max(0, (work_w - width) // 2)
            y = work_y + max(0, (work_h - height) // 3)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        self._build_statusbar()
        self.container = tk.Frame(self, bg=theme.PAGE_BG)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        self.show_page(self._initial_page)

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=theme.WHITE, height=theme.px(30))
        bar.pack(side="bottom", fill="x")
        tk.Frame(bar, bg=theme.BORDER, height=1).pack(side="top", fill="x")
        self._status_dot = tk.Label(bar, text="●", fg=theme.SUCCESS, bg=theme.WHITE, font=theme.font(10))
        self._status_dot.pack(side="left", padx=(theme.px(14), theme.px(4)), pady=(theme.px(4), 0))
        self._status_label = tk.Label(
            bar,
            text="就绪",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True, pady=(theme.px(4), 0))
        self._camera_indicator = tk.Label(
            bar,
            text="",
            bg=theme.WHITE,
            fg=theme.PRIMARY,
            font=theme.font(10, "bold"),
        )
        self._camera_indicator.pack(side="right", padx=(0, theme.px(14)), pady=(theme.px(4), 0))
        tk.Label(
            bar,
            text=f"v{self.app_version}",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
        ).pack(side="right", padx=(0, theme.px(16)), pady=(theme.px(4), 0))

    # ------------------------------------------------------------------
    # 页面导航
    # ------------------------------------------------------------------
    def show_page(self, key: str) -> None:
        """切换到指定页面（懒加载 + 内嵌切换）。"""
        if key not in PAGES:
            key = "home"
        if self._current_key == key:
            page = self._pages.get(key)
            if page is not None and hasattr(page, "on_show"):
                page.on_show()
            return
        page = self._pages.get(key)
        if page is None:
            page = self._create_page(key)
            self._pages[key] = page
        current = self._pages.get(self._current_key) if self._current_key else None
        if current is not None and hasattr(current, "on_hide"):
            try:
                current.on_hide()
            except Exception:  # noqa: BLE001 - 页面隐藏异常不影响切换
                log.exception("页面隐藏异常：%s", self._current_key)
            try:
                current.grid_remove()
            except tk.TclError:
                pass
        page.grid(row=0, column=0, sticky="nsew")
        page.tkraise()
        self._current_key = key
        title = PAGES[key][2]
        self.title(APP_TITLE if key == "home" else f"{APP_TITLE} · {title}")
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:  # noqa: BLE001
                log.exception("页面显示异常：%s", key)
                self.set_status(f"页面加载异常：{key}", "error", 4000)
        self.set_status(f"已进入「{title}」", "info", 2500)

    def _create_page(self, key: str):
        module_name, class_name, _ = PAGES[key]
        try:
            module = importlib.import_module(module_name)
            page_class = getattr(module, class_name)
            return page_class(self.container, self)
        except Exception as exc:  # noqa: BLE001 - 单页构建失败兜底，避免整个应用崩溃
            log.exception("页面构建失败：%s", key)
            return _ErrorPage(
                self.container,
                self,
                f"页面「{PAGES[key][2]}」构建失败：{exc.__class__.__name__}: {exc}\n"
                "请查看日志文件获取详细信息，或向开发者反馈。",
            )

    def get_page(self, key: str):
        """获取已创建的页面实例（不存在返回 None）。"""
        return self._pages.get(key)

    def go_home(self) -> None:
        self.show_page("home")

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------
    def set_status(self, text: str, kind: str = "info", timeout_ms: int | None = None) -> None:
        """更新底部状态栏文字；timeout_ms 后恢复为「就绪」。"""
        colors = {
            "info": theme.MUTED,
            "success": theme.SUCCESS,
            "error": theme.DANGER,
            "warning": theme.WARNING,
            "primary": theme.PRIMARY,
        }
        try:
            self._status_label.configure(text=text, fg=colors.get(kind, theme.MUTED))
            self._status_dot.configure(fg=colors.get(kind, theme.MUTED))
        except tk.TclError:
            return
        if self._status_reset_job is not None:
            try:
                self.after_cancel(self._status_reset_job)
            except tk.TclError:
                pass
            self._status_reset_job = None
        if timeout_ms:
            self._status_reset_job = self.after(timeout_ms, self._reset_status)

    def _reset_status(self) -> None:
        self._status_reset_job = None
        try:
            self._status_label.configure(text="就绪", fg=theme.MUTED)
            self._status_dot.configure(fg=theme.SUCCESS)
        except tk.TclError:
            pass

    def set_camera_indicator(self, running: bool) -> None:
        """状态栏右侧显示一键相机运行状态。"""
        try:
            self._camera_indicator.configure(text="● 一键相机运行中" if running else "")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 后台模式 / 启动恢复
    # ------------------------------------------------------------------
    def _resume_camera_if_needed(self) -> None:
        """若用户上次开启了一键相机，则启动后自动恢复监听。"""
        if self._smoke_test:
            return
        try:
            enabled = bool(settings.get("camera_enabled"))
        except Exception:  # noqa: BLE001
            enabled = False
        if enabled:
            self.after(700, self._auto_start_camera)
        if self._background:
            self.after(900, self._enter_background)

    def _auto_start_camera(self) -> None:
        try:
            page = self._pages.get("camera")
            if page is None:
                page = self._create_page("camera")
                self._pages["camera"] = page
            start = getattr(page, "start_camera", None)
            if callable(start):
                start(auto=True)
        except Exception:  # noqa: BLE001 - 自动恢复失败不能影响启动
            log.exception("一键相机自动恢复失败")

    def _enter_background(self) -> None:
        """--background 模式：最小化到任务栏后台运行。"""
        try:
            self.iconify()
            self.set_status("已最小化到后台运行（一键相机会继续监听）", "info", 5000)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 异常与关闭
    # ------------------------------------------------------------------
    def _on_tk_exception(self, exc_type, exc_value, exc_traceback) -> None:
        """Tk 回调异常兜底：记录日志并在状态栏提示，不退出应用。"""
        log.error("Tk 回调异常", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            self.set_status(f"发生异常：{exc_value}", "error", 6000)
        except Exception:  # noqa: BLE001
            pass

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            geometry = self.geometry()
            settings.set("window_geometry", geometry if _GEOMETRY_RE.match(geometry) else "")
        except Exception:  # noqa: BLE001
            pass
        for key, page in list(self._pages.items()):
            try:
                on_close = getattr(page, "on_close", None)
                if callable(on_close):
                    on_close()
            except Exception:  # noqa: BLE001
                log.exception("页面退出清理异常：%s", key)
        try:
            self.destroy()
        except tk.TclError:
            pass
