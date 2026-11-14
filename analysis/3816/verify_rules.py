#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EasiCamera 2.0.10.3816 规则自动校验脚本（契约 analysis/CONTRACT.md §3.4）。

做的事（可重复、幂等、只读原版）：

1. 从 ``InspireCameraTools/core/rules/v2_0_10_3816.py`` 载入 ``RULES``（按文件路径载入，
   与包结构无关，避免污染导入路径），并用真实补丁引擎（若可用）校验规则格式；
2. 对 ``extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main/`` 的原版文件核对
   ``RULES["files"]`` 的 SHA-256（版本指纹必须完全一致，否则拒绝继续）；
3. 在内存中按 ``RULES`` 应用补丁，逐 op 断言 ``expected`` 原字节，输出补丁后字节；
4. 断言：
   - 每个 op 等长替换、文件总大小不变；
   - 除 op 覆盖区间外的字节完全不变（等价于「只改了该改的地方」）；
   - 补丁后整文件 SHA-256 等于脚本内置期望值（单功能 / 全功能三种组合）；
   - 再应用一次时全部 op 已是 patched 状态（幂等）。
5. 把补丁后文件写到 ``work/re3816/verify_out/``（默认；可用 ``--out`` 改），并打印哈希表。
6. ``--ilspy``：用 ``.tools/ilspycmd`` 对补丁后程序集做完整反编译（结构合法性校验），
   在临时 Main 目录里硬链接依赖程序集，保证 ILSpy 能解析全部引用。

用法（Windows，bash 或 cmd 均可）::

    D:/Software/python314/python.exe analysis/3816/verify_rules.py            # 基本校验
    D:/Software/python314/python.exe analysis/3816/verify_rules.py --ilspy   # 附带 ILSpy 结构校验

退出码：0=全部通过；1=有断言失败；2=环境/参数错误。

注意：本脚本**绝不修改** ``extracted/`` 与 ``installers/`` 下的原文件，只在内存与
``work/re3816/`` 下操作。补丁未在真机/真展台验证。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

# Windows 控制台默认 GBK：强制 UTF-8 输出并容错，避免打印中文/符号时 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - 旧解释器/特殊环境忽略
        pass

HERE = os.path.dirname(os.path.abspath(__file__))          # analysis/3816
ROOT = os.path.dirname(os.path.dirname(HERE))              # 仓库根目录
RULE_PATH = os.path.join(ROOT, "InspireCameraTools", "core", "rules", "v2_0_10_3816.py")
DEFAULT_MAIN = os.path.join(
    ROOT, "extracted", "v2.0.10.3816", "EasiCamera_2.0.10.3816", "Main"
)
DEFAULT_OUT = os.path.join(ROOT, "work", "re3816", "verify_out")
ILSPY_DIR = os.path.join(ROOT, ".tools", "ilspycmd", "ilspycmd.dll")

#: 由本规则+引擎生成的补丁后 SHA-256（可用 patch_engine.simulate_patch 复现）
EXPECTED_PATCHED = {
    ("remove_english",): "6adf10e8a545adae68a64dc13e0cd10645f4f079a7784238390054ce50268847",
    ("force_scan",): "2678df7291053b8555b1e894b1968c7a45b16b468544f69c869c060259ec1508",
    ("remove_english", "force_scan"): "84df05d7ddbd3eef2a2642349c5ad3b75d3ca89ad1fe1704c134e725368e6216",
}

