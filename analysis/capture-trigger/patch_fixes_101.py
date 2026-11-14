import io

BASE = r'D:\开发\SeewoCamera\InspireCameraTools'

# ============ 1) 一键相机页：删除兜底快捷键 ============
p = BASE + r'\app\camera_page.py'
s = io.open(p, encoding='utf-8').read()

s = s.replace(
    '不写入 HID、不与希沃进程抢设备。可选兜底热键仅在 UI 自动化失败时使用。\n',
    '不写入 HID、不与希沃进程抢设备；也不再发送任何键盘快捷键。\n',
)
s = s.replace(
    '    "· 找不到按钮时可点「检测拍照按钮」查看诊断信息，或用兜底热键 / 修改 EasiCamera 界面后重试。"',
    '    "· 找不到按钮时可点「检测拍照按钮」查看诊断信息，或确认 EasiCamera 处于拍照界面后重试。"',
)
s = s.replace('        self._target_key = str(settings.get("camera_target_key") or "F12")\n', '')

start = s.index('        # 兜底按键（UI 自动化失败时才会使用）')
end = s.index('        # 防抖')
s = s[:start] + s[end:]

# start_camera 中的目标按键校验
old = '''        # 校验目标按键
        try:
            sysinfo.parse_key_combo(self._target_key)
        except ValueError as exc:
            common.show_error(self, "目标按键无效", f"「{self._target_key}」不是受支持的按键组合：{exc}")
            self._set_switch(False)
            return
'''
assert old in s
s = s.replace(old, '')

s = s.replace(
    '''            f"拍照触发：UI 自动化点击 EasiCamera「拍照」按钮；兜底按键 {self._target_key}（防抖 {self._debounce_ms} ms）",''',
    '''            f"拍照触发：UI 自动化点击 EasiCamera「拍照」按钮（防抖 {self._debounce_ms} ms）",''',
)

# _do_trigger 中删除兜底热键分支
old = s[s.index('    def _do_trigger(self, frame: hid.FrameInfo) -> None:'):s.index('    def _on_probe_click(self) -> None:')]
new = '''    def _do_trigger(self, frame: hid.FrameInfo) -> None:
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

'''
s = s.replace(old, new)

# 删除 _on_target_key_changed 方法
start = s.index('    def _on_target_key_changed(self, _event=None) -> None:')
end = s.index('    def _on_debounce_changed(self) -> None:')
s = s[:start] + s[end:]

io.open(p, 'w', encoding='utf-8').write(s)
print('camera_page: hotkey removed')

# ============ 2) 补丁页：粘贴路径自动检测 ============
p = BASE + r'\app\patch_page.py'
s = io.open(p, encoding='utf-8').read()

# 2.1 import os
s = s.replace('import logging\nimport tkinter as tk\nfrom pathlib import Path',
              'import logging\nimport os\nimport tkinter as tk\nfrom pathlib import Path')

# 2.2 插入 normalize 函数（在 class PatchPage 之前）
anchor = 'class PatchPage(BasePage):'
assert anchor in s
normalize_fn = '''def normalize_main_dir_input(raw: str | None) -> str | None:
    """把用户粘贴/输入的路径规整成 EasiCamera 的 Main 目录。

    支持：
    * 资源管理器「复制路径」带引号/尾部反斜杠；
    * file:///C:/... 形式；
    * 直接粘贴 EasiCamera.exe / 任意 DLL 文件路径（取所在目录）；
    * 粘贴版本目录（...\\EasiCamera_2.1.0.4419）或安装根目录（自动向下找 Main）；
    * 粘贴 Main 目录本身（原样返回）。
    """
    text = (raw or "").strip()
    if not text:
        return None
    # 去掉成对引号（可能反复出现）与首尾单/双引号
    for _ in range(3):
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\\"'":
            text = text[1:-1]
        else:
            break
    text = text.strip().strip("\\"'").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("file:///"):
        text = text[8:].replace("/", "\\\\").lstrip("\\\\")
    text = os.path.expandvars(os.path.expanduser(text))
    text = text.replace("/", "\\\\").rstrip("\\\\")
    if not text:
        return None
    try:
        path = Path(text)
    except Exception:  # noqa: BLE001 - 无法解析时原样交给引擎报告
        return text

    if path.is_file():
        path = path.parent

    candidates: list[Path] = []
    if path.is_dir():
        candidates.append(path)
        candidates.append(path / "Main")
        for parent in list(path.parents)[:3]:
            candidates.append(parent / "Main")
    for candidate in candidates:
        try:
            if (candidate / "EasiCamera.UI.dll").is_file() and (candidate / "EasiCamera.exe").is_file():
                return str(candidate)
        except OSError:
            continue
    return str(path) if path.is_dir() else text


'''
s = s.replace(anchor, normalize_fn + anchor, 1)

