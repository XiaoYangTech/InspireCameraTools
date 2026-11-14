"""一键相机页：按下展台机身补光灯按键 → 自动触发 EasiCamera 拍照。

原理：后台监听展台 HID 输入帧 ``BB CC 05``（机身补光灯按键通知）或 ``BB CC 02``
（灯状态变化），触发时**通过 UI Automation 调用 EasiCamera 的「拍照」按钮**
（``ECCommands.CaptureImage``，与按机身拍照键执行的同一命令），不发送键盘快捷键、
不写入 HID、不与希沃进程抢设备；也不再发送任何键盘快捷键。
无展台时允许开启，监听会等待设备接入。
"""

from __future__ import annotations

import logging
import threading
import time
import tkinter as tk

import ttkbootstrap as tb

from core import capture_trigger, hid, settings, startup

from . import common, theme
from .base_page import BasePage

log = logging.getLogger(__name__)

#: 触发一键相机的 HID 帧类型
TRIGGER_KINDS = ("led", "led_key")

INSTRUCTIONS = (
    "使用说明：\n"
    "1. 连接希沃展台，打开 EasiCamera 并进入拍照/展台界面（无需前台焦点，最小化也可尝试）；\n"
    "2. 打开下方「一键相机」开关（可同时开启开机自启，后台运行并自动监听）；\n"
    "3. 按下展台机身上的补光灯按键，程序会通过 UI 自动化点击 EasiCamera 的「拍照」按钮完成拍照。\n\n"
    "说明：\n"
    "· 触发的是 EasiCamera 自己的拍照命令（与机身拍照键最终执行的动作一致），不是键盘快捷键；\n"
    "· 期间若 EasiCamera 未运行或不在拍照界面，日志会提示「未找到 EasiCamera 窗口/拍照按钮」；\n"
    "· 同一按键 800ms 内只触发一次（防抖），避免连拍；\n"
    "· 找不到按钮时可点「检测拍照按钮」查看诊断信息，或确认 EasiCamera 处于拍照界面后重试。"
)


