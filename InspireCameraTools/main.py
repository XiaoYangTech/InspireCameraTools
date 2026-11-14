"""亿方展台管家（InspireCameraTools）入口。

用法::

    python main.py                 # 正常启动
    python main.py --smoke-test    # 构建 UI 后 3 秒自动退出（自动化验证用）
    python main.py --auto-close 5  # 启动 5 秒后自动关闭（人工冒烟测试用）
    python main.py --background    # 后台模式（开机自启用，启动后最小化）

高 DPI：优先 ``shcore.SetProcessDpiAwareness(2)``（Per-Monitor），失败回退
``user32.SetProcessDPIAware()``；随后按 ``winfo_fpixels('1i')/96`` 设置 Tk scaling。
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import logging.handlers
import os
import sys
import traceback

APP_NAME = "InspireCameraTools"
APP_TITLE = "亿方展台管家"
APP_VERSION = "1.1.0"


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="InspireCameraTools",
        description="亿方展台管家 — 希沃视频展台辅助工具",
    )
    parser.add_argument("--smoke-test", action="store_true", help="构建 UI 后 3 秒自动退出（自动化验证）")
    parser.add_argument("--auto-close", type=float, default=0.0, metavar="秒", help="指定秒数后自动关闭窗口")
    parser.add_argument("--background", action="store_true", help="后台模式：启动后最小化（用于开机自启）")
    parser.add_argument("--self-check", action="store_true", help="运行环境自检（资源/主题/补丁规则/HID）并退出")
    parser.add_argument("--version", action="store_true", help="显示版本号并退出")
    parser.add_argument(
        "--page",
        default="home",
        choices=["home", "patch", "hid", "download", "autoupdate", "camera", "settings"],
        help="启动后直接进入指定页面（默认 home，用于截图/演示/自动化）",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# 高 DPI（必须在创建任何 Tk 窗口之前调用）
# ---------------------------------------------------------------------------
def enable_dpi_awareness() -> str:
    """启用进程 DPI 感知，返回实际生效的模式描述。"""
    if sys.platform != "win32":
        return "unsupported"
    try:
        shcore = ctypes.windll.shcore
        result = shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        if result == 0:
            return "per-monitor"
    except Exception:  # noqa: BLE001 - Win7 无 shcore，回退 user32
        pass
    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            return "system"
    except Exception:  # noqa: BLE001
        pass
    return "none"


def set_app_user_model_id() -> None:
    """设置任务栏 AppUserModelID，让任务栏图标正确归属本程序。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Seewo.InspireCameraTools.1")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
def setup_logging(smoke_test: bool = False) -> str:
    """配置日志：写入 %APPDATA%/InspireCameraTools/logs/app.log，同时输出到控制台。"""
    from core import settings

    log_dir = settings.logs_dir()
    log_file = os.path.join(log_dir, "app.log")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError:
        pass
    if sys.stdout is not None and not smoke_test:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)
    return log_file


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
def _print(message: str) -> None:
    """安全打印（pythonw 下 stdout 可能为 None）。"""
    if sys.stdout is not None:
        try:
            print(message, flush=True)
        except Exception:  # noqa: BLE001
            pass


def show_fatal_error(message: str) -> None:
    """启动失败时尽量弹窗提示，便于用户反馈。"""
    _print("启动失败：" + message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, f"程序启动失败：\n\n{message}")
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


