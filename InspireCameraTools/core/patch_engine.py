# -*- coding: utf-8 -*-
"""补丁引擎 —— 亿方展台管家核心模块。

契约：``analysis/CONTRACT.md`` §3.3（接口固定，app-dev / Lead 按此调用）。

设计要点
--------
* **纯标准库**：不 import 任何第三方库，保证 PyInstaller 打包后可用。
* **规则驱动**：版本识别、可用功能、字节补丁全部来自 ``core/rules/v2_*.py`` 的
  ``RULES`` 字典（格式见契约 §3.2），引擎本身不含任何版本相关硬编码。
* **先校验后写盘**：所有被选中功能的每个 op 都先校验原字节（``expected``），
  同一文件多功能合并后按偏移排序并**禁止重叠**；校验阶段任何失败都**整体回滚
  （此时尚未写盘）**。
* **备份 + 原子写回**：写盘前把原始文件备份到
  ``<main_dir>/../_InspirePatchBackup/<YYYYmmdd-HHMMSS>/``（保留相对路径），
  每个文件先写 ``.tmp`` 再 ``os.replace``；多个文件写入中途失败会把已写文件
  用备份恢复。
* **幂等**：已应用的功能重复 apply 不会重复写盘；``is_patched`` 按
  ``expected``/``patched`` 字节判断。

规则文件里 ``expected`` / ``patched`` 必须等长（引擎会校验），偏移为原版文件
绝对偏移。规则文件的 ``files`` 给出原版关键文件 SHA-256，用于版本识别与补丁前
指纹校验（目标文件必须处于原版或本引擎已知的补丁状态）。

本模块额外提供几个**供规则作者使用**的辅助函数（不属于契约核心接口、只增不改）：
:func:`validate_rule` / :func:`validate_all_rules` / :func:`simulate_patch`。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from .features import (
    FEATURES,
    FEATURE_IDS,
    FEATURE_MAP,
    Feature,
    get_feature,
    normalize_feature_ids,
)
from .rules import (
    all_rules as _all_rules,
    get_rules as _get_rules,
    load_errors as _rule_load_errors,
    versions as _rule_versions,
)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

#: 默认备份目录名（位于 Main 的上一级，即安装根目录）
BACKUP_DIR_NAME = "_InspirePatchBackup"

#: 备份/识别相关的时间戳格式：20241114-173015
TIMESTAMP_FMT = "%Y%m%d-%H%M%S"

#: 备份目录内的清单文件名
MANIFEST_NAME = "_patch_manifest.json"

#: 版本识别至少需要匹配的文件数（规则 files 少于 2 个时取实际个数）
DETECTION_MIN_FILES = 2

#: EasiCamera.exe 文件名（用于判断目录是否是 Main 目录）
MAIN_EXE_NAME = "EasiCamera.exe"

_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class PatchEngineError(Exception):
    """补丁引擎通用异常。"""


class RuleError(PatchEngineError):
    """规则文件格式/内容错误。"""


# --------------------------------------------------------------------------- #
# 数据类（契约 §3.3）
# --------------------------------------------------------------------------- #


@dataclass
class DetectedVersion:
    """识别到的 EasiCamera 版本。"""

    version: str
    display_name: str
    rule: dict
    matched_files: dict  # 文件名 -> 匹配成功时的 SHA-256（当前文件实际哈希）

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "display_name": self.display_name,
            "matched_files": dict(self.matched_files),
            "files_count": len(self.rule.get("files") or {}),
            "features": sorted((self.rule.get("features") or {}).keys()),
        }


@dataclass
class PatchResult:
    """补丁 / 恢复操作结果。"""

    ok: bool
    message: str
    applied: list[str] = field(default_factory=list)  # 成功的 feature id
    failed: list[tuple[str, str]] = field(default_factory=list)  # (feature id, 原因)
    backup_dir: Optional[str] = None
    needs_restart_hint: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "message": self.message,
            "applied": list(self.applied),
            "failed": [{"feature": fid, "reason": reason} for fid, reason in self.failed],
            "backup_dir": self.backup_dir,
            "needs_restart_hint": self.needs_restart_hint,
        }


@dataclass
class FeatureAvailability:
    """某个功能在某版本上的可用性。"""

    feature: Feature
    available: bool
    reason: Optional[str] = None
    already_patched: bool = False

    def to_dict(self) -> dict:
        return {
            "feature": self.feature.to_dict(),
            "id": self.feature.id,
            "name": self.feature.name,
            "available": self.available,
            "reason": self.reason,
            "already_patched": self.already_patched,
        }


@dataclass
class PatchPlanItem:
    """dry-run 计划中的一项（对应一个功能）。"""

    feature: Feature
    available: bool
    reason: Optional[str] = None
    already_patched: bool = False
    ops: list[dict] = field(default_factory=list)  # 操作说明（文件/偏移/说明）
    files: list[str] = field(default_factory=list)  # 涉及文件（去重排序）

    def to_dict(self) -> dict:
        return {
            "id": self.feature.id,
            "name": self.feature.name,
            "available": self.available,
            "reason": self.reason,
            "already_patched": self.already_patched,
            "files": list(self.files),
            "ops": list(self.ops),
        }


# --------------------------------------------------------------------------- #
# 基础工具：哈希 / 路径 / 原子写
# --------------------------------------------------------------------------- #


def sha256_bytes(data: bytes) -> str:
    """计算 bytes 的 SHA-256（小写 hex）。"""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    """计算文件 SHA-256（小写 hex），大文件分块读取。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_dir(path) -> Optional[str]:
    """把任意输入规范成存在的绝对目录路径；不存在/非法返回 None。"""
    if path is None:
        return None
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = os.path.expandvars(os.path.expanduser(str(text).strip()))
    if not text:
        return None
    absolute = os.path.abspath(os.path.normpath(text))
    return absolute if os.path.isdir(absolute) else None


def _split_rel(rel) -> list[str]:
    """把规则里的相对路径拆成安全的分段；拒绝绝对路径与 ``..``。"""
    text = str(rel).strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise RuleError("非法的相对路径: %r" % (rel,))
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise RuleError("非法的相对路径: %r" % (rel,))
    return parts


def _join(main_dir: str, rel) -> str:
    """把规则相对路径拼到 Main 目录下。"""
    return os.path.join(main_dir, *_split_rel(rel))