FAILURES: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if cond:
        print("  [PASS] " + msg)
    else:
        print("  [FAIL] " + msg)
        FAILURES.append(msg)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_rules():
    """按文件路径载入规则模块，返回 RULES 字典。"""
    if not os.path.isfile(RULE_PATH):
        raise SystemExit("规则文件不存在: %s" % RULE_PATH)
    spec = importlib.util.spec_from_file_location("rules_3816_verify", RULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    rules = getattr(module, "RULES", None)
    if not isinstance(rules, dict):
        raise SystemExit("规则模块没有导出 RULES 字典: %s" % RULE_PATH)
    return rules


def try_engine():
    """尝试导入真实补丁引擎（patch-core 提供）；失败返回 None（脚本仍可独立工作）。"""
    core_dir = os.path.join(ROOT, "InspireCameraTools")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    try:
        import core.patch_engine as engine  # noqa: WPS433 (延迟导入)
        return engine
    except Exception as exc:  # noqa: BLE001
        print("[WARN] 未能导入补丁引擎（%s），使用脚本内置的最小应用逻辑" % exc)
        return None


def apply_ops_local(data: bytes, ops: list) -> bytes:
    """脚本内置最小实现：逐 op 断言 expected 并替换为 patched（等长校验）。"""
    buf = bytearray(data)
    for op in ops:
        offset = int(op["offset"])
        expected = bytes.fromhex(op["expected"])
        patched = bytes.fromhex(op["patched"])
        if len(expected) != len(patched):
            raise AssertionError("op 长度不一致: %r" % op)
        if offset < 0 or offset + len(expected) > len(buf):
            raise AssertionError("op 越界: 0x%X + %d > %d" % (offset, len(expected), len(buf)))
        got = bytes(buf[offset:offset + len(expected)])
        if got != expected:
            raise AssertionError(
                "偏移 0x%X 原字节不符: 期望 %s 实际 %s" % (offset, expected.hex(), got.hex())
            )
        buf[offset:offset + len(patched)] = patched
    return bytes(buf)


def gather_file_ops(rules: dict, file_name: str, feature_ids=None) -> list:
    """收集某文件上的全部 op（可过滤功能），返回 [op dict + feature_id]。"""
    result = []
    for feature_id, ops in (rules.get("features") or {}).items():
        if feature_ids is not None and feature_id not in feature_ids:
            continue
        for op in ops:
            if op.get("file") == file_name:
                item = dict(op)
                item["feature_id"] = feature_id
                result.append(item)
    result.sort(key=lambda o: int(o["offset"]))
    return result


def diff_sites(original: bytes, patched: bytes) -> list[tuple[int, int]]:
    """返回发生变化的连续区间 [(start, end_exclusive)]。"""
    spans = []
    n = min(len(original), len(patched))
    i = 0
    changed = original != patched
    if len(original) != len(patched):
        raise AssertionError("文件长度发生变化: %d -> %d" % (len(original), len(patched)))
    while i < n:
        if original[i] != patched[i]:
            start = i
            while i < n and original[i] != patched[i]:
                i += 1
            spans.append((start, i))
        else:
            i += 1
    if changed and not spans:
        raise AssertionError("哈希不同但未找到差异区间")
    return spans


def spans_inside(sites: list[tuple[int, int]], allowed: list[tuple[int, int]]) -> bool:
    """diff 区间是否全部落在 op 覆盖范围内。"""
    for start, end in sites:
        if not any(a_start <= start and end <= a_end for a_start, a_end in allowed):
            return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EasiCamera 2.0.10.3816 规则自动校验")
    default_main = DEFAULT_MAIN if os.path.isdir(DEFAULT_MAIN) else ""
    ap.add_argument("--main", default=default_main, help="原版 Main 目录（默认 extracted/.../Main）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="补丁后文件输出目录（默认 work/re3816/verify_out）")
    ap.add_argument("--ilspy", action="store_true", help="额外用 ILSpy 反编译补丁后程序集做结构校验")
    ap.add_argument("--keep", action="store_true", help="保留 --ilspy 使用的临时 Main 目录")
    args = ap.parse_args(argv)

    print("=" * 78)
    print("EasiCamera 2.0.10.3816 规则自动校验")
    print("  仓库根目录 : %s" % ROOT)
    print("  规则文件   : %s" % RULE_PATH)
    print("  原版 Main  : %s" % (args.main or "<未找到>"))
    print("=" * 78)

    if not args.main or not os.path.isdir(args.main):
        print("[ERROR] 原版 Main 目录不存在: %r（可用 --main 指定）" % args.main)
        return 2

    rules = load_rules()
    engine = try_engine()

    # ---------- 1. 规则结构与版本 ----------
    print("\n[1/6] 规则结构与版本")
    ok(rules.get("version") == "2.0.10.3816", "RULES.version == 2.0.10.3816（实际 %r）" % rules.get("version"))
    ok(isinstance(rules.get("files"), dict) and len(rules["files"]) >= 2,
       "RULES.files 至少 2 个指纹文件（实际 %d）" % len(rules.get("files") or {}))
    if engine is not None:
        errors = engine.validate_rule(rules)
        ok(not errors, "补丁引擎 validate_rule 通过%s" % ("" if not errors else "：" + "；".join(errors)))
        grouped = engine._all_ops_by_file(rules)  # 内部结构：文件 -> [_Op]
        overlaps = engine.detect_overlaps(grouped)
        ok(not overlaps, "同文件 op 无重叠%s" % ("" if not overlaps else "：" + "；".join(overlaps)))
    else:
        # 无引擎时至少自查：功能 ID 必须来自契约 §3.1 的 8 个固定 ID
        allowed_ids = {
            "no_third_party_block", "force_scan", "hide_login", "disable_freeze",
            "enable_hygon_freeze", "remove_english", "remove_ocr", "disable_ai_key",
        }
        bad_ids = [fid for fid in (rules.get("features") or {}) if fid not in allowed_ids]
        ok(not bad_ids, "功能 ID 均在契约固定列表内%s" % ("" if not bad_ids else "：" + ",".join(bad_ids)))

    # ---------- 2. 原版文件指纹 ----------
    print("\n[2/6] 原版文件 SHA-256 指纹（RULES.files）")
    file_data: dict[str, bytes] = {}
    for file_name, expected_sha in (rules.get("files") or {}).items():
        path = os.path.join(args.main, file_name)
        if not os.path.isfile(path):
            ok(False, "原版文件缺失: %s" % file_name)
            continue
        data = open(path, "rb").read()
        file_data[file_name] = data
        actual = sha256_bytes(data)
        ok(actual.lower() == str(expected_sha).lower(),
           "%s 原版哈希匹配（%s…）" % (file_name, actual[:16]))
    if FAILURES:
        print("\n[STOP] 原版指纹校验失败，说明目录不是 2.0.10.3816 原版或已被改过；"
              "请从 installers/ 重新解包后再跑。")
        return 1

    # ---------- 3. 逐功能/全功能应用（内存），断言后哈希 ----------
    print("\n[3/6] 应用 RULES 并断言补丁后 SHA-256")
    ui_name = "EasiCamera.UI.dll"
    ui_original = file_data[ui_name]
    patched_outputs: dict[str, bytes] = {}
    for combo, expected_sha in EXPECTED_PATCHED.items():
        feature_ids = list(combo)
        ops = gather_file_ops(rules, ui_name, feature_ids)
        ok(bool(ops), "组合 %-32s 在 %s 上有 op（%d 条）" % ("+".join(feature_ids), ui_name, len(ops)))
        if engine is not None:
            patched = engine.simulate_patch(rules, ui_original, ui_name, feature_ids)
        else:
            patched = apply_ops_local(ui_original, ops)
        actual = sha256_bytes(patched)
        ok(len(patched) == len(ui_original), "组合 %-32s 文件大小不变（%d）" % ("+".join(feature_ids), len(patched)))
        ok(actual == expected_sha,
           "组合 %-32s 补丁后 sha256=%s%s" % ("+".join(feature_ids), actual,
                                               "" if actual == expected_sha else "（期望 %s）" % expected_sha))
        # 差异必须全部落在 op 区间内
        allowed = [(int(o["offset"]), int(o["offset"]) + len(bytes.fromhex(o["expected"]))) for o in ops]
        sites = diff_sites(ui_original, patched)
        ok(spans_inside(sites, allowed),
           "组合 %-32s 差异只出现在 op 覆盖区间（%d 处）" % ("+".join(feature_ids), len(sites)))
        if len(feature_ids) == len(rules["features"]):
            patched_outputs[ui_name] = patched
            patched_outputs[ui_name + ".combo"] = patched

    # ---------- 4. 幂等性 ----------
    print("\n[4/6] 幂等性（已是补丁状态时再次应用不应变化）")
    all_ops = gather_file_ops(rules, ui_name)
    once = apply_ops_local(ui_original, all_ops)
    twice = apply_ops_local(once, [
        {**op, "expected": op["patched"], "patched": op["patched"]} for op in all_ops
    ])
    ok(twice == once, "再次应用全部 op 后字节不变")
    # 逐功能单独应用同样可重复
    for feature_id in (rules.get("features") or {}):
        ops = gather_file_ops(rules, ui_name, [feature_id])
        one = apply_ops_local(ui_original, ops)
        two = apply_ops_local(one, [{**op, "expected": op["patched"], "patched": op["patched"]} for op in ops])
        ok(two == one, "功能 %-20s 单应用幂等" % feature_id)

    # ---------- 5. 输出补丁后文件 + 哈希表 ----------
    print("\n[5/6] 输出补丁后文件与哈希表")
    os.makedirs(args.out, exist_ok=True)
    summary_lines = []
    # 单功能输出
    for combo in EXPECTED_PATCHED:
        feature_ids = list(combo)
        patched = patched_outputs.get(ui_name) if len(feature_ids) == len(rules["features"]) else None
        if patched is None:
            ops = gather_file_ops(rules, ui_name, feature_ids)
            patched = apply_ops_local(ui_original, ops)
        suffix = "+".join(feature_ids)
        out_path = os.path.join(args.out, "EasiCamera.UI.%s.dll" % suffix.replace("+", "_"))
        with open(out_path, "wb") as f:
            f.write(patched)
        digest = sha256_bytes(patched)
        print("  %-52s %s" % (os.path.basename(out_path), digest))
        summary_lines.append((os.path.basename(out_path), digest, len(patched)))
        ok(os.path.isfile(out_path) and sha256_bytes(open(out_path, "rb").read()) == digest,
           "回读 %s 哈希一致" % os.path.basename(out_path))

    print("\n  原版 / 补丁后 SHA-256 汇总：")
    print("  %-22s %-64s %s" % ("文件", "SHA-256", "大小"))
    for file_name, data in sorted(file_data.items()):
        print("  %-22s %-64s %d" % (file_name + "(原版)", sha256_bytes(data), len(data)))

    # ---------- 6. ILSpy 结构校验（可选） ----------
    if args.ilspy:
        print("\n[6/6] ILSpy 反编译补丁后程序集（结构合法性）")
        # 安全检查：记录原版文件哈希，ILSpy 步骤结束后必须逐字节不变（绝不修改 extracted/）
        guard = {name: sha256_bytes(data) for name, data in file_data.items()}
        error = ilspy_check(args.main, patched_outputs[ui_name], args.keep, args.out)
        ok(error is None, "ILSpy 完整反编译补丁后 EasiCamera.UI.dll 成功%s" % ("" if error is None else "：" + error))
        for file_name, expected_sha in guard.items():
            path = os.path.join(args.main, file_name)
            try:
                after = sha256_bytes(open(path, "rb").read())
            except OSError as exc:
                after = "读取失败: %s" % exc
            ok(after == expected_sha, "原版文件 %s 在 ILSpy 步骤后未被修改" % file_name)
    else:
        print("\n[6/6] ILSpy 结构校验未启用（加 --ilspy 启用）")

    # ---------- 结果 ----------
    print("\n" + "=" * 78)
    if FAILURES:
        print("校验失败：%d 项" % len(FAILURES))
        for msg in FAILURES:
            print("  - " + msg)
        print("=" * 78)
        return 1
    print("全部校验通过 ✓  原版→应用 RULES→字节/哈希断言 均符合预期（未在真机验证）")
    print("=" * 78)
    return 0


def ilspy_check(original_main: str, patched_ui: bytes, keep: bool, out_dir: str) -> str | None:
    """把补丁后 UI.dll 放进一个「硬链接依赖」的临时 Main 目录，用 ILSpy 完整反编译。"""
    if not os.path.isfile(ILSPY_DIR):
        return "找不到 .tools/ilspycmd/ilspycmd.dll"
    tmp_dir = os.path.join(ROOT, "work", "re3816", "ilspy_main")
    try:
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)
        linked = copied = 0
        for entry in os.listdir(original_main):
            src = os.path.join(original_main, entry)
            dst = os.path.join(tmp_dir, entry)
            if not os.path.isfile(src):
                continue
            try:
                os.link(src, dst)  # NTFS 硬链接：同卷、无需管理员、零拷贝
                linked += 1
            except OSError:
                try:
                    shutil.copy2(src, dst)
                    copied += 1
                except OSError:
                    pass
        # 注意：EasiCamera.UI.dll 是硬链接，必须先 unlink 断开再写，
        # 否则 open(...,"wb") 会顺着硬链接写穿到原版 Main（严禁修改 extracted/）。
        ui_dst = os.path.join(tmp_dir, "EasiCamera.UI.dll")
        if os.path.exists(ui_dst):
            os.unlink(ui_dst)
        with open(ui_dst, "wb") as f:
            f.write(patched_ui)
        print("  临时 Main 目录: %s（硬链接 %d 个文件，复制 %d 个）" % (tmp_dir, linked, copied))
        out_src = os.path.join(out_dir, "ilspy_patched_src")
        if os.path.isdir(out_src):
            shutil.rmtree(out_src)
        proc = subprocess.run(
            ["dotnet", ILSPY_DIR, "-p", "-o", out_src, os.path.join(tmp_dir, "EasiCamera.UI.dll")],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
        output = (proc.stdout or "")
        decompiled_ok = any("\n" in line for line in output.splitlines()) or os.path.isdir(out_src)
        if proc.returncode != 0:
            return "dotnet ilspycmd 退出码 %d：%s" % (proc.returncode, output[-500:])
        if not os.path.isdir(out_src) or not os.listdir(out_src):
            return "ILSpy 未产出反编译工程目录"
        # 结构证据：两个目标方法都能被正常反编译出来
        cc = find_decompiled(out_src, "CompositionCorrectionDisplayToolBarItem.cs")
        ie = find_decompiled(out_src, "ImageEnhanceDisplayToolBarItem.cs")
        print("  反编译输出目录: %s" % out_src)
        if cc:
            text = open(cc, "r", encoding="utf-8", errors="replace").read()
            print("  [ILSpy] CompositionCorrectionDisplayToolBarItem: %s" %
                  ("FunctionModule = FunctionModule.None" if "FunctionModule.None" in text else "未见 None 赋值"))
            if "FunctionModule.None" not in text:
                return "补丁后 CompositionCorrectionDisplayToolBarItem 反编译结果不符合预期"
        else:
            return "ILSpy 输出中找不到 CompositionCorrectionDisplayToolBarItem.cs"
        if ie:
            text = open(ie, "r", encoding="utf-8", errors="replace").read()
            has_visibility_binding = "VisibilityProperty" in text
            print("  [ILSpy] ImageEnhanceDisplayToolBarItem: Visibility 绑定已移除=%s" % (not has_visibility_binding))
            if has_visibility_binding:
                return "补丁后 ImageEnhanceDisplayToolBarItem 仍存在 Visibility 绑定"
        else:
            return "ILSpy 输出中找不到 ImageEnhanceDisplayToolBarItem.cs"
        if not keep:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return None
    except subprocess.TimeoutExpired:
        return "dotnet ilspycmd 超时"
    except OSError as exc:
        return "ILSpy 执行失败: %s" % exc


def find_decompiled(root: str, filename: str) -> str | None:
    for dirpath, _dirnames, filenames in os.walk(root):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None


if __name__ == "__main__":
    sys.exit(main())
