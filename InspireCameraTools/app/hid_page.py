"""状态调试页：展台 HID 设备枚举、灯控、触摸灯、MCU 查询与原始帧监听。"""

from __future__ import annotations

import logging
import tkinter as tk

import ttkbootstrap as tb

from core import hid, settings

from . import common, theme
from .base_page import BasePage

log = logging.getLogger(__name__)

LEVEL_CHOICES = ["默认(50)", "25", "50", "70"]
LEVEL_VALUES = [0, 1, 2, 3]
FRAME_KIND_LEVEL = {
    "led": "success",
    "led_key": "success",
    "key": "warning",
    "touch": "primary",
    "heartbeat": "muted",
    "mcu": "primary",
    "cover": "primary",
    "mode": "muted",
    "other": "muted",
}


class HidPage(BasePage):
    """状态调试页面。"""

    title = "状态调试"
    subtitle = "枚举展台 HID 接口，控制补光灯/触摸灯，监听机身按键与原始协议帧"
    icon = "hid"

    def __init__(self, master: tk.Misc, app) -> None:
        self._devices: list[hid.HidDeviceInfo] = []
        self._device_map: dict[str, hid.HidDeviceInfo] = {}
        self._busy = False
        self._monitor: hid.HidMonitor | None = None
        self._frame_count = 0
        super().__init__(master, app)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_body(self) -> None:
        self.add_header_button("刷新设备", self.refresh_devices, bootstyle="secondary-outline")
        self.body.grid_columnconfigure(0, weight=2, uniform="hid-cols")
        self.body.grid_columnconfigure(1, weight=3, uniform="hid-cols")
        self.body.grid_rowconfigure(0, weight=1)
        # 左侧设备/灯控卡片：高 DPI 下窗口较矮时可滚动，避免控件被裁切
        left_scroll = common.ScrollFrame(self.body, bg=theme.PAGE_BG, fill_height=True)
        left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, theme.px(14)))
        left = left_scroll.inner
        right = tk.Frame(self.body, bg=theme.PAGE_BG)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_device_card(left)
        self._build_control_card(left)
        self._build_listen_card(right)

    # ---------- 设备卡片 ----------
    def _build_device_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="展台设备", subtitle="按希沃 VID/PID 白名单枚举 HID 接口", icon="hid")
        card.pack(fill="x", pady=(0, theme.px(12)))
        row = tk.Frame(card.body, bg=theme.WHITE)
        row.pack(fill="x")
        self._device_var = tk.StringVar(value="未发现展台")
        self._device_combo = tb.Combobox(
            row,
            textvariable=self._device_var,
            values=[],
            state="disabled",
            bootstyle="secondary",
        )
        self._device_combo.pack(side="left", fill="x", expand=True, padx=(0, theme.px(8)))
        self._connection_badge = common.Badge(row, text="未连接", kind="secondary")
        self._connection_badge.pack(side="left")
        self._device_detail = tk.Label(
            card.body,
            text="未发现希沃展台 HID 接口（VID 1FF7 / 254A）。请确认展台已连接、并使用「刷新设备」。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(390),
        )
        self._device_detail.pack(fill="x", pady=(theme.px(8), 0))

    # ---------- 灯控卡片 ----------
    def _build_control_card(self, parent: tk.Misc) -> None:
        card = common.Card(
            parent,
            title="灯光控制",
            subtitle="命令通过展台控制口 HID 发送，设备无应答时可先关闭 EasiCamera",
            icon="patch",
        )
        card.pack(fill="both", expand=True)

        status_row = tk.Frame(card.body, bg=theme.WHITE)
        status_row.pack(fill="x", pady=(0, theme.px(10)))
        tk.Label(status_row, text="灯状态", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(8))
        )
        self._led_badge = common.Badge(status_row, text="未知", kind="secondary")
        self._led_badge.pack(side="left")
        self._led_detail = tk.Label(
            status_row, text="", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(9), anchor="w"
        )
        self._led_detail.pack(side="left", padx=(theme.px(8), 0))

        # 主补光灯
        self._section_label(card.body, "主补光灯")
        light_row = tk.Frame(card.body, bg=theme.WHITE)
        light_row.pack(fill="x", pady=(0, theme.px(12)))
        self._query_led_button = tb.Button(
            light_row, text="查询灯态", bootstyle="secondary-outline", command=self.query_led, cursor="hand2", width=9
        )
        self._query_led_button.pack(side="left", padx=(0, theme.px(6)))
        self._level_combo = tb.Combobox(
            light_row,
            values=LEVEL_CHOICES,
            state="readonly",
            width=8,
            bootstyle="secondary",
        )
        self._level_combo.current(0)
        self._level_combo.pack(side="left", padx=(0, theme.px(6)))
        self._on_button = tb.Button(
            light_row, text="开灯", bootstyle="primary", command=self.turn_on_light, cursor="hand2", width=7
        )
        self._on_button.pack(side="left", padx=(0, theme.px(6)))
        self._off_button = tb.Button(
            light_row, text="关灯", bootstyle="warning-outline", command=self.turn_off_light, cursor="hand2", width=7
        )
        self._off_button.pack(side="left")

        # 触摸灯
        self._section_label(card.body, "触摸指示灯")
        touch_row = tk.Frame(card.body, bg=theme.WHITE)
        touch_row.pack(fill="x", pady=(0, theme.px(12)))
        self._touch_on_button = tb.Button(
            touch_row, text="触摸灯开", bootstyle="secondary-outline", command=self.touch_on, cursor="hand2", width=9
        )
        self._touch_on_button.pack(side="left", padx=(0, theme.px(6)))
        self._touch_off_button = tb.Button(
            touch_row, text="触摸灯关", bootstyle="secondary-outline", command=self.touch_off, cursor="hand2", width=9
        )
        self._touch_off_button.pack(side="left", padx=(0, theme.px(6)))
        self._touch_flash_button = tb.Button(
            touch_row, text="闪烁", bootstyle="secondary-outline", command=self.touch_flash, cursor="hand2", width=6
        )
        self._touch_flash_button.pack(side="left", padx=(0, theme.px(6)))
        self._touch_query_button = tb.Button(
            touch_row, text="查询", bootstyle="secondary-outline", command=self.query_touch, cursor="hand2", width=6
        )
        self._touch_query_button.pack(side="left")

        # MCU
        self._section_label(card.body, "MCU 版本")
        mcu_row = tk.Frame(card.body, bg=theme.WHITE)
        mcu_row.pack(fill="x")
        self._mcu_button = tb.Button(
            mcu_row, text="查询 MCU 版本", bootstyle="secondary-outline", command=self.query_mcu, cursor="hand2", width=13
        )
        self._mcu_button.pack(side="left", padx=(0, theme.px(8)))
        self._mcu_value = tk.Label(
            mcu_row, text="—", bg=theme.WHITE, fg=theme.TEXT, font=theme.font(11, "bold"), anchor="w"
        )
        self._mcu_value.pack(side="left", fill="x", expand=True)

        self._light_buttons = [
            self._query_led_button,
            self._on_button,
            self._off_button,
            self._touch_on_button,
            self._touch_off_button,
            self._touch_flash_button,
            self._touch_query_button,
            self._mcu_button,
        ]
        self._set_light_controls_enabled(False)

    def _section_label(self, parent: tk.Misc, text: str) -> None:
        tk.Label(parent, text=text, bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10, "bold"), anchor="w").pack(
            fill="x", pady=(0, theme.px(4))
        )

    # ---------- 监听卡片 ----------
    def _build_listen_card(self, parent: tk.Misc) -> None:
        card = common.Card(
            parent,
            title="原始帧监听",
            subtitle="后台线程读取 HID 输入报告，自动应答设备心跳（BB CC 04 01）",
            icon="download",
        )
        card.pack(fill="both", expand=True)
        if card.header_right is not None:
            self._frames_label = tk.Label(
                card.header_right, text="已监听 0 帧", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(9)
            )
            self._frames_label.pack(side="right")
        toolbar = tk.Frame(card.body, bg=theme.WHITE)
        toolbar.pack(fill="x", pady=(0, theme.px(8)))
        self._start_button = tb.Button(
            toolbar, text="开始监听", bootstyle="primary", command=self.start_listening, cursor="hand2", width=9
        )
        self._start_button.pack(side="left", padx=(0, theme.px(6)))
        self._stop_button = tb.Button(
            toolbar,
            text="停止监听",
            bootstyle="secondary-outline",
            command=self.stop_listening,
            cursor="hand2",
            width=9,
            state="disabled",
        )
        self._stop_button.pack(side="left", padx=(0, theme.px(6)))
        tb.Button(toolbar, text="清空", bootstyle="link", command=self.clear_log, cursor="hand2").pack(
            side="left", padx=(0, theme.px(10))
        )
        self._heartbeat_var = tk.BooleanVar(value=bool(settings.get("hid_heartbeat_reply", True)))
        tb.Checkbutton(
            toolbar,
            text="自动应答心跳",
            variable=self._heartbeat_var,
            bootstyle="round-toggle",
            command=self._on_heartbeat_toggle,
            cursor="hand2",
        ).pack(side="left")
        self._last_key_label = tk.Label(
            toolbar, text="最近按键：—", bg=theme.WHITE, fg=theme.PRIMARY_DARK, font=theme.font(10, "bold")
        )
        self._last_key_label.pack(side="right")

        self._log_box = common.LogText(card.body, height=18, max_lines=3000)
        self._log_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._devices:
            self.refresh_devices()

    def on_close(self) -> None:
        self.stop_listening(silent=True)

    # ------------------------------------------------------------------
    # 设备
    # ------------------------------------------------------------------
    def refresh_devices(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._connection_badge.set("检测中…", "info")
        self.set_status("正在枚举 HID 设备…", "primary")
        common.run_async(
            self,
            lambda: hid.find_seewo_devices(),
            on_success=self._apply_devices,
            on_error=self._device_error,
            name="hid-enumerate",
        )

    def _apply_devices(self, devices: list[hid.HidDeviceInfo]) -> None:
        self._busy = False
        self._devices = devices
        self._device_map = {}
        values = []
        for info in devices:
            text = f"{info.display_name}（{info.vid_pid_text}）"
            self._device_map[text] = info
            values.append(text)
        self._device_combo.configure(values=values, state="readonly" if values else "disabled")
        if values:
            self._device_var.set(values[0])
            info = devices[0]
            self._connection_badge.set("已连接", "success")
            self._device_detail.configure(
                text=f"机型：{info.model} · VID/PID：{info.vid_pid_text} · 输入报告 {info.input_len} 字节 / 输出 {info.output_len} 字节"
                f"\n路径：{info.path}",
                fg=theme.MUTED,
            )
            self._log_box.log(f"发现展台 HID：{info.model}（{info.vid_pid_text}）", "success")
            self.set_status(f"发现 {len(devices)} 个希沃展台 HID 接口", "success", 3000)
            self._set_light_controls_enabled(True)
        else:
            self._device_var.set("未发现展台")
            self._connection_badge.set("未连接", "secondary")
            self._device_detail.configure(
                text="未发现希沃展台 HID 接口（VID 1FF7 / 254A）。\n"
                "请确认展台已通过 USB 连接；若 EasiCamera 正在运行并占用设备，可先退出后再刷新。",
                fg=theme.MUTED,
            )
            self._log_box.log("未发现希沃展台 HID 接口", "warning")
            self.set_status("未连接展台（HID 未发现设备）", "warning", 4000)
            self._set_light_controls_enabled(False)

    def _device_error(self, exc: BaseException) -> None:
        self._busy = False
        self._connection_badge.set("枚举失败", "danger")
        self._log_box.log(f"HID 设备枚举失败：{exc.__class__.__name__}: {exc}", "error")
        self.set_status(f"HID 枚举失败：{exc}", "error", 5000)

    def _set_light_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in getattr(self, "_light_buttons", []):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # 灯控
    # ------------------------------------------------------------------
    def _run_hid(self, func, action: str):
        if self._busy:
            return
        if not self._devices:
            common.show_warning(self, "未连接展台", "未发现希沃展台 HID 接口，请连接展台后点击「刷新设备」。")
            return
        self._busy = True
        for button in self._light_buttons:
            try:
                button.configure(state="disabled")
            except tk.TclError:
                pass
        self.set_status(f"正在{action}…", "primary")
        common.run_async(
            self,
            func,
            on_success=lambda result: self._hid_done(result, action),
            on_error=lambda exc: self._hid_failed(exc, action),
            name=f"hid-{action}",
        )

    def _hid_done(self, result, action: str) -> None:
        self._busy = False
        self._set_light_controls_enabled(bool(self._devices))
        if action == "查询灯状态":
            state: hid.LedState | None = result
            if state is None:
                self._led_badge.set("未知", "secondary")
                self._led_detail.configure(text="未收到应答")
                self._log_box.log("未收到灯状态应答：请确认展台已连接，或先关闭 EasiCamera 后重试", "warning")
                self.set_status("未收到灯状态应答", "warning", 4000)
            else:
                self._apply_led_state(state)
                self._log_box.log(f"灯状态：{state.text}（来源 {state.source}）", "success")
                self.set_status(f"灯状态：{state.text}", "success", 3000)
            return
        if action == "查询 MCU 版本":
            version = result
            if version:
                self._mcu_value.configure(text=version)
                self._log_box.log(f"MCU 版本：{version}", "success")
                self.set_status(f"MCU 版本：{version}", "success", 3000)
            else:
                self._mcu_value.configure(text="未获取到")
                self._log_box.log("未获取到 MCU 版本应答", "warning")
                self.set_status("未获取到 MCU 版本", "warning", 4000)
            return
        # 一般命令（dict）
        if isinstance(result, dict):
            message = str(result.get("message") or "")
            ok = bool(result.get("ok", False))
            self._log_box.log(message or action, "success" if ok else "error")
            if ok:
                if action == "开灯":
                    self._led_badge.set("已开灯", "success")
                elif action == "关灯":
                    self._led_badge.set("已关灯", "secondary")
                self.set_status(message or action, "success", 3000)
            else:
                self.set_status(message or f"{action}失败", "warning", 5000)
        else:
            self._log_box.log(f"{action}：{result}", "info")

    def _apply_led_state(self, state: hid.LedState) -> None:
        self._led_badge.set("已开灯" if state.on else "已关灯", "success" if state.on else "secondary")
        self._led_detail.configure(text=f"亮度 {state.level}")

    def _hid_failed(self, exc: BaseException, action: str) -> None:
        self._busy = False
        self._set_light_controls_enabled(bool(self._devices))
        self._log_box.log(f"{action}失败：{exc.__class__.__name__}: {exc}", "error")
        self.set_status(f"{action}失败：{exc}", "error", 5000)

    def query_led(self) -> None:
        self._run_hid(lambda: hid.HidController().query_led(), "查询灯状态")

    def turn_on_light(self) -> None:
        level = LEVEL_VALUES[self._level_combo.current()] if self._level_combo.current() >= 0 else 0
        self._run_hid(lambda: hid.HidController().turn_on_light(level), "开灯")

    def turn_off_light(self) -> None:
        self._run_hid(lambda: hid.HidController().turn_off_light(), "关灯")

    def touch_on(self) -> None:
        self._run_hid(lambda: hid.HidController().touch_on(), "触摸灯开")

    def touch_off(self) -> None:
        self._run_hid(lambda: hid.HidController().touch_off(), "触摸灯关")

    def touch_flash(self) -> None:
        self._run_hid(lambda: hid.HidController().touch_flash(), "触摸灯闪烁")

    def query_touch(self) -> None:
        self._run_hid(lambda: hid.HidController().query_touch(), "查询触摸灯")

    def query_mcu(self) -> None:
        self._run_hid(lambda: hid.HidController().query_mcu(), "查询 MCU 版本")

    # ------------------------------------------------------------------
    # 监听
    # ------------------------------------------------------------------
    def _ensure_monitor(self) -> hid.HidMonitor:
        if self._monitor is None:
            self._monitor = hid.HidMonitor(
                on_frame=self._on_frame,
                on_log=self._on_monitor_log,
                on_led=self._on_led,
                on_key=self._on_key,
                on_connection=self._on_connection,
                heartbeat_reply=bool(self._heartbeat_var.get()),
            )
        return self._monitor

    def start_listening(self) -> None:
        monitor = self._ensure_monitor()
        monitor.heartbeat_reply = bool(self._heartbeat_var.get())
        if monitor.running:
            return
        monitor.start()
        self._start_button.configure(state="disabled")
        self._stop_button.configure(state="normal")
        self._log_box.log("开始监听 HID 输入帧…", "primary")
        self.set_status("HID 监听已启动", "primary", 3000)

    def stop_listening(self, silent: bool = False) -> None:
        if self._monitor is not None and self._monitor.running:
            self._monitor.stop(timeout=1.5)
            if not silent:
                self._log_box.log("已停止 HID 监听", "muted")
                self.set_status("HID 监听已停止", "info", 3000)
        try:
            self._start_button.configure(state="normal")
            self._stop_button.configure(state="disabled")
        except tk.TclError:
            pass

    def clear_log(self) -> None:
        self._log_box.clear()
        self._frame_count = 0
        self._frames_label.configure(text="已监听 0 帧")

    def _on_heartbeat_toggle(self) -> None:
        value = bool(self._heartbeat_var.get())
        try:
            settings.set("hid_heartbeat_reply", value)
        except Exception:  # noqa: BLE001
            pass
        if self._monitor is not None:
            self._monitor.heartbeat_reply = value
        self._log_box.log(f"心跳自动应答：{'开启' if value else '关闭'}", "muted")

    # ---- 监听线程回调（需切回主线程）----
    def _ui(self, func, *args) -> None:
        common.post_ui(self, lambda: func(*args))

    def _on_frame(self, frame: hid.FrameInfo) -> None:
        self._ui(self._render_frame, frame)

    def _render_frame(self, frame: hid.FrameInfo) -> None:
        self._frame_count += 1
        try:
            self._frames_label.configure(text=f"已监听 {self._frame_count} 帧")
        except tk.TclError:
            return
        level = FRAME_KIND_LEVEL.get(frame.kind, "info")
        source = f"[{frame.source}] " if frame.source else ""
        self._log_box.log(f"{source}RAW={frame.hex_raw}  => {frame.description}", level)

    def _on_monitor_log(self, message: str) -> None:
        self._ui(lambda: self._log_box.log(message, "info"))

    def _on_led(self, state: hid.LedState) -> None:
        self._ui(self._apply_led_state, state)

    def _on_connection(self, connected: bool, devices: list[hid.HidDeviceInfo]) -> None:
        def _update() -> None:
            if connected:
                self._connection_badge.set("监听中", "success")
                self._set_light_controls_enabled(bool(self._devices))
            else:
                self._connection_badge.set("未连接", "secondary")

        self._ui(_update)

    def _on_key(self, key_index: int, key_name: str) -> None:
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M:%S")

        def _update() -> None:
            try:
                self._last_key_label.configure(text=f"最近按键：{key_name}（{stamp}）")
            except tk.TclError:
                pass

        self._ui(_update)
