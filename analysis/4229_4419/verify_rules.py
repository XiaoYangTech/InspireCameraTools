#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EasiCamera 2.0.10.4229 / 2.1.0.4419 规则自动校验脚本。

做三件事（全部离线、不修改任何文件）：
1. 用 ``core.patch_engine.validate_rule`` 校验规则文件格式（hex、等长、指纹等）；
2. 读 ``extracted/`` 下的原版 DLL，逐功能用 ``simulate_patch`` 打补丁，
   断言补丁后 SHA-256 与**上游脚本内置期望值**一致；
3. 断言全功能组合后的整文件 SHA-256（记录在本目录 verify.md）。

用法（在仓库根目录 ``D:\\开发\\SeewoCamera`` 下）::

    D:/Software/python314/python.exe analysis/4229_4419/verify_rules.py

需要先下载/解包官方安装包（见 analysis/CONTRACT.md §2 与 analysis/4229_4419/README.md）。
退出码：0 = 全部通过；1 = 有失败；2 = 缺少解包文件。
"""

from __future__ import annotations

import hashlib
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "InspireCameraTools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from core import patch_engine  # noqa: E402
from core import rules as rules_pkg  # noqa: E402

INSTALLS = {
    "2.0.10.4229": os.path.join(
        REPO_ROOT, "extracted", "v2.0.10.4229", "EasiCamera_2.0.10.4229", "Main"
    ),
    "2.1.0.4419": os.path.join(
        REPO_ROOT, "extracted", "v2.1.0.4419", "EasiCamera_2.1.0.4419", "Main"
    ),
}

# 原版文件 SHA-256（来自上游脚本内置值；本次下载的官方安装包解包后逐一核对一致）
ORIGINAL_SHA = {
    ("2.0.10.4229", "EasiCamera.UI.dll"): "2821c3a7ef3d7deb68acaeee0475f0ba857bca979f7e0d03ec23098547bb9907",
    ("2.0.10.4229", "EasiCamera.Business.dll"): "700371fff8c0e41d7308224997359f4d122c5c3bb8cae0025ccebfa3c6d3ae93",
    ("2.0.10.4229", "EasiCamera.Util.dll"): "b4a40baf8786c06e6eabbabb47c9129c85d91ff2013955cbcb901259ab0fee73",
    ("2.1.0.4419", "EasiCamera.UI.dll"): "c80fd035926ea74a5362cc4748a66902e39def5784f46fa96b27928c2e0b06f4",
    ("2.1.0.4419", "EasiCamera.Business.dll"): "37f77a24083bd3c27eb20e8828125fb905b3d3c7dbc175d6a8fbd0b497561bb6",
}

# 单功能补丁后 SHA-256（上游脚本内置期望值 / 本次推导值）
PATCHED_SHA = {
    ("2.0.10.4229", "EasiCamera.UI.dll", "remove_ocr"):
        "fd8ec805cb10e9733ffd5fe122246a826f1e3d8cc5ed2765cb65f74b3f607f27",
    ("2.0.10.4229", "EasiCamera.Business.dll", "disable_ai_key"):
        "d6ef2173ae18dda68819ea91da0a4f0f46063e39a5951aea13ff94089220bf82",
    ("2.0.10.4229", "EasiCamera.Util.dll", "enable_hygon_freeze"):
        "231efe7f4fd2a7d0d2e895440902ad3c3ebd83b53be3e7baed991cd2cc8d948d",
    # 2026-11-14 修复：原上游 ctor 补丁会被 BoardApiOnFunctionModuleChanged 重新设为 Visible，
    # 现追加第二处补丁（0x1EE0C, 0x17→0x16：登录按钮可见性标志恒 false），哈希已更新。
    ("2.1.0.4419", "EasiCamera.UI.dll", "hide_login"):
        "0e7fc83e7b29f63c0c04766b2de33fb202b0eef599f5bb7525063cbb0aad3418",
    ("2.1.0.4419", "EasiCamera.UI.dll", "force_scan"):
        "0715d54b7f9d082b61bd1e47d5984cc64d38eba105c485c01ba23756c88087db",
    ("2.1.0.4419", "EasiCamera.Business.dll", "no_third_party_block"):
        "4e1ca8bacd5f798fd27e7f312c99830641d4f1d4247412cd680fd7372c01b8c2",
    ("2.1.0.4419", "EasiCamera.Business.dll", "disable_freeze"):
        "4f42886f8e026eeae95240b5f94baca5e89c8676e255fd4c5107001b5f4120c3",
}

# 全功能组合后 SHA-256（本引擎按 RULES 合并应用后计算，见 verify.md）
COMBINED_SHA = {
    "2.0.10.4229": {
        "EasiCamera.UI.dll": "fd8ec805cb10e9733ffd5fe122246a826f1e3d8cc5ed2765cb65f74b3f607f27",
        "EasiCamera.Business.dll": "d6ef2173ae18dda68819ea91da0a4f0f46063e39a5951aea13ff94089220bf82",
        "EasiCamera.Util.dll": "231efe7f4fd2a7d0d2e895440902ad3c3ebd83b53be3e7baed991cd2cc8d948d",
    },
    "2.1.0.4419": {
        "EasiCamera.UI.dll": "8e900aaa3732672e8d3634e27732c1f3ff0112328f4aa2e35979dad43b0797c6",
        "EasiCamera.Business.dll": "63d3abff82c50b7c73f31a12d05c3a100b4540dac74d50917a7283901630d7a1",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_file(main_dir: str, name: str) -> bytes:
    with open(os.path.join(main_dir, name), "rb") as fp:
        return fp.read()


def main() -> int:
    failures: list[str] = []
    checked = 0

    for version in ("2.0.10.4229", "2.1.0.4419"):
        print("=" * 78)
        print("版本 %s" % version)
        rule = rules_pkg.get_rules(version)
        if not rule:
            failures.append("%s: 规则文件不存在" % version)
            continue
        rule_errors = patch_engine.validate_rule(rule)
        if rule_errors:
            failures.append("%s: 规则格式错误: %s" % (version, "；".join(rule_errors)))
            print("  [FAIL] 规则格式: %s" % "；".join(rule_errors))
        else:
            print("  [ OK ] 规则格式校验通过（files/features/等长/指纹）")
        main_dir = INSTALLS[version]
        if not os.path.isdir(main_dir):
            print("  [SKIP] 缺少解包目录: %s" % main_dir)
            failures.append("%s: 缺少解包目录 %s" % (version, main_dir))
            continue

        # 1) 原版 SHA-256
        for file_name in rule["files"]:
            expected = ORIGINAL_SHA.get((version, file_name))
            actual = sha256_bytes(read_file(main_dir, file_name))
            checked += 1
            if expected and actual != expected:
                failures.append("%s/%s 原版 SHA-256 不符: %s != %s" % (version, file_name, actual, expected))
                print("  [FAIL] %s 原版哈希 %s（期望 %s）" % (file_name, actual, expected))
            else:
                print("  [ OK ] %s 原版哈希 %s" % (file_name, actual))

        # 2) 单功能补丁后 SHA-256（对照上游脚本内置值）
        for (ver, file_name, feature_id), expected in PATCHED_SHA.items():
            if ver != version:
                continue
            original = read_file(main_dir, file_name)
            patched = patch_engine.simulate_patch(rule, original, file_name, [feature_id])
            actual = sha256_bytes(patched)
            checked += 1
            if actual != expected:
                failures.append("%s/%s/%s 补丁后 SHA-256 不符: %s != %s"
                                % (version, file_name, feature_id, actual, expected))
                print("  [FAIL] %-22s %-20s 补丁后 %s（期望 %s）" % (file_name, feature_id, actual, expected))
            else:
                print("  [ OK ] %-22s %-20s 补丁后 %s" % (file_name, feature_id, actual))

        # 3) 全功能组合 SHA-256
        for file_name, expected in COMBINED_SHA.get(version, {}).items():
            original = read_file(main_dir, file_name)
            features = [feature for feature in rule["features"]
                        if any(op["file"] == file_name for op in rule["features"][feature])]
            patched = patch_engine.simulate_patch(rule, original, file_name, features)
            actual = sha256_bytes(patched)
            checked += 1
            if actual != expected:
                failures.append("%s/%s 组合补丁 SHA-256 不符: %s != %s"
                                % (version, file_name, actual, expected))
                print("  [FAIL] %-22s 组合补丁后 %s（期望 %s）" % (file_name, actual, expected))
            else:
                print("  [ OK ] %-22s 组合补丁后 %s" % (file_name, actual))

    print("=" * 78)
    print("共校验 %d 项，失败 %d 项" % (checked, len(failures)))
    if failures:
        for item in failures:
            print("  - %s" % item)
        print("结果: FAILED")
        return 1
    print("结果: ALL PASS（未在真机/真展台验证，仅静态字节级校验）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