def _write_atomic(path: str, data: bytes) -> None:
    """原子写：先写同目录临时文件，再 os.replace 覆盖目标。"""
    directory = os.path.dirname(path) or "."
    tmp_path = os.path.join(directory, ".inspire-tmp-%d-%s" % (os.getpid(), os.path.basename(path)))
    try:
        with open(tmp_path, "wb") as fp:
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _write_json_atomic(path: str, obj: Any) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    _write_atomic(path, text.encode("utf-8"))


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fp:
        return fp.read()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


# --------------------------------------------------------------------------- #
# 规则解析与校验
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Op:
    """规则里的一条字节补丁 op（已解析成 bytes）。"""

    feature_id: str
    file: str
    offset: int
    expected: bytes
    patched: bytes
    note: str

    @property
    def length(self) -> int:
        return len(self.expected)

    def describe(self) -> dict:
        return {
            "file": self.file,
            "offset": "0x%X" % self.offset,
            "length": self.length,
            "note": self.note,
        }


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value.strip()))


def _parse_op(feature_id: str, raw: Mapping) -> _Op:
    """把一个规则 op 字典解析成 :class:`_Op`；格式错误抛 :class:`RuleError`。"""
    if not isinstance(raw, Mapping):
        raise RuleError("功能 %s 的 op 不是字典: %r" % (feature_id, raw))
    file_name = raw.get("file")
    if not isinstance(file_name, str) or not file_name.strip():
        raise RuleError("功能 %s 的 op 缺少 file" % feature_id)
    _split_rel(file_name)  # 校验路径安全
    offset = raw.get("offset")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise RuleError("功能 %s 的 op.offset 必须是非负整数: %r" % (feature_id, offset))
    expected_text = raw.get("expected")
    patched_text = raw.get("patched")
    if not isinstance(expected_text, str) or not isinstance(patched_text, str):
        raise RuleError("功能 %s 的 op.expected/patched 必须是 hex 字符串" % feature_id)
    try:
        expected = bytes.fromhex(expected_text)
        patched = bytes.fromhex(patched_text)
    except ValueError as exc:
        raise RuleError("功能 %s 的 op hex 字符串非法: %s" % (feature_id, exc)) from None
    if not expected or not patched:
        raise RuleError("功能 %s 的 op.expected/patched 不能为空" % feature_id)
    if len(expected) != len(patched):
        raise RuleError(
            "功能 %s 的 op 长度不一致: expected=%d patched=%d（必须等长替换）"
            % (feature_id, len(expected), len(patched))
        )
    note = str(raw.get("note") or "")
    return _Op(
        feature_id=feature_id,
        file=file_name.strip().replace("\\", "/"),
        offset=offset,
        expected=expected,
        patched=patched,
        note=note,
    )


def _parse_feature_ops(rule: Mapping, feature_id: str) -> list[_Op]:
    """解析某功能的全部 op。"""
    raw_ops = (rule.get("features") or {}).get(feature_id)
    if not isinstance(raw_ops, list) or not raw_ops:
        raise RuleError("功能 %s 没有可用的补丁操作" % feature_id)
    return [_parse_op(feature_id, raw) for raw in raw_ops]


def _ops_by_file(rule: Mapping, feature_ids: Iterable[str]) -> dict[str, list[_Op]]:
    """收集指定功能的 op，按文件分组（保持功能内顺序）。"""
    grouped: dict[str, list[_Op]] = {}
    for feature_id in feature_ids:
        for op in _parse_feature_ops(rule, feature_id):
            grouped.setdefault(op.file, []).append(op)
    return grouped


def _all_ops_by_file(rule: Mapping) -> dict[str, list[_Op]]:
    """规则内所有功能的 op，按文件分组。"""
    features = rule.get("features") or {}
    return _ops_by_file(rule, list(features.keys()))


def detect_overlaps(ops_grouped: Mapping[str, Sequence[_Op]]) -> list[str]:
    """检查同一文件的 op 是否重叠；返回中文错误列表（空表示无重叠）。"""
    errors: list[str] = []
    for file_name, ops in ops_grouped.items():
        ordered = sorted(ops, key=lambda op: op.offset)
        for prev, cur in zip(ordered, ordered[1:]):
            if prev.offset + prev.length > cur.offset:
                errors.append(
                    "文件 %s 的补丁范围重叠：功能 %s [0x%X, 0x%X) 与功能 %s [0x%X, 0x%X)"
                    % (
                        file_name,
                        prev.feature_id,
                        prev.offset,
                        prev.offset + prev.length,
                        cur.feature_id,
                        cur.offset,
                        cur.offset + cur.length,
                    )
                )
    return errors


def _rule_errors_by_feature(rule: Mapping) -> tuple[list[str], dict[str, list[str]]]:
    """把 :func:`validate_rule` 的结果拆成（全局错误，{功能: 错误列表}）。"""
    global_errors: list[str] = []
    per_feature: dict[str, list[str]] = {}
    for message in validate_rule(rule):
        match = re.match(r"^\[([a-z0-9_]+)\]", message)
        if match:
            per_feature.setdefault(match.group(1), []).append(message)
        else:
            global_errors.append(message)
    return global_errors, per_feature


def validate_rule(rule: Mapping) -> list[str]:
    """校验一个 RULES 字典是否符合契约 §3.2；返回中文错误列表（空=合法）。"""
    errors: list[str] = []
    if not isinstance(rule, Mapping):
        return ["RULES 不是字典"]
    version = rule.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("RULES.version 缺失或不是字符串")
    files = rule.get("files")
    if not isinstance(files, Mapping):
        errors.append("RULES.files 必须是 dict")
        files = {}
    for file_name, digest in files.items():
        if not isinstance(file_name, str) or not file_name.strip():
            errors.append("RULES.files 存在非法文件名: %r" % (file_name,))
            continue
        try:
            _split_rel(file_name)
        except RuleError as exc:
            errors.append("RULES.files 路径非法: %s" % exc)
        if not _is_sha256_hex(digest):
            errors.append("RULES.files[%r] 必须是 64 位 hex SHA-256" % (file_name,))
    features = rule.get("features")
    if not isinstance(features, Mapping):
        errors.append("RULES.features 必须是 dict")
        features = {}
    unavailable = rule.get("unavailable_reason")
    if unavailable is not None and not isinstance(unavailable, Mapping):
        errors.append("RULES.unavailable_reason 必须是 dict")
    for feature_id, raw_ops in features.items():
        if feature_id not in FEATURE_MAP:
            errors.append("[%s] 未知功能 ID（契约 §3.1 固定 8 个）" % feature_id)
            continue
        if not isinstance(raw_ops, list) or not raw_ops:
            errors.append("[%s] 的 op 列表不能为空" % feature_id)
            continue
        for index, raw in enumerate(raw_ops):
            try:
                op = _parse_op(feature_id, raw)
            except RuleError as exc:
                errors.append("[%s] %s" % (feature_id, exc))
                continue
            if op.file not in files:
                errors.append(
                    "[%s] op 文件 %s 未在 RULES.files 中给出原版 SHA-256（补丁前无法做指纹校验）"
                    % (feature_id, op.file)
                )
            # 同一功能内部也不允许自重叠
            for other in raw_ops[:index]:
                try:
                    other_op = _parse_op(feature_id, other)
                except RuleError:
                    continue
                if other_op.file == op.file and other_op.offset < op.offset + op.length and op.offset < other_op.offset + other_op.length:
                    errors.append(
                        "[%s] 同一功能内的两条 op 重叠: %s 0x%X 与 0x%X"
                        % (feature_id, op.file, other_op.offset, op.offset)
                    )
    return errors


