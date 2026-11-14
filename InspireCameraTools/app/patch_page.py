"""一键补丁页：检测 EasiCamera 版本、选择功能、应用/恢复字节级补丁。

引擎接口见 ``analysis/CONTRACT.md`` §3.3（core.patch_engine，patch-core 实现）。
本页对引擎做延迟导入：引擎文件缺失/导入异常时优雅降级为「补丁引擎未就绪」，
不影响应用启动与其它功能。
"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from pathlib import Path
from typing import Any

import ttkbootstrap as tb

from core import settings, sysinfo

from . import common, theme
from .base_page import BasePage

log = logging.getLogger(__name__)

#: 引擎不可用时的功能定义兜底（与契约 §3.1 / core/features.py 保持一致）
FALLBACK_FEATURES: list[dict[str, Any]] = [
    {
        "id": "no_third_party_block",
        "name": "去除新版本不允许使用第三方展台的限制",
        "description": "解除新版对非希沃展台的屏蔽，让普通 USB 摄像头/第三方展台也能出画面。",
        "risk": None,
        "default_on": True,
    },
    {
        "id": "force_scan",
        "name": "去除第三方展台不能用扫描的限制",
        "description": "强制显示「扫描 / 文档增强」工具按钮，不再按希沃机型白名单隐藏。",
        "risk": None,
        "default_on": True,
    },
    {
        "id": "hide_login",
        "name": "去除登录按钮",
        "description": "隐藏主界面右上角的登录 / 头像入口（仅隐藏入口，不改变登录逻辑本身）。",
        "risk": None,
        "default_on": True,
    },
    {
        "id": "disable_freeze",
        "name": "去除兆芯/海光锁画面限制",
        "description": "取消国产化芯片机器进入批注等模式时自动冻结画面，恢复实时画面。",
        "risk": "warning:国产化平台（兆芯/海光）可能出现批注卡顿",
        "default_on": False,
    },
    {
        "id": "enable_hygon_freeze",
        "name": "为海光处理器加入锁画面功能（修复批注卡顿）",
        "description": "让程序把本机识别为国产化芯片，启用点击画笔自动冻结画面，缓解海光平台批注卡顿。",
        "risk": "warning:补丁会强制启用冻结逻辑，非海光/兆芯机器可能出现画面冻结，建议仅在卡顿时使用",
        "default_on": False,
    },
    {
        "id": "remove_english",
        "name": "去除英文批改",
        "description": "移除英文批改相关入口，界面更简洁（不改变其他批改功能）。",
        "risk": None,
        "default_on": True,
    },
    {
        "id": "remove_ocr",
        "name": "去除OCR（智能识别）",
        "description": "隐藏「智能识别 / 口算批改」等 OCR 入口，避免误触与弹出。",
        "risk": None,
        "default_on": True,
    },
    {
        "id": "disable_ai_key",
        "name": "禁用展台AI按键",
        "description": "屏蔽展台硬件 AI 按键（HID 命令 13）触发智能识别 / AI 菜单。",
        "risk": None,
        "default_on": True,
    },
]


def _risk_text(risk: str | None) -> str:
    """把规则里的 risk 字段（warning:xxx / warn:xxx）转换为提示文案。"""
    if not risk:
        return ""
    text = str(risk)
    for prefix in ("warning:", "warn:"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text.strip()


def normalize_main_dir_input(raw: str | None) -> str | None:
    r"""把用户粘贴/输入的路径规整成 EasiCamera 的 Main 目录。

    支持：
    * 资源管理器「复制路径」带引号/尾部反斜杠；
    * file:///C:/... 形式；
    * 直接粘贴 EasiCamera.exe / 任意 DLL 文件路径（取所在目录）；
    * 粘贴版本目录（...\EasiCamera_2.1.0.4419）或安装根目录（自动向下找 Main）；
    * 粘贴 Main 目录本身（原样返回）。
    """
    text = (raw or "").strip()
    if not text:
        return None
    # 去掉成对引号（可能反复出现）与首尾单/双引号
    for _ in range(3):
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1]
        else:
            break
    text = text.strip().strip("\"'").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("file:///"):
        text = text[8:].replace("/", "\\").lstrip("\\")
    text = os.path.expandvars(os.path.expanduser(text))
    text = text.replace("/", "\\").rstrip("\\")
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
        # 安装根目录（下含 EasiCamera_<版本>\Main）或类似一层子目录
        try:
            for child in list(path.iterdir())[:20]:
                if not child.is_dir():
                    continue
                candidates.append(child / "Main")
                candidates.append(child) if child.name.lower().startswith("easicamera") else None
        except OSError:
            pass
    for candidate in candidates:
        try:
            if (candidate / "EasiCamera.UI.dll").is_file() and (candidate / "EasiCamera.exe").is_file():
                return str(candidate)
        except OSError:
            continue
    return str(path) if path.is_dir() else text


class PatchPage(BasePage):
    """一键补丁页面。"""

    title = "一键补丁"
    subtitle = "检测 EasiCamera 版本，勾选功能后一键应用字节级补丁（应用前请先关闭 EasiCamera）"
    icon = "patch"

    def __init__(self, master: tk.Misc, app) -> None:
        self._engine: Any = None
        self._engine_error: str = ""
        self._features: list[Any] = []
        self._main_dir: str = ""
        self._detected: Any = None
        self._availabilities: dict[str, Any] = {}
        self._rows: dict[str, dict[str, Any]] = {}
        self._busy = False
        self._detect_loaded = False
        self._backups: list[str] = []
        self._pending_detection: tuple[str | None, bool] | None = None
        self._detect_after: str | None = None
        self._syncing_path = False
        super().__init__(master, app)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def build_body(self) -> None:
        self.add_header_button("重新检测", self.refresh_detection, bootstyle="secondary-outline")
        self.body.grid_columnconfigure(0, weight=3, uniform="patch-cols")
        self.body.grid_columnconfigure(1, weight=2, uniform="patch-cols")
        self.body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(self.body, bg=theme.PAGE_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, theme.px(14)))
        right = tk.Frame(self.body, bg=theme.PAGE_BG)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_directory_card(left)
        self._build_features_card(left)
        self._build_actions(left)
        self._build_log_card(right)

    # ---------- 目录 / 版本卡片 ----------
    def _build_directory_card(self, parent: tk.Misc) -> None:
        card = common.Card(
            parent, title="安装目录与版本", subtitle="自动探测 EasiCamera 的 Main 目录，也可手动指定", icon="patch"
        )
        card.pack(fill="x", pady=(0, theme.px(12)))

        path_row = tk.Frame(card.body, bg=theme.WHITE)
        path_row.pack(fill="x")
        tk.Label(path_row, text="Main 目录", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)).pack(
            side="left", padx=(0, theme.px(8))
        )
        self._path_var = tk.StringVar(value="")
        self._path_entry = tb.Entry(path_row, textvariable=self._path_var, bootstyle="secondary")
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
        path_hint.pack(fill="x", pady=(theme.px(6), 0))
        self._browse_button = tb.Button(
            path_row, text="浏览…", bootstyle="secondary-outline", command=self._browse_dir, cursor="hand2", width=7
        )
        self._browse_button.pack(side="left", padx=(0, theme.px(6)))
        self._auto_button = tb.Button(
            path_row, text="自动探测", bootstyle="secondary-outline", command=self._auto_detect, cursor="hand2", width=8
        )
        self._auto_button.pack(side="left")

        info_row = tk.Frame(card.body, bg=theme.WHITE)
        info_row.pack(fill="x", pady=(theme.px(10), 0))
        self._version_badge = common.Badge(info_row, text="未检测", kind="secondary")
        self._version_badge.pack(side="left", padx=(0, theme.px(10)))
        self._version_label = tk.Label(
            info_row,
            text="尚未检测安装目录",
            bg=theme.WHITE,
            fg=theme.TEXT,
            font=theme.font(11),
            anchor="w",
        )
        self._version_label.pack(side="left", fill="x", expand=True)

        self._engine_banner = tk.Label(
            card.body,
            text="",
            bg=theme.WARNING_BG,
            fg=theme.WARNING,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(620),
            padx=theme.px(10),
            pady=theme.px(6),
        )
        self._engine_banner.pack(fill="x", pady=(theme.px(10), 0))
        self._engine_banner.pack_forget()

    # ---------- 功能列表卡片 ----------
    def _build_features_card(self, parent: tk.Misc) -> None:
        self._features_card = common.Card(
            parent,
            title="功能列表",
            subtitle="勾选需要应用的功能；灰色项表示该版本不支持或已打过补丁",
            icon="settings",
            padding=theme.px(14),
        )
        self._features_card.pack(fill="both", expand=True)
        header_right = self._features_card.header_right
        if header_right is not None:
            self._count_label = tk.Label(
                header_right, text="已选 0 项", bg=theme.WHITE, fg=theme.MUTED, font=theme.font(10)
            )
            self._count_label.pack(side="right", padx=(theme.px(8), 0))
            tb.Button(
                header_right, text="反选", bootstyle="link", command=self._invert_selection, cursor="hand2"
            ).pack(side="right")
            tb.Button(
                header_right, text="全选", bootstyle="link", command=self._select_all, cursor="hand2"
            ).pack(side="right")

        self._list_scroll = common.ScrollFrame(self._features_card.body, bg=theme.WHITE)
        self._list_scroll.pack(fill="both", expand=True)
        self._list_body = self._list_scroll.inner
        feature_defs = self._load_feature_defs()
        for index, feature in enumerate(feature_defs):
            self._create_feature_row(index, feature)

    def _load_feature_defs(self) -> list[Any]:
        """读取功能定义：优先 core.features，失败则使用内置兜底列表。"""
        try:
            from core import features as features_module

            return list(features_module.FEATURES)
        except Exception as exc:  # noqa: BLE001 - 引擎文件缺失时允许降级
            log.warning("core.features 不可用，使用内置功能定义：%s", exc)
            return [self._FallbackFeature(**item) for item in FALLBACK_FEATURES]

    class _FallbackFeature:
        """内置兜底功能对象（与 core.features.Feature 字段兼容）。"""

        def __init__(self, **kwargs) -> None:
            self.id = kwargs["id"]
            self.name = kwargs["name"]
            self.description = kwargs["description"]
            self.risk = kwargs.get("risk")
            self.default_on = bool(kwargs.get("default_on", False))

    def _create_feature_row(self, index: int, feature: Any) -> None:
        row = tk.Frame(self._list_body, bg=theme.WHITE)
        row.pack(fill="x", pady=(0, theme.px(2)))
        var = tk.BooleanVar(value=False)
        check = tb.Checkbutton(
            row,
            variable=var,
            bootstyle="round-toggle",
            command=self._update_count,
            state="disabled",
            cursor="hand2",
        )
        check.pack(side="left", anchor="n", padx=(0, theme.px(10)), pady=(theme.px(4), 0))
        # 状态徽标先靠右 pack，保证窗口变窄/高 DPI 时不会被标题文字挤掉
        badge = common.Badge(row, text="待检测", kind="secondary")
        badge.pack(side="right", anchor="n", padx=(theme.px(8), 0), pady=(theme.px(6), 0))
        text_box = tk.Frame(row, bg=theme.WHITE)
        text_box.pack(side="left", fill="x", expand=True)
        name_label = tk.Label(
            text_box,
            text=feature.name,
            bg=theme.WHITE,
            fg=theme.TEXT,
            font=theme.font(11, "bold"),
            anchor="w",
            justify="left",
            wraplength=theme.px(300),
        )
        name_label.pack(anchor="w")
        desc_label = tk.Label(
            text_box,
            text=feature.description,
            bg=theme.WHITE,
            fg=theme.MUTED,
            font=theme.font(10),
            anchor="w",
            justify="left",
            wraplength=theme.px(310),
        )
        desc_label.pack(anchor="w", pady=(1, 0))
        risk = _risk_text(getattr(feature, "risk", None))
        risk_label = tk.Label(
            text_box,
            text=f"⚠ 风险提示：{risk}" if risk else "",
            bg=theme.WHITE,
            fg=theme.WARNING,
            font=theme.font(9),
            anchor="w",
            justify="left",
            wraplength=theme.px(310),
        )
        if risk:
            risk_label.pack(anchor="w", pady=(2, 0))
        if index < 7:
            tk.Frame(self._list_body, bg=theme.BORDER, height=1).pack(fill="x", pady=(theme.px(3), theme.px(4)))
        self._rows[feature.id] = {
            "frame": row,
            "var": var,
            "check": check,
            "name": name_label,
            "desc": desc_label,
            "risk": risk_label,
            "badge": badge,
            "feature": feature,
            "reason": "",
        }

    # ---------- 操作按钮 ----------
    def _build_actions(self, parent: tk.Misc) -> None:
        actions = tk.Frame(parent, bg=theme.PAGE_BG)
        actions.pack(fill="x", pady=(theme.px(12), 0))
        self._apply_button = tb.Button(
            actions,
            text="应用所选补丁",
            bootstyle="primary",
            command=self._on_apply,
            cursor="hand2",
            state="disabled",
            width=14,
        )
        self._apply_button.pack(side="left")
        self._restore_button = tb.Button(
            actions,
            text="恢复最新备份",
            bootstyle="warning-outline",
            command=self._on_restore,
            cursor="hand2",
            state="disabled",
            width=12,
        )
        self._restore_button.pack(side="left", padx=(theme.px(8), 0))
        self._refresh_button = tb.Button(
            actions,
            text="刷新",
            bootstyle="secondary-outline",
            command=self.refresh_detection,
            cursor="hand2",
            width=8,
        )
        self._refresh_button.pack(side="left", padx=(theme.px(8), 0))
        self._progress = tb.Progressbar(actions, mode="indeterminate", bootstyle="primary-striped", length=theme.px(140))
        # 默认隐藏，执行时 pack 显示
        self._progress.pack_forget()
        self._backup_label = tk.Label(
            actions,
            text="",
            bg=theme.PAGE_BG,
            fg=theme.MUTED,
            font=theme.font(9),
            anchor="e",
        )
        self._backup_label.pack(side="right", padx=(theme.px(8), 0))

    # ---------- 日志卡片 ----------
    def _build_log_card(self, parent: tk.Misc) -> None:
        card = common.Card(parent, title="执行日志", subtitle="补丁操作的结果与错误明细", icon="download")
        card.pack(fill="both", expand=True)
        if card.header_right is not None:
            tb.Button(
                card.header_right, text="清空", bootstyle="link", command=lambda: self._log.clear(), cursor="hand2"
            ).pack(side="right")
        self._log = common.LogText(card.body, height=14)
        self._log.pack(fill="both", expand=True)
        self._log.log("等待检测安装目录…", "muted")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._ensure_engine()
        if not self._detect_loaded:
            self._detect_loaded = True
            self._start_detection()

    def refresh_detection(self) -> None:
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
        self._start_detection(normalize_main_dir_input(raw))

    def _auto_detect(self) -> None:
        self._path_var.set("")
        settings.set("install_dir", "")
        self._start_detection(None, auto=True)

    def _browse_dir(self) -> None:
        initial = self._path_var.get().strip() or str(Path.home())
        selected = common.ask_directory(self, "选择 EasiCamera 的 Main 目录", initial)
        if not selected:
            return
        self._path_var.set(selected)
        self._start_detection(selected, auto=False)

    # ------------------------------------------------------------------
    # 引擎加载 / 检测
    # ------------------------------------------------------------------
    def _ensure_engine(self) -> bool:
        """延迟导入补丁引擎。"""
        if self._engine is not None:
            return True
        if self._engine_error:
            return False
        try:
            import core.patch_engine as engine

            required = (
                "detect_version",
                "list_features",
                "apply_patches",
                "restore_backup",
                "find_main_dir",
                "is_patched",
            )
            missing = [name for name in required if not callable(getattr(engine, name, None))]
            if missing:
                raise RuntimeError("缺少接口：" + ", ".join(missing))
            self._engine = engine
            self._log.log("补丁引擎已加载（core.patch_engine）", "success")
            return True
        except Exception as exc:  # noqa: BLE001 - 引擎未就绪时降级显示
            self._engine_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("补丁引擎未就绪：%s", self._engine_error)
            self._show_engine_unavailable()
            return False

    def _show_engine_unavailable(self) -> None:
        """引擎缺失时：提示横幅 + 所有功能置灰 + 禁用应用/恢复按钮。"""
        self._engine_banner.configure(
            text=f"补丁引擎未就绪：{self._engine_error}\n"
            "「core/patch_engine.py」尚未提供或导入失败，暂时无法检测与应用补丁；"
            "历史版本下载、状态调试等功能仍可正常使用。"
        )
        self._engine_banner.pack(fill="x", pady=(theme.px(10), 0))
        self._version_badge.set("引擎未就绪", "warning")
        self._version_label.configure(text="补丁引擎未就绪，无法检测版本", fg=theme.WARNING)
        for row in self._rows.values():
            row["check"].configure(state="disabled")
            row["badge"].set("不可用", "secondary")
        self._apply_button.configure(state="disabled")
        self._restore_button.configure(state="disabled")
        self._log.log(f"补丁引擎未就绪：{self._engine_error}", "warning")

    def _start_detection(self, main_dir: str | None = None, auto: bool = False) -> None:
        if self._busy:
            # 正在检测/应用时用户再次触发：记下来，等当前任务结束自动补跑
            self._pending_detection = (main_dir, auto)
            return
        if not self._ensure_engine():
            return
        requested = normalize_main_dir_input(main_dir)
        self._set_busy(True, "正在检测 EasiCamera 安装目录…")
        engine = self._engine

        def _work() -> dict:
            data: dict[str, Any] = {"main_dir": "", "detected": None, "availabilities": {}, "errors": [], "backups": []}
            try:
                configured = requested
                if configured and not Path(configured).is_dir():
                    data["errors"].append(f"目录不存在：{configured}")
                    return data
                resolved = engine.find_main_dir(configured)
                if not resolved:
                    data["errors"].append("未自动检测到 EasiCamera 安装目录，请手动选择 Main 目录。")
                    return data
                data["main_dir"] = resolved
                detected = engine.detect_version(resolved)
                data["detected"] = detected
                if detected is None:
                    data["errors"].append("无法识别该目录下的 EasiCamera 版本（可能版本不在支持列表中）。")
                    return data
                version = getattr(detected, "version", "")
                try:
                    avail_list = engine.list_features(version, resolved)
                except TypeError:
                    avail_list = engine.list_features(version)
                data["availabilities"] = {item.feature.id: item for item in avail_list}
                data["backups"] = self._list_backups(resolved)
            except Exception as exc:  # noqa: BLE001 - 检测失败友好提示
                log.exception("检测补丁信息失败")
                data["errors"].append(f"检测失败：{exc.__class__.__name__}: {exc}")
            return data

        common.run_async(
            self,
            _work,
            on_success=lambda data: self._apply_detection(data, auto=auto),
            on_error=self._detection_error,
            name="patch-detect",
        )

    @staticmethod
    def _list_backups(main_dir: str) -> list[str]:
        """列出该 Main 目录对应的补丁备份（最新在前）。"""
        backups: list[str] = []
        roots = []
        try:
            configured_root = str(settings.get("patch_backup_root") or "").strip()
            if configured_root:
                roots.append(Path(configured_root))
        except Exception:  # noqa: BLE001
            pass
        roots.append(Path(main_dir).resolve().parent / "_InspirePatchBackup")
        seen: set[str] = set()
        for root in roots:
            try:
                if not root.is_dir():
                    continue
                for child in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
                    if child.is_dir() and str(child) not in seen:
                        seen.add(str(child))
                        backups.append(str(child))
            except OSError:
                continue
        return backups

    def _apply_detection(self, data: dict, auto: bool = False) -> None:
        self._set_busy(False)
        self._backups = data.get("backups") or []
        main_dir = data.get("main_dir") or ""
        detected = data.get("detected")
        self._main_dir = main_dir
        if main_dir:
            self._syncing_path = True
            try:
                self._path_var.set(main_dir)
            finally:
                self._syncing_path = False
            try:
                settings.set("install_dir", main_dir)
            except Exception:  # noqa: BLE001
                pass
        if not main_dir:
            self._detected = None
            self._version_badge.set("未检测到", "secondary")
            self._version_label.configure(text="未检测到 EasiCamera 安装目录", fg=theme.TEXT)
            self._reset_rows("未检测到安装目录")
            for message in data.get("errors") or []:
                self._log.log(message, "warning")
            if auto:
                self._log.log("提示：可在上方手动选择 EasiCamera 的 Main 目录。", "muted")
            self.set_status("未检测到 EasiCamera 安装目录", "warning", 5000)
            return
        if detected is None:
            self._detected = None
            self._version_badge.set("未识别", "danger")
            self._version_label.configure(text=f"已选择：{main_dir}", fg=theme.TEXT)
            self._reset_rows("该版本暂无补丁规则")
            self._log.log(f"无法识别版本：{main_dir}", "error")
            for message in data.get("errors") or []:
                self._log.log(message, "muted")
            self.set_status("无法识别 EasiCamera 版本", "warning", 5000)
            return

        self._detected = detected
        version_text = getattr(detected, "display_name", None) or getattr(detected, "version", "未知")
        matched = getattr(detected, "matched_files", None) or {}
        self._version_badge.set("已识别", "success")
        self._version_label.configure(
            text=f"版本 {version_text} · 目录 {main_dir} · 指纹匹配 {len(matched)} 个文件",
            fg=theme.TEXT,
        )
        self._log.log(f"检测完成：{version_text}（{main_dir}）", "success")
        self._apply_availabilities(data.get("availabilities") or {})
        self._update_backup_label()
        self.set_status(f"检测完成：{version_text}", "success", 3000)

    def _detection_error(self, exc: BaseException) -> None:
        self._set_busy(False)
        self._log.log(f"检测异常：{exc.__class__.__name__}: {exc}", "error")
        self.set_status(f"检测失败：{exc}", "error", 5000)

    def _reset_rows(self, reason: str) -> None:
        for row in self._rows.values():
            row["var"].set(False)
            row["check"].configure(state="disabled")
            row["badge"].set("不可用", "secondary")
            row["reason"] = reason
        self._apply_button.configure(state="disabled")
        self._restore_button.configure(state="disabled")
        self._update_count()

    def _apply_availabilities(self, availabilities: dict[str, Any]) -> None:
        self._availabilities = availabilities
        self._notify_missing_rules(availabilities)
        for feature_id, row in self._rows.items():
            availability = availabilities.get(feature_id)
            if availability is None:
                row["var"].set(False)
                row["check"].configure(state="disabled")
                row["badge"].set("不适用", "secondary")
                row["reason"] = "该功能不适用于当前版本"
                continue
            already = bool(getattr(availability, "already_patched", False))
            available = bool(getattr(availability, "available", False))
            reason = getattr(availability, "reason", None)
            if already:
                row["var"].set(False)
                row["check"].configure(state="disabled")
                row["badge"].set("已打补丁", "success")
                row["reason"] = "已应用"
            elif not available:
                row["var"].set(False)
                row["check"].configure(state="disabled")
                row["badge"].set("不可用", "secondary")
                row["reason"] = reason or "当前版本不可用"
            else:
                row["check"].configure(state="normal")
                row["badge"].set("可应用", "info")
                row["reason"] = ""
                row["var"].set(bool(getattr(row["feature"], "default_on", False)))
        self._update_count()

    def _notify_missing_rules(self, availabilities: dict[str, Any]) -> None:
        """提示“该版本缺少哪些功能的规则”，方便用户理解置灰原因。"""
        if not availabilities:
            return
        missing = [fid for fid, avail in availabilities.items() if not getattr(avail, "available", False)]
        if not missing:
            return
        names = []
        for fid in missing:
            feature = getattr(availabilities.get(fid), "feature", None)
            names.append(getattr(feature, "name", fid))
        self._log.log(f"当前版本不可用功能（{len(names)} 项）：{'；'.join(names)}", "muted")

    # ------------------------------------------------------------------
    # 选择交互
    # ------------------------------------------------------------------
    def _select_all(self) -> None:
        for row in self._rows.values():
            if str(row["check"].cget("state")) == "normal":
                row["var"].set(True)
        self._update_count()

    def _invert_selection(self) -> None:
        for row in self._rows.values():
            if str(row["check"].cget("state")) == "normal":
                row["var"].set(not row["var"].get())
        self._update_count()

    def _update_count(self) -> None:
        count = sum(1 for row in self._rows.values() if row["var"].get())
        try:
            self._count_label.configure(text=f"已选 {count} 项")
            risky = [
                row
                for row in self._rows.values()
                if row["var"].get() and _risk_text(getattr(row["feature"], "risk", None))
            ]
            self._apply_button.configure(
                state="normal" if count > 0 and not self._busy and self._detected is not None else "disabled"
            )
            if risky:
                self._apply_button.configure(bootstyle="danger")
            else:
                self._apply_button.configure(bootstyle="primary")
        except tk.TclError:
            pass

    def _selected_ids(self) -> list[str]:
        return [fid for fid, row in self._rows.items() if row["var"].get()]

    # ------------------------------------------------------------------
    # 应用 / 恢复
    # ------------------------------------------------------------------
    def _on_apply(self) -> None:
        if self._busy or not self._engine or not self._main_dir or self._detected is None:
            return
        selected = self._selected_ids()
        if not selected:
            common.show_warning(self, "未选择功能", "请至少勾选一个要应用的功能。")
            return
        engine = self._engine
        main_dir = self._main_dir
        backup_root = str(settings.get("patch_backup_root") or "").strip() or None

        risk_lines = []
        for feature_id in selected:
            row = self._rows.get(feature_id)
            if row is None:
                continue
            risk = _risk_text(getattr(row["feature"], "risk", None))
            if risk:
                risk_lines.append(f"· {row['feature'].name}\n  {risk}")
        if risk_lines:
            confirmed = common.ask_yes_no(
                self,
                "确认应用有风险的功能？",
                "你勾选了以下带风险提示的功能：\n\n"
                + "\n".join(risk_lines)
                + "\n\n补丁会自动备份原文件，可随时恢复。是否继续应用？",
            )
            if not confirmed:
                return

        self._set_busy(True, "正在检查 EasiCamera 进程…")
        engine_ok = engine

        def _check_process() -> dict:
            running = sysinfo.find_easicamera_processes()
            return {"running": running}

        def _after_process_check(result: dict) -> None:
            running = result.get("running") or []
            if running:
                self._set_busy(False)
                common.show_warning(
                    self,
                    "请先关闭 EasiCamera",
                    "检测到以下程序正在运行：\n"
                    + "\n".join(f"· {name}" for name in running)
                    + "\n\n补丁需要写入 EasiCamera 的文件，请先完全退出这些程序（包括右下角托盘图标）后再试。",
                )
                self.set_status("请先关闭 EasiCamera 后再应用补丁", "warning", 5000)
                return
            self._do_apply(engine_ok, main_dir, selected, backup_root)

        common.run_async(
            self,
            _check_process,
            on_success=_after_process_check,
            on_error=lambda exc: (self._set_busy(False), self._log.log(f"进程检查失败：{exc}", "error")),
            name="patch-process-check",
        )

    def _do_apply(self, engine, main_dir: str, selected: list[str], backup_root: str | None) -> None:
        self._set_busy(True, f"正在应用 {len(selected)} 项补丁…")
        self._log.log(f"开始应用补丁：{', '.join(selected)}", "primary")
        for feature_id in selected:
            feature = getattr(self._rows[feature_id]["feature"], "name", feature_id)
            self._log.log(f"  待应用：{feature}", "muted")

        def _work():
            return engine.apply_patches(main_dir, selected, backup_root)

        def _done(result) -> None:
            self._set_busy(False)
            self._render_result(result, "应用")
            try:
                self._start_detection(self._main_dir)
            except Exception:  # noqa: BLE001
                pass

        def _failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._log.log(f"应用补丁异常：{exc.__class__.__name__}: {exc}", "error")
            self.set_status(f"应用补丁失败：{exc}", "error", 6000)

        common.run_async(self, _work, on_success=_done, on_error=_failed, name="patch-apply")

    def _render_result(self, result: Any, action: str) -> None:
        """渲染 PatchResult（兼容对象/字典两种形态）。"""
        if result is None:
            self._log.log(f"{action}失败：引擎未返回结果", "error")
            return
        if isinstance(result, dict):
            get = result.get
        else:
            get = lambda key, default=None: getattr(result, key, default)  # noqa: E731
        ok = bool(get("ok", False))
        message = str(get("message", "") or "")
        applied = list(get("applied", []) or [])
        failed = list(get("failed", []) or [])
        backup_dir = get("backup_dir", None)
        restart_hint = bool(get("needs_restart_hint", False))
        if ok:
            self._log.log(f"{action}成功：{message or '操作完成'}", "success")
            self._log.log(f"  成功 {len(applied)} 项：{', '.join(applied) or '无'}", "success")
            if backup_dir:
                self._log.log(f"  备份目录：{backup_dir}", "muted")
                self._backups = self._list_backups(self._main_dir) if self._main_dir else self._backups
            if restart_hint:
                self._log.log("  请重新启动 EasiCamera 使补丁生效。", "warning")
            self.set_status(f"{action}成功", "success", 5000)
        else:
            self._log.log(f"{action}失败：{message or '未知错误'}", "error")
            for feature_id, reason in failed:
                feature = getattr(self._rows.get(feature_id, {}).get("feature", None), "name", feature_id)
                self._log.log(f"  {feature}：{reason}", "error")
            self.set_status(f"{action}失败：{message}", "error", 6000)
        self._update_backup_label()

    def _on_restore(self) -> None:
        if self._busy or not self._engine or not self._main_dir:
            return
        backup_dir = self._backups[0] if self._backups else ""
        if not backup_dir:
            selected = common.ask_directory(self, "选择补丁备份目录（_InspirePatchBackup 下的时间戳目录）", "")
            if not selected:
                common.show_info(self, "没有可用备份", "未找到补丁备份目录。应用补丁时会自动创建备份。")
                return
            backup_dir = selected
        if not common.ask_yes_no(
            self,
            "确认恢复备份？",
            f"将使用以下备份还原 EasiCamera 文件：\n\n{backup_dir}\n\n恢复会覆盖当前文件，建议先关闭 EasiCamera。是否继续？",
        ):
            return
        engine = self._engine
        main_dir = self._main_dir
        self._set_busy(True, "正在检查 EasiCamera 进程…")

        def _check_and_restore() -> dict:
            running = sysinfo.find_easicamera_processes()
            if running:
                return {"running": running}
            return {"running": [], "result": engine.restore_backup(main_dir, backup_dir)}

        def _done(data: dict) -> None:
            self._set_busy(False)
            running = data.get("running") or []
            if running:
                common.show_warning(
                    self,
                    "请先关闭 EasiCamera",
                    "检测到以下程序正在运行：\n" + "\n".join(f"· {name}" for name in running) + "\n\n请退出后重试。",
                )
                return
            self._log.log(f"开始恢复备份：{backup_dir}", "primary")
            self._render_result(data.get("result"), "恢复")
            try:
                self._start_detection(self._main_dir)
            except Exception:  # noqa: BLE001
                pass

        def _failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._log.log(f"恢复备份异常：{exc.__class__.__name__}: {exc}", "error")
            self.set_status(f"恢复备份失败：{exc}", "error", 6000)

        common.run_async(self, _check_and_restore, on_success=_done, on_error=_failed, name="patch-restore")

    # ------------------------------------------------------------------
    # 通用
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, status_text: str = "") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self._browse_button, self._auto_button, self._refresh_button, self._restore_button):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        try:
            if busy:
                self._apply_button.configure(state="disabled")
                self._progress.pack(side="left", padx=(theme.px(8), 0))
                self._progress.start(12)
                if status_text:
                    self.set_status(status_text, "primary")
                    self._log.log(status_text, "primary")
            else:
                self._progress.stop()
                self._progress.pack_forget()
                self._update_count()
                # 检测期间用户又点了刷新/浏览：当前任务结束后补跑
                pending = self._pending_detection
                self._pending_detection = None
                if pending is not None:
                    self.after(60, lambda p=pending: self._start_detection(*p))
        except tk.TclError:
            pass

    def _update_backup_label(self) -> None:
        try:
            if self._backups:
                latest = Path(self._backups[0]).name
                self._backup_label.configure(text=f"最新备份：{latest}")
                self._restore_button.configure(state="normal" if not self._busy else "disabled")
            else:
                self._backup_label.configure(text="暂无补丁备份")
        except tk.TclError:
            pass
