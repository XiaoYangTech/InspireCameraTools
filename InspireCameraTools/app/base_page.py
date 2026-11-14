"""子页面基类：统一标题栏（返回按钮 + 标题 + 右侧操作区）与内容区。"""

from __future__ import annotations

import tkinter as tk

import ttkbootstrap as tb

from . import common, theme


class BasePage(tk.Frame):
    """所有功能页面的基类。

    子类实现 :meth:`build_body` 构建内容；页面进入时 :meth:`on_show` 被调用，
    离开时 :meth:`on_hide` 被调用。子类可用 :meth:`add_header_button` 在标题栏
    右侧添加操作按钮。
    """

    #: 标题栏文案（子类覆盖）
    title = "页面"
    subtitle = ""
    #: 标题栏左侧图标名（assets/icons 下，不含扩展名）
    icon = ""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, bg=theme.PAGE_BG)
        self.app = app
        self._header_right: tk.Frame | None = None
        self._header_buttons: list[tk.Widget] = []
        # 页面四周留白，避免内容贴窗口边缘
        self._outer = tk.Frame(self, bg=theme.PAGE_BG)
        self._outer.pack(fill="both", expand=True, padx=theme.px(24), pady=theme.px(16))
        self._build_header()
        self.body = tk.Frame(self._outer, bg=theme.PAGE_BG)
        self.body.pack(fill="both", expand=True, pady=(theme.px(14), 0))
        self.build_body()

    # ---------- 标题栏 ----------
    def _build_header(self) -> None:
        header = tk.Frame(self._outer, bg=theme.PAGE_BG)
        header.pack(fill="x")
        back = tb.Button(
            header,
            text="← 返回",
            bootstyle="secondary-outline",
            command=self.app.go_home,
            cursor="hand2",
            width=7,
        )
        back.pack(side="left", padx=(0, theme.px(14)))
        if self.icon:
            tk.Label(
                header,
                image=theme.load_icon(self.icon, theme.px(28), master=self),
                bg=theme.PAGE_BG,
            ).pack(side="left", padx=(0, theme.px(8)))
        text_box = tk.Frame(header, bg=theme.PAGE_BG)
        text_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            text_box,
            text=self.title,
            bg=theme.PAGE_BG,
            fg=theme.TEXT,
            font=theme.font(17, "bold"),
            anchor="w",
        ).pack(fill="x")
        if self.subtitle:
            tk.Label(
                text_box,
                text=self.subtitle,
                bg=theme.PAGE_BG,
                fg=theme.MUTED,
                font=theme.font(11),
                anchor="w",
            ).pack(fill="x", pady=(2, 0))
        self._header_right = tk.Frame(header, bg=theme.PAGE_BG)
        self._header_right.pack(side="right")

    def add_header_button(self, text: str, command, bootstyle: str = "secondary-outline", width: int = 0) -> tb.Button:
        """在标题栏右侧添加按钮。"""
        options = {
            "text": text,
            "command": command,
            "bootstyle": bootstyle,
            "cursor": "hand2",
        }
        if width > 0:
            options["width"] = width
        button = tb.Button(self._header_right, **options)
        button.pack(side="right", padx=(theme.px(8), 0))
        self._header_buttons.append(button)
        return button

    # ---------- 内容区 ----------
    def build_body(self) -> None:  # pragma: no cover - 由子类实现
        raise NotImplementedError

    # ---------- 生命周期 ----------
    def on_show(self) -> None:
        """页面显示时调用（子类可刷新数据）。"""

    def on_hide(self) -> None:
        """页面隐藏时调用。"""

    def on_close(self) -> None:
        """应用退出时调用（子类可停止线程）。"""

    # ---------- 便捷方法 ----------
    def set_status(self, text: str, kind: str = "info", timeout_ms: int | None = None) -> None:
        """更新窗口底部状态栏。"""
        try:
            self.app.set_status(text, kind, timeout_ms)
        except Exception:  # noqa: BLE001 - 状态栏更新失败不影响业务
            pass

    def card_row(self, parent: tk.Misc | None = None, pady: int = 12) -> tk.Frame:
        """创建一行卡片区域。"""
        row = tk.Frame(parent or self.body, bg=theme.PAGE_BG)
        row.pack(fill="x", pady=(0, pady))
        return row