def validate_all_rules() -> dict[str, list[str]]:
    """校验所有已发现规则；返回 {版本: 错误列表}（空列表=通过）。"""
    return {version: validate_rule(rule) for version, rule in _all_rules().items()}


# --------------------------------------------------------------------------- #
# 文件状态判断（原版 / 补丁后 / 混合 / 不匹配）
# --------------------------------------------------------------------------- #


def _revert_known_patches(data: bytes, ops: Sequence[_Op]) -> Optional[bytes]:
    """把处于「已知补丁状态」的文件还原回原版字节；无法识别返回 None。

    只在检测/指纹校验用：把所有当前等于 ``patched`` 的 op 区域换回 ``expected``，
    最终哈希若等于原版 SHA-256 则说明该文件是本引擎已知的补丁状态。
    """
    buffer = bytearray(data)
    changed = False
    for op in ops:
        end = op.offset + op.length
        if end > len(buffer):
            return None
        region = bytes(buffer[op.offset:end])
        if region == op.patched:
            buffer[op.offset:end] = op.expected
            changed = True
        elif region == op.expected:
            continue
        else:
            return None
    return bytes(buffer) if changed else None


def _file_matches_original(data: bytes, rule: Mapping, file_name: str) -> bool:
    """判断文件内容是否属于「原版」或「本引擎已知的补丁状态」。"""
    expected_sha = str((rule.get("files") or {}).get(file_name, "")).lower()
    if not expected_sha:
        return True  # 规则没给哈希时不做阻断（validate_rule 会另行报错）
    if sha256_bytes(data).lower() == expected_sha:
        return True
    try:
        all_ops = _all_ops_by_file(rule).get(file_name) or []
    except RuleError:
        return False
    if not all_ops:
        return False
    reverted = _revert_known_patches(data, all_ops)
    return reverted is not None and sha256_bytes(reverted).lower() == expected_sha


def _read_ops_files(main_dir: str, ops_grouped: Mapping[str, Sequence[_Op]],
                    cache: Optional[dict[str, bytes]] = None) -> dict[str, bytes]:
    """读取 ops 涉及的全部文件（失败抛 OSError，带上文件名上下文）。"""
    cache = cache if cache is not None else {}
    result: dict[str, bytes] = {}
    for file_name in ops_grouped:
        if file_name in cache:
            result[file_name] = cache[file_name]
            continue
        path = _join(main_dir, file_name)
        try:
            data = _read_bytes(path)
        except FileNotFoundError:
            raise PatchEngineError("缺少文件: %s" % path) from None
        except OSError as exc:
            raise PatchEngineError("读取文件失败 %s: %s" % (path, exc)) from None
        cache[file_name] = data
        result[file_name] = data
    return result


def _feature_state(ops: Sequence[_Op], data_by_file: Mapping[str, bytes]) -> tuple[str, Optional[str]]:
    """判断一个功能当前状态。

    返回 (state, detail)：
      ``clean``    全部 op 均为原版字节（未打补丁）
      ``patched``  全部 op 均为补丁后字节（已打补丁）
      ``mixed``    部分已打（异常/其它工具改过，引擎仍可补齐）
      ``missing``  目标文件缺失 / 读取失败
      ``mismatch`` 存在未知字节（版本不符或文件被修改）
    """
    states: set[str] = set()
    for op in ops:
        data = data_by_file.get(op.file)
        if data is None:
            return "missing", "缺少文件 %s" % op.file
        end = op.offset + op.length
        if end > len(data):
            return (
                "mismatch",
                "%s 长度不足：偏移 0x%X+%d 越界（文件 %d 字节）"
                % (op.file, op.offset, op.length, len(data)),
            )
        region = data[op.offset:end]
        if region == op.expected:
            states.add("clean")
        elif region == op.patched:
            states.add("patched")
        else:
            return (
                "mismatch",
                "%s 偏移 0x%X 处字节校验失败（期望 %s / 已补丁 %s，实际 %s）"
                % (op.file, op.offset, op.expected.hex(), op.patched.hex(), region.hex()),
            )
    if states == {"patched"}:
        return "patched", None
    if states == {"clean"}:
        return "clean", None
    return "mixed", None


def _read_feature_state(main_dir: str, ops: Sequence[_Op],
                        cache: Optional[dict[str, bytes]] = None) -> tuple[str, Optional[str]]:
    grouped: dict[str, list[_Op]] = {}
    for op in ops:
        grouped.setdefault(op.file, []).append(op)
    try:
        data_by_file = _read_ops_files(main_dir, grouped, cache)
    except PatchEngineError as exc:
        return "missing", str(exc)
    return _feature_state(ops, data_by_file)


# --------------------------------------------------------------------------- #
# 安装目录探测
# --------------------------------------------------------------------------- #


def _looks_like_main(path: str) -> bool:
    """判断目录是否像 EasiCamera 的 Main 目录。"""
    try:
        if not os.path.isdir(path):
            return False
        if os.path.isfile(os.path.join(path, MAIN_EXE_NAME)):
            return True
        return os.path.isfile(os.path.join(path, "EasiCamera.UI.dll")) and os.path.isfile(
            os.path.join(path, "EasiCamera.Business.dll")
        )
    except OSError:
        return False


