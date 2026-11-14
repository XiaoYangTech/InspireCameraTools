"""通用 UI 组件与线程工具：卡片、徽标、日志框、对话框封装等。"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from datetime import datetime
from typing import Callable

import ttkbootstrap as tb

from . import theme

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 主线程任务分发器（Tk 不是线程安全的：后台线程绝不能直接调用 Tk/after）
# ---------------------------------------------------------------------------
class _UiDispatcher:
    """把后台线程投递的回调放到 Tk 主线程执行。

    Tkinter 的 ``after``/控件操作必须在创建解释器的线程（主线程）调用。
    后台线程只往 ``queue.Queue`` 里放回调，主线程用 ``after`` 定时轮询执行。
    """

    def __init__(self, widget: tk.Misc) -> None:
        self._widget = widget
        self._queue: queue.Queue = queue.Queue()
        self._stopped = False
        self._after_id: str | None = None
        self._schedule(40)

    def _schedule(self, delay: int = 40) -> None:
        try:
            self._after_id = self._widget.after(delay, self._poll)
        except (tk.TclError, RuntimeError):
            self._stopped = True

    def post(self, func: Callable[[], None]) -> None:
        if not self._stopped:
            self._queue.put(func)

    def _poll(self) -> None:
        self._after_id = None
        if self._stopped:
            return
        try:
            while True:
                func = self._queue.get_nowait()
                try:
                    func()
                except Exception:  # noqa: BLE001 - 单个回调异常不影响后续
                    log.exception("UI 回调异常")
        except queue.Empty:
            pass
        try:
            if not self._widget.winfo_exists():
                self._stop()
                return
        except (tk.TclError, RuntimeError):
            self._stop()
            return
        self._schedule()

    def _stop(self) -> None:
        self._stopped = True
        self._queue = queue.Queue()
        _dispatchers.pop(id(self._widget), None)


_dispatchers: dict[int, _UiDispatcher] = {}
_dispatchers_lock = threading.Lock()


def post_ui(widget: tk.Misc, func: Callable[[], None]) -> None:
    """线程安全地把 ``func`` 投递到 Tk 主线程执行。"""
    if widget is None:
        return
    key = id(widget)
    with _dispatchers_lock:
        dispatcher = _dispatchers.get(key)
        if dispatcher is None:
            try:
                dispatcher = _UiDispatcher(widget)
            except (tk.TclError, RuntimeError):
                return
            _dispatchers[key] = dispatcher
    dispatcher.post(func)


# ---------------------------------------------------------------------------
# 线程工具：耗时任务放后台线程，结果安全回主线程
# ---------------------------------------------------------------------------
def run_async(
    widget: tk.Misc,
    func: Callable[[], object],
    on_success: Callable[[object], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    name: str = "app-worker",
) -> threading.Thread:
    """在后台线程执行 ``func``，完成后在主线程回调 on_success/on_error。

    回调异常会记录日志，不会冒泡导致 Tk 崩溃。
    """

    def _dispatch(callback, arg) -> None:
        if callback is None:
            return
        post_ui(widget, lambda: _safe_call(callback, arg))

    def _worker() -> None:
        try:
            result = func()
        except BaseException as exc:  # noqa: BLE001 - 后台任务异常统一交给 UI 处理
            log.exception("后台任务异常（%s）", name)
            _dispatch(on_error, exc)
        else:
            _dispatch(on_success, result)

    thread = threading.Thread(target=_worker, daemon=True, name=name)
    thread.start()
    return thread


def _safe_call(callback, arg) -> None:
    try:
        callback(arg)
    except Exception:  # noqa: BLE001 - 回调异常不能打断 Tk 事件循环
        log.exception("UI 回调异常：%s", getattr(callback, "__name__", callback))


# ---------------------------------------------------------------------------
# 基础视觉组件
# ---------------------------------------------------------------------------
class Card(tk.Frame):
    """白底描边卡片容器（内部统一使用 ``.body`` 作为内容区）。"""

    def __init__(
        self,
        master: tk.Misc,
        title: str | None = None,
        subtitle: str | None = None,
        icon: str | None = None,
        padding: int = 16,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            bg=theme.WHITE,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            bd=0,
            **kwargs,
        )
        self._pad = padding
        self.inner = tk.Frame(self, bg=theme.WHITE)
        self.inner.pack(fill="both", expand=True, padx=padding, pady=padding)
        self.header_right: tk.Frame | None = None
        if title:
            header = tk.Frame(self.inner, bg=theme.WHITE)
            header.pack(fill="x")
            if icon:
                icon_label = tk.Label(
                    header,
                    image=theme.load_icon(icon, theme.px(22), master=self),
                    bg=theme.WHITE,
                )
                icon_label.pack(side="left", padx=(0, 8))
            title_box = tk.Frame(header, bg=theme.WHITE)
            title_box.pack(side="left", fill="x", expand=True)
            tk.Label(
                title_box,
                text=title,
                bg=theme.WHITE,
                fg=theme.TEXT,
                font=theme.font(13, "bold"),
                anchor="w",
            ).pack(fill="x")
            if subtitle:
                tk.Label(
                    title_box,
                    text=subtitle,
                    bg=theme.WHITE,
                    fg=theme.MUTED,
                    font=theme.font(11),
                    anchor="w",
                ).pack(fill="x", pady=(2, 0))
            self.header_right = tk.Frame(header, bg=theme.WHITE)
            self.header_right.pack(side="right")
        self.body = tk.Frame(self.inner, bg=theme.WHITE)
        self.body.pack(fill="both", expand=True, pady=(12, 0) if title else (0, 0))

    def add_header_widget(self, widget: tk.Widget) -> None:
        """把控件放到卡片标题栏右侧。"""
        target = self.header_right if self.header_right is not None else self.body
        widget.pack(in_=target, side="right", padx=(8, 0))


class Badge(tk.Label):
    """状态徽标（圆角效果用 padding + 单色底模拟）。"""

    def __init__(self, master: tk.Misc, text: str = "", kind: str = "secondary", **kwargs) -> None:
        super().__init__(
            master,
            text=text,
            font=theme.font(10),
            bd=0,
            padx=theme.px(8),
            pady=theme.px(2),
            **kwargs,
        )
        self.set(text, kind)

    def set(self, text: str, kind: str = "secondary") -> None:
        fg, bg = theme.BADGE_STYLES.get(kind, theme.BADGE_STYLES["secondary"])
        self.configure(text=text, fg=fg, bg=bg)


class LogText(tk.Frame):
    """带滚动条和颜色标签的只读日志框。"""

    TAGS = {
        "time": theme.MUTED,
        "info": theme.TEXT,
        "success": theme.SUCCESS,
        "error": theme.DANGER,
        "warning": theme.WARNING,
        "primary": theme.PRIMARY_DARK,
        "muted": theme.MUTED,
    }

    def __init__(self, master: tk.Misc, height: int = 8, max_lines: int = 2000, **kwargs) -> None:
        super().__init__(master, bg=theme.WHITE, **kwargs)
        self.max_lines = max_lines
        self.text = tk.Text(
            self,
            height=height,
            wrap="word",
            bg=theme.LIGHT,
            fg=theme.TEXT,
            relief="flat",
            bd=0,
            padx=theme.px(10),
            pady=theme.px(8),
            font=(theme.FONT_FAMILY, 11),
            insertwidth=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.BORDER,
        )
        scrollbar = tb.Scrollbar(self, orient="vertical", command=self.text.yview, bootstyle="secondary-round")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(state="disabled")
        for tag, color in self.TAGS.items():
            self.text.tag_configure(tag, foreground=color)

    def log(self, message: str, level: str = "info", with_time: bool = True) -> None:
        """追加一行日志；level 决定文字颜色。"""
        if level not in self.TAGS:
            level = "info"
        timestamp = datetime.now().strftime("%H:%M:%S") if with_time else ""
        try:
            at_bottom = self.text.yview()[1] > 0.995
            self.text.configure(state="normal")
            if timestamp:
                self.text.insert("end", f"[{timestamp}] ", "time")
            self.text.insert("end", f"{message}\n", level)
            line_count = int(self.text.index("end-1c").split(".")[0])
            if line_count > self.max_lines:
                self.text.delete("1.0", f"{line_count - self.max_lines}.0")
            self.text.configure(state="disabled")
            if at_bottom:
                self.text.see("end")
        except tk.TclError:
            pass

    def clear(self) -> None:
        try:
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")
        except tk.TclError:
            pass


class ScrollFrame(tk.Frame):
    """纵向可滚动容器（用于内容较长的页面）。内容放到 ``.inner``。

    ``fill_height=True`` 时，内容不足一屏会自动拉伸填满可视区域；内容超过一屏则可滚动
    （用于主页等「正常 DPI 下撑满、高 DPI 下可滚动」的页面）。
    """

    def __init__(self, master: tk.Misc, bg: str = theme.PAGE_BG, fill_height: bool = False, **kwargs) -> None:
        super().__init__(master, bg=bg, **kwargs)
        self._fill_height = fill_height
        self._resize_job: str | None = None
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = tb.Scrollbar(self, orient="vertical", command=self.canvas.yview, bootstyle="secondary-round")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._scroll_needed = True
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_wheel()

    def _on_inner_configure(self, _event=None) -> None:
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass
        if self._fill_height:
            self._schedule_fill()
        else:
            self._update_scrollbar()

    def _on_canvas_configure(self, event) -> None:
        try:
            self.canvas.itemconfigure(self._window, width=event.width)
        except tk.TclError:
            pass
        if self._fill_height:
            self._schedule_fill()
        else:
            self._update_scrollbar()

    def _update_scrollbar(self) -> None:
        """内容不足一屏时自动隐藏滚动条，保持界面整洁。"""
        try:
            needed = self.inner.winfo_reqheight() > self.canvas.winfo_height() + 2
        except tk.TclError:
            return
        if needed == self._scroll_needed:
            return
        self._scroll_needed = needed
        try:
            if needed:
                if not self.scrollbar.winfo_manager():
                    self.scrollbar.pack(side="right", fill="y", before=self.canvas)
            elif self.scrollbar.winfo_manager():
                self.scrollbar.pack_forget()
        except tk.TclError:
            pass

    def _schedule_fill(self) -> None:
        if self._resize_job is not None:
            return
        try:
            self._resize_job = self.after_idle(self._apply_fill_height)
        except tk.TclError:
            self._resize_job = None

    def _apply_fill_height(self) -> None:
        self._resize_job = None
        try:
            needed = self.inner.winfo_reqheight()
            available = self.canvas.winfo_height()
            target = max(needed, available)
            if abs(self.inner.winfo_height() - target) > 1:
                self.canvas.itemconfigure(self._window, height=target)
        except tk.TclError:
            pass
        self._update_scrollbar()

    def _bind_wheel(self) -> None:
        def _on_wheel(event):
            try:
                if self.canvas.yview() == (0.0, 1.0):
                    return
                delta = -1 if event.delta > 0 else 1
                self.canvas.yview_scroll(delta * 2, "units")
            except tk.TclError:
                pass

        # 进入区域时绑定，避免抢占其它控件滚轮事件
        self.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", _on_wheel))
        self.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))


# ---------------------------------------------------------------------------
# 行/文本小工具
# ---------------------------------------------------------------------------
def separator(master: tk.Misc, pady: int = 8) -> tk.Frame:
    """1px 分隔线。"""
    line = tk.Frame(master, bg=theme.BORDER, height=1)
    line.pack(fill="x", pady=pady)
    return line


def label(
    master: tk.Misc,
    text: str,
    size: int = 12,
    weight: str = "normal",
    fg: str = theme.TEXT,
    bg: str = theme.WHITE,
    **kwargs,
) -> tk.Label:
    """快捷创建 tk.Label。"""
    return tk.Label(master, text=text, font=theme.font(size, weight), fg=fg, bg=bg, **kwargs)


def key_value(
    master: tk.Misc,
    label_text: str,
    value_text: str = "-",
    value_weight: str = "bold",
    width: int = 92,
) -> tuple[tk.Frame, tk.Label]:
    """两列「标签：值」行，返回 (行容器, 值 Label) 便于动态更新。"""
    row = tk.Frame(master, bg=theme.WHITE)
    label(row, label_text, size=11, fg=theme.MUTED, width=width // 12, anchor="w").pack(
        side="left", padx=(0, 6)
    )
    value = label(row, value_text, size=11, weight=value_weight, anchor="w")
    value.pack(side="left", fill="x", expand=True)
    return row, value


# ---------------------------------------------------------------------------
# 对话框封装（优先 ttkbootstrap 风格，失败退回 tkinter）
# ---------------------------------------------------------------------------
def ask_yes_no(parent: tk.Misc, title: str, message: str) -> bool:
    try:
        from ttkbootstrap.dialogs import Messagebox

        result = Messagebox.yesno(message, title, parent=parent)
        if isinstance(result, bool):
            return result
        return str(result).strip().lower() in ("yes", "是", "确认", "ok", "true", "1")
    except Exception:  # noqa: BLE001
        from tkinter import messagebox

        return bool(messagebox.askyesno(title, message, parent=parent))


def show_info(parent: tk.Misc, title: str, message: str) -> None:
    _show(parent, title, message, "info")


def show_warning(parent: tk.Misc, title: str, message: str) -> None:
    _show(parent, title, message, "warning")


def show_error(parent: tk.Misc, title: str, message: str) -> None:
    _show(parent, title, message, "error")


def _show(parent: tk.Misc, title: str, message: str, kind: str) -> None:
    try:
        from ttkbootstrap.dialogs import Messagebox

        getattr(Messagebox, f"show_{kind}")(message, title, parent=parent)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        from tkinter import messagebox

        getattr(messagebox, f"show{kind}")(title, message, parent=parent)
    except Exception:  # noqa: BLE001
        log.warning("%s: %s", title, message)


def ask_directory(parent: tk.Misc, title: str, initial: str = "") -> str:
    """选择目录（返回空字符串表示取消）。"""
    from tkinter import filedialog

    try:
        return filedialog.askdirectory(parent=parent, title=title, initialdir=initial or None) or ""
    except Exception:  # noqa: BLE001
        return ""
