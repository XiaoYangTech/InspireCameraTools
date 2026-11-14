#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EasiCamera 2.0.10.4087 规则自动校验脚本（可重复运行，纯只读原版文件）。

流程：
  1. 读取 ``analysis/CONTRACT.md`` §3.2 格式的 4087 规则（``core.rules`` 自动发现）；
  2. 校验规则格式 + 原版文件 SHA-256 指纹；
  3. 用 ``core.patch_engine.simulate_patch`` 在内存里逐个功能 / 全功能应用补丁，
     逐 op 断言 expected 原字节、补丁后字节，并与内置的补丁后 SHA-256 比对；
  4. 断言补丁后单功能/全功能哈希与 ``analysis/4087/verify.md`` 记录一致；
  5. 幂等性检查：对补丁后字节再次应用返回相同结果；
  6. 可选 ``--out DIR``：把补丁后的文件写到该目录（供 ILSpy 反编译验证，不碰原文件）。

用法（在仓库根目录或任意目录均可）::

    D:/Software/python314/python.exe analysis/4087/verify_rules.py
    D:/Software/python314/python.exe analysis/4087/verify_rules.py --main <Main目录> --out work/re4087/patched

退出码：0 全部通过；1 有失败。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

VERSION = "2.0.10.4087"
DEFAULT_MAIN = "extracted/v20240912161108/EasiCamera_2.0.10.4087/Main"

# 单个功能补丁后的文件 SHA-256（由 work/re4087/compute_patches.py 对原版实测得到）
EXPECTED_FEATURE_SHA = {
    ("remove_ocr", "EasiCamera.UI.dll"): "b55847ff1427ea918ef95186c00e564ebe65ccba030c1637ce9135bdcb0985fa",
    ("hide_login", "EasiCamera.UI.dll"): "791aeef8cf69eabfaa8b5fa9bd9a86e2f7ff037717f6d75324b6d61bbf2f7cc9",
    ("force_scan", "EasiCamera.UI.dll"): "65e9bfcc5a514e6236a905c8c89006e14a9e2056a3adfa42a0fafadd7c6e83c0",
    ("remove_english", "EasiCamera.UI.dll"): "ae1d8591cb7d85d4bbf590fdf3605fd38090924d87dbc6a72435f37a3727a968",
    ("disable_ai_key", "EasiCamera.Business.dll"): "50a565decf9c7a847082cc6b6853deb06644ad65a6bc7c517e641aab315358a2",
}

# 全部可用功能一起应用后的文件 SHA-256
EXPECTED_ALL_SHA = {
    "EasiCamera.UI.dll": "55e089394ef128ac297fe575b6eafda831890a522d1ff37a5645d4630acbdedd",
    "EasiCamera.Business.dll": "50a565decf9c7a847082cc6b6853deb06644ad65a6bc7c517e641aab315358a2",
}