def _versioned_main_candidates(install_root: str) -> list[str]:
    """安装根目录下的版本化布局候选：``EasiCamera_<版本>/Main``。

    EasiCamera 2.x 实际安装布局（静态分析结合注册表 ``Seewo\\EasiCamera`` 的
    ``VersionPath``/``ActualExePath`` 字段）为::

        <安装根>\\EasiCamera_<版本>\\Main\\EasiCamera.exe

    同时兼容非版本化旧布局（安装根下直接有 ``Main``）。
    """
    candidates: list[str] = []
    try:
        entries = sorted(os.listdir(install_root), reverse=True)
    except OSError:
        return candidates
    for entry in entries:
        lowered = entry.lower()
        if not lowered.startswith("easicamera_"):
            continue
        main_dir = os.path.join(install_root, entry, "Main")
        if _looks_like_main(main_dir):
            candidates.append(main_dir)
    legacy_main = os.path.join(install_root, "Main")
    if _looks_like_main(legacy_main) and legacy_main not in candidates:
        candidates.append(legacy_main)
    return candidates


def _seewo_registry_candidates() -> list[str]:
    """从 ``HKLM\\SOFTWARE[\\WOW6432Node]\\Seewo\\EasiCamera`` 读取安装路径。

    EasiCamera 2.x 安装后写入的键值：``version``、``code``、``VersionPath``（当前版本目录）、
    ``ActualExePath``（当前 Main\\EasiCamera.exe）、``ExePath``（启动器）。这里做容错读取。
    """
    candidates: list[str] = []

    def add(path: Any) -> None:
        if not path:
            return
        try:
            normalized = _normalize_main_dir(str(path))
        except (OSError, ValueError):
            normalized = None
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    try:
        import winreg  # type: ignore[import-not-found]
    except Exception:
        return candidates
    try:
        for sub_key in (r"SOFTWARE\Seewo\EasiCamera", r"SOFTWARE\WOW6432Node\Seewo\EasiCamera"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_key, 0, winreg.KEY_READ) as key:
                    for name in ("ActualExePath", "VersionPath", "ExePath", "path"):
                        try:
                            value = winreg.QueryValueEx(key, name)[0]
                        except OSError:
                            continue
                        if not isinstance(value, str) or not value.strip():
                            continue
                        add(value)  # _normalize_main_dir 会处理 Main/版本目录/启动器路径
                        text = os.path.abspath(os.path.expandvars(value.strip().strip('"')))
                        # ActualExePath 指向 Main\EasiCamera.exe 时取其父目录
                        if os.path.isfile(text):
                            parent = os.path.dirname(text)
                            if os.path.basename(parent).lower() == "main":
                                add(parent)
                            # VersionPath 指向版本目录时取 <版本目录>/Main
                            add(os.path.join(parent, "Main"))
                        elif os.path.isdir(text):
                            add(os.path.join(text, "Main"))
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - 注册表异常一律容错
        pass
    return candidates


def _build_default_main_dirs() -> list[str]:
    """构造常见安装目录候选（不访问磁盘，仅拼路径）。"""
    candidates: list[str] = []

    def add(path: str) -> None:
        text = os.path.normpath(path)
        if text not in candidates:
            candidates.append(text)

    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env_name)
        if base:
            add(os.path.join(base, "Seewo", "EasiCamera", "Main"))
            add(os.path.join(base, "Seewo", "EasiCamera"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        add(os.path.join(local_app_data, "Seewo", "EasiCamera", "Main"))
    for drive in ("C:", "D:", "E:", "F:"):
        for program_files in ("Program Files", "Program Files (x86)"):
            add(os.path.join(drive + os.sep, program_files, "Seewo", "EasiCamera", "Main"))
    return candidates


#: 常见安装目录候选（契约 §3.3 的 DEFAULT_MAIN_DIRS）
DEFAULT_MAIN_DIRS: list[str] = _build_default_main_dirs()


def _registry_candidates() -> list[str]:
    """从注册表卸载项 / App Paths 里找安装目录（容错，失败返回空列表）。"""
    try:
        import winreg  # type: ignore[import-not-found]
    except Exception:
        return []

    found: list[str] = []

    def add(path: Any) -> None:
        if not path:
            return
        try:
            text = os.fspath(path).strip().strip('"')
        except TypeError:
            return
        if not text:
            return
        # DisplayIcon 常见形式： "C:\...\EasiCamera.exe",0
        text = text.strip().strip('"').split(",")[0].strip().strip('"')
        if not text:
            return
        candidates = []
        if os.path.isfile(text):
            candidates.extend([os.path.dirname(text), os.path.join(os.path.dirname(text), "Main")])
        else:
            candidates.extend([text, os.path.join(text, "Main"), os.path.join(text, "EasiCamera", "Main")])
        for candidate in candidates:
            candidate = os.path.normpath(candidate)
            if candidate not in found:
                found.append(candidate)

    def read_value(key, name: str) -> Optional[str]:
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else None
        except OSError:
            return None

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
         winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
         winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
         winreg.KEY_READ),
    ]
    keywords = ("easicamera", "希沃视频展台", "视频展台", "seewo")
    try:
        for hive, sub_key, access in roots:
            try:
                with winreg.OpenKey(hive, sub_key, 0, access) as root_key:
                    index = 0
                    while True:
                        try:
                            child_name = winreg.EnumKey(root_key, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(root_key, child_name, 0, access) as child:
                                display_name = (read_value(child, "DisplayName") or "").lower()
                                if not any(word in display_name for word in keywords):
                                    continue
                                add(read_value(child, "InstallLocation"))
                                add(read_value(child, "DisplayIcon"))
                                uninstall = read_value(child, "UninstallString")
                                if uninstall:
                                    command = uninstall.strip().strip('"')
                                    text = command.split('"')[0]
                                    if os.path.isfile(text):
                                        add(os.path.dirname(text))
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - 注册表异常一律容错
        pass

    # App Paths
    try:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\EasiCamera.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\EasiCamera.exe",
            ):
                try:
                    with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ) as key:
                        add(read_value(key, None))
                except OSError:
                    continue
    except Exception:  # noqa: BLE001
        pass
    return found


