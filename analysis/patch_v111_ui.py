import io

BASE = r'D:\开发\SeewoCamera\InspireCameraTools'

# ============ settings_page.py：删除匿名统计开关、API 地址文本 ============
p = BASE + r'\app\settings_page.py'
s = io.open(p, encoding='utf-8').read()

s = s.replace('''        self._cloud_values: dict[str, tk.Label] = {}
        items = [
            ("current", "当前版本"),
            ("latest", "云端最新版本"),
            ("report", "匿名统计"),
            ("device", "匿名设备标识"),
        ]''','''        self._cloud_values: dict[str, tk.Label] = {}
        items = [
            ("current", "当前版本"),
            ("latest", "云端最新版本"),
            ("device", "匿名设备标识"),
        ]''')

s = s.replace('''        self._check_update_button.pack(side="left")
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
        self._refresh_cloud_card()''','''        self._check_update_button.pack(side="left")
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
        self._refresh_cloud_card()''')

s = s.replace('''            values = {
                "current": settings.APP_VERSION,
                "report": "已开启" if status.get("report_enabled") else "已关闭",
                "device": masked,
            }''','''            values = {
                "current": settings.APP_VERSION,
                "device": masked,
            }''')

# 删除 _on_report_toggled 方法
start = s.index('    def _on_report_toggled(self) -> None:')
end = s.index('    def _check_update_clicked(self) -> None:')
s = s[:start] + s[end:]

io.open(p, 'w', encoding='utf-8').write(s)
print('settings_page patched')

# ============ common.py：修复鼠标滚轮（无需先拖滚动条） ============
p = BASE + r'\app\common.py'
s = io.open(p, encoding='utf-8').read()

old = '''        self._scroll_needed = True
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_wheel()'''
new = '''        self._scroll_needed = True
        self._wheel_bind_pending = False
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_wheel()
        # 直接给画布与容器绑定滚轮，避免依赖 <Enter> 全局绑定（旧实现要先把滚动条拖一次才生效）
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<MouseWheel>", self._on_mousewheel)'''
assert old in s
s = s.replace(old, new, 1)

old = '''    def _bind_wheel(self) -> None:
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
        self.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))'''
new = '''    def _bind_wheel(self) -> None:
        """给内容区所有子控件递归绑定滚轮（内容变化时重绑）。

        旧实现用 ``<Enter>`` 时 ``bind_all``，实际指针常落在子控件上导致 Enter 不触发，
        表现为「必须先用滚动条拖一次，滚轮才生效」。改为直接绑定到每个子控件：
        指针在内容任意位置都能立即滚动，也不会抢其它可滚动控件（Text/Listbox/Treeview）的滚轮。
        """
        self._bind_wheel_tree(self.inner)

    def _bind_wheel_tree(self, widget: tk.Misc) -> None:
        if isinstance(widget, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Combobox)):
            return  # 自身可滚动的控件保留原生滚轮行为
        try:
            widget.bind("<MouseWheel>", self._on_mousewheel)
        except tk.TclError:
            pass
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return
        for child in children:
            self._bind_wheel_tree(child)

    def _on_mousewheel(self, event) -> str | None:
        try:
            first, last = self.canvas.yview()
            if (first, last) == (0.0, 1.0):
                return None
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            self.canvas.yview_scroll(delta * 2, "units")
            return "break"
        except tk.TclError:
            return None

    def _schedule_bind_wheel(self) -> None:
        """内容变化后（子控件新增）重新绑定滚轮。"""
        if self._wheel_bind_pending:
            return
        self._wheel_bind_pending = True

        def _do() -> None:
            self._wheel_bind_pending = False
            try:
                self._bind_wheel()
            except tk.TclError:
                pass

        try:
            self.after_idle(_do)
        except tk.TclError:
            self._wheel_bind_pending = False'''
assert old in s
s = s.replace(old, new, 1)

# 在内容 Configure 时重新绑定
old = '''        self._scroll_needed = True
        self.inner.bind("<Configure>", self._on_inner_configure)'''
new = '''        self._scroll_needed = True
        self.inner.bind("<Configure>", self._on_inner_configure)'''
# 在 _on_inner_configure 末尾追加调度
old2 = '''        if self._fill_height:
            self._schedule_fill()
        else:
            self._update_scrollbar()'''
new2 = '''        if self._fill_height:
            self._schedule_fill()
        else:
            self._update_scrollbar()
        self._schedule_bind_wheel()'''
assert old2 in s
s = s.replace(old2, new2, 1)

# ttk 模块引用（顶部 import ttkbootstrap as tb；tkinter.ttk 需要引入）
if 'from tkinter import ttk' not in s and 'import tkinter.ttk' not in s:
    s = s.replace('import tkinter as tk\n', 'import tkinter as tk\nfrom tkinter import ttk\n', 1)

io.open(p, 'w', encoding='utf-8').write(s)
print('common.py ScrollFrame patched')
