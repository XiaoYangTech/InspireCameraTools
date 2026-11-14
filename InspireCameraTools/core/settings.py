"""应用配置模块：JSON 持久化。

配置保存在 ``%APPDATA%/InspireCameraTools/config.json``，写入使用「临时文件 + 原子替换」，
避免异常退出导致配置文件损坏。所有读取接口都带默认值兜底，配置文件缺失/损坏不影响启动。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

APP_NAME = "InspireCameraTools"
APP_NAME_CN = "亿方展台管家"
APP_VERSION = "1.1.1"
ORG_NAME = "InspireCameraTools"

#: 默认配置。新增配置项只需在这里加默认值，旧配置文件自动兼容。
DEFAULTS: dict[str, Any] = {
    # 安装目录（EasiCamera 的 Main 目录）；空字符串表示自动探测
    "install_dir": "",
    # 历史版本下载目录；空字符串表示 ~/Downloads/InspireCameraTools
    "download_dir": "",
    # 一键相机开关（用户点击开关时持久化，用于后台模式恢复）
    "camera_enabled": False,
    # 一键相机目标按键
    "camera_target_key": "F12",
    # 一键相机防抖（毫秒）
    "camera_debounce_ms": 800,
    # 是否注册开机自启
    "camera_autostart": False,
    # 主题名（ttkbootstrap）
    "theme": "bootstrap-light",
    # 窗口尺寸记忆
    "window_geometry": "",
    # 一键补丁备份根目录；空表示默认（Main 目录同级 _InspirePatchBackup）
    "patch_backup_root": "",
    # HID 监听时自动应答心跳
    "hid_heartbeat_reply": True,
    # 亿方智云：匿名设备标识（安装后生成一次并持久化；仅用于匿名统计）
    "cloud_device_key": "",
    # 已展示过的启动弹窗（{弹窗id: 日期}，用于「今日不再显示」）
    "cloud_popup_seen": {},
    # 用户选择跳过的更新版本（避免每次启动重复提示同一版本）
    "cloud_skip_version": "",
    # 最近一次匿名上报时间（Unix 秒）
    "cloud_last_ping": 0,
}

_lock = threading.RLock()
_cache: dict[str, Any] | None = None


def app_data_dir() -> Path:
    """返回应用数据目录（自动创建）。"""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path.home() / ("." + APP_NAME)
        path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    """日志目录（自动创建）。"""
    path = app_data_dir() / "logs"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def _read_disk() -> dict[str, Any]:
    path = config_path()
    data: dict[str, Any] = {}
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                data = raw
    except (OSError, ValueError):
        # 配置损坏时静默回退默认值，并把损坏文件备份一份便于排查
        try:
            if path.is_file():
                path.with_suffix(".json.bad").write_bytes(path.read_bytes())
        except OSError:
            pass
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def load(reload: bool = False) -> dict[str, Any]:
    """读取全部配置（首次调用读盘，之后读内存缓存）。"""
    global _cache
    with _lock:
        if _cache is None or reload:
            _cache = _read_disk()
        return dict(_cache)


def get(key: str, default: Any = None) -> Any:
    """读取单个配置项。"""
    with _lock:
        data = load()
        if key in data:
            return data[key]
        return DEFAULTS.get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001 - 与 get 对称，语义清晰
    """写入单个配置项并立即持久化。"""
    with _lock:
        data = load()
        data[key] = value
        _write(data)


def update(**kwargs: Any) -> None:
    """批量更新若干配置项并持久化。"""
    with _lock:
        data = load()
        data.update(kwargs)
        _write(data)


def reset() -> None:
    """恢复默认配置并落盘。"""
    with _lock:
        _write(dict(DEFAULTS))


def _write(data: dict[str, Any]) -> None:
    global _cache
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    path = config_path()
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        _cache = merged
    except OSError:
        _cache = merged
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def default_download_dir() -> Path:
    """历史版本下载默认目录：~/Downloads/InspireCameraTools（遵循系统「下载」目录）。"""
    configured = str(get("download_dir") or "").strip()
    if configured:
        return Path(configured)
    home = Path.home()
    # Windows 中文系统下载目录通常就是 ~/Downloads，这里优先用已知存在的中文/英文候选
    for name in ("Downloads", "下载"):
        cand = home / name
        if cand.is_dir():
            return cand / APP_NAME
    return home / "Downloads" / APP_NAME