def _normalize_main_dir(path) -> Optional[str]:
    """把用户给的路径规范化为 Main 目录：Main 本身 / 版本目录 / 安装根目录 / exe 文件都接受。"""
    absolute = _normalize_dir(path)
    if absolute is None:
        # 兼容直接传入 EasiCamera.exe / EasiCamera.UI.dll 文件路径
        try:
            text = os.fspath(path)
            if isinstance(text, bytes):
                text = text.decode("utf-8", "replace")
            text = os.path.expandvars(os.path.expanduser(str(text).strip().strip('"')))
            if text and os.path.isfile(os.path.abspath(os.path.normpath(text))):
                absolute = os.path.dirname(os.path.abspath(os.path.normpath(text)))
        except (TypeError, OSError):
            absolute = None
    if absolute is None:
        return None
    if _looks_like_main(absolute):
        return absolute
    nested = os.path.join(absolute, "Main")
    if os.path.isdir(nested) and _looks_like_main(nested):
        return nested
    # 安装根目录：其下可能有版本化目录 EasiCamera_<版本>/Main
    versioned = _versioned_main_candidates(absolute)
    if versioned:
        return versioned[0]
    return None


def find_main_dir(explicit: Optional[str] = None) -> Optional[str]:
    """查找 EasiCamera 安装的 Main 目录。

    * ``explicit`` 非空：只检查该路径（Main 本身 / 版本目录 / 安装根目录均可），找不到返回 None；
    * ``explicit`` 为空：依次搜索注册表 ``Seewo\\EasiCamera``（VersionPath/ActualExePath，
      兼容 2.x 版本化安装布局）、环境变量程序目录、卸载项注册表、常见盘符路径。
    """
    if explicit:
        return _normalize_main_dir(explicit)
    candidates: list[str] = []
    candidates.extend(_seewo_registry_candidates())
    candidates.extend(DEFAULT_MAIN_DIRS)
    candidates.extend(_registry_candidates())
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.normpath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        main_dir = _normalize_main_dir(candidate)
        if main_dir:
            return main_dir
    return None


# --------------------------------------------------------------------------- #
# 版本识别 / 功能矩阵 / 补丁状态
# --------------------------------------------------------------------------- #


def detect_version(main_dir: str) -> Optional[DetectedVersion]:
    """按规则指纹识别 Main 目录；未识别返回 None。"""
    absolute = _normalize_dir(main_dir)
    if absolute is None:
        return None
    best: Optional[DetectedVersion] = None
    best_count = 0
    for version, rule in _all_rules().items():
        file_hashes = rule.get("files") or {}
        if not file_hashes:
            continue
        matched: dict[str, str] = {}
        for file_name, expected_sha in file_hashes.items():
            try:
                data = _read_bytes(_join(absolute, file_name))
            except (OSError, RuleError):
                continue
            actual = sha256_bytes(data)
            if actual.lower() == str(expected_sha).lower() or _file_matches_original(data, rule, file_name):
                matched[file_name] = actual
        need = min(DETECTION_MIN_FILES, len(file_hashes))
        if len(matched) >= need and len(matched) > best_count:
            best_count = len(matched)
            best = DetectedVersion(
                version=version,
                display_name=str(rule.get("display_name") or ("V" + version)),
                rule=rule,
                matched_files=matched,
            )
    return best


def _unavailable_reason(rule: Mapping, feature_id: str) -> str:
    """某功能在某版本不可用的原因（中文）。"""
    reasons = rule.get("unavailable_reason") or {}
    reason = reasons.get(feature_id)
    if reason:
        return str(reason)
    return "该版本未提供此功能"


def is_patched(main_dir: str) -> dict[str, bool]:
    """返回 ``{feature_id: 是否已应用}``；未安装/未识别时全部 False。"""
    result: dict[str, bool] = {feature_id: False for feature_id in FEATURE_IDS}
    absolute = _normalize_dir(main_dir)
    if absolute is None:
        return result
    detected = detect_version(absolute)
    if detected is None:
        return result
    cache: dict[str, bytes] = {}
    for feature_id, raw_ops in (detected.rule.get("features") or {}).items():
        if feature_id not in result or not raw_ops:
            continue
        try:
            ops = _parse_feature_ops(detected.rule, feature_id)
        except RuleError:
            continue
        state, _detail = _read_feature_state(absolute, ops, cache)
        result[feature_id] = state == "patched"
    return result


def list_features(version: str, main_dir: Optional[str] = None) -> list[FeatureAvailability]:
    """返回某版本 8 个功能的可用性。

    ``main_dir`` 可选：给出时同时计算 ``already_patched``（找 Main 目录用）。
    未知版本抛 ``ValueError``。
    """
    rule = _get_rules(version)
    if rule is None:
        raise ValueError(
            "未知版本: %s（已发现: %s）" % (version, ", ".join(_rule_versions()) or "无")
        )
    global_errors, per_feature_errors = _rule_errors_by_feature(rule)
    absolute = _normalize_dir(main_dir) if main_dir else None
    patched_map: dict[str, bool] = {}
    if absolute:
        patched_map = is_patched(absolute)
    result: list[FeatureAvailability] = []
    for feature in FEATURES:
        raw_ops = (rule.get("features") or {}).get(feature.id)
        available = True
        reason: Optional[str] = None
        if global_errors:
            available = False
            reason = "规则文件无效：%s" % global_errors[0]
        elif feature.id in per_feature_errors:
            available = False
            reason = "规则文件无效：%s" % per_feature_errors[feature.id][0]
        elif not raw_ops:
            available = False
            reason = _unavailable_reason(rule, feature.id)
        elif global_errors is None:  # pragma: no cover - 防御
            pass
        already = bool(patched_map.get(feature.id))
        if already:
            reason = "已应用（无需重复补丁）"
        result.append(
            FeatureAvailability(
                feature=feature,
                available=available,
                reason=reason,
                already_patched=already,
            )
        )
    return result


# --------------------------------------------------------------------------- #
# dry-run 计划
# --------------------------------------------------------------------------- #


def _new_patch_plan_item(feature: Feature, available: bool,
                         reason: Optional[str], already_patched: bool = False,
                         ops: Optional[Sequence[_Op]] = None) -> PatchPlanItem:
    ops = list(ops or [])
    return PatchPlanItem(
        feature=feature,
        available=available,
        reason=reason,
        already_patched=already_patched,
        ops=[op.describe() for op in ops],
        files=sorted({op.file for op in ops}),
    )


