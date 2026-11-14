import io

p = r'D:\开发\SeewoCamera\InspireCameraTools\app\app_window.py'
s = io.open(p, encoding='utf-8').read()

# imports
s = s.replace('''import importlib
import logging
import re
import tkinter as tk
from pathlib import Path

import ttkbootstrap as tb

from core import settings, sysinfo''','''import importlib
import logging
import re
import threading
import tkinter as tk
import webbrowser
from datetime import date
from pathlib import Path

import ttkbootstrap as tb

from core import cloud, settings, sysinfo''')

# __init__ 字段 + 启动云任务
s = s.replace('''        self._setup_dpi_and_style()
        self._setup_window()
        self._build_ui()
        self._resume_camera_if_needed()''','''        self._setup_dpi_and_style()
        self._setup_window()
        self._build_ui()
        self._resume_camera_if_needed()
        # 亿方智云：启动弹窗公告 / 手动更新检查 / 匿名上报（后台线程，失败静默）
        self._cloud_ping: cloud.PingLoop | None = None
        self.after(1200, self._start_cloud_tasks)''')

# 新增云服务方法（插到 _on_tk_exception 之前）
anchor = '''    # ------------------------------------------------------------------
    # 异常与关闭
    # ------------------------------------------------------------------'''
cloud_block = '''    # ------------------------------------------------------------------
    # 亿方智云：公告弹窗 / 手动更新 / 匿名上报
    # ------------------------------------------------------------------
    def _start_cloud_tasks(self) -> None:
        """界面就绪后再做云请求，避免拖慢启动；smoke-test 下不联网。"""
        if self._smoke_test:
            return
        try:
            self._cloud_ping = cloud.PingLoop()
            self._cloud_ping.start()
        except Exception:  # noqa: BLE001
            log.debug("启动匿名上报失败", exc_info=True)
        worker = threading.Thread(target=self._cloud_worker, name="cloud-fetch", daemon=True)
        worker.start()

    def _cloud_worker(self) -> None:
        """后台线程：拉取启动弹窗公告与版本信息（失败静默）。"""
        try:
            popup = cloud.get_popup()
            if popup:
                common.post_ui(self, lambda item=popup: self._handle_cloud_popup(item))
        except Exception:  # noqa: BLE001
            log.debug("获取启动弹窗失败", exc_info=True)
        try:
            info = cloud.check_update()
            if info:
                common.post_ui(self, lambda data=info: self._handle_cloud_update(data))
        except Exception:  # noqa: BLE001
            log.debug("检查更新失败", exc_info=True)

    def _handle_cloud_popup(self, item: dict) -> None:
        """显示启动弹窗公告（同一公告每天最多展示一次，由客户端记录）。"""
        try:
            popup_id = item.get("id")
            today = date.today().isoformat()
            seen = settings.get("cloud_popup_seen")
            if popup_id is not None and cloud.popup_seen_today(popup_id, today, seen):
                return
            title = str(item.get("title") or "公告")
            content = str(item.get("content") or "").strip()
            kind = str(item.get("kind") or "text")
            action, suppress = self._show_cloud_dialog(
                title=f"公告 · {title}",
                body=content or "（无内容）",
                actions=[("本次也打开链接", "primary")] if kind == "url" else [],
                checkbox_text="今日不再显示",
                checkbox_default=True,
            )
            if kind == "url" and action == 0 and content:
                self._open_url(content)
            if suppress and popup_id is not None:
                try:
                    settings.set("cloud_popup_seen", cloud.mark_popup_seen(popup_id, today, seen))
                except Exception:  # noqa: BLE001
                    log.debug("保存弹窗已读状态失败", exc_info=True)
        except Exception:  # noqa: BLE001
            log.exception("处理启动弹窗失败")

    def _handle_cloud_update(self, info: dict) -> None:
        """显示手动更新提示（不做自动下载/安装）。"""
        try:
            latest = str(info.get("latest_version") or "").strip()
            if not latest:
                return
            if str(settings.get("cloud_skip_version") or "").strip() == latest:
                return
            url = cloud.update_download_url(info)
            action, suppress = self._show_cloud_dialog(
                title="发现新版本",
                body=cloud.update_summary(info),
                actions=[("前往下载", "primary")],
                checkbox_text="跳过此版本",
                checkbox_default=False,
            )
            if action == 0 and url:
                self._open_url(url)
            if suppress:
                try:
                    settings.set("cloud_skip_version", latest)
                except Exception:  # noqa: BLE001
                    log.debug("保存跳过版本失败", exc_info=True)
        except Exception:  # noqa: BLE001
            log.exception("处理更新提示失败")

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            log.debug("打开链接失败：%s", url)

    def _show_cloud_dialog(
        self,
        title: str,
        body: str,
        actions: list[tuple[str, str]] | None = None,
        checkbox_text: str | None = None,
        checkbox_default: bool = True,
    ) -> tuple[int, bool]:
        """简单的模态对话窗；返回 (点击的按钮序号, 复选框状态)。"""
        actions = list(actions or [])
        result: dict[str, object] = {"action": -1, "checked": checkbox_default}
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=theme.WHITE)
        win.transient(self)
        win.resizable(False, False)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        header = tk.Label(
            win,
            text=title,
            bg=theme.WHITE,
            fg=theme.TEXT,
            font=theme.font(13, "bold"),
            anchor="w",
            justify="left",
        )
        header.pack(fill="x", padx=theme.px(18), pady=(theme.px(16), theme.px(6)))

        text = tk.Text(
            win,
            wrap="word",
            width=58,
            height=min(14, max(4, body.count("\\n") + 4)),
            bg=theme.WHITE,
            fg=theme.TEXT,
            relief="flat",
            borderwidth=0,
            font=theme.font(10),
            highlightthickness=0,
        )
        text.insert("1.0", body)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=theme.px(18), pady=(0, theme.px(8)))

        checked_var = tk.BooleanVar(value=checkbox_default)
        if checkbox_text:
            tb.Checkbutton(
                win,
                text=checkbox_text,
                variable=checked_var,
                bootstyle="round-toggle",
                cursor="hand2",
            ).pack(anchor="w", padx=theme.px(18), pady=(0, theme.px(6)))

        footer = tk.Frame(win, bg=theme.WHITE)
        footer.pack(fill="x", padx=theme.px(18), pady=(theme.px(4), theme.px(14)))

        def _close(action: int) -> None:
            result["action"] = action
            result["checked"] = bool(checked_var.get())
            try:
                win.destroy()
            except tk.TclError:
                pass

        for index in reversed(range(len(actions))):
            label, style = actions[index]
            tb.Button(
                footer,
                text=label,
                bootstyle=style,
                command=lambda i=index: _close(i),
                cursor="hand2",
            ).pack(side="right", padx=(theme.px(8), 0))
        tb.Button(
            footer,
            text="关闭",
            bootstyle="secondary-outline",
            command=lambda: _close(-1),
            cursor="hand2",
        ).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", lambda: _close(-1))
        win.update_idletasks()
        try:
            parent_x = self.winfo_rootx()
            parent_y = self.winfo_rooty()
            parent_w = self.winfo_width()
            parent_h = self.winfo_height()
            width = win.winfo_width()
            height = win.winfo_height()
            x = parent_x + max(0, (parent_w - width) // 2)
            y = parent_y + max(0, (parent_h - height) // 3)
            win.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        try:
            win.wait_window()
        except tk.TclError:
            pass
        return int(result["action"]), bool(result["checked"])

''' + anchor
s = s.replace(anchor, cloud_block, 1)

# 关闭时停止上报线程
s = s.replace('''        self._closing = True
        try:
            geometry = self.geometry()''','''        self._closing = True
        try:
            if self._cloud_ping is not None:
                self._cloud_ping.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            geometry = self.geometry()''')

io.open(p, 'w', encoding='utf-8').write(s)
print('app_window cloud integration patched')
