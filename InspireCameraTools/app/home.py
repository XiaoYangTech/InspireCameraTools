"""主页：展台状态卡片 + 功能入口网格。"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable

import ttkbootstrap as tb

from core import hid, settings, sysinfo

from . import common, theme
from .app_window import APP_TITLE

log = logging.getLogger(__name__)

#: 功能入口定义：(页面 key, 图标, 标题, 说明)
FEATURE_ENTRIES: list[tuple[str, str, str, str]] = [
    ("patch", "patch", "一键补丁", "检测版本并一键应用功能补丁"),
    ("hid", "hid", "状态调试", "灯控、触摸灯、按键与原始帧调试"),
    ("download", "download", "历史版本下载", "从希沃官方源下载历史版本安装包"),
    ("autoupdate", "autoupdate", "破坏自动更新", "阻止自动升级覆盖已打补丁的文件"),
    ("camera", "camera", "一键相机", "机身补光灯键触发拍照快捷键"),
    ("settings", "settings", "设置与关于", "安装目录、数据目录与免责声明"),
]


class FeatureCard(tk.Frame):
    """功能入口卡片：图标 + 标题 + 说明，带悬停高亮。"""

    def __init__(self, master: tk.Misc, icon: str, title: str, description: str, command: Callable) -> None:
        super().__init__(
            master,
            bg=theme.WHITE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            bd=0,
            cursor="hand2",
        )
        self._command = command
        inner = tk.Frame(self, bg=theme.WHITE)
        inner.pack(fill="both", expand=True, padx=theme.px(18), pady=theme.px(16))
        self._icon_label = tk.Label(
            inner,
            image=theme.load_icon(icon, theme.px(52), master=self),
            bg=theme.WHITE,
        )
        self._icon_label.pack(anchor="w")
        self._title_label = tk.Label(
            inner,
            text=title,
            bg=theme.WHITE,
            fg=theme.TEXT,
            font=theme.font(14, "bold"),
            anchor="w",
        )
        self._title_label.pack(anchor="w", pady=(theme.px(10), theme.px(2)))
        self._desc_label = tk.Label(
            inner,
            text=description,
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(11),
            anchor="w",
            justify="left",
            wraplength=theme.px(230),
        )
        self._desc_label.pack(anchor="w")
        self._hover_widgets = [self, inner, self._icon_label, self._title_label, self._desc_label]
        for widget in self._hover_widgets:
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", self._on_click)
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass

    def _on_enter(self, _event=None) -> None:
        for widget in self._hover_widgets:
            try:
                widget.configure(bg=theme.HOVER_BG)
            except tk.TclError:
                pass
        try:
            self.configure(highlightbackground=theme.PRIMARY)
        except tk.TclError:
            pass

    def _on_leave(self, _event=None) -> None:
        for widget in self._hover_widgets:
            try:
                widget.configure(bg=theme.WHITE)
            except tk.TclError:
                pass
        try:
            self.configure(highlightbackground=theme.BORDER)
        except tk.TclError:
            pass

    def _on_click(self, _event=None) -> None:
        try:
            self._command()
        except Exception:  # noqa: BLE001
            log.exception("功能入口点击处理失败")


class HomePage(tk.Frame):
    """主页。"""

    title = "主页"
    subtitle = ""
    icon = ""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, bg=theme.PAGE_BG)
        self.app = app
        self._refreshing = False
        self._values: dict[str, object] = {}
        self._last_refresh = 0.0
        pad = theme.px(26)
        # 可滚动容器：正常 DPI 下自动撑满窗口；高 DPI 下内容超出时可滚动，避免裁切
        self._scroll = common.ScrollFrame(self, bg=theme.PAGE_BG, fill_height=True)
        self._scroll.pack(fill="both", expand=True)
        self._root = tk.Frame(self._scroll.inner, bg=theme.PAGE_BG)
        self._root.pack(fill="both", expand=True, padx=pad, pady=theme.px(20))
        self._build_header()
        self._build_status_card()
        self._build_feature_grid()
        self._build_footer()

    # ------------------------------------------------------------------
    # 顶部品牌区
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self._root, bg=theme.PAGE_BG)
        header.pack(fill="x", pady=(0, theme.px(16)))
        tk.Label(
            header,
            image=theme.load_icon("logo", theme.px(52), master=self),
            bg=theme.PAGE_BG,
        ).pack(side="left", padx=(0, theme.px(14)))
        text_box = tk.Frame(header, bg=theme.PAGE_BG)
        text_box.pack(side="left")
        tk.Label(
            text_box,
            text=APP_TITLE,
            bg=theme.PAGE_BG,
            fg=theme.TEXT,
            font=theme.font(22, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text_box,
            text="希沃视频展台辅助工具 · InspireCameraTools",
            bg=theme.PAGE_BG,
            fg=theme.MUTED,
            font=theme.font(11),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        right = tk.Frame(header, bg=theme.PAGE_BG)
        right.pack(side="right")
        tk.Label(
            right,
            text=f"v{settings.APP_VERSION}",
            bg=theme.PAGE_BG,
            fg=theme.MUTED,
            font=theme.font(11),
        ).pack(anchor="e")
        self._refresh_button = tb.Button(
            right,
            text="刷新状态",
            bootstyle="primary-outline",
            command=self.refresh_status,
            cursor="hand2",
            width=8,
        )
        self._refresh_button.pack(anchor="e", pady=(theme.px(4), 0))

    # ------------------------------------------------------------------
    # 展台状态
    # ------------------------------------------------------------------
    def _build_status_card(self) -> None:
        card = common.Card(
            self._root,
            title="展台状态",
            subtitle="实时检测展台硬件连接与 EasiCamera 软件环境",
            icon="hid",
            padding=theme.px(18),
        )
        card.pack(fill="x", pady=(0, theme.px(18)))
        self._status_badge = common.Badge(card.header_right, text="检测中…", kind="info")
        self._status_badge.pack(side="right")

        grid = tk.Frame(card.body, bg=theme.WHITE)
        grid.pack(fill="x")
        for col in range(4):
            grid.grid_columnconfigure(col, weight=1, uniform="status")
        items = [
            ("connection", "连接状态"),
            ("model", "识别机型"),
            ("vid_pid", "VID / PID"),
            ("led", "展台灯状态"),
            ("software", "EasiCamera 版本"),
            ("patch", "补丁状态"),
            ("mcu", "MCU 版本"),
            ("system", "系统环境"),
        ]
        for index, (key, label_text) in enumerate(items):
            row, col = divmod(index, 4)
            cell = tk.Frame(grid, bg=theme.WHITE)
            cell.grid(row=row, column=col, sticky="nsew", padx=(0, theme.px(10)), pady=theme.px(6))
            tk.Label(
                cell,
                text=label_text,
                bg=theme.WHITE,
                fg=theme.MUTED,
                font=theme.font(10),
                anchor="w",
            ).pack(anchor="w")
            if key == "connection":
                value_widget = common.Badge(cell, text="—", kind="secondary")
                value_widget.pack(anchor="w", pady=(theme.px(3), 0))
            else:
                value_widget = tk.Label(
                    cell,
                    text="—",
                    bg=theme.WHITE,
                    fg=theme.TEXT,
                    font=theme.font(12, "bold"),
                    anchor="w",
                )
                value_widget.pack(anchor="w", pady=(theme.px(3), 0))
            self._values[key] = value_widget

    # ------------------------------------------------------------------
    # 功能入口
    # ------------------------------------------------------------------
    def _build_feature_grid(self) -> None:
        title_row = tk.Frame(self._root, bg=theme.PAGE_BG)
        title_row.pack(fill="x", pady=(0, theme.px(10)))
        tk.Label(
            title_row,
            text="功能入口",
            bg=theme.PAGE_BG,
            fg=theme.TEXT,
            font=theme.font(14, "bold"),
        ).pack(side="left")
        tk.Label(
            title_row,
            text="点击卡片进入对应功能页",
            bg=theme.PAGE_BG,
            fg=theme.MUTED,
            font=theme.font(10),
        ).pack(side="left", padx=(theme.px(10), 0), pady=(theme.px(2), 0))

        grid = tk.Frame(self._root, bg=theme.PAGE_BG)
        grid.pack(fill="both", expand=True)
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="features")
        for row in range(2):
            grid.grid_rowconfigure(row, weight=1, uniform="features")
        for index, (key, icon, title, description) in enumerate(FEATURE_ENTRIES):
            row, col = divmod(index, 3)
            card = FeatureCard(
                grid,
                icon=icon,
                title=title,
                description=description,
                command=lambda k=key: self.app.show_page(k),
            )
            card.grid(
                row=row,
                column=col,
                sticky="nsew",
                padx=(0 if col == 0 else theme.px(10), 0),
                pady=(0 if row == 0 else theme.px(10), 0),
            )

    def _build_footer(self) -> None:
        footer = tk.Frame(self._root, bg=theme.PAGE_BG)
        footer.pack(fill="x", pady=(theme.px(12), 0))
        tk.Label(
            footer,
            text="提示：未连接展台时「状态调试 / 一键相机」会提示未连接，补丁、下载等功能不受影响。",
            bg=theme.PAGE_BG,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        ).pack(side="left")

    # ------------------------------------------------------------------
    # 状态刷新
    # ------------------------------------------------------------------
    def set_status(self, text: str, kind: str = "info", timeout_ms: int | None = None) -> None:
        """更新窗口底部状态栏（主页非 BasePage，这里做同样封装）。"""
        try:
            self.app.set_status(text, kind, timeout_ms)
        except Exception:  # noqa: BLE001 - 状态栏更新失败不影响业务
            pass

    def on_show(self) -> None:
        self.refresh_status()

    def refresh_status(self) -> None:
        """后台采集展台/软件状态并刷新卡片。"""
        if self._refreshing:
            return
        self._refreshing = True
        self._refresh_button.configure(state="disabled")
        self._status_badge.set("检测中…", "info")
        self.set_status("正在检测展台与软件状态…", "info")
        common.run_async(
            self,
            self._collect_status,
            on_success=self._apply_status,
            on_error=self._status_error,
            name="home-status",
        )

    def _collect_status(self) -> dict:
        """后台线程：采集状态（不触碰 Tk 控件）。"""
        data: dict = {
            "camera": sysinfo.detect_camera_status(),
            "system": sysinfo.windows_version_text(),
            "admin": sysinfo.is_admin(),
            "led": "",
            "mcu": "",
            "software": "",
            "patch": "",
            "patch_kind": "secondary",
            "errors": [],
        }
        # 灯状态 / MCU：仅在检测到展台时查询（避免无硬件时无谓等待）
        try:
            if data["camera"].connected:
                controller = hid.HidController()
                led = controller.query_led()
                if led is not None:
                    data["led"] = led.text
                else:
                    data["led"] = "未获取到灯状态"
                mcu = controller.query_mcu()
                data["mcu"] = mcu or "—"
        except Exception as exc:  # noqa: BLE001
            data["errors"].append(f"HID 状态查询失败：{exc}")

        # EasiCamera 安装与补丁状态
        try:
            data.update(self._collect_patch_status())
        except Exception as exc:  # noqa: BLE001
            data["software"] = "检测失败"
            data["patch"] = "检测失败"
            data["errors"].append(f"补丁状态检测失败：{exc}")
        return data

    def _collect_patch_status(self) -> dict:
        """探测 EasiCamera 安装版本与补丁状态（引擎未就绪时优雅降级）。"""
        result = {"software": "未检测到安装", "patch": "未检测", "patch_kind": "secondary"}
        try:
            import core.patch_engine as engine  # noqa: F401 - 延迟导入，允许尚不存在
        except Exception as exc:  # noqa: BLE001
            log.debug("补丁引擎不可用：%s", exc)
            result["software"] = "补丁引擎未就绪"
            result["patch"] = "补丁引擎未就绪"
            return result
        try:
            configured = str(settings.get("install_dir") or "").strip() or None
            main_dir = engine.find_main_dir(configured)
        except Exception as exc:  # noqa: BLE001
            result["patch"] = f"目录探测失败：{exc}"
            return result
        if not main_dir:
            result["software"] = "未检测到 EasiCamera"
            result["patch"] = "未检测到安装目录"
            return result
        try:
            detected = engine.detect_version(main_dir)
        except Exception as exc:  # noqa: BLE001
            result["software"] = "版本识别失败"
            result["patch"] = f"识别异常：{exc}"
            return result
        if detected is None:
            result["software"] = "未识别的版本"
            result["patch"] = "无匹配补丁规则"
            return result
        result["software"] = getattr(detected, "display_name", None) or getattr(detected, "version", "未知版本")
        try:
            patched = engine.is_patched(main_dir)
            count = sum(1 for value in patched.values() if value)
            total = len(patched)
            if count > 0:
                result["patch"] = f"已打补丁 {count}/{total} 项"
                result["patch_kind"] = "success"
            else:
                result["patch"] = "原版（未打补丁）"
        except Exception as exc:  # noqa: BLE001
            result["patch"] = f"补丁状态读取失败：{exc}"
        return result

    def _status_error(self, exc: BaseException) -> None:
        """状态采集失败时的兜底展示。"""
        self._refreshing = False
        try:
            self._refresh_button.configure(state="normal")
        except tk.TclError:
            return
        self._status_badge.set("检测失败", "danger")
        try:
            self._values["connection"].set("未知", "secondary")
        except (tk.TclError, KeyError):
            pass
        self.set_status(f"状态检测失败：{exc}", "error", 6000)

    def _apply_status(self, data: dict) -> None:
        self._refreshing = False
        try:
            self._refresh_button.configure(state="normal")
        except tk.TclError:
            return
        camera: sysinfo.CameraStatus = data["camera"]
        try:
            if camera.connected:
                self._status_badge.set("已连接", "success")
                self._values["connection"].set("已连接", "success")
                self._values["model"].configure(text=camera.model or "未知机型")
                self._values["vid_pid"].configure(text=camera.vid_pid_text)
                self._values["led"].configure(text=data.get("led") or "未获取到灯状态")
                self._values["mcu"].configure(text=data.get("mcu") or "—")
            else:
                self._status_badge.set("未连接", "secondary")
                self._values["connection"].set("未连接", "secondary")
                self._values["model"].configure(text="未检测到展台")
                self._values["vid_pid"].configure(text="—")
                self._values["led"].configure(text="—")
                self._values["mcu"].configure(text="—")
            self._values["software"].configure(text=str(data.get("software") or "未知"))
            patch_kind = str(data.get("patch_kind") or "secondary")
            self._values["patch"].configure(
                text=str(data.get("patch") or "未知"),
                fg=theme.SUCCESS if patch_kind == "success" else theme.TEXT,
            )
            admin_text = "管理员" if data.get("admin") else "普通用户"
            self._values["system"].configure(text=f"{data.get('system', '')} · {admin_text}")
        except (tk.TclError, KeyError) as exc:
            log.debug("刷新首页状态失败：%s", exc)
        errors = data.get("errors") or []
        if errors:
            self.set_status("；".join(errors[:2]), "warning", 5000)
        else:
            self.set_status("状态检测完成", "success", 3000)