def plan(main_dir: str, feature_ids: Sequence[str]) -> list[PatchPlanItem]:
    """dry-run：不写盘，返回每个功能的可用性与操作说明。"""
    ids = normalize_feature_ids(feature_ids)  # 未知 ID 抛 KeyError
    absolute = _normalize_dir(main_dir)
    detected = detect_version(absolute) if absolute else None
    if detected is None:
        return [
            _new_patch_plan_item(get_feature(feature_id), False, "未识别到 EasiCamera 版本（Main 目录不匹配任何规则指纹）")
            for feature_id in ids
        ]
    rule = detected.rule
    global_errors, per_feature_errors = _rule_errors_by_feature(rule)
    features = rule.get("features") or {}
    items: dict[str, PatchPlanItem] = {}
    cache: dict[str, bytes] = {}
    for feature_id in ids:
        feature = get_feature(feature_id)
        raw_ops = features.get(feature_id)
        if global_errors:
            items[feature_id] = _new_patch_plan_item(feature, False, "规则文件无效：%s" % global_errors[0])
            continue
        if feature_id in per_feature_errors:
            items[feature_id] = _new_patch_plan_item(feature, False, "规则文件无效：%s" % per_feature_errors[feature_id][0])
            continue
        if not raw_ops:
            items[feature_id] = _new_patch_plan_item(feature, False, _unavailable_reason(rule, feature_id))
            continue
        try:
            ops = _parse_feature_ops(rule, feature_id)
        except RuleError as exc:
            items[feature_id] = _new_patch_plan_item(feature, False, "规则文件无效：%s" % exc)
            continue
        state, detail = _read_feature_state(absolute, ops, cache)
        if state == "patched":
            items[feature_id] = _new_patch_plan_item(feature, True, "已应用（无需重复补丁）", True, ops)
        elif state in ("clean", "mixed"):
            items[feature_id] = _new_patch_plan_item(feature, True, None, False, ops)
        else:
            items[feature_id] = _new_patch_plan_item(feature, False, detail or "目标文件状态异常")

    # 检查所选功能之间的偏移重叠（同一文件）
    pending_ids = [fid for fid in ids if items[fid].available and not items[fid].already_patched]
    try:
        grouped = _ops_by_file(rule, pending_ids)
    except RuleError:
        grouped = {}
    overlap_messages = detect_overlaps(grouped)
    if overlap_messages:
        involved: set[str] = set()
        for message in overlap_messages:
            match = re.search(r"功能 ([a-z0-9_]+)", message)
            if match:
                involved.add(match.group(1))
        for feature_id in involved:
            if feature_id in items:
                items[feature_id].available = False
                items[feature_id].reason = overlap_messages[0]
    return [items[feature_id] for feature_id in ids]


# --------------------------------------------------------------------------- #
# 备份
# --------------------------------------------------------------------------- #


def _make_backup_dir(main_dir: str, backup_root: Optional[str] = None) -> str:
    """创建带时间戳的唯一备份目录，返回绝对路径。"""
    if backup_root:
        root = os.path.abspath(os.path.expandvars(str(backup_root)))
    else:
        root = os.path.join(os.path.dirname(os.path.abspath(main_dir)), BACKUP_DIR_NAME)
    os.makedirs(root, exist_ok=True)
    stamp = time.strftime(TIMESTAMP_FMT)
    candidate = os.path.join(root, stamp)
    suffix = 1
    while os.path.exists(candidate):
        candidate = os.path.join(root, "%s-%d" % (stamp, suffix))
        suffix += 1
    os.makedirs(candidate, exist_ok=False)
    return candidate


def _backup_files(main_dir: str, backup_dir: str,
                  files: Mapping[str, bytes]) -> dict[str, str]:
    """把原始文件按相对路径复制进备份目录，返回 {相对路径: 备份绝对路径}。"""
    created: dict[str, str] = {}
    for file_name, data in files.items():
        parts = _split_rel(file_name)
        target = os.path.join(backup_dir, *parts)
        os.makedirs(os.path.dirname(target) or backup_dir, exist_ok=True)
        _write_atomic(target, data)
        created[file_name] = target
    return created


# --------------------------------------------------------------------------- #
# 应用补丁
# --------------------------------------------------------------------------- #


def _apply_error(ids: Sequence[str], reason: str) -> PatchResult:
    return PatchResult(
        ok=False,
        message=reason,
        applied=[],
        failed=[(feature_id, reason) for feature_id in ids],
        backup_dir=None,
        needs_restart_hint=False,
    )


