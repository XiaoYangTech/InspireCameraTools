"""破坏自动更新页：调用 ``core.autoupdate`` 检测/执行/还原自动更新防护。

``core.autoupdate`` 由 patch-core 提供且接口尚未最终固定，本页用「宽松适配器」调用：
- 依次探测常见的 detect/apply/restore 函数名；
- 根据函数签名自动决定是否传入 Main 目录；
- 模块不存在或接口不匹配时优雅降级显示「模块未就绪」，不影响其它页面。
"""

from __future__ import annotations

import inspect
import logging
import tkinter as tk
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

import ttkbootstrap as tb

from core import settings, sysinfo

from . import common, theme
from .base_page import BasePage

log = logging.getLogger(__name__)

#: 候选接口名（按优先级）
DETECT_NAMES = ("detect", "detect_status", "inspect", "get_status", "status", "check", "scan")
APPLY_NAMES = ("apply", "enable", "protect", "apply_protection", "disable_autoupdate", "block")
RESTORE_NAMES = ("restore", "revert", "undo", "restore_protection", "unblock")

REQUIRED_GROUPS = ("detect", "apply", "restore")


class AutoUpdatePage(BasePage):
    """破坏自动更新页面。"""

    title = "破坏自动更新"
    subtitle = "阻止 EasiCamera 自动升级覆盖已打补丁的文件（计划任务 / 更新器 / 服务 / 缓存）"
    icon = "autoupdate"

    def __init__(self, master: tk.Misc, app) -> None:
        self._module: Any = None
        self._module_error: str = ""
        self._functions: dict[str, Callable | None] = {name: None for name in REQUIRED_GROUPS}
        self._main_dir = ""
        self._busy = False
        self._detect_loaded = False
        super().__init__(master, app)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_body(self) -> None:
        self.add_header_button("检测状态", self.detect_status, bootstyle="secondary-outline")
        self.body.grid_rowconfigure(1, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self._build_module_card()
        self._build_log_card()
        self._build_actions()

    def _build_module_card(self) -> None:
        card = common.Card(
            self.body,
            title="模块状态",
            subtitle="对接 core.autoupdate；需要管理员权限的操作会给出明确提示",
            icon="autoupdate",
        )
        card.grid(row=0, column=0, sticky="ew", pady=(0, theme.px(12)))

        badges = tk.Frame(card.body, bg=theme.WHITE)
        badges.pack(fill="x")
        tk.Label(badges, text="模块", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(6))
        )
        self._module_badge = common.Badge(badges, text="检测中…", kind="info")
        self._module_badge.pack(side="left", padx=(0, theme.px(18)))
        tk.Label(badges, text="管理员权限", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(6))
        )
        admin = sysinfo.is_admin()
        self._admin_badge = common.Badge(
            badges, text="已获得" if admin else "普通用户", kind="success" if admin else "warning"
        )
        self._admin_badge.pack(side="left", padx=(0, theme.px(18)))
        tk.Label(badges, text="EasiCamera 目录", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(6))
        )
        self._dir_label = tk.Label(
            badges, text="检测中…", bg=theme.WHITE, fg=theme.TEXT, font=theme.font(10), anchor="w"
        )
        self._dir_label.pack(side="left", fill="x", expand=True)

        hint = tk.Label(
            card.body,
            text="执行防护会重命名/禁用 EasiCamera 的更新器、禁用相关计划任务并清理更新缓存；"
            "「还原」可恢复原状。若提示权限不足，请右键以管理员身份运行本程序。",
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(940),
        )
        hint.pack(fill="x", pady=(theme.px(10), 0))

        self._module_banner = tk.Label(
            card.body,
            text="",
            bg=theme.WARNING_BG,
            fg=theme.WARNING,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(940),
            padx=theme.px(10),
            pady=theme.px(6),
        )
        self._module_banner.pack_forget()

    def _build_log_card(self) -> None:
        card = common.Card(
            self.body, title="检测与执行结果", subtitle="状态清单与操作日志", icon="download"
        )
        card.grid(row=1, column=0, sticky="nsew", pady=(0, theme.px(12)))
        if card.header_right is not None:
            tb.Button(
                card.header_right, text="清空", bootstyle="link", command=lambda: self._log.clear(), cursor="hand2"
            ).pack(side="right")
        self._log = common.LogText(card.body, height=15)
        self._log.pack(fill="both", expand=True)
        self._log.log("等待检测自动更新防护状态…", "muted")

    def _build_actions(self) -> None:
        actions = tk.Frame(self.body, bg=theme.PAGE_BG)
        actions.grid(row=2, column=0, sticky="ew")
        self._detect_button = tb.Button(
            actions, text="检测状态", bootstyle="secondary-outline", command=self.detect_status, cursor="hand2", width=10
        )
        self._detect_button.pack(side="left")
        self._apply_button = tb.Button(
            actions,
            text="执行防护",
            bootstyle="primary",
            command=self.apply_protection,
            cursor="hand2",
            width=10,
            state="disabled",
        )
        self._apply_button.pack(side="left", padx=(theme.px(8), 0))
        self._restore_button = tb.Button(
            actions,
            text="还原防护",
            bootstyle="warning-outline",
            command=self.restore_protection,
            cursor="hand2",
            width=10,
            state="disabled",
        )
        self._restore_button.pack(side="left", padx=(theme.px(8), 0))
        self._progress = tb.Progressbar(actions, mode="indeterminate", bootstyle="primary-striped", length=theme.px(140))
        self._progress.pack_forget()
        self._status_label = tk.Label(
            actions, text="", bg=theme.PAGE_BG, fg=theme.MUTED, font=theme.font(9), anchor="e"
        )
        self._status_label.pack(side="right")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._detect_loaded:
            self._detect_loaded = True
            self._load_module_and_detect()

    def on_hide(self) -> None:
        pass

    # ------------------------------------------------------------------
    # 模块适配
    # ------------------------------------------------------------------
    def _load_module(self) -> bool:
        if self._module is not None:
            return True
        if self._module_error:
            return False
        try:
            import core.autoupdate as module  # noqa: F401

            self._module = module
            self._functions["detect"] = self._find_function(module, DETECT_NAMES)
            self._functions["apply"] = self._find_function(module, APPLY_NAMES)
            self._functions["restore"] = self._find_function(module, RESTORE_NAMES)
            missing = [name for name in REQUIRED_GROUPS if self._functions[name] is None]
            if missing:
                raise RuntimeError(
                    "模块接口不完整，缺少：" + ", ".join(f"{name}({ '/'.join(self._candidate_names(name)) })" for name in missing)
                )
            self._module_badge.set("已就绪", "success")
            self._log.log("自动更新防护模块已加载（core.autoupdate）", "success")
            try:
                self._module_badge.master.update_idletasks()
            except tk.TclError:
                pass
            self._apply_button.configure(state="normal")
            self._restore_button.configure(state="normal")
            return True
        except Exception as exc:  # noqa: BLE001 - 模块未就绪时降级
            self._module_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("自动更新模块未就绪：%s", self._module_error)
            self._module_badge.set("未就绪", "warning")
            self._module_banner.configure(
                text=f"自动更新防护模块未就绪：{self._module_error}\n"
                "该功能需要 core/autoupdate.py（patch-core 提供）。模块就绪后重新打开本页即可自动加载。"
            )
            self._module_banner.pack(fill="x", pady=(theme.px(8), 0))
            self._log.log(f"自动更新模块未就绪：{self._module_error}", "warning")
            self._apply_button.configure(state="disabled")
            self._restore_button.configure(state="disabled")
            try:
                self._dir_label.configure(
                    text="未检测（模块未就绪）", fg=theme.MUTED
                )
                self._status_label.configure(text="模块未就绪")
            except tk.TclError:
                pass
            return False

    @staticmethod
    def _candidate_names(kind: str) -> tuple[str, ...]:
        return {
            "detect": DETECT_NAMES,
            "apply": APPLY_NAMES,
            "restore": RESTORE_NAMES,
        }.get(kind, ())

    @staticmethod
    def _find_function(module, names: tuple[str, ...]) -> Callable | None:
        for name in names:
            func = getattr(module, name, None)
            if callable(func):
                return func
        return None

    def _detect_main_dir(self) -> str:
        """获取 EasiCamera Main 目录（优先 patch_engine，其次 sysinfo）。"""
        try:
            import core.patch_engine as engine

            found = engine.find_main_dir(str(settings.get("install_dir") or "").strip() or None)
            if found:
                return str(found)
        except Exception:  # noqa: BLE001
            pass
        try:
            return sysinfo.detect_install_dir() or ""
        except Exception:  # noqa: BLE001
            return ""

    def _invoke(self, kind: str, *_unused):
        """按函数签名调用模块函数（自动决定是否传入 Main 目录）。"""
        func = self._functions.get(kind)
        if func is None:
            raise RuntimeError(f"模块缺少 {kind} 接口")
        main_dir = self._main_dir
        try:
            signature = inspect.signature(func)
            parameters = signature.parameters
        except (TypeError, ValueError):
            parameters = {}
        # 接口若声明 main_dir 参数（patch-core 的 detect/apply/restore 均如此），按关键字传入
        if "main_dir" in parameters:
            try:
                return func(main_dir=main_dir or None)
            except TypeError:
                pass
        required = [
            param
            for param in parameters.values()
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD) and param.default is param.empty
        ]
        if not required:
            return func()
        if len(required) == 1:
            return func(main_dir or None)
        return func(main_dir or None, False)

    # ------------------------------------------------------------------
    # 状态检测
    # ------------------------------------------------------------------
    def _load_module_and_detect(self) -> None:
        if not self._load_module():
            return
        self.detect_status()

    def detect_status(self) -> None:
        if self._busy:
            return
        if self._module is None and not self._load_module():
            return
        self._main_dir = self._detect_main_dir()

        def _on_dir(main_dir: str) -> None:
            self._main_dir = main_dir or ""
            self._dir_label.configure(
                text=self._main_dir or "未检测到（部分操作可能无法定位更新器路径）",
                fg=theme.TEXT if self._main_dir else theme.WARNING,
            )
            self._set_busy(True, "正在检测自动更新防护状态…")
            self._log.log(f"EasiCamera Main 目录：{self._main_dir or '未检测到'}", "muted")

            def _work():
                return self._invoke("detect")

            common.run_async(
                self,
                _work,
                on_success=self._render_detect_result,
                on_error=lambda exc: self._op_failed(exc, "检测"),
                name="autoupdate-detect",
            )

        if self._main_dir:
            _on_dir(self._main_dir)
        else:
            common.run_async(
                self,
                self._detect_main_dir,
                on_success=_on_dir,
                on_error=lambda exc: self._op_failed(exc, "检测目录"),
                name="autoupdate-dir",
            )

    def _render_detect_result(self, result: Any) -> None:
        self._set_busy(False)
        self._log.log("检测完成，结果如下：", "primary")
        summary_text = self._summarize_detect(result)
        if summary_text:
            self._log.log(summary_text, "info")
        if isinstance(result, (list, tuple)):
            self._render_detect_items(list(result))
        else:
            for line in self._format_result(result):
                self._log.log(line, "info")
        try:
            self._status_label.configure(text="检测完成")
        except tk.TclError:
            pass
        self.set_status("自动更新防护状态检测完成", "success", 4000)

    #: 状态项状态 -> (展示前缀, 日志颜色)
    _STATUS_STYLE = {
        "blocked": ("[已阻止]", "success"),
        "active": ("[未处理]", "warning"),
        "missing": ("[不存在]", "muted"),
        "not_installed": ("[未安装]", "muted"),
        "shared": ("[共享·跳过]", "primary"),
        "unknown": ("[未知]", "muted"),
    }

    def _render_detect_items(self, items: list) -> None:
        """把 detect() 的状态项列表渲染成简洁的中文清单。"""
        if not items:
            self._log.log("（没有检测到任何状态项）", "muted")
            return
        for item in items:
            if not isinstance(item, dict):
                self._log.log(str(item), "info")
                continue
            status = str(item.get("status") or "unknown")
            prefix, level = self._STATUS_STYLE.get(status, (f"[{status}]", "info"))
            name = item.get("name") or item.get("id") or "未知项"
            label = item.get("label") or status
            detail = str(item.get("detail") or "").strip()
            extra = "（需要管理员）" if item.get("requires_admin") and item.get("actionable") else ""
            line = f"{prefix} {name}：{label}{extra}"
            if detail:
                line += f" —— {detail}"
            self._log.log(line, level)

    def _render_action_result(self, result: Any, action: str) -> None:
        """渲染 apply()/restore() 返回的 dict 结果（ok/message/results[]）。"""
        if not isinstance(result, dict):
            for line in self._format_result(result):
                self._log.log(line, "info")
            return
        ok = bool(result.get("ok", False))
        message = str(result.get("message") or ("操作完成" if ok else "操作失败"))
        self._log.log(f"{action}结果：{message}", "success" if ok else "error")
        changed = result.get("changed")
        if changed:
            self._log.log(f"  已修改 {len(changed)} 项：{', '.join(str(x) for x in changed)}", "muted")
        if result.get("needs_restart_hint"):
            self._log.log("  建议重新启动 EasiCamera / 电脑以让改动完全生效。", "warning")
        results = result.get("results")
        if isinstance(results, (list, tuple)):
            for item in results:
                if not isinstance(item, dict):
                    self._log.log(f"  {item}", "muted")
                    continue
                name = item.get("name") or item.get("id") or "操作项"
                item_ok = bool(item.get("ok", False))
                skipped = bool(item.get("skipped", False))
                requires_admin = bool(item.get("requires_admin", False))
                item_message = str(item.get("message") or "")
                if skipped:
                    level, flag = "muted", "[跳过]"
                elif item_ok:
                    level, flag = "success", "[成功]"
                else:
                    level, flag = "error", "[失败]"
                suffix = "（需要管理员）" if requires_admin else ""
                self._log.log(f"  {flag} {name}：{item_message}{suffix}", level)

    def _summarize_detect(self, result: Any) -> str:
        """对 detect() 的状态项列表生成一行摘要（若模块提供 summarize）。"""
        if not isinstance(result, (list, tuple)):
            return ""
        summarize = getattr(self._module, "summarize", None)
        if not callable(summarize):
            return f"共检测到 {len(result)} 个状态项"
        try:
            summary = summarize(list(result))
        except Exception:  # noqa: BLE001 - 摘要失败不影响明细展示
            return f"共检测到 {len(result)} 个状态项"
        if not isinstance(summary, dict):
            return f"共检测到 {len(result)} 个状态项"
        if summary.get("installed") is False:
            return "未检测到 EasiCamera 安装，无需破坏自动更新。"
        parts = [
            f"状态项 {summary.get('total', len(result))} 个",
            f"可处理 {summary.get('actionable_total', 0)} 个",
            f"已阻止 {summary.get('blocked', 0)} 个",
        ]
        if summary.get("requires_admin"):
            parts.append("部分操作需要管理员权限")
        return "摘要：" + "，".join(parts)

    # ------------------------------------------------------------------
    # 执行 / 还原
    # ------------------------------------------------------------------
    def apply_protection(self) -> None:
        self._run_action(
            "apply",
            "执行防护",
            "确定要执行自动更新防护吗？\n\n将重命名/禁用 EasiCamera 的更新器，并禁用相关计划任务、"
            "清理更新缓存。操作可还原，但建议先关闭 EasiCamera。",
        )

    def restore_protection(self) -> None:
        self._run_action(
            "restore",
            "还原防护",
            "确定要还原自动更新防护吗？\n\n将恢复被重命名的更新器文件并重新启用相关计划任务/服务。",
        )

    def _run_action(self, kind: str, label: str, confirm_message: str) -> None:
        if self._busy:
            return
        if self._module is None and not self._load_module():
            common.show_warning(self, f"{label}不可用", "自动更新防护模块尚未就绪（core/autoupdate.py 未提供）。")
            return
        if not self._main_dir:
            self._main_dir = self._detect_main_dir()
        if not common.ask_yes_no(self, f"确认{label}？", confirm_message):
            return
        self._set_busy(True, f"正在{label}…")
        self._log.log(f"开始{label}…", "primary")

        def _work():
            return self._invoke(kind)

        def _done(result: Any) -> None:
            self._set_busy(False)
            self._log.log(f"{label}完成，结果如下：", "success")
            self._render_action_result(result, label)
            self.set_status(f"{label}完成", "success", 5000)
            try:
                self._status_label.configure(text=f"{label}完成")
            except tk.TclError:
                pass
            # 执行/还原后重新检测状态
            if self._module is not None:
                self.after(800, self.detect_status)

        def _failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._log.log(f"{label}失败：{exc.__class__.__name__}: {exc}", "error")
            message = str(exc)
            if any(keyword in message for keyword in ("管理员", "权限", "拒绝访问", "Access is denied", "WinError 5")):
                self._log.log("提示：该操作需要管理员权限，请关闭本程序后右键「以管理员身份运行」再试。", "warning")
                common.show_warning(
                    self,
                    "需要管理员权限",
                    f"{label}失败：权限不足。\n\n请关闭本程序后，右键选择「以管理员身份运行」再试。\n\n详细信息：{message}",
                )
            else:
                common.show_error(self, f"{label}失败", message)
            self.set_status(f"{label}失败：{message}", "error", 6000)

        common.run_async(self, _work, on_success=_done, on_error=_failed, name=f"autoupdate-{kind}")

    # ------------------------------------------------------------------
    # 结果格式化
    # ------------------------------------------------------------------
    def _format_result(self, result: Any, depth: int = 0) -> list[str]:
        """把模块返回值（dict/list/dataclass/对象/字符串）转成可读文本行。"""
        indent = "  " * depth
        if result is None:
            return [indent + "（操作完成，无返回信息）"]
        if isinstance(result, bool):
            return [indent + ("成功" if result else "失败")]
        if isinstance(result, str):
            return [indent + line for line in result.splitlines() or [""]]
        if isinstance(result, dict):
            lines: list[str] = []
            for key, value in result.items():
                label = str(key)
                if isinstance(value, (dict, list, tuple)) and value:
                    lines.append(f"{indent}{label}：")
                    lines.extend(self._format_result(value, depth + 1))
                elif isinstance(value, (dict, list, tuple)):
                    lines.append(f"{indent}{label}：（空）")
                else:
                    lines.append(f"{indent}{label}：{self._format_scalar(value)}")
            return lines or [indent + "（空结果）"]
        if isinstance(result, (list, tuple, set)):
            lines = []
            for index, item in enumerate(result, start=1):
                if isinstance(item, (dict, list, tuple)):
                    lines.append(f"{indent}[{index}]")
                    lines.extend(self._format_result(item, depth + 1))
                else:
                    lines.append(f"{indent}[{index}] {self._format_scalar(item)}")
            return lines or [indent + "（空列表）"]
        if is_dataclass(result) and not isinstance(result, type):
            try:
                return self._format_result(asdict(result), depth)
            except Exception:  # noqa: BLE001
                pass
        to_dict = getattr(result, "to_dict", None)
        if callable(to_dict):
            try:
                return self._format_result(to_dict(), depth)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(result, "__dict__"):
            try:
                public = {k: v for k, v in vars(result).items() if not k.startswith("_")}
                if public:
                    return self._format_result(public, depth)
            except Exception:  # noqa: BLE001
                pass
        return [indent + str(result)]

    @staticmethod
    def _format_scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "是" if value else "否"
        if value is None:
            return "—"
        return str(value)

    # ------------------------------------------------------------------
    # 通用
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, status_text: str = "") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self._detect_button, self._apply_button, self._restore_button):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        try:
            if busy:
                self._progress.pack(side="left", padx=(theme.px(8), 0))
                self._progress.start(12)
                if status_text:
                    self.set_status(status_text, "primary")
            else:
                self._progress.stop()
                self._progress.pack_forget()
        except tk.TclError:
            pass