# 2.3 __init__ 增加状态
s = s.replace('        self._pending_detection: tuple[str | None, bool] | None = None\n',
              '        self._pending_detection: tuple[str | None, bool] | None = None\n'
              '        self._detect_after: str | None = None\n'
              '        self._syncing_path = False\n')

# 2.4 目录输入框：绑定回车/失焦/文本变化，并加提示
s = s.replace('''        self._path_entry = tb.Entry(path_row, textvariable=self._path_var, bootstyle="secondary")
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, theme.px(8)))''',
'''        self._path_entry = tb.Entry(path_row, textvariable=self._path_var, bootstyle="secondary")
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, theme.px(8)))
        # 手动粘贴/输入后自动检测（回车立即检测，输入停止 450ms 后自动检测）
        self._path_var.trace_add("write", self._on_path_changed)
        self._path_entry.bind("<Return>", lambda _e: self._detect_from_entry())
        self._path_entry.bind("<KP_Enter>", lambda _e: self._detect_from_entry())
        self._path_entry.bind("<FocusOut>", lambda _e: self._detect_from_entry())

        path_hint = tk.Label(
            card.body,
            text="提示：可直接 Ctrl+V 粘贴路径——支持 Main 目录、版本目录、安装根目录或 EasiCamera.exe；粘贴后会自动检测。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="w",
            justify="left",
            wraplength=theme.px(640),
        )
        path_hint.pack(fill="x", pady=(theme.px(6), 0))''')

# 2.5 新增事件处理方法（放在 refresh_detection 之后）
s = s.replace('''    def refresh_detection(self) -> None:
        self._start_detection(self._path_var.get().strip() or None)''',
'''    def refresh_detection(self) -> None:
        self._start_detection(normalize_main_dir_input(self._path_var.get()))

    def _on_path_changed(self, *_args) -> None:
        """输入框内容变化（含粘贴）→ 防抖后自动检测。"""
        if self._syncing_path:
            return
        raw = self._path_var.get()
        normalized = normalize_main_dir_input(raw)
        if normalized and self._main_dir and Path(normalized) == Path(self._main_dir):
            return
        if self._detect_after is not None:
            try:
                self.after_cancel(self._detect_after)
            except tk.TclError:
                pass
        self._detect_after = self.after(450, self._detect_from_entry)

    def _detect_from_entry(self) -> None:
        """立即检测输入框中的目录（回车/失焦/防抖到点）。"""
        if self._detect_after is not None:
            try:
                self.after_cancel(self._detect_after)
            except tk.TclError:
                pass
            self._detect_after = None
        raw = self._path_var.get().strip()
        self._start_detection(normalize_main_dir_input(raw))''')

# 2.6 _start_detection 使用规整后的路径
s = s.replace('''        if not self._ensure_engine():
            return
        self._set_busy(True, "正在检测 EasiCamera 安装目录…")
        engine = self._engine''',
'''        if not self._ensure_engine():
            return
        requested = normalize_main_dir_input(main_dir)
        self._set_busy(True, "正在检测 EasiCamera 安装目录…")
        engine = self._engine''')
s = s.replace('''                configured = (main_dir or "").strip() or None''',
              '''                configured = requested''')

# 2.7 检测成功后同步输入框时不要再次触发自动检测
s = s.replace('''        if main_dir:
            self._path_var.set(main_dir)''',
'''        if main_dir:
            self._syncing_path = True
            try:
                self._path_var.set(main_dir)
            finally:
                self._syncing_path = False''')

io.open(p, 'w', encoding='utf-8').write(s)
print('patch_page: paste auto-detect added')