def run_self_check() -> int:
    """运行环境自检：资源/主题/补丁规则/HID/自动更新模块，供打包产物与排障使用。"""
    lines: list[str] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        lines.append(f"[{'OK' if ok else 'FAIL'}] {name}" + (f"：{detail}" if detail else ""))
        if not ok:
            failures.append(name)

    lines.append(f"=== {APP_TITLE} 环境自检（{APP_NAME} {APP_VERSION}）===")
    from core import settings as app_settings

    check("Windows 平台", sys.platform == "win32", sys.platform)
    check("运行模式", True, "打包运行" if getattr(sys, "frozen", False) else "源码运行")
    check("配置目录", True, str(app_settings.app_data_dir()))
    check("日志目录", True, str(app_settings.logs_dir()))

    # 资源与主题
    try:
        from app import theme

        check("资源目录", theme.ASSETS_DIR.is_dir(), str(theme.ASSETS_DIR))
        icon_names = ["patch", "hid", "download", "autoupdate", "camera", "settings", "logo", "status_on", "status_off"]
        missing = [name for name in icon_names if not theme.icon_path(name).is_file()]
        check(f"图标资源（{len(icon_names)} 个）", not missing, "缺失: " + ", ".join(missing) if missing else "齐全")
        check("app.ico", theme.ico_path().is_file(), str(theme.ico_path()))
        theme.ensure_bootstrap_light_theme()
        from ttkbootstrap.themes.standard import STANDARD_THEMES

        check("bootstrap-light 主题", "bootstrap-light" in STANDARD_THEMES)
    except Exception as exc:  # noqa: BLE001
        check("界面资源/主题", False, f"{exc.__class__.__name__}: {exc}")

    # 补丁引擎与规则
    try:
        from core import patch_engine  # noqa: F401
        from core import rules as rules_pkg

        versions = rules_pkg.versions()
        check("补丁引擎", True, "core.patch_engine 可导入")
        check("补丁规则版本", bool(versions), ", ".join(versions) if versions else "无（规则文件缺失）")
        errors = rules_pkg.load_errors()
        check("规则导入错误", not errors, str(errors)[:300] if errors else "无")
        try:
            all_rules = rules_pkg.all_rules()
            feature_count = sum(len(rule.get("features") or {}) for rule in all_rules.values())
            check("规则功能项", feature_count > 0, f"{feature_count} 个功能项")
        except Exception as exc:  # noqa: BLE001
            check("规则功能项", False, f"{exc.__class__.__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        check("补丁引擎", False, f"{exc.__class__.__name__}: {exc}")

    # 自动更新模块
    try:
        import core.autoupdate  # noqa: F401

        check("自动更新模块", True, "core.autoupdate 可导入")
    except Exception as exc:  # noqa: BLE001
        check("自动更新模块", False, f"{exc.__class__.__name__}: {exc}")

    # HID
    try:
        from core import hid

        check("HID 底层库", hid.HID_AVAILABLE, "hid.dll / setupapi.dll 绑定成功" if hid.HID_AVAILABLE else "绑定失败")
        parsed = hid.parse_input_frame(bytes((0xAA, 0xBB, 0xCC, 0x02, 0x02, 0x02, 0x00, 0x01, 0x32, 0x00)))
        check("HID 帧解析自检", bool(parsed and parsed.led_on is True and parsed.led_level == 0x32))
        devices = hid.enumerate_devices()
        check("HID 设备枚举", True, f"{len(devices)} 个 HID 接口")
        seewo = [d for d in devices if d.is_seewo]
        check("希沃展台设备", True, f"{len(seewo)} 个" if seewo else "未连接（正常，无硬件也不影响其它功能）")
    except Exception as exc:  # noqa: BLE001
        check("HID 模块", False, f"{exc.__class__.__name__}: {exc}")

    # 亿方智云客户端（免登录；自检只验证模块与配置，不联网）
    try:
        from core import cloud

        status = cloud.cloud_status()
        check("亿方智云客户端", bool(status.get("base_url")), f"slug={status.get('slug')}")
        check(
            "匿名设备标识",
            bool(cloud.DEVICE_KEY_RE.match(str(status.get("device_key") or ""))),
            str(status.get("device_key") or "")[:8] + "…",
        )
    except Exception as exc:  # noqa: BLE001
        check("亿方智云客户端", False, f"{exc.__class__.__name__}: {exc}")

    # 一键相机拍照触发助手（UIA）
    try:
        from core import capture_trigger

        info = capture_trigger.helper_info()
        present = bool(info.get("bundled_present") or info.get("cached_present"))
        check("拍照触发助手", present, info.get("bundled_exe"))
        check("拍照触发 Remoting 备用通道", bool(info.get("remoting_port")), info.get("remoting_port"))
    except Exception as exc:  # noqa: BLE001
        check("拍照触发助手", False, f"{exc.__class__.__name__}: {exc}")

    # 开机自启（只读检查）
    try:
        from core import startup

        check("开机自启支持", startup.is_supported(), startup.get_registered_command() or "未设置自启项")
    except Exception as exc:  # noqa: BLE001
        check("开机自启支持", False, f"{exc.__class__.__name__}: {exc}")

    for line in lines:
        _print(line)
    _print("=" * 60)
    if failures:
        _print(f"SELF-CHECK FAILED（{len(failures)} 项）：{', '.join(failures)}")
        return 1
    _print("SELF-CHECK OK：全部检查通过")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.version:
        _print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if args.self_check:
        setup_logging(smoke_test=True)
        try:
            return run_self_check()
        except Exception as exc:  # noqa: BLE001 - 自检异常兜底
            _print(f"自检异常：{exc.__class__.__name__}: {exc}")
            return 1

    if sys.platform != "win32":
        _print("本程序仅支持 Windows 系统。")
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_TITLE, "本程序仅支持 Windows 系统。")
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
        return 1

    # 高 DPI 必须在创建 Tk 之前
    dpi_mode = enable_dpi_awareness()
    set_app_user_model_id()
    log_file = setup_logging(smoke_test=args.smoke_test)
    log = logging.getLogger("main")
    log.info(
        "启动 %s %s（DPI 模式=%s, 源码模式=%s, 参数=%s）",
        APP_NAME,
        APP_VERSION,
        dpi_mode,
        not getattr(sys, "frozen", False),
        sys.argv[1:],
    )

    window = None
    try:
        from app.app_window import MainWindow

        window = MainWindow(
            background=args.background, smoke_test=args.smoke_test, initial_page=args.page
        )

        exit_code = 0
        if args.smoke_test:
            _print("[smoke] UI 构建完成，3 秒后自动退出…")
            log.info("smoke-test：UI 构建完成")

            def _finish_smoke() -> None:
                nonlocal exit_code
                exit_code = 0
                _print("[smoke] 自动关闭窗口")
                log.info("smoke-test：自动关闭")
                window._on_close()

            window.after(3000, _finish_smoke)
        elif args.auto_close and args.auto_close > 0:
            _print(f"[auto-close] {args.auto_close} 秒后自动关闭…")
            window.after(int(args.auto_close * 1000), window._on_close)

        window.mainloop()
        log.info("程序正常退出（exit=%s）", exit_code)
        return exit_code
    except Exception as exc:  # noqa: BLE001 - 启动失败兜底
        details = traceback.format_exc()
        logging.getLogger("main").error("启动异常：%s\n%s", exc, details)
        try:
            if window is not None:
                window.destroy()
        except Exception:  # noqa: BLE001
            pass
        show_fatal_error(f"{exc}\n\n详细日志：{log_file}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
