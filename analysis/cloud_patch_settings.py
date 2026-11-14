import io

p = r'D:\开发\SeewoCamera\InspireCameraTools\app\settings_page.py'
s = io.open(p, encoding='utf-8').read()

# imports
s = s.replace('''import tkinter as tk

import ttkbootstrap as tb

from core import settings, sysinfo''','''import threading
import tkinter as tk

import ttkbootstrap as tb

from core import cloud, settings, sysinfo''')

# build_body 增加云服务卡片
s = s.replace('''        self._build_about_card(content)
        self._build_disclaimer_card(content)''','''        self._build_about_card(content)
        self._build_cloud_card(content)
        self._build_disclaimer_card(content)''')

# 关于卡片里的过时说明改为云服务说明
s = s.replace('''            text="程序本身不联网检查版本，可在「历史版本下载」页查看官方版本列表。",''','''            text="版本检查/公告走「亿方智云」接口，可在下方云服务卡片中手动检查更新。",''')

# 在免责声明卡片之前插入云服务卡片构建方法
anchor = '''    # ---------- 免责声明 ----------'''
cloud_card = '''    # ---------- 亿方智云（更新与公告） ----------
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
            ("report", "匿名统计"),
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
        self._report_var = tk.BooleanVar(value=bool(settings.get("cloud_report_enabled", True)))
        tb.Checkbutton(
            controls,
            text="参与匿名统计（仅设备随机标识 + 系统信息）",
            variable=self._report_var,
            bootstyle="round-toggle",
            command=self._on_report_toggled,
            cursor="hand2",
        ).pack(side="left", padx=(theme.px(16), 0))
        self._cloud_hint = tk.Label(
            card.body,
            text=f"接口：{cloud.BASE_URL}（slug={cloud.APP_SLUG}）· 免登录、无个人信息；失败自动忽略，不影响使用。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            justify="left",
            wraplength=theme.px(930),
        )
        self._cloud_hint.pack(fill="x", pady=(theme.px(6), 0))
        self._refresh_cloud_card()

    def _refresh_cloud_card(self) -> None:
        try:
            status = cloud.cloud_status()
            key = str(status.get("device_key") or "")
            masked = key[:6] + "…" + key[-4:] if len(key) > 12 else (key or "—")
            values = {
                "current": settings.APP_VERSION,
                "report": "已开启" if status.get("report_enabled") else "已关闭",
                "device": masked,
            }
            for name, text in values.items():
                self._cloud_values[name].configure(text=text)
            if "latest" not in getattr(self, "_cloud_latest_cache", {}):
                self._cloud_values["latest"].configure(text="点「检查更新」获取")
        except Exception:  # noqa: BLE001
            pass

    def _on_report_toggled(self) -> None:
        enabled = bool(self._report_var.get())
        try:
            settings.set("cloud_report_enabled", enabled)
        except Exception:  # noqa: BLE001
            pass
        self._refresh_cloud_card()
        self.set_status("已开启匿名统计" if enabled else "已关闭匿名统计", "info", 2500)

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
                            f"当前已是最新版本 v{settings.APP_VERSION}。\\n"
                            "（如果云端还没有发布版本记录，也会显示为已是最新。）",
                        )

            common.post_ui(self, _report)

        threading.Thread(target=_worker, name="cloud-update-check", daemon=True).start()

    # ---------- 免责声明 ----------'''
s = s.replace(anchor, cloud_card, 1)

# on_show 时刷新云卡片
s = s.replace('''    def on_show(self) -> None:
        self._refresh_system_info()''','''    def on_show(self) -> None:
        self._refresh_system_info()
        self._refresh_cloud_card()''')

io.open(p, 'w', encoding='utf-8').write(s)
print('settings page cloud card patched')
