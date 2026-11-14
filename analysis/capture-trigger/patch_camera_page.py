import io

p = r'D:\开发\SeewoCamera\InspireCameraTools\app\camera_page.py'
s = io.open(p, encoding='utf-8').read()

# A. 模块 docstring
old_doc = '''"""一键相机页：把展台机身补光灯按键映射为拍照快捷键（默认 F12）。

原理：后台监听展台 HID 输入帧 ``BB CC 05``（机身补光灯按键通知）或 ``BB CC 02``
（灯状态变化），触发时通过 Win32 ``SendInput`` 向前台窗口发送配置的按键。
需在 EasiCamera 拍照界面使用；无展台时允许开启，监听会等待设备接入。
"""'''
new_doc = '''"""一键相机页：按下展台机身补光灯按键 → 自动触发 EasiCamera 拍照。

原理：后台监听展台 HID 输入帧 ``BB CC 05``（机身补光灯按键通知）或 ``BB CC 02``
（灯状态变化），触发时**通过 UI Automation 调用 EasiCamera 的「拍照」按钮**
（``ECCommands.CaptureImage``，与按机身拍照键执行的同一命令），不发送键盘快捷键、
不写入 HID、不与希沃进程抢设备。可选兜底热键仅在 UI 自动化失败时使用。
无展台时允许开启，监听会等待设备接入。
"""'''
assert old_doc in s
s = s.replace(old_doc, new_doc)

# B. 使用说明
start = s.index('INSTRUCTIONS = (')
end = s.index('class CameraPage(BasePage):')
new_ins = '''INSTRUCTIONS = (
    "使用说明：\\n"
    "1. 连接希沃展台，打开 EasiCamera 并进入拍照/展台界面（无需前台焦点，最小化也可尝试）；\\n"
    "2. 打开下方「一键相机」开关（可同时开启开机自启，后台运行并自动监听）；\\n"
    "3. 按下展台机身上的补光灯按键，程序会通过 UI 自动化点击 EasiCamera 的「拍照」按钮完成拍照。\\n\\n"
    "说明：\\n"
    "· 触发的是 EasiCamera 自己的拍照命令（与机身拍照键最终执行的动作一致），不是键盘快捷键；\\n"
    "· 期间若 EasiCamera 未运行或不在拍照界面，日志会提示「未找到 EasiCamera 窗口/拍照按钮」；\\n"
    "· 同一按键 800ms 内只触发一次（防抖），避免连拍；\\n"
    "· 找不到按钮时可点「检测拍照按钮」查看诊断信息，或用兜底热键 / 修改 EasiCamera 界面后重试。"
)


'''
s = s[:start] + new_ins + s[end:]

# C. import
s = s.replace('import logging\nimport time\nimport tkinter as tk',
              'import logging\nimport threading\nimport time\nimport tkinter as tk')
s = s.replace('from core import hid, settings, startup, sysinfo',
              'from core import capture_trigger, hid, settings, startup, sysinfo')

# D. subtitle
s = s.replace('    subtitle = "展台机身补光灯按键 → 拍照快捷键（监听 HID 输入帧并注入键盘事件）"',
              '    subtitle = "展台机身补光灯按键 → 自动触发 EasiCamera 拍照（UI 自动化，等效机身拍照键）"')

# E. 并发保护字段
s = s.replace('        self._trigger_count = 0\n',
              '        self._trigger_count = 0\n        self._triggering = False\n')

# F. 兜底按键标签
s = s.replace('''        # 目标按键
        tk.Label(options, text="目标按键", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(''',
              '''        # 兜底按键（UI 自动化失败时才会使用）
        tk.Label(options, text="兜底按键", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(''')

# G. 检测按钮
s = s.replace('''        self._autostart_switch.pack(side="left")
        self._autostart_hint = tk.Label(''',
              '''        self._autostart_switch.pack(side="left")
        self._probe_button = tb.Button(
            options,
            text="检测拍照按钮",
            bootstyle="outline-secondary",
            command=self._on_probe_click,
            cursor="hand2",
        )
        self._probe_button.pack(side="left", padx=(theme.px(18), 0))
        self._autostart_hint = tk.Label(''')

# H. 状态字段
s = s.replace('''        items = [
            ("state", "运行状态"),
            ("connection", "展台连接"),
            ("key", "目标按键"),
            ("count", "已触发次数"),
        ]''',
              '''        items = [
            ("state", "运行状态"),
            ("connection", "展台连接"),
            ("trigger", "拍照触发方式"),
            ("count", "已触发次数"),
        ]''')
s = s.replace('        self._status_values["key"].configure(text=self._target_key)',
              '        self._status_values["trigger"].configure(text="模拟机身拍照键（UIA）")')

# I. 日志卡片副标题
s = s.replace('card = common.Card(parent, title="监听日志", subtitle="HID 监听与按键注入记录", icon="download")',
              'card = common.Card(parent, title="监听日志", subtitle="HID 监听、拍照触发与诊断记录", icon="download")')

# J. 启动日志
s = s.replace('        self._log.log(f"目标按键：{self._target_key}（防抖 {self._debounce_ms} ms）", "info")',
              '        self._log.log(\n'
              '            f"拍照触发：UI 自动化点击 EasiCamera「拍照」按钮；兜底按键 {self._target_key}（防抖 {self._debounce_ms} ms）",\n'
              '            "info",\n'
              '        )')

# K. 替换触发处理逻辑
start = s.index('    def _handle_trigger_frame(self, frame: hid.FrameInfo) -> None:')
end = s.index('    def _ui(self, func) -> None:')
new_handler = '''    def _handle_trigger_frame(self, frame: hid.FrameInfo) -> None:
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
        """后台线程：先走 UI 自动化（模拟拍照按钮），失败再尝试兜底热键。"""
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
                # UI 自动化失败 → 兜底热键
                self._log.log(f"UI 自动化触发失败：{result.message}", "warning")
                ok, error = sysinfo.send_key_combo(self._target_key)
                if ok:
                    self._trigger_count += 1
                    self._status_values["count"].configure(text=str(self._trigger_count))
                    self._log.log(
                        f"已退化为兜底按键 {self._target_key} 注入（第 {self._trigger_count} 次）", "warning"
                    )
                    self.set_status(f"已用兜底按键触发（第 {self._trigger_count} 次）", "warning", 3000)
                else:
                    self._log.log(f"兜底按键注入也失败：{error}", "error")
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

'''
s = s[:start] + new_handler + s[end:]

io.open(p, 'w', encoding='utf-8').write(s)
print('camera_page patched, lines =', len(s.splitlines()))