def apply_patches(main_dir: str, feature_ids: Sequence[str],
                  backup_root: Optional[str] = None) -> PatchResult:
    """应用所选补丁（先校验全部 op 的原始字节，再备份、原子写回）。

    * 失败时**不写盘**（校验阶段）或**回滚已写文件**（写盘阶段），返回明确中文原因；
    * 已应用的功能幂等跳过；
    * 调用方需自行保证 EasiCamera 未运行（本引擎不检测进程）。
    """
    absolute = _normalize_dir(main_dir)
    if absolute is None:
        return PatchResult(False, "安装目录无效或不存在: %r" % (main_dir,))
    try:
        ids = normalize_feature_ids(feature_ids)
    except KeyError as exc:
        return PatchResult(False, "功能 ID 无效: %s" % exc)
    if not ids:
        return PatchResult(False, "未选择任何功能")

    detected = detect_version(absolute)
    if detected is None:
        return _apply_error(ids, "无法识别 EasiCamera 版本：Main 目录不匹配任何已安装规则指纹")
    rule = detected.rule
    rule_errors = validate_rule(rule)
    if rule_errors:
        return _apply_error(ids, "版本规则文件无效：%s" % "；".join(rule_errors[:3]))

    # ---------- 1. 逐个功能做可用性 / 当前状态检查（不写盘） ----------
    cache: dict[str, bytes] = {}
    failed: list[tuple[str, str]] = []
    already_patched: list[str] = []
    pending: list[tuple[str, list[_Op]]] = []
    features = rule.get("features") or {}
    for feature_id in ids:
        if feature_id not in features:
            failed.append((feature_id, _unavailable_reason(rule, feature_id)))
            continue
        try:
            ops = _parse_feature_ops(rule, feature_id)
        except RuleError as exc:
            failed.append((feature_id, "规则错误：%s" % exc))
            continue
        state, detail = _read_feature_state(absolute, ops, cache)
        if state == "patched":
            already_patched.append(feature_id)
        elif state in ("clean", "mixed"):
            pending.append((feature_id, ops))
        else:
            failed.append((feature_id, detail or "目标文件状态异常"))

    if failed:
        return PatchResult(
            ok=False,
            message="补丁前置校验失败，未做任何修改：%s" % "；".join(reason for _, reason in failed),
            applied=[],
            failed=failed,
            backup_dir=None,
            needs_restart_hint=False,
        )
    if not pending:
        return PatchResult(
            ok=True,
            message="所选功能均已应用，无需重复补丁",
            applied=list(already_patched),
            failed=[],
            backup_dir=None,
            needs_restart_hint=False,
        )

    # ---------- 2. 合并同文件 op + 重叠检查 ----------
    pending_ids = [feature_id for feature_id, _ in pending]
    merged = _ops_by_file(rule, pending_ids)
    overlap_errors = detect_overlaps(merged)
    if overlap_errors:
        return _apply_error(pending_ids, "补丁范围重叠：%s" % "；".join(overlap_errors))

    # ---------- 3. 文件指纹 / 越界 / 原字节逐 op 校验 ----------
    try:
        data_by_file = _read_ops_files(absolute, merged, cache)
    except PatchEngineError as exc:
        return _apply_error(pending_ids, str(exc))
    for file_name, data in data_by_file.items():
        if not _file_matches_original(data, rule, file_name):
            return _apply_error(
                pending_ids,
                "文件指纹不匹配：%s 不是该版本原版文件，也未处于已知补丁状态（版本不符或已被其它程序修改）"
                % file_name,
            )
    op_errors: list[tuple[str, str]] = []
    for file_name, ops in merged.items():
        data = data_by_file[file_name]
        for op in ops:
            end = op.offset + op.length
            if end > len(data):
                op_errors.append(
                    (
                        op.feature_id,
                        "%s 偏移 0x%X+%d 越界（文件 %d 字节）" % (file_name, op.offset, op.length, len(data)),
                    )
                )
                continue
            region = data[op.offset:end]
            if region not in (op.expected, op.patched):
                op_errors.append(
                    (
                        op.feature_id,
                        "%s 偏移 0x%X 字节校验失败（期望原字节 %s，实际 %s）"
                        % (file_name, op.offset, op.expected.hex(), region.hex()),
                    )
                )
    if op_errors:
        return PatchResult(
            ok=False,
            message="补丁字节校验失败，未做任何修改：%s" % "；".join(reason for _, reason in op_errors[:3]),
            applied=[],
            failed=op_errors,
            backup_dir=None,
            needs_restart_hint=False,
        )

    # ---------- 4. 生成新内容（内存中完成） ----------
    changes: dict[str, tuple[bytes, bytes]] = {}  # 文件 -> (原字节, 新字节)
    for file_name, ops in merged.items():
        original = data_by_file[file_name]
        buffer = bytearray(original)
        for op in sorted(ops, key=lambda item: item.offset):
            if bytes(buffer[op.offset:op.offset + op.length]) == op.expected:
                buffer[op.offset:op.offset + op.length] = op.patched
        new_data = bytes(buffer)
        if new_data != original:
            changes[file_name] = (original, new_data)
    if not changes:
        return PatchResult(
            ok=True,
            message="所选功能均已是补丁后状态，无需重复补丁",
            applied=[feature_id for feature_id in ids],
            failed=[],
            backup_dir=None,
            needs_restart_hint=False,
        )

    # ---------- 5. 备份 + 原子写回（失败回滚） ----------
    try:
        backup_dir = _make_backup_dir(absolute, backup_root)
    except OSError as exc:
        return PatchResult(
            ok=False,
            message="创建备份目录失败，未做任何修改：%s" % exc,
            failed=[(feature_id, "创建备份目录失败") for feature_id in pending_ids],
        )
    try:
        _backup_files(absolute, backup_dir, {name: original for name, (original, _new) in changes.items()})
        manifest = {
            "tool": "InspireCameraTools patch_engine",
            "created_at": _now_iso(),
            "version": detected.version,
            "display_name": detected.display_name,
            "main_dir": absolute,
            "features": pending_ids,
            "files": {
                name: {
                    "sha256_before": sha256_bytes(original),
                    "sha256_after": sha256_bytes(new_data),
                    "size": len(original),
                }
                for name, (original, new_data) in changes.items()
            },
            "backup_files": sorted(changes.keys()),
        }
        _write_json_atomic(os.path.join(backup_dir, MANIFEST_NAME), manifest)
    except OSError as exc:
        return PatchResult(
            ok=False,
            message="备份原文件失败，未做任何修改：%s" % exc,
            failed=[(feature_id, "备份失败") for feature_id in pending_ids],
            backup_dir=backup_dir,
        )

    written: list[str] = []
    try:
        for file_name, (_original, new_data) in changes.items():
            target = _join(absolute, file_name)
            _write_atomic(target, new_data)
            written.append(file_name)
        for file_name, (_original, new_data) in changes.items():
            actual = sha256_file(_join(absolute, file_name))
            if actual != sha256_bytes(new_data):
                raise PatchEngineError("写入后校验失败：%s" % file_name)
    except Exception as exc:  # noqa: BLE001 - 需要把失败原因翻译成中文并回滚
        rollback_errors: list[str] = []
        for file_name in written:
            try:
                _write_atomic(_join(absolute, file_name), changes[file_name][0])
            except OSError as rollback_exc:
                rollback_errors.append("%s(%s)" % (file_name, rollback_exc))
        if rollback_errors:
            message = (
                "补丁写入失败且部分文件回滚失败，请用备份手动恢复（备份目录：%s）。原始错误：%s；回滚失败：%s"
                % (backup_dir, exc, "；".join(rollback_errors))
            )
        else:
            message = (
                "补丁写入失败，已回滚全部已写文件（可能 EasiCamera 正在运行或文件只读/无权限）。原始错误：%s"
                % exc
            )
        return PatchResult(
            ok=False,
            message=message,
            applied=[],
            failed=[(feature_id, "写入失败") for feature_id in pending_ids],
            backup_dir=backup_dir,
            needs_restart_hint=False,
        )

    applied_ids = set(already_patched) | set(pending_ids)
    applied = [feature_id for feature_id in ids if feature_id in applied_ids]
    parts = ["已应用 %d 个功能" % len(pending_ids)]
    if already_patched:
        parts.append("%d 个功能此前已应用" % len(already_patched))
    parts.append("备份目录：%s" % backup_dir)
    parts.append("请重启 EasiCamera 使补丁生效")
    return PatchResult(
        ok=True,
        message="；".join(parts),
        applied=applied,
        failed=[],
        backup_dir=backup_dir,
        needs_restart_hint=True,
    )


