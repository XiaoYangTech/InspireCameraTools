"""设置与关于页：安装目录、数据/日志目录、外观与系统信息、版本与免责声明。"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path

import ttkbootstrap as tb

from core import cloud, settings, sysinfo

from . import common, theme
from .base_page import BasePage

log = logging.getLogger(__name__)

DISCLAIMER = (
    "1. 本工具是个人学习与研究用途的第三方辅助工具，与希沃（CVTE）官方无关，未获得官方授权。\n"
    "2. 「一键补丁」通过字节级修改 EasiCamera 程序文件实现功能调整，存在导致程序异常的风险；"
    "应用前请自行备份原始安装包/文件，并承担使用风险。\n"
    "3. 官方升级会覆盖补丁，升级后需要重新检测与应用；请遵守软件许可协议与当地法律法规。\n"
    "4. 历史版本下载仅展示官方公开接口提供的下载链接，安装包版权归原厂商所有。\n"
    "5. 「破坏自动更新」「一键相机」等功能可能影响软件正常行为，请在了解后果的前提下使用。\n"
    "6. 使用本工具造成的一切直接或间接损失，作者不承担任何责任。"
)


class SettingsPage(BasePage):
    """设置与关于页面。"""

    title = "设置与关于"
    subtitle = "安装目录、数据与日志目录、系统信息、版本与免责声明"
    icon = "settings"

    def __init__(self, master: tk.Misc, app) -> None:
        self._install_dirs: list[str] = []
        self._detecting = False
        super().__init__(master, app)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_body(self) -> None:
        self.add_header_button("打开日志目录", self.open_logs_dir, bootstyle="secondary-outline")
        scroll = common.ScrollFrame(self.body, bg=theme.PAGE_BG)
        scroll.pack(fill="both", expand=True)
        content = scroll.inner
        self._install_dirs = sysinfo.find_easicamera_dirs()
        self._build_install_card(content)
        self._build_dirs_card(content)
        self._build_system_card(content)
        self._build_about_card(content)
        self._build_cloud_card(content)
        self._build_disclaimer_card(content)
        tk.Frame(content, bg=theme.PAGE_BG, height=theme.px(8)).pack()

    # ---------- 安装目录 ----------
    def _build_install_card(self, parent: tk.Misc) -> None:
        card = common.Card(
            parent,
            title="EasiCamera 安装目录",
            subtitle="一键补丁页会自动使用该目录；留空则每次自动探测",
            icon="patch",
        )
        card.pack(fill="x", pady=(0, theme.px(12)))
        row = tk.Frame(card.body, bg=theme.WHITE)
        row.pack(fill="x")
        self._dir_var = tk.StringVar(value=str(settings.get("install_dir") or ""))
        self._dir_entry = tb.Entry(row, textvariable=self._dir_var, bootstyle="secondary")
        self._dir_entry.pack(side="left", fill="x", expand=True, padx=(0, theme.px(8)))
        tb.Button(
            row, text="自动探测", bootstyle="secondary-outline", command=self._detect_dirs, cursor="hand2", width=8
        ).pack(side="left", padx=(0, theme.px(6)))
        tb.Button(row, text="浏览…", bootstyle="secondary-outline", command=self._browse_dir, cursor="hand2", width=7).pack(
            side="left", padx=(0, theme.px(6))
        )
        tb.Button(row, text="保存", bootstyle="primary", command=self._save_install_dir, cursor="hand2", width=6).pack(
            side="left"
        )
        self._detected_label = tk.Label(
            card.body,
            text="尚未探测",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(900),
        )
        self._detected_label.pack(fill="x", pady=(theme.px(8), 0))
        if self._install_dirs:
            self._detected_label.configure(
                text="已探测到：" + "；".join(self._install_dirs),
                fg=theme.TEXT,
            )
        else:
            self._detected_label.configure(
                text="尚未探测到 EasiCamera 安装目录，可点击「自动探测」或「浏览…」手动指定。",
                fg=theme.MUTED,
            )

    # ---------- 目录 ----------
    def _build_dirs_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="数据与日志目录", subtitle="排查问题时可将日志文件附给开发者", icon="download")
        card.pack(fill="x", pady=(0, theme.px(12)))
        rows = [
            ("数据目录", str(settings.app_data_dir()), self.open_data_dir),
            ("日志目录", str(settings.logs_dir()), self.open_logs_dir),
            ("日志文件", str(settings.logs_dir() / "app.log"), self.open_log_file),
            ("下载目录", str(settings.default_download_dir()), self.open_download_dir),
        ]
        for label_text, path_text, command in rows:
            row = tk.Frame(card.body, bg=theme.WHITE)
            row.pack(fill="x", pady=(0, theme.px(6)))
            tk.Label(row, text=label_text, bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10), width=8, anchor="w").pack(
                side="left"
            )
            tk.Label(
                row,
                text=path_text,
                bg=theme.WHITE,
                fg=theme.TEXT,
                font=theme.font(10),
                anchor="w",
                wraplength=theme.px(760),
            ).pack(side="left", fill="x", expand=True)
            tb.Button(row, text="打开", bootstyle="link", command=command, cursor="hand2", width=6).pack(side="right")

    # ---------- 系统信息 ----------
    def _build_system_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="外观与系统信息", subtitle="主题与缩放遵循高 DPI 适配设置", icon="settings")
        card.pack(fill="x", pady=(0, theme.px(12)))
        grid = tk.Frame(card.body, bg=theme.WHITE)
        grid.pack(fill="x")
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1, uniform="sys")
        self._system_values: dict[str, tk.Label] = {}
        items = [
            ("theme", "界面主题"),
            ("scale", "DPI 缩放"),
            ("system", "Windows 版本"),
            ("admin", "运行权限"),
            ("python", "Python / 架构"),
            ("mode", "运行模式"),
            ("camera", "展台连接"),
            ("engine", "补丁引擎"),
        ]
        for index, (key, label_text) in enumerate(items):
            row, col = divmod(index, 2)
            cell = tk.Frame(grid, bg=theme.WHITE)
            cell.grid(row=row, column=col, sticky="w", padx=(0, theme.px(20)), pady=theme.px(4))
            tk.Label(cell, text=label_text, bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(anchor="w")
            value = tk.Label(cell, text="—", bg=theme.WHITE, fg=theme.TEXT, font=theme.font(11, "bold"), anchor="w")
            value.pack(anchor="w")
            self._system_values[key] = value

    # ---------- 关于 ----------
    def _build_about_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="关于", icon="settings")
        card.pack(fill="x", pady=(0, theme.px(12)))
        top = tk.Frame(card.body, bg=theme.WHITE)
        top.pack(fill="x")
        tk.Label(top, image=theme.load_icon("logo", theme.px(56), master=self), bg=theme.WHITE).pack(side="left")
        text_box = tk.Frame(top, bg=theme.WHITE)
        text_box.pack(side="left", padx=(theme.px(14), 0))
        tk.Label(
            text_box, text="亿方展台管家", bg=theme.WHITE, fg=theme.TEXT, font=theme.font(16, "bold"), anchor="w"
        ).pack(anchor="w")
        tk.Label(
            text_box,
            text=f"InspireCameraTools v{settings.APP_VERSION} · 希沃视频展台辅助工具",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            text_box,
            text="提供一键补丁、HID 灯控调试、历史版本下载、自动更新防护与一键相机等功能。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        buttons = tk.Frame(card.body, bg=theme.WHITE)
        buttons.pack(fill="x", pady=(theme.px(12), 0))
        tb.Button(
            buttons,
            text="打开希沃官网（获取最新版 EasiCamera）",
            bootstyle="primary-outline",
            command=self.open_seewo_site,
            cursor="hand2",
        ).pack(side="left")
        tb.Button(
            buttons,
            text="打开程序所在目录",
            bootstyle="secondary-outline",
            command=self.open_app_dir,
            cursor="hand2",
        ).pack(side="left", padx=(theme.px(8), 0))
        tk.Label(
            buttons,
            text="版本检查/公告走「亿方智云」接口，可在下方云服务卡片中手动检查更新。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(9),
        ).pack(side="left", padx=(theme.px(12), 0))

    # ---------- 亿方智云（更新与公告） ----------
    def _build_cloud_card(self, parent: tk.Misc) -> None:
        card = common.Card(
            parent,
            title="亿方智云（更新与公告）",
            subtitle="匿名统计、启动公告弹窗、手动检查更新（不做自动下载/安装）",
            icon="download",
        )
        card.pack(fill="x", pady=(0, theme.px(12)))
        grid = tk.Frame(card.body, bg=theme.WHITE)
        grid.pack(fill="x")
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1, uniform="cloud")
        self._cloud_values: dict[str, tk.Label] = {}
        items = [
            ("current", "当前版本"),
            ("latest", "云端最新版本"),
            ("device", "匿名设备标识"),
        ]
        for index, (key, label_text) in enumerate(items):
            row, col = divmod(index, 2)
            cell = tk.Frame(grid, bg=theme.WHITE)
            cell.grid(row=row, column=col, sticky="w", padx=(0, theme.px(20)), pady=theme.px(4))
            tk.Label(cell, text=label_text, bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(anchor="w")
            value = tk.Label(cell, text="—", bg=theme.WHITE, fg=theme.TEXT, font=theme.font(11, "bold"), anchor="w")
            value.pack(anchor="w")
            self._cloud_values[key] = value

        controls = tk.Frame(card.body, bg=theme.WHITE)
        controls.pack(fill="x", pady=(theme.px(10), 0))
        self._check_update_button = tb.Button(
            controls,
            text="检查更新",
            bootstyle="primary-outline",
            command=self._check_update_clicked,
            cursor="hand2",
        )
        self._check_update_button.pack(side="left")
        tk.Label(
            card.body,
            text="匿名统计与公告弹窗均由亿方智云提供：仅上报随机设备标识与系统信息，不含账号与个人信息；网络异常时自动忽略，不影响使用。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            justify="left",
            wraplength=theme.px(930),
        ).pack(fill="x", pady=(theme.px(8), 0))
        self._refresh_cloud_card()

    def _refresh_cloud_card(self) -> None:
        try:
            status = cloud.cloud_status()
            key = str(status.get("device_key") or "")
            masked = key[:6] + "…" + key[-4:] if len(key) > 12 else (key or "—")
            values = {
                "current": settings.APP_VERSION,
                "device": masked,
            }
            for name, text in values.items():
                self._cloud_values[name].configure(text=text)
            if "latest" not in getattr(self, "_cloud_latest_cache", {}):
                self._cloud_values["latest"].configure(text="点「检查更新」获取")
        except Exception:  # noqa: BLE001
            pass

    def _check_update_clicked(self) -> None:
        """手动检查更新：只提示并打开下载页，不做自动下载/安装。"""
        try:
            self._check_update_button.configure(state="disabled")
        except tk.TclError:
            pass

        def _worker() -> None:
            info = None
            error = ""
            try:
                info = cloud.check_update()
            except Exception as exc:  # noqa: BLE001
                error = f"{exc.__class__.__name__}: {exc}"

            def _report() -> None:
                try:
                    self._check_update_button.configure(state="normal")
                except tk.TclError:
                    pass
                if info:
                    latest = str(info.get("latest_version") or "")
                    try:
                        self._cloud_values["latest"].configure(
                            text=f"{latest}（{info.get('latest_release_date') or '日期未知'}）", fg=theme.SUCCESS
                        )
                    except tk.TclError:
                        pass
                    self.app._handle_cloud_update(info)
                else:
                    try:
                        self._cloud_values["latest"].configure(
                            text=f"{settings.APP_VERSION}（已是最新）", fg=theme.MUTED
                        )
                    except tk.TclError:
                        pass
                    if error:
                        common.show_warning(self, "检查更新失败", f"暂时无法连接亿方智云：{error}")
                    else:
                        common.show_info(
                            self,
                            "检查更新",
                            f"当前已是最新版本 v{settings.APP_VERSION}。\n"
                            "（如果云端还没有发布版本记录，也会显示为已是最新。）",
                        )

            common.post_ui(self, _report)

        threading.Thread(target=_worker, name="cloud-update-check", daemon=True).start()

    # ---------- 免责声明 ----------
    def _build_disclaimer_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="免责声明", icon="autoupdate")
        card.pack(fill="x")
        tk.Label(
            card.body,
            text=DISCLAIMER,
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(930),
        ).pack(fill="x")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._refresh_system_info()
        self._refresh_cloud_card()

    def _refresh_system_info(self) -> None:
        try:
            scale = theme.ui_scale()
            tk_scaling = self.winfo_toplevel().tk.call("tk", "scaling")
            values = {
                "theme": "bootstrap-light",
                "scale": f"{scale * 100:.0f}%（Tk scaling {float(tk_scaling):.3f}）",
                "system": sysinfo.windows_version_text(),
                "admin": "管理员" if sysinfo.is_admin() else "普通用户",
                "python": f"Python {sysinfo.python_arch()}",
                "mode": "打包运行" if getattr(__import__("sys"), "frozen", False) else "源码运行",
            }
            for key, text in values.items():
                self._system_values[key].configure(text=text)
            status = sysinfo.detect_camera_status()
            self._system_values["camera"].configure(
                text=f"{status.model}（{status.vid_pid_text}）" if status.connected else "未连接",
                fg=theme.SUCCESS if status.connected else theme.MUTED,
            )
            try:
                import core.patch_engine as engine  # noqa: F401

                self._system_values["engine"].configure(text="已就绪", fg=theme.SUCCESS)
            except Exception:  # noqa: BLE001
                self._system_values["engine"].configure(text="未就绪", fg=theme.WARNING)
        except Exception:  # noqa: BLE001 - 系统信息展示失败不影响页面
            log.exception("刷新系统信息失败")

    # ------------------------------------------------------------------
    # 安装目录
    # ------------------------------------------------------------------
    def _detect_dirs(self) -> None:
        if self._detecting:
            return
        self._detecting = True
        self._detected_label.configure(text="正在探测 EasiCamera 安装目录…", fg=theme.MUTED)
        common.run_async(
            self,
            sysinfo.find_easicamera_dirs,
            on_success=self._apply_detected_dirs,
            on_error=lambda exc: self._detected_label.configure(text=f"探测失败：{exc}", fg=theme.DANGER),
            name="settings-detect",
        )

    def _apply_detected_dirs(self, dirs: list[str]) -> None:
        self._detecting = False
        self._install_dirs = dirs
        if dirs:
            if not self._dir_var.get().strip():
                self._dir_var.set(dirs[0])
            self._detected_label.configure(text="已探测到：" + "；".join(dirs), fg=theme.TEXT)
        else:
            self._detected_label.configure(
                text="未探测到 EasiCamera 安装目录（可手动选择 EasiCamera 的 Main 目录）", fg=theme.WARNING
            )

    def _browse_dir(self) -> None:
        initial = self._dir_var.get().strip() or str(Path.home())
        selected = common.ask_directory(self, "选择 EasiCamera 的 Main 目录", initial)
        if selected:
            self._dir_var.set(selected)
            self._save_install_dir()

    def _save_install_dir(self) -> None:
        value = self._dir_var.get().strip()
        if value and not Path(value).is_dir():
            common.show_warning(self, "目录不存在", f"目录不存在：\n{value}\n\n请确认选择的是 EasiCamera 的 Main 目录。")
            return
        try:
            settings.set("install_dir", value)
        except Exception as exc:  # noqa: BLE001
            common.show_error(self, "保存失败", str(exc))
            return
        self.set_status("安装目录已保存" if value else "已清空安装目录（下次自动探测）", "success", 4000)

    # ------------------------------------------------------------------
    # 打开目录 / 链接
    # ------------------------------------------------------------------
    def _open_path(self, path: str | Path) -> None:
        ok, error = sysinfo.open_path(path)
        if not ok:
            common.show_error(self, "打开失败", error)

    def open_data_dir(self) -> None:
        self._open_path(settings.app_data_dir())

    def open_logs_dir(self) -> None:
        self._open_path(settings.logs_dir())

    def open_log_file(self) -> None:
        path = settings.logs_dir() / "app.log"
        if not path.is_file():
            common.show_info(self, "日志文件不存在", f"当前还没有日志文件：\n{path}")
            return
        self._open_path(path)

    def open_download_dir(self) -> None:
        path = settings.default_download_dir()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            common.show_error(self, "无法创建下载目录", str(exc))
            return
        self._open_path(path)

    def open_app_dir(self) -> None:
        self._open_path(theme.APP_DIR)

    def open_seewo_site(self) -> None:
        ok, error = sysinfo.open_url("https://e.seewo.com/")
        if not ok:
            common.show_error(self, "打开链接失败", error)
