"""历史版本下载页：从希沃 swapp 官方源拉取版本列表并下载安装包。"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import ttkbootstrap as tb

from core import downloader, settings, sysinfo

from . import common, theme
from .base_page import BasePage

log = logging.getLogger(__name__)

COLUMNS = ("version", "size", "publish", "status")
HEADINGS = {"version": "版本", "size": "大小", "publish": "发布时间", "status": "下载状态"}


class DownloadPage(BasePage):
    """历史版本下载页面。"""

    title = "历史版本下载"
    subtitle = "数据源：希沃官方软件包接口（仅 Windows 版本，按发布时间倒序）"
    icon = "download"

    def __init__(self, master: tk.Misc, app) -> None:
        self._client = downloader.SwappClient()
        self._versions: list[downloader.SoftVersion] = []
        self._filtered: list[downloader.SoftVersion] = []
        self._row_map: dict[str, downloader.SoftVersion] = {}
        self._row_status: dict[str, str] = {}
        self._loading = False
        self._downloading = False
        self._cancel_event: threading.Event | None = None
        self._search_job: str | None = None
        self._loaded_once = False
        self._download_dir = settings.default_download_dir()
        super().__init__(master, app)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_body(self) -> None:
        self.add_header_button("刷新列表", self.load_versions, bootstyle="secondary-outline")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self._build_table_card()
        self._build_download_card()

    def _build_table_card(self) -> None:
        card = common.Card(
            self.body,
            title="版本列表",
            subtitle="支持搜索版本号；双击某行可直接下载",
            icon="download",
            padding=theme.px(14),
        )
        card.grid(row=0, column=0, sticky="nsew", pady=(0, theme.px(12)))
        toolbar = tk.Frame(card.body, bg=theme.WHITE)
        toolbar.pack(fill="x", pady=(0, theme.px(8)))
        tk.Label(toolbar, text="搜索", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(6))
        )
        self._search_var = tk.StringVar()
        search_entry = tb.Entry(toolbar, textvariable=self._search_var, bootstyle="secondary", width=18)
        search_entry.pack(side="left", padx=(0, theme.px(6)))
        search_entry.bind("<KeyRelease>", self._on_search_changed)
        self._search_var.trace_add("write", lambda *_: self._schedule_filter())
        self._count_label = tk.Label(
            toolbar, text="尚未加载", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)
        )
        self._count_label.pack(side="right")

        # 错误提示条（默认隐藏）
        self._error_banner = tk.Frame(card.body, bg=theme.DANGER_BG)
        self._error_label = tk.Label(
            self._error_banner,
            text="",
            bg=theme.DANGER_BG,
            fg=theme.DANGER,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(900),
            padx=theme.px(10),
            pady=theme.px(6),
        )
        self._error_label.pack(side="left", fill="x", expand=True)
        self._retry_button = tb.Button(
            self._error_banner,
            text="重试",
            bootstyle="danger-outline",
            command=self.load_versions,
            cursor="hand2",
            width=6,
        )
        self._retry_button.pack(side="right", padx=theme.px(8))

        table_frame = tk.Frame(card.body, bg=theme.WHITE)
        table_frame.pack(fill="both", expand=True)
        self._tree = tb.Treeview(
            table_frame,
            columns=COLUMNS,
            show="headings",
            selectmode="browse",
            bootstyle="secondary",
            height=12,
        )
        widths = {"version": 200, "size": 120, "publish": 170, "status": 130}
        for col in COLUMNS:
            self._tree.heading(col, text=HEADINGS[col])
            self._tree.column(col, width=theme.px(widths[col]), minwidth=theme.px(80), anchor="w", stretch=col == "version")
        scrollbar = tb.Scrollbar(table_frame, orient="vertical", command=self._tree.yview, bootstyle="secondary-round")
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._tree.tag_configure("done", foreground=theme.SUCCESS)
        self._tree.tag_configure("downloading", foreground=theme.PRIMARY_DARK)
        self._tree.tag_configure("failed", foreground=theme.DANGER)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _e: self.start_download())

    def _build_download_card(self) -> None:
        card = common.Card(self.body, title="下载", subtitle="", icon="download", padding=theme.px(14))
        card.grid(row=1, column=0, sticky="ew")
        info_row = tk.Frame(card.body, bg=theme.WHITE)
        info_row.pack(fill="x")
        self._selected_label = tk.Label(
            info_row,
            text="未选择版本",
            bg=theme.WHITE,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
            anchor="w",
        )
        self._selected_label.pack(side="left")
        self._dir_label = tk.Label(
            info_row,
            text=f"下载目录：{self._download_dir}",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="e",
        )
        self._dir_label.pack(side="right")

        progress_row = tk.Frame(card.body, bg=theme.WHITE)
        progress_row.pack(fill="x", pady=(theme.px(10), theme.px(8)))
        self._progress = ttk.Progressbar(
            progress_row, orient="horizontal", mode="determinate", maximum=100, bootstyle="primary-striped"
        )
        self._progress.pack(side="left", fill="x", expand=True, padx=(0, theme.px(10)))
        self._progress_label = tk.Label(
            progress_row, text="就绪", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10), width=26, anchor="e"
        )
        self._progress_label.pack(side="right")

        buttons = tk.Frame(card.body, bg=theme.WHITE)
        buttons.pack(fill="x")
        self._download_button = tb.Button(
            buttons,
            text="下载所选版本",
            bootstyle="primary",
            command=self.start_download,
            cursor="hand2",
            width=13,
            state="disabled",
        )
        self._download_button.pack(side="left")
        self._cancel_button = tb.Button(
            buttons,
            text="取消下载",
            bootstyle="secondary-outline",
            command=self.cancel_download,
            cursor="hand2",
            width=9,
            state="disabled",
        )
        self._cancel_button.pack(side="left", padx=(theme.px(8), 0))
        tb.Button(
            buttons,
            text="打开下载目录",
            bootstyle="secondary-outline",
            command=self.open_download_dir,
            cursor="hand2",
            width=11,
        ).pack(side="right")
        tb.Button(
            buttons,
            text="选择下载目录",
            bootstyle="secondary-outline",
            command=self.choose_download_dir,
            cursor="hand2",
            width=11,
        ).pack(side="right", padx=(0, theme.px(8)))

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded_once and not self._loading:
            self.load_versions()

    def on_close(self) -> None:
        self.cancel_download()
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 列表加载
    # ------------------------------------------------------------------
    def load_versions(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._hide_error()
        self._count_label.configure(text="正在拉取版本列表…")
        self.set_status("正在从希沃官方源拉取版本列表…", "primary")
        common.run_async(
            self,
            lambda: (self._client.fetch_versions(), self._client.ssl_warning),
            on_success=self._apply_versions,
            on_error=self._load_error,
            name="versions-fetch",
        )

    def _apply_versions(self, result: tuple[list[downloader.SoftVersion], str]) -> None:
        versions, ssl_warning = result
        self._loading = False
        self._loaded_once = True
        self._versions = versions
        self._refresh_table()
        if ssl_warning:
            self._show_error(ssl_warning)
        self._log_status(f"版本列表加载完成：{len(versions)} 个 Windows 版本")
        self.set_status(f"已加载 {len(versions)} 个历史版本", "success", 4000)

    def _load_error(self, exc: BaseException) -> None:
        self._loading = False
        message = str(exc)
        self._show_error(f"拉取版本列表失败：{message}（请检查网络后点击「重试」）")
        self._count_label.configure(text="加载失败")
        self.set_status(f"版本列表加载失败：{message}", "error", 6000)

    def _show_error(self, message: str) -> None:
        self._error_label.configure(text=message)
        if not self._error_banner.winfo_manager():
            self._error_banner.pack(fill="x", pady=(0, theme.px(8)), before=self._tree.master)

    def _hide_error(self) -> None:
        if self._error_banner.winfo_manager():
            self._error_banner.pack_forget()

    def _log_status(self, message: str) -> None:
        """下载页没有独立日志框，状态信息统一显示在窗口状态栏与进度标签。"""
        log.info("%s", message)

    # ------------------------------------------------------------------
    # 表格 / 搜索
    # ------------------------------------------------------------------
    def _schedule_filter(self) -> None:
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except tk.TclError:
                pass
        try:
            self._search_job = self.after(250, self._refresh_table)
        except tk.TclError:
            self._search_job = None

    def _on_search_changed(self, _event=None) -> None:
        self._schedule_filter()

    def _refresh_table(self) -> None:
        self._search_job = None
        keyword = self._search_var.get().strip().lower()
        self._filtered = [
            version
            for version in self._versions
            if not keyword or keyword in version.version.lower() or keyword in version.name.lower()
        ]
        # 清空并重建
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._row_map.clear()
        self._row_status.clear()
        for version in self._filtered:
            iid = self._tree.insert("", "end", values=self._row_values(version))
            self._row_map[iid] = version
            self._row_status[iid] = "未下载"
        total = len(self._versions)
        if total:
            self._count_label.configure(text=f"显示 {len(self._filtered)} / {total} 个 Windows 版本")
        else:
            self._count_label.configure(text="暂无版本数据")
        self._update_download_button()

    @staticmethod
    def _row_values(version: downloader.SoftVersion) -> tuple:
        return (version.version or "-", version.size_text, version.publish_text, "未下载")

    def _set_row_status(self, iid: str, status: str, tag: str = "") -> None:
        if iid not in self._row_map:
            return
        try:
            self._tree.set(iid, "status", status)
            if tag:
                self._tree.item(iid, tags=(tag,))
        except tk.TclError:
            pass
        self._row_status[iid] = status

    def _on_select(self, _event=None) -> None:
        version = self._selected_version()
        if version is None:
            self._selected_label.configure(text="未选择版本")
        else:
            self._selected_label.configure(
                text=f"已选择：{version.version}（{version.size_text} · {version.publish_text}）"
            )
        self._update_download_button()

    def _selected_version(self) -> downloader.SoftVersion | None:
        selection = self._tree.selection()
        if not selection:
            return None
        return self._row_map.get(selection[0])

    def _update_download_button(self) -> None:
        enabled = bool(self._tree.selection()) and not self._downloading and not self._loading
        try:
            self._download_button.configure(state="normal" if enabled else "disabled")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 下载
    # ------------------------------------------------------------------
    def start_download(self) -> None:
        if self._downloading:
            return
        version = self._selected_version()
        if version is None:
            common.show_warning(self, "未选择版本", "请先在列表中选择要下载的版本。")
            return
        if not version.download_url:
            common.show_warning(self, "下载地址缺失", "该版本没有可用的下载地址，请刷新列表后重试。")
            return
        try:
            self._download_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            common.show_error(self, "无法创建下载目录", f"{self._download_dir}\n\n{exc}")
            return
        target = self._download_dir / version.filename
        if target.exists():
            overwrite = common.ask_yes_no(
                self,
                "文件已存在",
                f"文件已存在：\n{target}\n\n是否删除后重新下载？",
            )
            if not overwrite:
                self._set_row_status(self._selected_iid(), "已下载", "done")
                self.set_status("文件已存在，未重新下载", "info", 4000)
                return
            try:
                target.unlink()
            except OSError as exc:
                common.show_error(self, "无法覆盖文件", f"{target}\n\n{exc}")
                return

        iid = self._selected_iid()
        self._downloading = True
        self._cancel_event = threading.Event()
        self._download_button.configure(state="disabled")
        self._cancel_button.configure(state="normal")
        self._progress.configure(value=0)
        self._progress_label.configure(text="开始下载…", fg=theme.MUTED)
        self._set_row_status(iid, "下载中 0%", "downloading")
        self.set_status(f"正在下载 {version.version}…", "primary")
        target_dir = self._download_dir
        cancel_event = self._cancel_event

        def _on_progress(downloaded: int, total: int | None, speed: float) -> None:
            common.post_ui(self, lambda: self._update_progress(iid, downloaded, total, speed))

        def _work():
            return downloader.download_file(
                version.download_url,
                target,
                on_progress=_on_progress,
                cancel_event=cancel_event,
                timeout=30,
            )

        def _done(result: downloader.DownloadResult) -> None:
            self._downloading = False
            try:
                self._cancel_button.configure(state="disabled")
            except tk.TclError:
                pass
            self._cancel_event = None
            if result.cancelled:
                self._set_row_status(iid, "已取消")
                self._progress_label.configure(text="已取消", fg=theme.MUTED)
                self.set_status("下载已取消（已保留断点，可重新下载续传）", "warning", 5000)
                self._update_download_button()
                return
            if result.ok:
                self._set_row_status(iid, "已下载", "done")
                self._progress.configure(value=100)
                self._progress_label.configure(text=f"完成 · {downloader.format_size(result.total_bytes)}", fg=theme.SUCCESS)
                self.set_status(f"下载完成：{result.path}", "success", 6000)
                self._update_download_button()
            else:
                failed = result.total_bytes == 0 and "中断" in result.message
                self._set_row_status(iid, "下载失败", "failed" if not result.path else "未完成")
                self._progress_label.configure(text="下载失败", fg=theme.DANGER)
                common.show_error(self, "下载失败", result.message)
                self.set_status(f"下载失败：{result.message}", "error", 6000)
                self._update_download_button()

        def _failed(exc: BaseException) -> None:
            self._downloading = False
            self._cancel_event = None
            try:
                self._cancel_button.configure(state="disabled")
            except tk.TclError:
                pass
            self._set_row_status(iid, "下载失败", "failed")
            self._progress_label.configure(text="下载失败", fg=theme.DANGER)
            common.show_error(self, "下载失败", f"下载过程发生异常：{exc}")
            self.set_status(f"下载失败：{exc}", "error", 6000)
            self._update_download_button()

        self._target_dir = target_dir
        common.run_async(self, _work, on_success=_done, on_error=_failed, name="version-download")

    def _selected_iid(self) -> str:
        selection = self._tree.selection()
        return selection[0] if selection else ""

    def _update_progress(self, iid: str, downloaded: int, total: int | None, speed: float) -> None:
        if not self._downloading:
            return
        if total:
            percent = min(100.0, downloaded * 100.0 / total)
            self._progress.configure(value=percent)
            text = f"{percent:.1f}% · {downloader.format_size(speed)}/s"
            self._set_row_status(iid, f"下载中 {percent:.0f}%", "downloading")
        else:
            self._progress.configure(value=0)
            text = f"{downloader.format_size(downloaded)} · {downloader.format_size(speed)}/s"
            self._set_row_status(iid, "下载中", "downloading")
        self._progress_label.configure(text=text)

    def cancel_download(self) -> None:
        if self._downloading and self._cancel_event is not None:
            self._cancel_event.set()
            try:
                self._cancel_button.configure(state="disabled")
            except tk.TclError:
                pass
            self._progress_label.configure(text="正在取消…")
            self.set_status("正在取消下载…", "warning")

    def choose_download_dir(self) -> None:
        selected = common.ask_directory(self, "选择历史版本下载目录", str(self._download_dir))
        if not selected:
            return
        self._download_dir = Path(selected)
        try:
            settings.set("download_dir", str(self._download_dir))
        except Exception:  # noqa: BLE001
            pass
        self._dir_label.configure(text=f"下载目录：{self._download_dir}")
        self.set_status(f"下载目录已设置为：{self._download_dir}", "success", 4000)

    def open_download_dir(self) -> None:
        try:
            self._download_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            common.show_error(self, "无法创建目录", str(exc))
            return
        ok, error = sysinfo.open_path(self._download_dir)
        if not ok:
            common.show_error(self, "打开目录失败", error)
