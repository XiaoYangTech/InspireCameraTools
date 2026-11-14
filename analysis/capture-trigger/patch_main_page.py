import io

# ---------- app_window.py：支持 --page 指定初始页面 ----------
p = r'D:\开发\SeewoCamera\InspireCameraTools\app\app_window.py'
s = io.open(p, encoding='utf-8').read()
old = '''    def __init__(self, background: bool = False, smoke_test: bool = False) -> None:'''
new = '''    def __init__(self, background: bool = False, smoke_test: bool = False, initial_page: str = "home") -> None:'''
assert old in s
s = s.replace(old, new)

old = '''        self._background = background
        self._smoke_test = smoke_test'''
new = '''        self._background = background
        self._smoke_test = smoke_test
        self._initial_page = initial_page if initial_page in PAGE_FACTORIES else "home"'''
assert old in s
s = s.replace(old, new)

old = '''        self.container.grid_columnconfigure(0, weight=1)
        self.show_page("home")'''
new = '''        self.container.grid_columnconfigure(0, weight=1)
        self.show_page(self._initial_page)'''
assert old in s
s = s.replace(old, new)
io.open(p, 'w', encoding='utf-8').write(s)
print('app_window patched')

# ---------- main.py：--page 参数 + 自检加入拍照触发助手 ----------
p = r'D:\开发\SeewoCamera\InspireCameraTools\main.py'
s = io.open(p, encoding='utf-8').read()
old = '''    parser.add_argument("--version", action="store_true", help="显示版本号并退出")'''
new = '''    parser.add_argument("--version", action="store_true", help="显示版本号并退出")
    parser.add_argument(
        "--page",
        default="home",
        choices=["home", "patch", "hid", "download", "autoupdate", "camera", "settings"],
        help="启动后直接进入指定页面（默认 home，用于截图/演示/自动化）",
    )'''
assert old in s
s = s.replace(old, new)

old = '''        window = MainWindow(background=args.background, smoke_test=args.smoke_test)'''
new = '''        window = MainWindow(
            background=args.background, smoke_test=args.smoke_test, initial_page=args.page
        )'''
assert old in s
s = s.replace(old, new)

# 自检：拍照触发助手
old = '''    # 开机自启（只读检查）'''
new = '''    # 一键相机拍照触发助手（UIA）
    try:
        from core import capture_trigger

        info = capture_trigger.helper_info()
        present = bool(info.get("bundled_present") or info.get("cached_present"))
        check("拍照触发助手", present, info.get("bundled_exe"))
        check("拍照触发 Remoting 备用通道", bool(info.get("remoting_port")), info.get("remoting_port"))
    except Exception as exc:  # noqa: BLE001
        check("拍照触发助手", False, f"{exc.__class__.__name__}: {exc}")

    # 开机自启（只读检查）'''
assert old in s
s = s.replace(old, new)
io.open(p, 'w', encoding='utf-8').write(s)
print('main patched')