class CameraPage(BasePage):
    """一键相机页面。"""

    title = "一键相机"
    subtitle = "展台机身补光灯按键 → 自动触发 EasiCamera 拍照（UI 自动化，等效机身拍照键）"
    icon = "camera"

    def __init__(self, master: tk.Misc, app) -> None:
        self._monitor: hid.HidMonitor | None = None
        self._enabled = False
        self._syncing = False
        self._last_trigger = 0.0
        self._trigger_count = 0
        self._triggering = False
        self._debounce_ms = int(settings.get("camera_debounce_ms") or 800)
        super().__init__(master, app)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_body(self) -> None:
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(1, weight=1)
        self._build_switch_card()
        content = tk.Frame(self.body, bg=theme.PAGE_BG)
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=3, uniform="cam-cols")
        content.grid_columnconfigure(1, weight=2, uniform="cam-cols")
        content.grid_rowconfigure(0, weight=1)
        self._build_status_card(content)
        self._build_log_card(content)

    def _build_switch_card(self) -> None:
        card = common.Card(
            self.body,
            title="开关与目标按键",
            subtitle="设置会自动保存；开机自启通过 HKCU Run 注册，命令带 --background 参数",
            icon="camera",
        )
        card.grid(row=0, column=0, sticky="ew", pady=(0, theme.px(12)))

        switch_row = tk.Frame(card.body, bg=theme.WHITE)
        switch_row.pack(fill="x")
        self._enabled_var = tk.BooleanVar(value=False)
        self._switch = tb.Checkbutton(
            switch_row,
            text="一键相机",
            variable=self._enabled_var,
            bootstyle="round-toggle",
            command=self._on_switch_toggled,
            cursor="hand2",
        )
        self._switch.pack(side="left")
        self._switch_desc = tk.Label(
            switch_row,
            text="关闭状态",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
        )
        self._switch_desc.pack(side="left", padx=(theme.px(12), 0))
        self._run_badge = common.Badge(switch_row, text="已停止", kind="secondary")
        self._run_badge.pack(side="right")

        options = tk.Frame(card.body, bg=theme.WHITE)
        options.pack(fill="x", pady=(theme.px(14), 0))
        # 防抖
        tk.Label(options, text="防抖(ms)", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(6))
        )
        self._debounce_var = tk.IntVar(value=self._debounce_ms)
        debounce_spin = tb.Spinbox(
            options,
            from_=100,
            to=3000,
            increment=100,
            textvariable=self._debounce_var,
            width=6,
            bootstyle="secondary",
            command=self._on_debounce_changed,
        )
        debounce_spin.pack(side="left", padx=(0, theme.px(18)))
        debounce_spin.bind("<FocusOut>", lambda _e: self._on_debounce_changed())
        # 开机自启
        self._autostart_var = tk.BooleanVar(value=startup.is_autostart_enabled())
        self._autostart_switch = tb.Checkbutton(
            options,
            text="开机自启（后台运行）",
            variable=self._autostart_var,
            bootstyle="round-toggle",
            command=self._on_autostart_toggled,
            cursor="hand2",
        )
        self._autostart_switch.pack(side="left")
        self._probe_button = tb.Button(
            options,
            text="检测拍照按钮",
            bootstyle="outline-secondary",
            command=self._on_probe_click,
            cursor="hand2",
        )
        self._probe_button.pack(side="left", padx=(theme.px(18), 0))
        self._autostart_hint = tk.Label(
            card.body,
            text="",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            justify="left",
            wraplength=theme.px(940),
        )
        self._autostart_hint.pack(fill="x", pady=(theme.px(8), 0))
        self._refresh_autostart_hint()

    def _build_status_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="运行状态", subtitle="", icon="hid")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, theme.px(14)))

        grid = tk.Frame(card.body, bg=theme.WHITE)
        grid.pack(fill="x")
        self._status_values: dict[str, tk.Label | common.Badge] = {}
        items = [
            ("state", "运行状态"),
            ("connection", "展台连接"),
            ("trigger", "拍照触发方式"),
            ("count", "已触发次数"),
        ]
        for index, (key, label_text) in enumerate(items):
            row, col = divmod(index, 2)
            cell = tk.Frame(grid, bg=theme.WHITE)
            cell.grid(row=row, column=col, sticky="w", padx=(0, theme.px(20)), pady=theme.px(5))
            tk.Label(cell, text=label_text, bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(anchor="w")
            if key in ("state", "connection"):
                value_widget = common.Badge(cell, text="—", kind="secondary")
                value_widget.pack(anchor="w", pady=(theme.px(2), 0))
            else:
                value_widget = tk.Label(
                    cell, text="—", bg=theme.WHITE, fg=theme.TEXT, font=theme.font(12, "bold"), anchor="w"
                )
                value_widget.pack(anchor="w", pady=(theme.px(2), 0))
            self._status_values[key] = value_widget

        tk.Frame(card.body, bg=theme.BORDER, height=1).pack(fill="x", pady=theme.px(10))
        tk.Label(
            card.body,
            text=INSTRUCTIONS,
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(620),
        ).pack(fill="x")
        self._status_values["trigger"].configure(text="模拟机身拍照键（UIA）")

    def _build_log_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="监听日志", subtitle="HID 监听、拍照触发与诊断记录", icon="download")
        card.grid(row=0, column=1, sticky="nsew")
        if card.header_right is not None:
            tb.Button(
                card.header_right, text="清空", bootstyle="link", command=lambda: self._log.clear(), cursor="hand2"
            ).pack(side="right")
        self._log = common.LogText(card.body, height=20, max_lines=1500)
        self._log.pack(fill="both", expand=True)
        self._log.log("一键相机尚未开启。", "muted")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._run_badge.set("运行中" if self._enabled else "已停止", "success" if self._enabled else "secondary")
        self._autostart_var.set(startup.is_autostart_enabled())
        self._refresh_autostart_hint()

    def on_hide(self) -> None:
        # 页面隐藏时保持后台监听（关闭开关才会停止）
        pass

    def on_close(self) -> None:
        self._stop_monitor()
        try:
            self.app.set_camera_indicator(False)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 开关逻辑
    # ------------------------------------------------------------------
    def _on_switch_toggled(self) -> None:
        if self._syncing:
            return
        want_enabled = bool(self._enabled_var.get())
        if want_enabled:
            self.start_camera()
        else:
            self.stop_camera()

    def _set_switch(self, enabled: bool) -> None:
        self._syncing = True
        try:
            self._enabled_var.set(enabled)
        finally:
            self._syncing = False

    def start_camera(self, auto: bool = False) -> None:
        """开启一键相机（无展台时也允许开启，监听线程会等待设备接入）。"""
        if self._enabled and self._monitor is not None and self._monitor.running:
            self._set_switch(True)
            self._update_running_state(True)
            return
        monitor = self._ensure_monitor()
        monitor.heartbeat_reply = True
        monitor.start()
        self._enabled = True
        self._set_switch(True)
        try:
            settings.set("camera_enabled", True)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.app.set_camera_indicator(True)
        except Exception:  # noqa: BLE001
            pass
        self._update_running_state(True)
        if auto:
            self._log.log("检测到上次已开启一键相机，已自动恢复后台监听。", "primary")
        else:
            self._log.log("一键相机已开启，开始监听展台 HID 输入帧…", "primary")
        self._log.log(
            f"拍照触发：UI 自动化点击 EasiCamera「拍照」按钮（防抖 {self._debounce_ms} ms）",
            "info",
        )
        self.set_status("一键相机已开启", "success", 3000)

    def stop_camera(self) -> None:
        if not self._enabled and not (self._monitor and self._monitor.running):
            self._set_switch(False)
            return
        self._stop_monitor()
        self._enabled = False
        self._set_switch(False)
        try:
            settings.set("camera_enabled", False)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.app.set_camera_indicator(False)
        except Exception:  # noqa: BLE001
            pass
        self._update_running_state(False)
        self._log.log("一键相机已关闭，停止监听。", "muted")
        self.set_status("一键相机已关闭", "info", 3000)

    def _stop_monitor(self) -> None:
        if self._monitor is not None and self._monitor.running:
            self._monitor.stop(timeout=1.5)

    def _update_running_state(self, running: bool) -> None:
        try:
            self._run_badge.set("运行中" if running else "已停止", "success" if running else "secondary")
            self._status_values["state"].set("运行中" if running else "已停止", "success" if running else "secondary")
            self._switch_desc.configure(
                text="正在监听展台按键（页面可切换，后台继续工作）" if running else "关闭状态"
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 监听器
    # ------------------------------------------------------------------
    def _ensure_monitor(self) -> hid.HidMonitor:
        if self._monitor is None:
            self._monitor = hid.HidMonitor(
                on_frame=self._on_frame,
                on_log=self._on_log,
                on_connection=self._on_connection,
                heartbeat_reply=True,
            )
        return self._monitor

    def _on_log(self, message: str) -> None:
        self._ui(lambda: self._log.log(message, "info"))

    def _on_connection(self, connected: bool, devices: list[hid.HidDeviceInfo]) -> None:
        def _update() -> None:
            if connected:
                names = "、".join(device.model for device in devices[:2]) or "展台"
                self._status_values["connection"].set(f"已连接 · {names}", "success")
                self._log.log(f"展台已连接：{names}", "success")
            else:
                self._status_values["connection"].set("未连接（等待接入）", "warning")
                self._log.log("展台未连接，等待设备接入…", "warning")

        self._ui(_update)

    def _on_frame(self, frame: hid.FrameInfo) -> None:
        if frame.kind not in TRIGGER_KINDS:
            return
        self._ui(lambda: self._handle_trigger_frame(frame))

    def _handle_trigger_frame(self, frame: hid.FrameInfo) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        elapsed_ms = (now - self._last_trigger) * 1000.0
        if self._last_trigger and elapsed_ms < self._debounce_ms:
            self._log.log(
                f"检测到灯光按键变化帧，但距上次触发 {elapsed_ms:.0f}ms < 防抖 {self._debounce_ms}ms，已忽略",
                "muted",
            )
            return
        if self._triggering:
            self._log.log("上一次拍照触发尚未完成，本次忽略", "muted")
            return
        self._last_trigger = now
        self._triggering = True
        worker = threading.Thread(target=self._do_trigger, args=(frame,), name="capture-trigger", daemon=True)
        worker.start()

    def _do_trigger(self, frame: hid.FrameInfo) -> None:
        """后台线程：通过 UI 自动化触发 EasiCamera 拍照按钮。"""
        try:
            result = capture_trigger.trigger_capture()
        except capture_trigger.CaptureTriggerError as exc:
            result = capture_trigger.TriggerResult(ok=False, message=f"拍照触发助手不可用：{exc}")
        except Exception as exc:  # noqa: BLE001
            result = capture_trigger.TriggerResult(ok=False, message=f"拍照触发异常：{exc}")

        def _report() -> None:
            try:
                if result.ok:
                    self._trigger_count += 1
                    self._status_values["count"].configure(text=str(self._trigger_count))
                    name = (result.element or {}).get("name") or (result.element or {}).get("automationId") or "拍照按钮"
                    self._log.log(
                        f"检测到机身灯光按键（{frame.description}）→ 已点击 EasiCamera「{name}」"
                        f"（{result.method or 'UIA'}，第 {self._trigger_count} 次）",
                        "success",
                    )
                    self.set_status(f"已触发拍照（第 {self._trigger_count} 次）", "success", 2500)
                    return
                self._log.log(f"拍照触发失败：{result.message}", "error")
                self.set_status(f"拍照触发失败：{result.message}", "error", 4000)
            finally:
                self._triggering = False

        self._ui(_report)

    def _on_probe_click(self) -> None:
        """检测 EasiCamera 拍照按钮是否可被 UI 自动化定位（不实际点击）。"""
        self._log.log("正在检测 EasiCamera 拍照按钮…", "info")
        try:
            self._probe_button.configure(state="disabled")
        except tk.TclError:
            pass

        def _worker() -> None:
            try:
                data = capture_trigger.probe_capture_button()
            except Exception as exc:  # noqa: BLE001
                data = {"ok": False, "error": f"检测失败：{exc}"}

            def _report() -> None:
                try:
                    if data.get("ok"):
                        element = data.get("element") or {}
                        name = element.get("name") or element.get("automationId") or "（无名称）"
                        self._log.log(
                            f"已找到拍照按钮：{name}（type={element.get('type')}，"
                            f"automationId={element.get('automationId')}，method={data.get('method')}）",
                            "success",
                        )
                        self.set_status("拍照按钮检测成功", "success", 3000)
                    else:
                        self._log.log(f"未找到拍照按钮：{data.get('error')}", "warning")
                        self.set_status("未找到拍照按钮（详见日志）", "warning", 4000)
                finally:
                    try:
                        self._probe_button.configure(state="normal")
                    except tk.TclError:
                        pass

            self._ui(_report)

        threading.Thread(target=_worker, name="capture-probe", daemon=True).start()

    def _ui(self, func) -> None:
        common.post_ui(self, func)

    # ------------------------------------------------------------------
    # 设置项
    # ------------------------------------------------------------------
    def _on_debounce_changed(self) -> None:
        try:
            value = int(self._debounce_var.get())
        except (tk.TclError, ValueError):
            return
        value = max(100, min(3000, value))
        if value == self._debounce_ms:
            return
        self._debounce_ms = value
        self._debounce_var.set(value)
        try:
            settings.set("camera_debounce_ms", value)
        except Exception:  # noqa: BLE001
            pass

    def _on_autostart_toggled(self) -> None:
        want = bool(self._autostart_var.get())
        ok, message = startup.set_autostart(want)
        if ok:
            try:
                settings.set("camera_autostart", want)
            except Exception:  # noqa: BLE001
                pass
            self._log.log(message, "success")
            self.set_status(message, "success", 4000)
        else:
            self._autostart_var.set(startup.is_autostart_enabled())
            self._log.log(f"设置开机自启失败：{message}", "error")
            common.show_error(self, "设置开机自启失败", message)
        self._refresh_autostart_hint()

    def _refresh_autostart_hint(self) -> None:
        try:
            registered = startup.is_autostart_enabled()
            if not startup.is_supported():
                text = "当前系统不支持注册表开机自启。"
            elif registered:
                text = f"已注册开机自启：{startup.get_registered_command()}"
            else:
                text = "未注册开机自启；开启后程序会在登录 Windows 时以后台模式启动，并自动恢复一键相机监听。"
            self._autostart_hint.configure(text=text)
        except tk.TclError:
            pass
