# -*- coding: utf-8 -*-
"""规则包：自动发现同目录下的 ``v2_*.py`` 版本规则模块。

每个规则模块只导出 ``RULES`` 字典（格式见 analysis/CONTRACT.md §3.2）。
新增版本时把 ``v2_x_y_z_build.py`` 放进本目录即可，无需修改本文件。

约束：
- 规则模块必须能被 ``import`` 且**不访问磁盘/网络**；
- 模块导入失败不会影响其它版本（错误收集在 :func:`load_errors` 里，CLI 可见）；
- 仅使用标准库，可在 PyInstaller one-folder 下运行（打包时需
  ``--collect-submodules core.rules``，见 README）。

对外接口：
    all_rules()      -> dict[version, RULES]（按版本号从高到低）
    get_rules(ver)   -> RULES | None
    versions()       -> list[str]（从高到低）
    discover(force)  -> 重新扫描
    reload()         -> 重新扫描 + 重新 import
    load_errors()    -> list[dict] 导入失败详情
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys
import traceback
from typing import Optional

_PKG = __name__  # "core.rules"
_PREFIX = "v2_"  # 只发现 v2_ 开头的模块

_RULES: dict[str, dict] = {}
_ERRORS: list[dict] = []
_DISCOVERED = False


def _version_key(version: str) -> tuple:
    """把 "2.0.10.4229" 转成 (2, 0, 10, 4229) 用于排序（非数字段按 0）。"""
    parts = []
    for piece in str(version).replace("-", ".").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _iter_module_names() -> list[str]:
    """列出本包内的候选规则模块名（不含包名前缀）。"""
    names: set[str] = set()
    # 常规：pkgutil（支持 zipped/egg；PyInstaller one-folder 也适用）
    try:
        for info in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
            if info.name.startswith(_PREFIX):
                names.add(info.name)
    except Exception:  # 极端环境下退回文件系统扫描
        pass
    # 兜底：直接扫目录（pkgutil 在个别冻结环境可能拿不到 __path__）
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        for fn in os.listdir(here):
            if fn.startswith(_PREFIX) and fn.endswith(".py"):
                names.add(fn[:-3])
    except OSError:
        pass
    return sorted(names)


def _import_rule_module(module_name: str) -> Optional[dict]:
    """导入单个规则模块并返回其 RULES；失败记录到 _ERRORS。"""
    full_name = "%s.%s" % (_PKG, module_name)
    try:
        module = importlib.import_module(full_name)
    except Exception as exc:  # noqa: BLE001 - 单个规则坏掉不能影响全引擎
        _ERRORS.append(
            {
                "module": module_name,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc(limit=3),
            }
        )
        return None
    rules = getattr(module, "RULES", None)
    if not isinstance(rules, dict):
        _ERRORS.append(
            {
                "module": module_name,
                "error": "模块中没有 RULES 字典（或类型不对）",
                "traceback": "",
            }
        )
        return None
    version = str(rules.get("version") or "").strip()
    if not version:
        _ERRORS.append(
            {"module": module_name, "error": "RULES 缺少 version 字段", "traceback": ""}
        )
        return None
    features = rules.get("features")
    if not isinstance(features, dict):
        _ERRORS.append(
            {"module": module_name, "error": "RULES.features 不是 dict", "traceback": ""}
        )
        return None
    return rules


def discover(force: bool = False) -> dict[str, dict]:
    """扫描并导入规则；返回 {version: RULES}。结果缓存，``force=True`` 重扫。"""
    global _DISCOVERED
    if _DISCOVERED and not force:
        return _RULES
    _RULES.clear()
    _ERRORS.clear()
    for module_name in _iter_module_names():
        rules = _import_rule_module(module_name)
        if rules is None:
            continue
        version = str(rules["version"])
        if version in _RULES:
            _ERRORS.append(
                {
                    "module": module_name,
                    "error": "版本号 %s 与其它规则文件重复，已忽略" % version,
                    "traceback": "",
                }
            )
            continue
        rules.setdefault("display_name", "V" + version)
        rules.setdefault("files", {})
        rules.setdefault("unavailable_reason", {})
        _RULES[version] = rules
    _DISCOVERED = True
    return _RULES


def reload() -> dict[str, dict]:
    """清掉缓存并重新导入所有规则（供开发调试 / CLI --reload 使用）。"""
    # 删除已加载的规则子模块，保证改动后的 .py 真正重新执行
    for module_name in list(sys.modules):
        if module_name.startswith(_PKG + "."):
            del sys.modules[module_name]
    return discover(force=True)


def _sorted_versions() -> list[str]:
    discover()
    return sorted(_RULES.keys(), key=_version_key, reverse=True)


def versions() -> list[str]:
    """已发现版本号，从高到低。"""
    return _sorted_versions()


def all_rules() -> dict[str, dict]:
    """所有规则，按版本号从高到低。"""
    return {version: _RULES[version] for version in _sorted_versions()}


def get_rules(version: str) -> Optional[dict]:
    """按版本号取规则；不存在返回 None。"""
    discover()
    return _RULES.get(str(version))


def load_errors() -> list[dict]:
    """返回规则导入错误列表（module/error/traceback）。"""
    discover()
    return list(_ERRORS)


__all__ = [
    "all_rules",
    "get_rules",
    "versions",
    "discover",
    "reload",
    "load_errors",
]
