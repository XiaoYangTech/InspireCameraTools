# -*- coding: utf-8 -*-
"""破坏展台自动更新（EasiCamera 自动更新链阻断）。

契约：``analysis/CONTRACT.md`` §7。静态分析记录见
``analysis/4229_4419/autoupdate.md``（证据、IL、注册表/服务/路径）。

更新链（静态分析结论，2.0.10.4229 / 2.1.0.4419 相同）
--------------------------------------------------------
1. ``Main/EasiCamera.exe`` 启动 3 秒后由 ``AutoUpdateExtension`` 触发
   ``EasiCamera.Business.Services.AutoUpdateService.Check()``；
2. 有新版时启动 ``<VersionPath>\\Updater.exe -task check/update -type autostart/userstart ...``；
3. ``Updater.exe``（Cvte.Updater）通过 ``LibEasiUpdate.dll``（P/Invoke）请求
   ``EasiUpdate`` Windows 服务（``C:\\ProgramData\\Seewo\\Easiupdate\\easiupdate\\EasiUpdate.exe``，
   ZMQ 39171 / socket 39172）下载官方安装包到
   ``...\\easiupdate\\NginxDownload\\<AppKey>\\``；
4. 安装包静默安装到安装根目录下的新版本目录 ``EasiCamera_<版本>``，
   安装后 ``After.bat`` 调 ``UpdateFix.exe /S``（写注册表 VersionPath/ActualExePath、
   加防火墙规则、清理旧版本）、``Main\\EasiCamera.UpdateFix.exe /S``、``GuardianUpdater.exe /S``；
5. ``sweclauncher.exe`` 用注册表 ``ActualExePath`` 启动主程序；``EasiCameraGuardian.exe``
   是展台 HID/通信辅助进程（**与更新无关，绝不能禁用**）；``EasiUpdate`` 服务是希沃多产品
   共用组件（**默认不禁用**，避免影响希沃白板等其它软件）。

因此本模块的破坏策略是：**只动 EasiCamera 自己的更新器文件与缓存，不碰共享服务/主程序/启动器**。
重命名更新器可执行文件后，``AutoUpdateService`` 找不到 Updater.exe（日志 "Updater missing."），
更新链在第一步即断；官方安装包无法下载/执行，补丁不会被覆盖。

安全设计
--------
* 无 EasiCamera 安装时 :func:`detect` 返回一项 "not_installed"，:func:`apply`/:func:`restore`
  直接返回成功（幂等、不做任何写操作）；
* 所有破坏/还原操作幂等（重复执行只报告"已是目标状态/已跳过"）；
* 需要写 ``Program Files`` / ``ProgramData`` / 计划任务 / 防火墙的操作，失败时在结果里标注
  ``requires_admin=True`` 并给出中文错误，绝不静默失败；
* 只写标准库；Windows 相关 API 全部 try/except 容错，非 Windows 返回"不支持"而不是崩溃。

对外接口（app-dev 按此调用）
----------------------------
    detect() -> list[dict]          当前状态项（见下方 item 字段）
    apply(include_firewall=False) -> dict   执行；返回 ok/message/results/...
    restore() -> dict               还原
    is_admin() -> bool
    summarize(items) -> dict        汇总（已安装/已阻断数量/是否需管理员）
    INSTALLED_KEYWORDS / DISABLED_SUFFIX / SHARED_SERVICE_NAMES 等常量

item 字段::

    {
      "id": str,              # 稳定 ID（如 "updater:Updater.exe" / "cache:nginx"）
      "name": str,            # 中文名称
      "category": str,        # "install"|"updater_file"|"cache"|"task"|"service"|"registry"|"firewall"|"hosts"
      "status": str,          # "active"（更新能力可用）|"blocked"（已阻止）|"missing"|"not_installed"|"shared"|"unknown"
      "label": str,           # status 的中文展示
      "detail": str,          # 路径/说明
      "requires_admin": bool, # 变更此项是否需要管理员权限
      "actionable": bool,     # 是否由本工具管理（False=仅展示，如共享服务）
      "shared": bool,         # 是否为希沃其它产品共用组件（本工具不修改）
    }

apply()/restore() 返回::

    {
      "ok": bool,                 # 全部操作成功（含"已跳过"）
      "message": str,             # 中文摘要
      "is_admin": bool,
      "installed": bool,
      "requires_admin": bool,     # 存在因权限不足失败的操作（此时 ok=False，应提示提权）
      "needs_restart_hint": bool,
      "changed": int,             # 实际变更数量
      "results": [ {"id","name","ok","skipped","requires_admin","message"} ],
    }
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import time
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

APP_NAME = "亿方展台管家"
INSTALLED_KEYWORDS = ("easicamera", "希沃视频展台")

#: 禁用后的文件/目录后缀（还原时反向重命名）
DISABLED_SUFFIX = ".inspire-disabled"

#: EasiCamera 自己的更新器文件（相对 VersionPath 的版本目录）
UPDATER_FILES = (
    ("Updater.exe", "更新执行器（AutoUpdateService 启动它检查/执行更新）"),
    ("Update_Cam2.exe", "独立更新界面（P/Invoke LibEasiUpdate 旧式更新器）"),
    ("GuardianUpdater.exe", "安装后写回 Guardian 开机启动项"),
    ("UpdateFix.exe", "安装后修复：写注册表版本/ActualExePath、防火墙、清理旧版本"),
    (os.path.join("Main", "EasiCamera.UpdateFix.exe"), "主程序目录内安装后修复任务"),
    (os.path.join("Main", "SupportFiles", "EasiUpdateSetup.exe"), "EasiUpdate 服务安装器（共享更新服务）"),
)

#: 希沃共享更新服务（本工具不修改，避免影响希沃白板等其它产品）
SHARED_SERVICE_NAMES = ("EasiUpdate", "EasiUpdate3", "EasiUpdate3Protect", "easiupdate-nginx")

#: 共享注册表/ 服务信息键
EASIUPDATE_REG_KEYS = (
    r"SOFTWARE\Seewo\EasiUpdate",
    r"SOFTWARE\WOW6432Node\Seewo\EasiUpdate",
)
EASICAMERA_REG_KEYS = (
    r"SOFTWARE\Seewo\EasiCamera",
    r"SOFTWARE\WOW6432Node\Seewo\EasiCamera",
)

#: 计划任务名称过滤：仅处理明确属于 EasiCamera 的任务；共享任务只展示
TASK_OWN_KEYWORDS = ("easicamera", "easicam")
TASK_SHARED_KEYWORDS = ("easiupdate", "seewo")

#: 防火墙规则名（检测 + apply(include_firewall=True) 时创建）
FIREWALL_BLOCK_RULE_NAME = "InspireCameraTools-Block-EasiCamera-Update"

#: 状态文件（记录本次执行改了哪些东西，供 restore 精确还原）
STATE_FILENAME = "autoupdate_state.json"

_IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #


def is_admin() -> bool:
    """当前进程是否具有管理员权限（非 Windows 返回 False）。"""
    if not _IS_WINDOWS:
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _system_exe(name: str) -> str:
    """返回 System32 下系统程序路径（避免 PATH 污染）。"""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(root, "System32", name)


def _run_command(args: list[str], timeout: int = 20) -> tuple[int, str]:
    """运行系统命令，返回 (退出码, 输出合并)。失败不抛异常。"""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output
    except Exception as exc:  # noqa: BLE001
        return -1, "命令执行失败: %s: %s" % (type(exc).__name__, exc)


def _is_permission_error(message: str) -> bool:
    """判断命令输出是否属于权限不足（中英文系统兼容）。"""
    text = (message or "").lower()
    markers = (
        "拒绝访问",
        "access is denied",
        "access denied",
        "requires elevation",
        "权限不足",
        "permission denied",
        "winerror 5",
        "error 5",
    )
    return any(marker in text for marker in markers)


def _norm_dir(path: Any) -> Optional[str]:
    if not path:
        return None
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    text = os.path.expandvars(os.path.expanduser(str(text).strip().strip('"')))
    if not text:
        return None
    absolute = os.path.abspath(os.path.normpath(text))
    return absolute if os.path.isdir(absolute) else None


def _read_text(path: str, limit: int = 256 * 1024) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fp:
            return fp.read(limit)
    except OSError:
        return None


def _write_json(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path: str) -> Optional[dict]:
    text = _read_text(path)
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


_state_dir_override: Optional[str] = None  # 测试用：替换状态文件目录


def _state_path() -> str:
    """状态文件路径：%LOCALAPPDATA%\\InspireCameraTools\\autoupdate_state.json。"""
    base = _state_dir_override
    if not base:
        base = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "InspireCameraTools"
        )
    return os.path.join(base, STATE_FILENAME)


def _appdata_dir() -> str:
    return os.environ.get("APPDATA") or os.path.expanduser("~")


def _program_data_dir() -> str:
    return os.environ.get("ProgramData") or r"C:\ProgramData"


# --------------------------------------------------------------------------- #
# 注册表读取（只读；失败返回 None）
# --------------------------------------------------------------------------- #


def _reg_read_value(hive: int, sub_key: str, value_name: Optional[str]):
    try:
        import winreg
    except Exception:  # noqa: BLE001
        return None
    try:
        with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_READ) as key:
            data, _kind = winreg.QueryValueEx(key, value_name) if value_name else (winreg.QueryValue(key, None), 0)
            return data
    except OSError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _reg_enum_subkeys(root: int, sub_key: str) -> list[str]:
    try:
        import winreg
    except Exception:  # noqa: BLE001
        return []
    names: list[str] = []
    try:
        with winreg.OpenKey(root, sub_key, 0, winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    names.append(winreg.EnumKey(key, index))
                except OSError:
                    break
                index += 1
    except OSError:
        return []
    except Exception:  # noqa: BLE001
        return []
    return names


def _reg_app_info() -> dict:
    """从注册表读取 EasiCamera 安装信息（注册表不存在时返回空 dict）。"""
    try:
        import winreg

        hklm = winreg.HKEY_LOCAL_MACHINE
    except Exception:  # noqa: BLE001
        return {}
    info: dict = {}
    for sub_key in EASICAMERA_REG_KEYS:
        found: dict = {}
        for name, key in (
            ("version", "version"),
            ("code", "code"),
            ("install_path", "path"),
            ("version_path", "VersionPath"),
            ("actual_exe_path", "ActualExePath"),
            ("exe_path", "ExePath"),
        ):
            value = _reg_read_value(hklm, sub_key, name if name != "install_path" else "path")
            if value:
                found[key] = str(value)
        if found:
            found["registry_key"] = sub_key
            info = found
            break
    return info


def _reg_easiupdate_info() -> dict:
    """读取共享 EasiUpdate 服务安装信息。"""
    try:
        import winreg

        hklm = winreg.HKEY_LOCAL_MACHINE
    except Exception:  # noqa: BLE001
        return {}
    for sub_key in EASIUPDATE_REG_KEYS:
        path = _reg_read_value(hklm, sub_key, "path")
        if path:
            return {
                "path": str(path),
                "appkey": str(_reg_read_value(hklm, sub_key, "appkey") or ""),
                "version": str(_reg_read_value(hklm, sub_key, "version") or ""),
                "registry_key": sub_key,
            }
    return {}


def _service_registry_status(service_name: str) -> Optional[dict]:
    """从注册表读服务配置（是否存在/启动类型）。"""
    try:
        import winreg

        hklm = winreg.HKEY_LOCAL_MACHINE
    except Exception:  # noqa: BLE001
        return None
    sub_key = r"SYSTEM\CurrentControlSet\Services\%s" % service_name
    try:
        with winreg.OpenKey(hklm, sub_key, 0, winreg.KEY_READ) as key:
            start = winreg.QueryValueEx(key, "Start")[0]
            image = winreg.QueryValueEx(key, "ImagePath")[0]
            display = ""
            try:
                display = str(winreg.QueryValueEx(key, "DisplayName")[0])
            except OSError:
                display = service_name
            start = int(start)
            start_types = {0: "boot", 1: "system", 2: "auto", 3: "manual", 4: "disabled"}
            return {
                "name": service_name,
                "exists": True,
                "start": start,
                "start_label": start_types.get(start, "unknown"),
                "image_path": str(image),
                "display_name": display,
            }
    except OSError:
        return None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# 安装定位
# --------------------------------------------------------------------------- #


def _read_ini(path: str) -> dict:
    """解析简单 ini（Config.ini / Update.config）。"""
    result: dict = {}
    text = _read_text(path)
    if not text:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith((";", "#", "[", "//")):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip().lower()] = value.strip()
    return result


def _find_version_dir_near(main_dir: str) -> Optional[str]:
    """由 Main 目录向上找 ``EasiCamera_<版本>`` 版本目录。"""
    current = os.path.dirname(os.path.abspath(main_dir))
    for _ in range(3):
        name = os.path.basename(current)
        lowered = name.lower()
        if lowered.startswith("easicamera_") or lowered.startswith("easicamera-"):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def _scan_install_roots() -> list[str]:
    """扫描常见安装根目录（其下含 EasiCamera_* 版本目录）。"""
    roots: list[str] = []
    candidates: list[str] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(os.path.join(base, "Seewo", "EasiCamera"))
    for drive in ("C:", "D:", "E:", "F:"):
        for program_files in ("Program Files", "Program Files (x86)"):
            candidates.append(os.path.join(drive + os.sep, program_files, "Seewo", "EasiCamera"))
    for candidate in candidates:
        normalized = _norm_dir(candidate)
        if normalized and normalized not in roots:
            roots.append(normalized)
    return roots


def _find_version_dir_by_scan(install_root: str) -> Optional[str]:
    """在安装根目录下找带 Main\\EasiCamera.exe 的 EasiCamera_* 版本目录。"""
    try:
        entries = sorted(os.listdir(install_root), reverse=True)
    except OSError:
        return None
    for entry in entries:
        if not entry.lower().startswith("easicamera_"):
            continue
        candidate = os.path.join(install_root, entry)
        if os.path.isfile(os.path.join(candidate, "Main", "EasiCamera.exe")):
            return candidate
    # 兼容非版本化安装：安装根目录本身即版本目录
    if os.path.isfile(os.path.join(install_root, "Main", "EasiCamera.exe")):
        return install_root
    return None


class InstallInfo:
    """一次检测得到的安装信息。"""

    def __init__(self, main_dir: str, version_dir: str, app_name: str, app_key: str,
                 source: str):
        self.main_dir = main_dir
        self.version_dir = version_dir
        self.install_root = os.path.dirname(version_dir)
        self.app_name = app_name
        self.app_key = app_key
        self.source = source

    def to_dict(self) -> dict:
        return {
            "main_dir": self.main_dir,
            "version_dir": self.version_dir,
            "install_root": self.install_root,
            "app_name": self.app_name,
            "app_key": self.app_key,
            "source": self.source,
        }


def _locate(main_dir: Optional[str] = None) -> Optional[InstallInfo]:
    """定位 EasiCamera 安装。

    ``main_dir`` 可选：显式给出 Main 目录时跳过注册表/扫描（主要供测试）。
    """
    if main_dir:
        normalized = _norm_dir(main_dir)
        if normalized is None:
            return None
        version_dir = _find_version_dir_near(normalized) or os.path.dirname(normalized)
        return _build_install_info(normalized, version_dir, "explicit")

    registry = _reg_app_info()
    main_dir_candidate = _norm_dir(registry.get("actual_exe_path") and os.path.dirname(str(registry["actual_exe_path"])))
    if main_dir_candidate is None and registry.get("version_path"):
        main_dir_candidate = _norm_dir(os.path.join(str(registry["version_path"]), "Main"))
    if main_dir_candidate:
        version_dir = _norm_dir(registry.get("version_path")) or (_find_version_dir_near(main_dir_candidate) or os.path.dirname(main_dir_candidate))
        return _build_install_info(main_dir_candidate, version_dir, "registry")

    # 兜底扫描
    for root in _scan_install_roots():
        version_dir = _find_version_dir_by_scan(root)
        if version_dir:
            main_dir = os.path.join(version_dir, "Main")
            if os.path.isdir(main_dir):
                return _build_install_info(main_dir, version_dir, "scan")

    # 最后用补丁引擎的查找逻辑（它还会查注册表卸载项等）
    try:
        from . import patch_engine

        found_main = patch_engine.find_main_dir()
    except Exception:  # noqa: BLE001
        found_main = None
    if found_main:
        version_dir = _find_version_dir_near(found_main) or os.path.dirname(found_main)
        return _build_install_info(found_main, version_dir, "patch_engine")
    return None


def _build_install_info(main_dir: str, version_dir: Optional[str], source: str) -> InstallInfo:
    version_dir = version_dir or os.path.dirname(main_dir)
    app_name = "EasiCamera"
    app_key = ""
    for dirname in (version_dir, os.path.dirname(version_dir), main_dir):
        if not dirname:
            continue
        update_config = _read_ini(os.path.join(dirname, "Update.config"))
        if update_config.get("appname"):
            app_name = update_config["appname"]
        if update_config.get("appkey"):
            app_key = update_config["appkey"]
        if app_name and app_key:
            break
    return InstallInfo(main_dir, version_dir, app_name, app_key, source)


# --------------------------------------------------------------------------- #
# EasiUpdate 共享组件信息 / 缓存路径
# --------------------------------------------------------------------------- #


def _easiupdate_paths() -> dict:
    """共享 EasiUpdate 服务的目录信息。"""
    info = _reg_easiupdate_info()
    root = _norm_dir(info.get("path")) or _norm_dir(os.path.join(_program_data_dir(), "Seewo", "Easiupdate"))
    service_status = _service_registry_status("EasiUpdate")
    return {
        "root": root,
        "easiupdate_dir": os.path.join(root, "easiupdate") if root else None,
        "nginx_download_dir": os.path.join(root, "easiupdate", "NginxDownload") if root else None,
        "config_dir": os.path.join(root, "easiupdate", "ConfigDirectory") if root else None,
        "service": service_status,
        "registry": info,
    }


def _cache_paths(info: InstallInfo) -> list[dict]:
    """EasiCamera 专属更新缓存项（文件名/目录名）。"""
    paths: list[dict] = []
    easi = _easiupdate_paths()
    nginx_download = easi.get("nginx_download_dir")
    config_dir = easi.get("config_dir")
    app_key = info.app_key
    if nginx_download and app_key:
        paths.append(
            {
                "id": "cache:nginx_download",
                "name": "更新下载缓存（NginxDownload）",
                "kind": "dir",
                "path": os.path.join(nginx_download, app_key),
                "detail": "EasiUpdate 服务为 EasiCamera 下载的安装包缓存（AppKey=%s）" % app_key,
            }
        )
    if config_dir and app_key:
        paths.append(
            {
                "id": "cache:config_ini",
                "name": "更新服务配置（ConfigDirectory）",
                "kind": "file",
                "path": os.path.join(config_dir, app_key + ".ini"),
                "detail": "EasiUpdate 服务中 EasiCamera 的更新配置（AppKey=%s）" % app_key,
            }
        )
    appdata = _appdata_dir()
    if appdata and info.app_name:
        paths.append(
            {
                "id": "cache:appdata",
                "name": "应用更新缓存（%APPDATA%\\EasiUpdate）",
                "kind": "dir",
                "path": os.path.join(appdata, "EasiUpdate", info.app_name),
                "detail": "Updater/Update_Cam2 的更新工作目录与日志",
            }
        )
    return paths


# --------------------------------------------------------------------------- #
# 计划任务
# --------------------------------------------------------------------------- #


def _query_scheduled_tasks() -> list[dict]:
    """列出计划任务（schtasks /query /fo csv /nh）；失败返回空列表。"""
    if not _IS_WINDOWS:
        return []
    code, output = _run_command([_system_exe("schtasks.exe"), "/query", "/fo", "csv", "/nh"], timeout=30)
    if code != 0 or not output.strip():
        return []
    tasks: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or not line.startswith('"'):
            continue
        try:
            row = next(csv.reader(io.StringIO(line)))
        except (StopIteration, csv.Error):
            continue
        if not row:
            continue
        name = row[0].strip()
        status = row[2].strip() if len(row) > 2 else ""
        if not name or name.lower() in ("任务名", "taskname"):
            continue
        tasks.append({"name": name, "status": status})
    return tasks


def _classified_tasks() -> tuple[list[dict], list[dict]]:
    """返回 (EasiCamera 专属任务, 希沃共享任务)。专属任务可禁用，共享任务只展示。"""
    owned: list[dict] = []
    shared: list[dict] = []
    for task in _query_scheduled_tasks():
        name = task["name"].lower()
        if any(keyword in name for keyword in TASK_OWN_KEYWORDS):
            owned.append(task)
        elif any(keyword in name for keyword in TASK_SHARED_KEYWORDS):
            shared.append(task)
    return owned, shared


def _is_task_enabled(task_name: str) -> Optional[bool]:
    """查询任务是否启用；查询失败返回 None。"""
    if not _IS_WINDOWS:
        return None
    code, output = _run_command([_system_exe("schtasks.exe"), "/query", "/tn", task_name, "/xml"], timeout=20)
    if code != 0:
        return None
    text = output.lower()
    if "<enabled>false</enabled>" in text:
        return False
    if "<enabled>true</enabled>" in text:
        return True
    return None


# --------------------------------------------------------------------------- #
# 产品专属服务（EasiCamera 自己的服务；EasiUpdate 为共享组件，不动）
# --------------------------------------------------------------------------- #


def _product_services() -> list[dict]:
    """扫描注册表服务表，返回 EasiCamera 专属服务（通常没有）。"""
    try:
        import winreg

        hklm = winreg.HKEY_LOCAL_MACHINE
    except Exception:  # noqa: BLE001
        return []
    services_root = r"SYSTEM\CurrentControlSet\Services"
    result: list[dict] = []
    for name in _reg_enum_subkeys(hklm, services_root):
        if name in SHARED_SERVICE_NAMES:
            continue
        status = _service_registry_status(name)
        if not status:
            continue
        image = str(status.get("image_path") or "").lower()
        display = str(status.get("display_name") or "").lower()
        if "easicamera" in image or "easicamera" in display:
            result.append(status)
    return result


# --------------------------------------------------------------------------- #
# 防火墙 / hosts（只读展示为主）
# --------------------------------------------------------------------------- #


def _firewall_rule_exists(rule_name: str) -> Optional[bool]:
    """检测指定防火墙规则是否存在；无法判断返回 None。"""
    if not _IS_WINDOWS:
        return None
    code, output = _run_command(
        [_system_exe("netsh.exe"), "advfirewall", "firewall", "show", "rule", "name=%s" % rule_name],
        timeout=20,
    )
    if code != 0:
        return False
    text = output or ""
    lowered = text.lower()
    if not text.strip():
        return False
    # 找不到规则时：中文 "没有与指定条件匹配的规则"、英文 "No rules match"
    if "没有与指定条件匹配的规则" in text or "no rules match" in lowered:
        return False
    # 找到时 netsh 会输出规则表头（中文"规则名称"/英文"Rule Name"）
    if "规则名称" in text or "rule name" in lowered:
        return True
    return None


def _hosts_related_entries() -> list[str]:
    """读取 hosts 中与希沃更新域名相关的条目（只读展示）。"""
    if not _IS_WINDOWS:
        return []
    hosts_path = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "drivers", "etc", "hosts")
    text = _read_text(hosts_path)
    if not text:
        return []
    keywords = ("easicamera", "easiupdate", "cvte", "seewo", "myou")
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        if any(keyword in lowered for keyword in keywords):
            entries.append(stripped)
    return entries


# --------------------------------------------------------------------------- #
# 对外：检测
# --------------------------------------------------------------------------- #


def _item(item_id: str, name: str, category: str, status: str, label: str,
          detail: str, requires_admin: bool = False, actionable: bool = True,
          shared: bool = False) -> dict:
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "status": status,
        "label": label,
        "detail": detail,
        "requires_admin": requires_admin,
        "actionable": actionable,
        "shared": shared,
    }


def _updater_file_items(info: InstallInfo) -> list[dict]:
    items: list[dict] = []
    for relative, description in UPDATER_FILES:
        path = os.path.join(info.version_dir, relative)
        disabled_path = path + DISABLED_SUFFIX
        writable = os.access(os.path.dirname(path), os.W_OK)
        if os.path.isfile(disabled_path) and not os.path.isfile(path):
            status, label = "blocked", "已禁用（已阻止更新）"
        elif os.path.isfile(path):
            status, label = "active", "启用（可自动更新）"
        elif os.path.isfile(disabled_path):
            status, label = "blocked", "已禁用（已阻止更新）"
        else:
            status, label = "missing", "不存在"
        detail = "%s：%s" % (description, path)
        items.append(
            _item(
                item_id="updater_file:%s" % relative.replace("\\", "/"),
                name="更新器文件 %s" % os.path.basename(relative),
                category="updater_file",
                status=status,
                label=label,
                detail=detail,
                requires_admin=not writable and status == "active",
                actionable=True,
            )
        )
    return items


def _cache_items(info: InstallInfo) -> list[dict]:
    items: list[dict] = []
    for cache in _cache_paths(info):
        path = cache["path"]
        disabled = path + DISABLED_SUFFIX
        exists = os.path.exists(path)
        is_dir = os.path.isdir(path)
        writable = os.access(os.path.dirname(path) if not is_dir else path, os.W_OK)
        if os.path.exists(disabled) and not exists:
            status, label = "blocked", "已清理（已阻止更新）"
        elif exists:
            status, label = "active", "存在（可能含已下载的更新包）"
        elif os.path.exists(disabled):
            status, label = "blocked", "已清理（已阻止更新）"
        else:
            status, label = "missing", "不存在"
        items.append(
            _item(
                item_id=cache["id"],
                name=cache["name"],
                category="cache",
                status=status,
                label=label,
                detail="%s：%s" % (cache["detail"], path),
                requires_admin=not writable and status == "active",
                actionable=True,
            )
        )
    return items


def _task_items() -> list[dict]:
    items: list[dict] = []
    owned, shared = _classified_tasks()
    for task in owned:
        enabled = _is_task_enabled(task["name"])
        if enabled is False:
            status, label = "blocked", "已禁用"
        else:
            status, label = "active", "启用"
        items.append(
            _item(
                item_id="task:%s" % task["name"],
                name="计划任务 %s" % task["name"],
                category="task",
                status=status,
                label=label,
                detail="schtasks 状态：%s" % (task.get("status") or "未知"),
                requires_admin=True,
                actionable=True,
            )
        )
    for task in shared:
        items.append(
            _item(
                item_id="task_shared:%s" % task["name"],
                name="希沃共享计划任务 %s" % task["name"],
                category="task",
                status="shared",
                label="共享组件（不修改）",
                detail="希沃其它产品共用，禁用它会影响其它软件；本工具不处理",
                requires_admin=True,
                actionable=False,
                shared=True,
            )
        )
    if not items:
        items.append(
            _item(
                item_id="task:none",
                name="计划任务",
                category="task",
                status="missing",
                label="未发现相关计划任务",
                detail="静态分析（Updater/UpdateFix/GuardianUpdater/After.bat）未发现创建计划任务的代码",
                requires_admin=False,
                actionable=False,
            )
        )
    return items


def _service_items() -> list[dict]:
    items: list[dict] = []
    easi = _easiupdate_paths()
    service = easi.get("service")
    if service:
        start_label = "自启动" if service["start"] == 2 else (
            "手动" if service["start"] == 3 else ("已禁用" if service["start"] == 4 else service["start_label"]))
        status = "shared"
        label = "共享组件（%s）" % start_label
        items.append(
            _item(
                item_id="service:EasiUpdate",
                name="通用更新服务 EasiUpdate",
                category="service",
                status=status,
                label=label,
                detail="希沃多产品共用更新服务（%s，%s）；禁用会影响希沃白板等其它软件，本工具只移除 EasiCamera 的更新器与缓存，不禁用该服务"
                % (service.get("image_path", ""), service.get("display_name", "")),
                requires_admin=True,
                actionable=False,
                shared=True,
            )
        )
    for service in _product_services():
        status = "blocked" if service.get("start") == 4 else "active"
        items.append(
            _item(
                item_id="service:%s" % service["name"],
                name="EasiCamera 服务 %s" % service["name"],
                category="service",
                status=status,
                label="已禁用" if status == "blocked" else "启用",
                detail=str(service.get("image_path") or ""),
                requires_admin=True,
                actionable=True,
            )
        )
    return items


def _registry_items() -> list[dict]:
    items: list[dict] = []
    info = _reg_app_info()
    if info:
        items.append(
            _item(
                item_id="registry:EasiCamera",
                name="注册表安装信息 Seewo\\EasiCamera",
                category="registry",
                status="shared",
                label="主程序运行所需（不修改）",
                detail="版本/路径信息（version=%s，VersionPath=%s）；修改会破坏启动器，本工具不处理"
                % (info.get("version", "?"), info.get("version_path", "?")),
                requires_admin=True,
                actionable=False,
                shared=True,
            )
        )
    # 开机启动项：检查 Run 键里与 EasiCamera 相关的项（Guardian 为主程序 HID 辅助，不是更新器）
    try:
        import winreg

        run_keys = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        )
        for hive, sub_key in run_keys:
            try:
                with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_READ) as key:
                    index = 0
                    while True:
                        try:
                            value_name, value_data, _kind = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        index += 1
                        combined = ("%s %s" % (value_name, value_data)).lower()
                        if any(keyword in combined for keyword in INSTALLED_KEYWORDS):
                            is_guardian = "guardian" in combined
                            items.append(
                                _item(
                                    item_id="registry:run:%s" % value_name,
                                    name="开机启动项 %s" % value_name,
                                    category="registry",
                                    status="shared",
                                    label="主程序辅助（不修改）" if is_guardian else "展示",
                                    detail="%s = %s；Guardian 是展台 HID 辅助进程，不是更新器，禁用会影响展台按键/灯光功能"
                                    % (value_name, value_data),
                                    requires_admin=True,
                                    actionable=False,
                                    shared=True,
                                )
                            )
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        pass
    return items


def _firewall_items() -> list[dict]:
    items: list[dict] = []
    exists = _firewall_rule_exists(FIREWALL_BLOCK_RULE_NAME)
    if exists:
        items.append(
            _item(
                item_id="firewall:block_rule",
                name="出站防火墙拦截规则",
                category="firewall",
                status="blocked",
                label="已添加",
                detail="规则名：%s" % FIREWALL_BLOCK_RULE_NAME,
                requires_admin=True,
                actionable=True,
            )
        )
    for name in ("EasiUpdate", "EasiUpdate-39171", "EasiUpdate-39172"):
        if _firewall_rule_exists(name):
            items.append(
                _item(
                    item_id="firewall:shared:%s" % name,
                    name="希沃共享防火墙规则 %s" % name,
                    category="firewall",
                    status="shared",
                    label="共享组件（不修改）",
                    detail="EasiUpdate 服务安装的放行规则，属于希沃共用组件",
                    requires_admin=True,
                    actionable=False,
                    shared=True,
                )
            )
    if not items:
        items.append(
            _item(
                item_id="firewall:none",
                name="防火墙规则",
                category="firewall",
                status="missing",
                label="未发现相关规则",
                detail="apply(include_firewall=True) 可添加 EasiCamera 更新器出站拦截规则（需管理员）",
                requires_admin=True,
                actionable=False,
            )
        )
    return items


def _hosts_items() -> list[dict]:
    entries = _hosts_related_entries()
    if entries:
        return [
            _item(
                item_id="hosts:entries",
                name="hosts 中的希沃域名条目",
                category="hosts",
                status="active",
                label="存在 %d 条" % len(entries),
                detail="；".join(entries[:5]),
                requires_admin=True,
                actionable=False,
            )
        ]
    return [
        _item(
            item_id="hosts:none",
            name="hosts 文件",
            category="hosts",
            status="missing",
            label="无相关条目",
            detail="本工具不修改 hosts（会同时影响希沃其它软件的联网与登录，且容易被安全软件还原）",
            requires_admin=False,
            actionable=False,
        )
    ]


def detect(main_dir: Optional[str] = None) -> list[dict]:
    """检测当前自动更新状态，返回状态项列表（每项为 dict，见模块 docstring）。

    ``main_dir`` 可选：显式指定 EasiCamera 的 Main 目录（测试/自定义路径用）；
    默认从注册表 ``Seewo\\EasiCamera`` 与常见安装目录定位。
    """
    info = _locate(main_dir)
    if info is None:
        return [
            _item(
                item_id="install",
                name="EasiCamera 安装",
                category="install",
                status="not_installed",
                label="未安装",
                detail="未检测到 EasiCamera 安装（注册表 Seewo\\EasiCamera / 常见安装目录均未找到），无需破坏自动更新",
                requires_admin=False,
                actionable=False,
            )
        ]
    items: list[dict] = [
        _item(
            item_id="install",
            name="EasiCamera 安装",
            category="install",
            status="shared",
            label="已安装",
            detail="版本目录：%s；Main：%s；定位方式：%s；AppName=%s"
            % (info.version_dir, info.main_dir, info.source, info.app_name),
            requires_admin=False,
            actionable=False,
            shared=True,
        )
    ]
    items.extend(_updater_file_items(info))
    items.extend(_cache_items(info))
    items.extend(_task_items())
    items.extend(_service_items())
    items.extend(_registry_items())
    items.extend(_firewall_items())
    items.extend(_hosts_items())
    return items


def summarize(items: list[dict]) -> dict:
    """对 :func:`detect` 结果做汇总（供 UI 状态卡片使用）。"""
    installed = not any(item["status"] == "not_installed" for item in items)
    relevant = [item for item in items if item.get("actionable", False)]
    blocked = sum(1 for item in relevant if item["status"] == "blocked")
    active = sum(1 for item in relevant if item["status"] == "active")
    return {
        "installed": installed,
        "is_admin": is_admin(),
        "total": len(items),
        "actionable_total": len(relevant),
        "blocked": blocked,
        "active": active,
        "fully_blocked": installed and active == 0 and blocked > 0,
        "requires_admin": any(item.get("requires_admin") for item in items),
    }


# --------------------------------------------------------------------------- #
# 执行 / 还原
# --------------------------------------------------------------------------- #


def _result(item_id: str, name: str, ok: bool, message: str,
            skipped: bool = False, requires_admin: bool = False) -> dict:
    return {
        "id": item_id,
        "name": name,
        "ok": ok,
        "skipped": skipped,
        "requires_admin": requires_admin,
        "message": message,
    }


def _rename_to_disabled(path: str) -> dict:
    """把文件/目录重命名为 ``*.inspire-disabled``（幂等）。"""
    disabled = path + DISABLED_SUFFIX
    if not os.path.exists(path) and os.path.exists(disabled):
        return {"changed": False, "skipped": True, "message": "已是禁用状态"}
    if not os.path.exists(path):
        return {"changed": False, "skipped": True, "message": "不存在，无需处理"}
    if os.path.exists(disabled) and path != disabled:
        return {"changed": False, "skipped": True, "message": "目标禁用名已存在，跳过"}
    try:
        os.rename(path, disabled)
        return {"changed": True, "skipped": False, "message": "已重命名为 %s" % os.path.basename(disabled)}
    except OSError as exc:
        message = "重命名失败：%s" % exc
        return {"changed": False, "skipped": False, "message": message,
                "requires_admin": _is_permission_error(message) or not os.access(os.path.dirname(path), os.W_OK)}


def _rename_back(path: str) -> dict:
    """把 ``*.inspire-disabled`` 还原为原名（幂等）。"""
    disabled = path + DISABLED_SUFFIX
    if not os.path.exists(disabled):
        if os.path.exists(path):
            return {"changed": False, "skipped": True, "message": "未禁用，无需还原"}
        return {"changed": False, "skipped": True, "message": "原文件与禁用文件都不存在"}
    if os.path.exists(path):
        return {"changed": False, "skipped": True, "message": "原名文件已存在，跳过还原"}
    try:
        os.rename(disabled, path)
        return {"changed": True, "skipped": False, "message": "已还原为 %s" % os.path.basename(path)}
    except OSError as exc:
        message = "还原失败：%s" % exc
        return {"changed": False, "skipped": False, "message": message,
                "requires_admin": _is_permission_error(message) or not os.access(os.path.dirname(path), os.W_OK)}


def _save_state(state: dict) -> Optional[str]:
    try:
        path = _state_path()
        _write_json(path, state)
        return path
    except OSError:
        return None


def _load_state() -> dict:
    return _read_json(_state_path()) or {}


def _task_needs_admin() -> bool:
    return not is_admin()


def _disable_tasks(tasks: list[dict], state: dict) -> list[dict]:
    results: list[dict] = []
    disabled_now: list[str] = []
    for task in tasks:
        name = task["name"]
        enabled = _is_task_enabled(name)
        if enabled is False:
            results.append(_result("task:%s" % name, "禁用计划任务 %s" % name, True, "已是禁用状态", skipped=True))
            continue
        code, output = _run_command(
            [_system_exe("schtasks.exe"), "/change", "/tn", name, "/disable"], timeout=30
        )
        if code == 0:
            disabled_now.append(name)
            results.append(_result("task:%s" % name, "禁用计划任务 %s" % name, True, "已禁用"))
        else:
            requires_admin = _is_permission_error(output) or _task_needs_admin()
            results.append(
                _result(
                    "task:%s" % name,
                    "禁用计划任务 %s" % name,
                    False,
                    "禁用失败（%s）：%s" % ("需要管理员权限" if requires_admin else "命令失败", output.strip()[:200]),
                    requires_admin=requires_admin,
                )
            )
    if disabled_now:
        state.setdefault("tasks_disabled", []).extend(disabled_now)
    return results


def _enable_tasks(tasks: list[str]) -> list[dict]:
    results: list[dict] = []
    for name in tasks:
        enabled = _is_task_enabled(name)
        if enabled is True:
            results.append(_result("task:%s" % name, "启用计划任务 %s" % name, True, "已是启用状态", skipped=True))
            continue
        if enabled is None:
            results.append(_result("task:%s" % name, "启用计划任务 %s" % name, True, "任务不存在，跳过", skipped=True))
            continue
        code, output = _run_command(
            [_system_exe("schtasks.exe"), "/change", "/tn", name, "/enable"], timeout=30
        )
        if code == 0:
            results.append(_result("task:%s" % name, "启用计划任务 %s" % name, True, "已启用"))
        else:
            requires_admin = _is_permission_error(output) or _task_needs_admin()
            results.append(
                _result(
                    "task:%s" % name,
                    "启用计划任务 %s" % name,
                    False,
                    "启用失败（%s）：%s" % ("需要管理员权限" if requires_admin else "命令失败", output.strip()[:200]),
                    requires_admin=requires_admin,
                )
            )
    return results


def _disable_product_services(services: list[dict], state: dict) -> list[dict]:
    results: list[dict] = []
    stopped: list[str] = []
    for service in services:
        name = service["name"]
        if service.get("start") == 4:
            results.append(_result("service:%s" % name, "禁用服务 %s" % name, True, "已是禁用状态", skipped=True))
            continue
        _run_command([_system_exe("sc.exe"), "stop", name], timeout=30)
        code, output = _run_command([_system_exe("sc.exe"), "config", name, "start=", "disabled"], timeout=30)
        if code == 0:
            stopped.append(name)
            results.append(_result("service:%s" % name, "禁用服务 %s" % name, True, "已停止并禁用"))
        else:
            requires_admin = _is_permission_error(output) or _task_needs_admin()
            results.append(
                _result(
                    "service:%s" % name,
                    "禁用服务 %s" % name,
                    False,
                    "禁用失败（%s）：%s" % ("需要管理员权限" if requires_admin else "命令失败", output.strip()[:200]),
                    requires_admin=requires_admin,
                )
            )
    if stopped:
        state.setdefault("services_disabled", []).extend(stopped)
    return results


def _enable_product_services(services: list[str]) -> list[dict]:
    results: list[dict] = []
    for name in services:
        status = _service_registry_status(name)
        if status is None:
            results.append(_result("service:%s" % name, "启用服务 %s" % name, True, "服务不存在，跳过", skipped=True))
            continue
        if status.get("start") != 4:
            results.append(_result("service:%s" % name, "启用服务 %s" % name, True, "未禁用，跳过", skipped=True))
            continue
        # 恢复为手动启动（原启动类型未知时用 demand 较安全）
        code, output = _run_command([_system_exe("sc.exe"), "config", name, "start=", "demand"], timeout=30)
        if code == 0:
            results.append(_result("service:%s" % name, "启用服务 %s" % name, True, "已恢复为手动启动"))
        else:
            requires_admin = _is_permission_error(output) or _task_needs_admin()
            results.append(
                _result(
                    "service:%s" % name,
                    "启用服务 %s" % name,
                    False,
                    "启用失败（%s）：%s" % ("需要管理员权限" if requires_admin else "命令失败", output.strip()[:200]),
                    requires_admin=requires_admin,
                )
            )
    return results


def _add_firewall_block(info: InstallInfo, state: dict) -> list[dict]:
    """给更新器程序加出站拦截规则（需管理员，失败明确提示）。"""
    if not _IS_WINDOWS:
        return [_result("firewall:block_rule", "添加出站防火墙规则", True, "非 Windows，跳过", skipped=True)]
    programs = [
        os.path.join(info.version_dir, "Updater.exe"),
        os.path.join(info.version_dir, "Update_Cam2.exe"),
    ]
    results: list[dict] = []
    rules_added: list[str] = []
    for program in programs:
        rule_name = "%s-%s" % (FIREWALL_BLOCK_RULE_NAME, os.path.basename(program))
        code, output = _run_command(
            [
                _system_exe("netsh.exe"),
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=%s" % rule_name,
                "dir=out",
                "action=block",
                "program=%s" % program,
                "enable=yes",
            ],
            timeout=30,
        )
        if code == 0:
            rules_added.append(rule_name)
            results.append(_result("firewall:%s" % rule_name, "添加出站拦截规则 %s" % rule_name, True, "已添加（出站拦截）"))
        else:
            requires_admin = _is_permission_error(output) or not is_admin()
            results.append(
                _result(
                    "firewall:%s" % rule_name,
                    "添加出站拦截规则 %s" % rule_name,
                    False,
                    "添加失败（%s）：%s" % ("需要管理员权限" if requires_admin else "命令失败", output.strip()[:200]),
                    requires_admin=requires_admin,
                )
            )
    if rules_added:
        state.setdefault("firewall_rules", []).extend(rules_added)
    return results


def _remove_firewall_rules(rule_names: list[str]) -> list[dict]:
    results: list[dict] = []
    for rule_name in rule_names:
        code, output = _run_command(
            [_system_exe("netsh.exe"), "advfirewall", "firewall", "delete", "rule", "name=%s" % rule_name],
            timeout=30,
        )
        if code == 0:
            results.append(_result("firewall:%s" % rule_name, "删除出站拦截规则 %s" % rule_name, True, "已删除"))
        else:
            requires_admin = _is_permission_error(output) or not is_admin()
            results.append(
                _result(
                    "firewall:%s" % rule_name,
                    "删除出站拦截规则 %s" % rule_name,
                    False,
                    "删除失败（%s）：%s" % ("需要管理员权限" if requires_admin else "命令失败", output.strip()[:200]),
                    requires_admin=requires_admin,
                )
            )
    return results


def _apply_common(info: Optional[InstallInfo], include_firewall: bool, restore: bool) -> dict:
    admin = is_admin()
    results: list[dict] = []
    state = _load_state() if not restore else {}
    changed = 0

    if info is None:
        return {
            "ok": True,
            "message": "未检测到 EasiCamera 安装，无需操作（不做任何修改）",
            "is_admin": admin,
            "installed": False,
            "requires_admin": False,
            "needs_restart_hint": False,
            "changed": 0,
            "results": [],
        }

    if restore:
        # 1) 更新器文件
        for relative, _description in UPDATER_FILES:
            path = os.path.join(info.version_dir, relative)
            outcome = _rename_back(path)
            results.append(
                _result(
                    "updater_file:%s" % relative.replace("\\", "/"),
                    "还原 %s" % os.path.basename(relative),
                    bool(outcome.get("changed", False)) or outcome.get("skipped", False),
                    outcome["message"],
                    skipped=outcome.get("skipped", False),
                    requires_admin=outcome.get("requires_admin", False),
                )
            )
            changed += 1 if outcome.get("changed") else 0
        # 2) 缓存
        for cache in _cache_paths(info):
            outcome = _rename_back(cache["path"])
            results.append(
                _result(
                    cache["id"],
                    "还原 %s" % cache["name"],
                    bool(outcome.get("changed", False)) or outcome.get("skipped", False),
                    outcome["message"],
                    skipped=outcome.get("skipped", False),
                    requires_admin=outcome.get("requires_admin", False),
                )
            )
            changed += 1 if outcome.get("changed") else 0
        # 3) 计划任务 / 服务 / 防火墙（按状态文件）
        if state.get("tasks_disabled"):
            task_results = _enable_tasks(state["tasks_disabled"])
            results.extend(task_results)
            changed += sum(1 for item in task_results if item["ok"] and not item["skipped"])
        if state.get("services_disabled"):
            service_results = _enable_product_services(state["services_disabled"])
            results.extend(service_results)
            changed += sum(1 for item in service_results if item["ok"] and not item["skipped"])
        if state.get("firewall_rules"):
            firewall_results = _remove_firewall_rules(state["firewall_rules"])
            results.extend(firewall_results)
            changed += sum(1 for item in firewall_results if item["ok"] and not item["skipped"])
        # 清空状态
        try:
            os.remove(_state_path())
        except OSError:
            pass
        message = "已还原 EasiCamera 自动更新相关改动（%d 项变更）" % changed
        if changed:
            message += "；下次启动 EasiCamera 后自动更新能力恢复"
    else:
        # 1) 更新器文件改名
        for relative, _description in UPDATER_FILES:
            path = os.path.join(info.version_dir, relative)
            outcome = _rename_to_disabled(path)
            results.append(
                _result(
                    "updater_file:%s" % relative.replace("\\", "/"),
                    "禁用 %s" % os.path.basename(relative),
                    bool(outcome.get("changed", False)) or outcome.get("skipped", False),
                    outcome["message"],
                    skipped=outcome.get("skipped", False),
                    requires_admin=outcome.get("requires_admin", False),
                )
            )
            changed += 1 if outcome.get("changed") else 0
            if outcome.get("changed"):
                state.setdefault("renamed", []).append(path)
        # 2) 缓存清理（改名，保留可还原）
        for cache in _cache_paths(info):
            outcome = _rename_to_disabled(cache["path"])
            results.append(
                _result(
                    cache["id"],
                    "清理 %s" % cache["name"],
                    bool(outcome.get("changed", False)) or outcome.get("skipped", False),
                    outcome["message"],
                    skipped=outcome.get("skipped", False),
                    requires_admin=outcome.get("requires_admin", False),
                )
            )
            changed += 1 if outcome.get("changed") else 0
            if outcome.get("changed"):
                state.setdefault("cache_renamed", []).append(cache["path"])
        # 3) EasiCamera 专属计划任务禁用（共享任务不动）
        owned_tasks, _shared = _classified_tasks()
        if owned_tasks:
            task_results = _disable_tasks(owned_tasks, state)
            results.extend(task_results)
            changed += sum(1 for item in task_results if item["ok"] and not item["skipped"])
        for service in _product_services():
            service_results = _disable_product_services([service], state)
            results.extend(service_results)
            changed += sum(1 for item in service_results if item["ok"] and not item["skipped"])
        # 4) 可选防火墙（需管理员）
        if include_firewall:
            firewall_results = _add_firewall_block(info, state)
            results.extend(firewall_results)
            changed += sum(1 for item in firewall_results if item["ok"] and not item["skipped"])
        state.update(
            {
                "tool": "InspireCameraTools.autoupdate",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "version_dir": info.version_dir,
                "app_name": info.app_name,
                "app_key": info.app_key,
                "include_firewall": include_firewall,
            }
        )
        _save_state(state)
        message = "已破坏 EasiCamera 自动更新：更新器文件已禁用、更新缓存已清理（%d 项变更）" % changed
        message += "；EasiUpdate 共享服务与主程序未改动；重新安装/手动修复后需重新执行"

    failed = [item for item in results if not item["ok"]]
    requires_admin = any(item.get("requires_admin") for item in failed) or (
        bool(failed) and not admin
    )
    if failed and requires_admin:
        message += "。部分操作需要管理员权限，请以管理员身份运行本程序后重试"
    elif failed:
        message += "。%d 项操作失败：%s" % (len(failed), "；".join(item["message"] for item in failed[:3]))
    return {
        "ok": not failed,
        "message": message,
        "is_admin": admin,
        "installed": True,
        "requires_admin": requires_admin,
        "needs_restart_hint": changed > 0,
        "changed": changed,
        "results": results,
    }


def apply(main_dir: Optional[str] = None, include_firewall: bool = False) -> dict:
    """执行「破坏自动更新」。

    * 只禁用 EasiCamera 自己的更新器文件 / 缓存 / 专属任务/服务，**不动**共享 EasiUpdate
      服务、主程序、sweclauncher、EasiCameraGuardian、注册表版本信息；
    * 幂等；无安装时直接返回成功；
    * ``include_firewall=True`` 时额外添加出站防火墙拦截规则（需管理员，失败会明确标注）。
    """
    info = _locate(main_dir)
    return _apply_common(info, include_firewall=include_firewall, restore=False)


def restore(main_dir: Optional[str] = None) -> dict:
    """还原 :func:`apply` 做过的改动（幂等；无安装时直接返回成功）。"""
    info = _locate(main_dir)
    return _apply_common(info, include_firewall=False, restore=True)


__all__ = [
    "detect",
    "apply",
    "restore",
    "summarize",
    "is_admin",
    "InstallInfo",
    "UPDATER_FILES",
    "DISABLED_SUFFIX",
    "SHARED_SERVICE_NAMES",
    "FIREWALL_BLOCK_RULE_NAME",
]