# 不可用功能 -> 期望在规则 unavailable_reason 中出现的原因关键字
UNAVAILABLE = {
    "no_third_party_block": "第三方",
    "disable_freeze": "冻结",
    "enable_hygon_freeze": "冻结",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, cond: bool, message: str) -> None:
        self.checks += 1
        if not cond:
            self.failures.append(message)
            print("  [FAIL] " + message)
        else:
            print("  [ OK ] " + message)

    def eq(self, actual, expected, message: str) -> None:
        self.check(actual == expected, "%s（实际 %r / 期望 %r）" % (message, actual, expected))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EasiCamera 2.0.10.4087 规则校验")
    parser.add_argument("--main", default=None, help="原版 Main 目录（默认仓库内 4087 解包目录）")
    parser.add_argument("--out", default=None, help="可选：把补丁后文件写到该目录（供 ILSpy 验证）")
    args = parser.parse_args(argv)

    root = _repo_root()
    main_dir = Path(args.main) if args.main else root / DEFAULT_MAIN
    sys.path.insert(0, str(root / "InspireCameraTools"))
    from core.patch_engine import RuleError, sha256_bytes as _sh, simulate_patch, validate_rule  # noqa: E402
    from core.rules import get_rules  # noqa: E402

    c = Checker()
    print("=" * 78)
    print("EasiCamera %s 规则校验（原版 Main: %s）" % (VERSION, main_dir))
    print("=" * 78)

    rule = get_rules(VERSION)
    if rule is None:
        print("  [FAIL] 未发现 %s 规则（core.rules 自动发现失败）" % VERSION)
        return 1
    c.eq(rule.get("version"), VERSION, "规则版本号")
    errors = validate_rule(rule)
    c.check(not errors, "规则格式合法（validate_rule）: %s" % ("；".join(errors) if errors else "无错误"))

    files = rule.get("files") or {}
    ops_by_file: dict[str, list[dict]] = {}
    for feature_id, ops in (rule.get("features") or {}).items():
        c.check(bool(ops), "功能 %s 至少有一条 op" % feature_id)
        for op in ops:
            ops_by_file.setdefault(op["file"], []).append(op)

    # ---------- 1. 原版指纹 ----------
    print("\n[1] 原版文件 SHA-256 指纹")
    originals: dict[str, bytes] = {}
    for fname, digest in files.items():
        path = main_dir / fname
        if not path.is_file():
            c.check(False, "缺少原版文件 %s" % path)
            continue
        data = path.read_bytes()
        originals[fname] = data
        c.eq(sha256_bytes(data), digest, "%s 原版 SHA-256" % fname)

    # ---------- 2. 逐功能补丁哈希 ----------
    print("\n[2] 单功能补丁（expected 断言 + 补丁后 SHA-256）")
    patched_by_feature: dict[tuple[str, str], bytes] = {}
    for (feature_id, fname), expect_sha in EXPECTED_FEATURE_SHA.items():
        if fname not in originals:
            continue
        try:
            patched = simulate_patch(rule, originals[fname], fname, [feature_id])
        except RuleError as exc:
            c.check(False, "%s/%s 应用失败: %s" % (feature_id, fname, exc))
            continue
        patched_by_feature[(feature_id, fname)] = patched
        got = _sh(patched)
        c.eq(got, expect_sha, "%s/%s 补丁后 SHA-256" % (feature_id, fname))
        c.check(patched != originals[fname], "%s/%s 补丁后文件确实变化" % (feature_id, fname))
        # 逐 op 断言补丁后区域就是规则里的 patched 字节
        for op in ops_by_file[fname]:
            if op["file"] != fname:
                continue
            if (feature_id != "all") and (op not in (rule["features"].get(feature_id) or [])):
                continue
            end = op["offset"] + len(bytes.fromhex(op["patched"]))
            region = patched[op["offset"]:end]
            c.eq(region.hex(), op["patched"], "%s 偏移 0x%X 补丁后字节" % (fname, op["offset"]))

    # ---------- 3. 全功能合并 ----------
    print("\n[3] 全部可用功能合并补丁")
    all_features = sorted((rule.get("features") or {}).keys())
    combined: dict[str, bytes] = {}
    for fname, expect_sha in EXPECTED_ALL_SHA.items():
        if fname not in originals:
            continue
        patched = simulate_patch(rule, originals[fname], fname, all_features)
        combined[fname] = patched
        c.eq(_sh(patched), expect_sha, "%s 全功能补丁后 SHA-256" % fname)

    # ---------- 4. 幂等 ----------
    print("\n[4] 幂等性（对已补丁字节重复应用）")
    for (feature_id, fname), patched in patched_by_feature.items():
        try:
            again = simulate_patch(rule, patched, fname, [feature_id])
        except RuleError as exc:
            c.check(False, "%s/%s 幂等应用失败: %s" % (feature_id, fname, exc))
            continue
        c.eq(_sh(again), _sh(patched), "%s/%s 重复应用结果不变" % (feature_id, fname))

    # ---------- 5. 不可用功能原因 ----------
    print("\n[5] 不可用功能说明")
    reasons = rule.get("unavailable_reason") or {}
    for feature_id, keyword in UNAVAILABLE.items():
        reason = str(reasons.get(feature_id) or "")
        c.check(bool(reason), "unavailable_reason 覆盖 %s" % feature_id)
        c.check(keyword in reason, "%s 的原因包含关键字「%s」" % (feature_id, keyword))
    available = set((rule.get("features") or {}).keys())
    for feature_id in ("no_third_party_block", "force_scan", "hide_login", "disable_freeze",
                       "enable_hygon_freeze", "remove_english", "remove_ocr", "disable_ai_key"):
        c.check(
            feature_id in available or feature_id in reasons,
            "功能 %s 要么可用、要么有 unavailable_reason" % feature_id,
        )

    # ---------- 6. 可选输出补丁后副本 ----------
    if args.out:
        out_dir = Path(args.out)
        if not out_dir.is_absolute():
            out_dir = root / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        for fname, data in combined.items():
            (out_dir / fname).write_bytes(data)
            print("\n[out] 已写出补丁后副本: %s (%s)" % (out_dir / fname, _sh(data)))

    # ---------- 汇总 ----------
    print("\n" + "=" * 78)
    print("补丁偏移 / 补丁后 SHA-256 汇总")
    print("=" * 78)
    print("%-16s %-24s %-10s %-6s %s" % ("功能", "文件", "偏移", "长度", "补丁后 SHA-256"))
    for (feature_id, fname), expect_sha in EXPECTED_FEATURE_SHA.items():
        ops = [op for op in (rule["features"].get(feature_id) or []) if op["file"] == fname]
        total = sum(len(bytes.fromhex(op["expected"])) for op in ops)
        offs = ",".join("0x%X" % op["offset"] for op in ops)
        print("%-16s %-24s %-10s %-6d %s" % (feature_id, fname, offs, total, expect_sha))
    for fname, expect_sha in EXPECTED_ALL_SHA.items():
        print("%-16s %-24s %-10s %-6s %s" % ("<全部功能>", fname, "-", "-", expect_sha))

    total_checks = c.checks
    if c.failures:
        print("\n结果：失败 %d / 共 %d 项检查" % (len(c.failures), total_checks))
        for message in c.failures:
            print("  - " + message)
        return 1
    print("\n结果：全部通过（%d 项检查）。注意：仅静态/字节级验证，未在真机运行 EasiCamera。" % total_checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