# --------------------------------------------------------------------------- #
# 恢复备份
# --------------------------------------------------------------------------- #


def restore_backup(main_dir: str, backup_dir: str) -> PatchResult:
    """从备份目录恢复文件（保留相对路径，原子写回）。"""
    absolute = _normalize_dir(main_dir)
    if absolute is None:
        return PatchResult(False, "安装目录无效或不存在: %r" % (main_dir,))
    backup_absolute = _normalize_dir(backup_dir)
    if backup_absolute is None:
        return PatchResult(False, "备份目录无效或不存在: %r" % (backup_dir,))

    manifest_path = os.path.join(backup_absolute, MANIFEST_NAME)
    manifest: Optional[dict] = None
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fp:
                manifest = json.load(fp)
            if not isinstance(manifest, dict):
                manifest = None
        except (OSError, ValueError):
            manifest = None

    # 待恢复文件列表：优先用清单，回退为目录遍历
    restore_names: list[str] = []
    expected_sha: dict[str, str] = {}
    if manifest and isinstance(manifest.get("files"), dict):
        restore_names = sorted(manifest["files"].keys())
        for name, info in manifest["files"].items():
            if isinstance(info, dict) and info.get("sha256_before"):
                expected_sha[name] = str(info["sha256_before"]).lower()
    else:
        for root, _dirs, files in os.walk(backup_absolute):
            for name in files:
                if name == MANIFEST_NAME:
                    continue
                absolute_file = os.path.join(root, name)
                relative = os.path.relpath(absolute_file, backup_absolute)
                restore_names.append(relative.replace(os.sep, "/"))
        restore_names.sort()

    if not restore_names:
        return PatchResult(False, "备份目录中没有可恢复的文件: %s" % backup_absolute, backup_dir=backup_absolute)

    failed: list[tuple[str, str]] = []
    restored = 0
    skipped = 0
    for file_name in restore_names:
        try:
            parts = _split_rel(file_name)
        except RuleError as exc:
            failed.append((file_name, str(exc)))
            continue
        source = os.path.join(backup_absolute, *parts)
        target = os.path.join(absolute, *parts)
        try:
            backup_data = _read_bytes(source)
        except OSError as exc:
            failed.append((file_name, "读取备份文件失败: %s" % exc))
            continue
        if os.path.isfile(target) and sha256_file(target) == sha256_bytes(backup_data):
            skipped += 1
            continue
        try:
            os.makedirs(os.path.dirname(target) or absolute, exist_ok=True)
            _write_atomic(target, backup_data)
            if sha256_file(target) != sha256_bytes(backup_data):
                raise PatchEngineError("恢复后哈希校验失败")
            if file_name in expected_sha and sha256_file(target) != expected_sha[file_name]:
                raise PatchEngineError("恢复后与原版 SHA-256 不一致")
            restored += 1
        except (OSError, PatchEngineError) as exc:
            failed.append((file_name, "恢复失败: %s" % exc))
    if failed:
        return PatchResult(
            ok=False,
            message="恢复完成 %d 个文件，%d 个失败：%s" % (restored, len(failed), "；".join(reason for _, reason in failed[:3])),
            applied=[],
            failed=failed,
            backup_dir=backup_absolute,
            needs_restart_hint=restored > 0,
        )
    message = "已从备份恢复 %d 个文件" % restored
    if skipped:
        message += "（%d 个文件与备份一致，已跳过）" % skipped
    message += "；请重启 EasiCamera 使恢复生效"
    return PatchResult(
        ok=True,
        message=message,
        applied=[],
        failed=[],
        backup_dir=backup_absolute,
        needs_restart_hint=restored > 0,
    )


# --------------------------------------------------------------------------- #
# 规则作者辅助：内存模拟打补丁（供 analysis/<version>/verify_rules.py 使用）
# --------------------------------------------------------------------------- #


def simulate_patch(rule: Mapping, data: bytes, file_name: str,
                   feature_ids: Optional[Sequence[str]] = None) -> bytes:
    """在内存中把规则应用到给定文件字节，返回补丁后字节（不写盘）。

    典型用法（规则验证脚本）::

        import core.rules
        from core.patch_engine import simulate_patch, sha256_bytes
        rule = core.rules.get_rules("2.0.10.4229")
        orig = open("Main/EasiCamera.UI.dll", "rb").read()
        patched = simulate_patch(rule, orig, "EasiCamera.UI.dll", ["remove_ocr"])
        assert sha256_bytes(patched) == "fd8ec805..."

    校验失败抛 :class:`RuleError`。``feature_ids`` 为空时应用该文件上的全部 op。
    """
    errors = validate_rule(rule)
    if errors:
        raise RuleError("规则文件无效：%s" % "；".join(errors[:3]))
    all_ops = _all_ops_by_file(rule)
    ops = [op for op in all_ops.get(str(file_name), []) if feature_ids is None or op.feature_id in set(feature_ids)]
    if not ops:
        raise RuleError("文件 %s 上没有指定功能的补丁操作" % file_name)
    overlap = detect_overlaps({str(file_name): ops})
    if overlap:
        raise RuleError("；".join(overlap))
    buffer = bytearray(data)
    for op in sorted(ops, key=lambda item: item.offset):
        end = op.offset + op.length
        if end > len(buffer):
            raise RuleError("%s 偏移 0x%X 越界" % (file_name, op.offset))
        region = bytes(buffer[op.offset:end])
        if region == op.expected:
            buffer[op.offset:end] = op.patched
        elif region == op.patched:
            continue
        else:
            raise RuleError(
                "%s 偏移 0x%X 字节校验失败：期望 %s / 已补丁 %s，实际 %s"
                % (file_name, op.offset, op.expected.hex(), op.patched.hex(), region.hex())
            )
    return bytes(buffer)


__all__ = [
    # 契约 §3.3 接口
    "DetectedVersion",
    "PatchResult",
    "FeatureAvailability",
    "PatchPlanItem",
    "detect_version",
    "list_features",
    "plan",
    "apply_patches",
    "restore_backup",
    "is_patched",
    "DEFAULT_MAIN_DIRS",
    "find_main_dir",
    # 额外辅助（只增不改）
    "BACKUP_DIR_NAME",
    "RuleError",
    "PatchEngineError",
    "sha256_bytes",
    "sha256_file",
    "validate_rule",
    "validate_all_rules",
    "detect_overlaps",
    "simulate_patch",
]
