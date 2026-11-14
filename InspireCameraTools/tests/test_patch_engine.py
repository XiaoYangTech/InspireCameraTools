# -*- coding: utf-8 -*-
"""补丁引擎单元自测（unittest）。

运行方式（在 ``InspireCameraTools/`` 下）::

    python -m unittest discover -s tests -v
    # 或
    python tests/test_patch_engine.py -v

覆盖：
* 规则格式校验 / 重叠检测 / 内存模拟打补丁（simulate_patch）
* 合成规则夹具上的 detect_version / plan / apply / is_patched / restore 全链路
* 失败不写盘、写盘失败回滚、备份清单、重复 apply 幂等
* find_main_dir 显式目录探测
* 真实 4229 / 4419 规则在**临时副本**上的端到端验证（对照上游脚本内置哈希）
* CLI ``python -m core.cli`` 的 JSON 输出（真实规则存在时）
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # InspireCameraTools/
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from core import patch_engine as engine  # noqa: E402
from core import rules as rules_pkg  # noqa: E402
from core.features import FEATURE_IDS  # noqa: E402

# --------------------------------------------------------------------------- #
# 合成规则夹具（不依赖真实安装包，任何机器上都能跑）
# --------------------------------------------------------------------------- #

FAKE_VERSION = "9.9.9.9001"

# 两个假 DLL 的确定性内容
FAKE_A = bytes((i * 7 + 3) % 256 for i in range(2048))  # 2048 字节
FAKE_B = bytes((i * 13 + 11) % 256 for i in range(1024))  # 1024 字节


def _hex(offset: int, length: int) -> str:
    return FAKE_A[offset:offset + length].hex()


def _flip(data: bytes, offset: int, length: int) -> bytes:
    patched = bytearray(data)
    for index in range(offset, offset + length):
        patched[index] = (patched[index] + 0x5A) & 0xFF
    return bytes(patched)


def make_fake_rule() -> dict:
    """构造一个含 4 个功能、覆盖两个文件的合成规则。

    布局（不重叠，除 remove_english 故意与 remove_ocr 重叠用于重叠检测）：
      remove_ocr          FakeA [0x10, 0x14)
      hide_login          FakeA [0x20, 0x23)
      disable_ai_key      FakeB [0x30, 0x32) + FakeA [0x40, 0x42)  （多 op / 多文件）
      enable_hygon_freeze FakeA [0x60, 0x64)
      remove_english      FakeA [0x11, 0x15)  ← 与 remove_ocr 重叠
    """
    features = {
        "remove_ocr": [
            {
                "file": "FakeA.dll",
                "offset": 0x10,
                "expected": _hex(0x10, 4),
                "patched": _flip(FAKE_A, 0x10, 4)[0x10:0x14].hex(),
                "note": "假补丁 A",
            }
        ],
        "hide_login": [
            {
                "file": "FakeA.dll",
                "offset": 0x20,
                "expected": _hex(0x20, 3),
                "patched": _flip(FAKE_A, 0x20, 3)[0x20:0x23].hex(),
                "note": "假补丁 B",
            }
        ],
        "disable_ai_key": [
            {
                "file": "FakeB.dll",
                "offset": 0x30,
                "expected": _hex_b(0x30, 2),
                "patched": _flip(FAKE_B, 0x30, 2)[0x30:0x32].hex(),
                "note": "假补丁 C1",
            },
            {
                "file": "FakeA.dll",
                "offset": 0x40,
                "expected": _hex(0x40, 2),
                "patched": _flip(FAKE_A, 0x40, 2)[0x40:0x42].hex(),
                "note": "假补丁 C2",
            },
        ],
        "enable_hygon_freeze": [
            {
                "file": "FakeA.dll",
                "offset": 0x60,
                "expected": _hex(0x60, 4),
                "patched": _flip(FAKE_A, 0x60, 4)[0x60:0x64].hex(),
                "note": "假补丁 D",
            }
        ],
        "remove_english": [
            {
                "file": "FakeA.dll",
                "offset": 0x11,
                "expected": _hex(0x11, 4),
                "patched": _flip(FAKE_A, 0x11, 4)[0x11:0x15].hex(),
                "note": "故意与 remove_ocr 重叠，用于测试重叠拒绝",
            }
        ],
    }
    return {
        "version": FAKE_VERSION,
        "display_name": "V" + FAKE_VERSION,
        "source_installer": "fake.exe",
        "files": {
            "FakeA.dll": hashlib.sha256(FAKE_A).hexdigest(),
            "FakeB.dll": hashlib.sha256(FAKE_B).hexdigest(),
        },
        "features": features,
        "unavailable_reason": {"force_scan": "合成规则未提供"},
    }


def _hex_b(offset: int, length: int) -> str:
    return FAKE_B[offset:offset + length].hex()


_ORIGINAL_ENGINE_FUNCS: dict = {}


def install_rules(rules: dict) -> None:
    """在测试内临时替换规则注册表（按版本降序）。"""
    ordered = {version: rules[version] for version in sorted(rules, reverse=True)}
    engine._all_rules = lambda: ordered  # type: ignore[attr-defined]
    engine._get_rules = lambda version: ordered.get(version)  # type: ignore[attr-defined]
    engine._rule_versions = lambda: list(ordered.keys())  # type: ignore[attr-defined]


def restore_rules() -> None:
    for name, func in _ORIGINAL_ENGINE_FUNCS.items():
        setattr(engine, name, func)


class FakeRuleTestCase(unittest.TestCase):
    """带合成规则 + 临时 Main 目录的测试基类。"""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="inspire-patch-test-")
        self.main_dir = os.path.join(self.tmp_dir, "Main")
        os.makedirs(self.main_dir)
        with open(os.path.join(self.main_dir, "FakeA.dll"), "wb") as fp:
            fp.write(FAKE_A)
        with open(os.path.join(self.main_dir, "FakeB.dll"), "wb") as fp:
            fp.write(FAKE_B)
        self.rule = make_fake_rule()
        install_rules({FAKE_VERSION: self.rule})

    def tearDown(self) -> None:
        restore_rules()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def read(self, name: str) -> bytes:
        with open(os.path.join(self.main_dir, name), "rb") as fp:
            return fp.read()

    def write(self, name: str, data: bytes) -> None:
        with open(os.path.join(self.main_dir, name), "wb") as fp:
            fp.write(data)


class TestRuleValidation(FakeRuleTestCase):
    def test_fake_rule_valid(self) -> None:
        self.assertEqual(engine.validate_rule(self.rule), [])

    def test_bad_rule_detected(self) -> None:
        rule = make_fake_rule()
        # expected/patched 等长约束
        rule["features"]["hide_login"][0]["patched"] = "00"
        errors = engine.validate_rule(rule)
        self.assertTrue(any("长度不一致" in message for message in errors), errors)

    def test_unknown_feature_id(self) -> None:
        rule = make_fake_rule()
        rule["features"]["not_a_feature"] = rule["features"]["hide_login"]
        errors = engine.validate_rule(rule)
        self.assertTrue(any("未知功能 ID" in message for message in errors), errors)

    def test_op_file_missing_from_files(self) -> None:
        rule = make_fake_rule()
        del rule["files"]["FakeB.dll"]
        errors = engine.validate_rule(rule)
        self.assertTrue(any("未在 RULES.files" in message for message in errors), errors)

    def test_bad_offset(self) -> None:
        rule = make_fake_rule()
        rule["features"]["hide_login"][0]["offset"] = "0x20"  # 字符串
        errors = engine.validate_rule(rule)
        self.assertTrue(any("offset" in message for message in errors), errors)


class TestDetectVersion(FakeRuleTestCase):
    def test_detect(self) -> None:
        detected = engine.detect_version(self.main_dir)
        self.assertIsNotNone(detected)
        self.assertEqual(detected.version, FAKE_VERSION)
        self.assertEqual(set(detected.matched_files), {"FakeA.dll", "FakeB.dll"})

    def test_detect_main_dir_via_find(self) -> None:
        # find_main_dir 通过 EasiCamera.exe / EasiCamera.UI.dll+Business.dll 判断是否 Main 目录
        with open(os.path.join(self.main_dir, "EasiCamera.exe"), "wb") as fp:
            fp.write(b"fake")
        self.assertEqual(engine.find_main_dir(self.main_dir), os.path.abspath(self.main_dir))
        self.assertEqual(engine.find_main_dir(self.tmp_dir), os.path.abspath(self.main_dir))
        self.assertIsNone(engine.find_main_dir(os.path.join(self.tmp_dir, "nope")))

    def test_detect_unknown_dir(self) -> None:
        other = os.path.join(self.tmp_dir, "Empty")
        os.makedirs(other)
        self.assertIsNone(engine.detect_version(other))
        self.assertIsNone(engine.detect_version(os.path.join(self.tmp_dir, "not-exists")))

    def test_detect_after_patch(self) -> None:
        result = engine.apply_patches(self.main_dir, ["remove_ocr"])
        self.assertTrue(result.ok, result.message)
        # 打成补丁后仍应能识别版本（回退已知补丁字节后比对原版哈希）
        detected = engine.detect_version(self.main_dir)
        self.assertIsNotNone(detected)
        self.assertEqual(detected.version, FAKE_VERSION)


class TestPlan(FakeRuleTestCase):
    def test_plan_availability(self) -> None:
        items = engine.plan(self.main_dir, ["remove_ocr", "force_scan"])
        by_id = {item.feature.id: item for item in items}
        self.assertTrue(by_id["remove_ocr"].available)
        self.assertFalse(by_id["force_scan"].available)
        self.assertIn("合成规则未提供", by_id["force_scan"].reason)
        self.assertEqual(len(by_id["remove_ocr"].ops), 1)
        self.assertEqual(by_id["remove_ocr"].ops[0]["file"], "FakeA.dll")

    def test_plan_overlap_marks_unavailable(self) -> None:
        items = engine.plan(self.main_dir, ["remove_ocr", "remove_english"])
        by_id = {item.feature.id: item for item in items}
        self.assertFalse(by_id["remove_ocr"].available)
        self.assertIn("重叠", by_id["remove_ocr"].reason)

    def test_plan_unknown_feature_id(self) -> None:
        with self.assertRaises(KeyError):
            engine.plan(self.main_dir, ["no_such_feature"])


class TestApplyRestore(FakeRuleTestCase):
    def test_apply_is_patched_restore(self) -> None:
        features = ["remove_ocr", "hide_login", "disable_ai_key"]
        before_a, before_b = self.read("FakeA.dll"), self.read("FakeB.dll")
        result = engine.apply_patches(self.main_dir, features)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(sorted(result.applied), sorted(features))
        self.assertEqual(result.failed, [])
        self.assertTrue(result.needs_restart_hint)
        self.assertIsNotNone(result.backup_dir)
        self.assertTrue(os.path.isdir(result.backup_dir))

        # 文件内容确实变化，且只有目标区域变化
        after_a, after_b = self.read("FakeA.dll"), self.read("FakeB.dll")
        self.assertNotEqual(before_a, after_a)
        self.assertNotEqual(before_b, after_b)
        self.assertEqual(len(before_a), len(after_a))

        patched = engine.is_patched(self.main_dir)
        for feature_id in features:
            self.assertTrue(patched[feature_id], feature_id)
        self.assertFalse(patched["enable_hygon_freeze"])

        # 备份内容 = 原版
        backup_a = os.path.join(result.backup_dir, "FakeA.dll")
        self.assertEqual(engine.sha256_file(backup_a), hashlib.sha256(before_a).hexdigest())
        self.assertTrue(os.path.isfile(os.path.join(result.backup_dir, engine.MANIFEST_NAME)))

        # 恢复
        restore = engine.restore_backup(self.main_dir, result.backup_dir)
        self.assertTrue(restore.ok, restore.message)
        self.assertEqual(self.read("FakeA.dll"), before_a)
        self.assertEqual(self.read("FakeB.dll"), before_b)
        self.assertFalse(any(engine.is_patched(self.main_dir).values()))

    def test_apply_idempotent(self) -> None:
        first = engine.apply_patches(self.main_dir, ["remove_ocr", "hide_login"])
        self.assertTrue(first.ok, first.message)
        second = engine.apply_patches(self.main_dir, ["remove_ocr"])
        self.assertTrue(second.ok, second.message)
        self.assertIsNone(second.backup_dir)
        self.assertFalse(second.needs_restart_hint)

    def test_apply_all_multi_file_feature(self) -> None:
        result = engine.apply_patches(self.main_dir, ["disable_ai_key"])
        self.assertTrue(result.ok, result.message)
        patched = self.read("FakeA.dll")
        self.assertNotEqual(patched[0x40:0x42], FAKE_A[0x40:0x42])
        patched_b = self.read("FakeB.dll")
        self.assertNotEqual(patched_b[0x30:0x32], FAKE_B[0x30:0x32])

    def test_unknown_feature_rejected(self) -> None:
        result = engine.apply_patches(self.main_dir, ["no_such_feature"])
        self.assertFalse(result.ok)
        self.assertEqual(self.read("FakeA.dll"), FAKE_A)  # 未写盘

    def test_unavailable_feature_rejected_atomically(self) -> None:
        result = engine.apply_patches(self.main_dir, ["remove_ocr", "force_scan"])
        self.assertFalse(result.ok)
        self.assertTrue(result.failed)
        self.assertEqual(self.read("FakeA.dll"), FAKE_A)  # 整体不写盘

    def test_overlap_rejected(self) -> None:
        result = engine.apply_patches(self.main_dir, ["remove_ocr", "remove_english"])
        self.assertFalse(result.ok)
        self.assertIn("重叠", result.message)
        self.assertEqual(self.read("FakeA.dll"), FAKE_A)

    def test_byte_mismatch_writes_nothing(self) -> None:
        broken = bytearray(FAKE_A)
        broken[0x12] ^= 0xFF  # 破坏 remove_ocr 目标区域
        self.write("FakeA.dll", bytes(broken))
        backup_root = os.path.join(self.tmp_dir, "backup-root")
        result = engine.apply_patches(self.main_dir, ["hide_login"], backup_root=backup_root)
        self.assertFalse(result.ok)
        self.assertIsNone(result.backup_dir)  # 校验阶段失败，不建备份
        self.assertEqual(self.read("FakeA.dll"), bytes(broken))
        self.assertFalse(os.path.isdir(backup_root))

    def test_restore_invalid_dir(self) -> None:
        result = engine.restore_backup(self.main_dir, os.path.join(self.tmp_dir, "nope"))
        self.assertFalse(result.ok)

    def test_restore_partial_from_missing_manifest(self) -> None:
        # 无清单的备份目录：按目录内文件相对路径恢复
        backup_dir = os.path.join(self.tmp_dir, "manual-backup")
        os.makedirs(backup_dir)
        self.write("FakeA.dll", b"BROKEN")
        with open(os.path.join(backup_dir, "FakeA.dll"), "wb") as fp:
            fp.write(FAKE_A)
        result = engine.restore_backup(self.main_dir, backup_dir)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.read("FakeA.dll"), FAKE_A)


class TestRollback(FakeRuleTestCase):
    def test_write_failure_rolls_back(self) -> None:
        original_write = engine._write_atomic
        state = {"real_writes": 0, "raised": False}

        def flaky_write(path: str, data: bytes) -> None:
            if os.sep + "_InspirePatchBackup" in path or "/_InspirePatchBackup" in path:
                return original_write(path, data)  # 备份裸写照常
            state["real_writes"] += 1
            if state["real_writes"] >= 2 and not state.get("raised"):
                state["raised"] = True
                raise PermissionError("模拟写盘失败（EasiCamera 占用）")
            return original_write(path, data)

        fake_a_before, fake_b_before = self.read("FakeA.dll"), self.read("FakeB.dll")
        engine._write_atomic = flaky_write  # type: ignore[assignment]
        try:
            # disable_ai_key 同时改 FakeB / FakeA，写入第二个文件时模拟失败
            result = engine.apply_patches(self.main_dir, ["disable_ai_key"])
        finally:
            engine._write_atomic = original_write  # type: ignore[assignment]
        self.assertFalse(result.ok)
        self.assertIn("回滚", result.message)
        self.assertIsNotNone(result.backup_dir)
        # 已写的文件被回滚，两个文件都应与原版一致
        self.assertEqual(self.read("FakeA.dll"), fake_a_before)
        self.assertEqual(self.read("FakeB.dll"), fake_b_before)


class TestFindMainDirLayout(unittest.TestCase):
    """真实安装布局探测：版本化目录 EasiCamera_<版本>/Main 与旧式 Main。"""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="inspire-findmain-")
        self.install_root = os.path.join(self.tmp_dir, "Seewo", "EasiCamera")
        self.version_dir = os.path.join(self.install_root, "EasiCamera_2.1.0.4419")
        self.main_dir = os.path.join(self.version_dir, "Main")
        os.makedirs(self.main_dir)
        with open(os.path.join(self.main_dir, "EasiCamera.exe"), "wb") as fp:
            fp.write(b"fake")
        with open(os.path.join(self.main_dir, "EasiCamera.UI.dll"), "wb") as fp:
            fp.write(b"fake-ui")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_explicit_paths(self) -> None:
        # Main 本身 / 版本目录 / 安装根目录 三种输入都应定位到 Main
        for given in (self.main_dir, self.version_dir, self.install_root):
            self.assertEqual(engine.find_main_dir(given), os.path.abspath(self.main_dir), given)
        self.assertIsNone(engine.find_main_dir(os.path.join(self.tmp_dir, "nope")))

    def test_scan_versioned_layout(self) -> None:
        with mock.patch.object(engine, "DEFAULT_MAIN_DIRS", [self.install_root]),                 mock.patch.object(engine, "_seewo_registry_candidates", return_value=[]),                 mock.patch.object(engine, "_registry_candidates", return_value=[]):
            self.assertEqual(engine.find_main_dir(), os.path.abspath(self.main_dir))

    def test_registry_candidate(self) -> None:
        with mock.patch.object(engine, "DEFAULT_MAIN_DIRS", []),                 mock.patch.object(engine, "_seewo_registry_candidates",
                                  return_value=[os.path.join(self.main_dir, "EasiCamera.exe")]),                 mock.patch.object(engine, "_registry_candidates", return_value=[]):
            self.assertEqual(engine.find_main_dir(), os.path.abspath(self.main_dir))


class TestSimulatePatch(FakeRuleTestCase):
    def test_simulate(self) -> None:
        patched = engine.simulate_patch(self.rule, FAKE_A, "FakeA.dll", ["remove_ocr"])
        self.assertEqual(patched[0x10:0x14], bytes.fromhex(self.rule["features"]["remove_ocr"][0]["patched"]))
        # 幂等：对已补丁内容再应用不报错
        again = engine.simulate_patch(self.rule, patched, "FakeA.dll", ["remove_ocr"])
        self.assertEqual(again, patched)

    def test_simulate_mismatch(self) -> None:
        broken = bytearray(FAKE_A)
        broken[0x10] ^= 0xFF
        with self.assertRaises(engine.RuleError):
            engine.simulate_patch(self.rule, bytes(broken), "FakeA.dll", ["remove_ocr"])


class TestOverlapHelper(unittest.TestCase):
    def test_detect_overlaps(self) -> None:
        op1 = engine._Op("f1", "X.dll", 0x10, b"\x01\x02", b"\x03\x04", "")
        op2 = engine._Op("f2", "X.dll", 0x11, b"\x05", b"\x06", "")
        errors = engine.detect_overlaps({"X.dll": [op1, op2]})
        self.assertTrue(errors)
        self.assertIn("重叠", errors[0])
        op3 = engine._Op("f3", "X.dll", 0x12, b"\x05", b"\x06", "")
        self.assertEqual(engine.detect_overlaps({"X.dll": [op1, op3]}), [])


# --------------------------------------------------------------------------- #
# 真实规则端到端（需要 extracted/ 下的官方解包目录；缺失则跳过）
# --------------------------------------------------------------------------- #

REAL_INSTALLS = {
    "2.0.10.4229": os.path.join(_REPO_ROOT, "extracted", "v2.0.10.4229", "EasiCamera_2.0.10.4229", "Main"),
    "2.1.0.4419": os.path.join(_REPO_ROOT, "extracted", "v2.1.0.4419", "EasiCamera_2.1.0.4419", "Main"),
}

# 上游脚本内置的单功能补丁后 SHA-256（用于交叉验证规则移植正确性）
UPSTREAM_PATCHED_SHA = {
    ("2.0.10.4229", "EasiCamera.UI.dll", "remove_ocr"): "fd8ec805cb10e9733ffd5fe122246a826f1e3d8cc5ed2765cb65f74b3f607f27",
    ("2.0.10.4229", "EasiCamera.Business.dll", "disable_ai_key"): "d6ef2173ae18dda68819ea91da0a4f0f46063e39a5951aea13ff94089220bf82",
    ("2.0.10.4229", "EasiCamera.Util.dll", "enable_hygon_freeze"): "231efe7f4fd2a7d0d2e895440902ad3c3ebd83b53be3e7baed991cd2cc8d948d",
    ("2.1.0.4419", "EasiCamera.UI.dll", "hide_login"): "0e7fc83e7b29f63c0c04766b2de33fb202b0eef599f5bb7525063cbb0aad3418",
    ("2.1.0.4419", "EasiCamera.UI.dll", "force_scan"): "0715d54b7f9d082b61bd1e47d5984cc64d38eba105c485c01ba23756c88087db",
    ("2.1.0.4419", "EasiCamera.Business.dll", "no_third_party_block"): "4e1ca8bacd5f798fd27e7f312c99830641d4f1d4247412cd680fd7372c01b8c2",
    ("2.1.0.4419", "EasiCamera.Business.dll", "disable_freeze"): "4f42886f8e026eeae95240b5f94baca5e89c8676e255fd4c5107001b5f4120c3",
}

# 全功能组合补丁后 SHA-256（4229 三个文件互不影响；4419 UI/Business 各有两个 op）
COMBINED_PATCHED_SHA = {
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


def _real_rule_available(version: str) -> bool:
    main_dir = REAL_INSTALLS.get(version)
    rule = rules_pkg.get_rules(version)
    return bool(rule) and bool(main_dir) and os.path.isdir(main_dir)


@unittest.skipUnless(rules_pkg.get_rules("2.0.10.4229"), "4229 规则文件不存在")
class TestRealRule4229(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = rules_pkg.get_rules("2.0.10.4229")
        self.tmp_dir = tempfile.mkdtemp(prefix="inspire-4229-")
        self.main_dir = os.path.join(self.tmp_dir, "Main")
        os.makedirs(self.main_dir)
        for file_name in self.rule["files"]:
            shutil.copy2(os.path.join(REAL_INSTALLS["2.0.10.4229"], file_name),
                         os.path.join(self.main_dir, file_name))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_detect(self) -> None:
        if not os.path.isdir(REAL_INSTALLS["2.0.10.4229"]):
            self.skipTest("缺少 4229 解包目录")
        detected = engine.detect_version(self.main_dir)
        self.assertIsNotNone(detected)
        self.assertEqual(detected.version, "2.0.10.4229")

    def test_simulate_against_upstream_hashes(self) -> None:
        if not os.path.isdir(REAL_INSTALLS["2.0.10.4229"]):
            self.skipTest("缺少 4229 解包目录")
        for (version, file_name, feature_id), expected_sha in UPSTREAM_PATCHED_SHA.items():
            if version != "2.0.10.4229":
                continue
            with open(os.path.join(self.main_dir, file_name), "rb") as fp:
                original = fp.read()
            patched = engine.simulate_patch(self.rule, original, file_name, [feature_id])
            self.assertEqual(engine.sha256_bytes(patched), expected_sha, "%s %s" % (file_name, feature_id))

    def test_apply_restore_chain(self) -> None:
        if not os.path.isdir(REAL_INSTALLS["2.0.10.4229"]):
            self.skipTest("缺少 4229 解包目录")
        originals = {}
        for file_name in self.rule["files"]:
            with open(os.path.join(self.main_dir, file_name), "rb") as fp:
                originals[file_name] = fp.read()
        features = sorted(self.rule["features"].keys())
        result = engine.apply_patches(self.main_dir, features)
        self.assertTrue(result.ok, result.message)
        for file_name, expected_sha in COMBINED_PATCHED_SHA["2.0.10.4229"].items():
            self.assertEqual(engine.sha256_file(os.path.join(self.main_dir, file_name)), expected_sha, file_name)
        patched = engine.is_patched(self.main_dir)
        for feature_id in features:
            self.assertTrue(patched[feature_id], feature_id)
        restore = engine.restore_backup(self.main_dir, result.backup_dir)
        self.assertTrue(restore.ok, restore.message)
        for file_name, data in originals.items():
            self.assertEqual(engine.sha256_file(os.path.join(self.main_dir, file_name)),
                             engine.sha256_bytes(data), file_name)


@unittest.skipUnless(rules_pkg.get_rules("2.1.0.4419"), "4419 规则文件不存在")
class TestRealRule4419(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = rules_pkg.get_rules("2.1.0.4419")
        self.tmp_dir = tempfile.mkdtemp(prefix="inspire-4419-")
        self.main_dir = os.path.join(self.tmp_dir, "Main")
        os.makedirs(self.main_dir)
        for file_name in self.rule["files"]:
            shutil.copy2(os.path.join(REAL_INSTALLS["2.1.0.4419"], file_name),
                         os.path.join(self.main_dir, file_name))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_detect(self) -> None:
        if not os.path.isdir(REAL_INSTALLS["2.1.0.4419"]):
            self.skipTest("缺少 4419 解包目录")
        detected = engine.detect_version(self.main_dir)
        self.assertIsNotNone(detected)
        self.assertEqual(detected.version, "2.1.0.4419")

    def test_simulate_against_upstream_hashes(self) -> None:
        if not os.path.isdir(REAL_INSTALLS["2.1.0.4419"]):
            self.skipTest("缺少 4419 解包目录")
        for (version, file_name, feature_id), expected_sha in UPSTREAM_PATCHED_SHA.items():
            if version != "2.1.0.4419":
                continue
            with open(os.path.join(self.main_dir, file_name), "rb") as fp:
                original = fp.read()
            patched = engine.simulate_patch(self.rule, original, file_name, [feature_id])
            self.assertEqual(engine.sha256_bytes(patched), expected_sha, "%s %s" % (file_name, feature_id))

    def test_apply_same_file_two_features(self) -> None:
        """同一文件两个功能（UI.dll 的 hide_login + force_scan，Business.dll 两个 op）合并应用。"""
        if not os.path.isdir(REAL_INSTALLS["2.1.0.4419"]):
            self.skipTest("缺少 4419 解包目录")
        result = engine.apply_patches(self.main_dir, ["hide_login", "force_scan", "no_third_party_block", "disable_freeze"])
        self.assertTrue(result.ok, result.message)
        for file_name, expected_sha in COMBINED_PATCHED_SHA["2.1.0.4419"].items():
            self.assertEqual(engine.sha256_file(os.path.join(self.main_dir, file_name)), expected_sha, file_name)
        reasons = engine.plan(self.main_dir, ["disable_freeze"])
        self.assertTrue(reasons[0].already_patched)


class TestCli(unittest.TestCase):
    """CLI 集成测试（真实规则 + 4229 解包目录）。"""

    def _run_cli(self, *args: str):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, "-m", "core.cli", *args],
            cwd=_TOOLS_DIR, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
        )

    def test_list_json(self) -> None:
        proc = self._run_cli("list", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        versions = [item["version"] for item in payload["versions"]]
        self.assertIn("2.0.10.4229", versions)
        self.assertIn("2.1.0.4419", versions)

    def test_detect_json(self) -> None:
        main_dir = REAL_INSTALLS["2.0.10.4229"]
        if not os.path.isdir(main_dir):
            self.skipTest("缺少 4229 解包目录")
        proc = self._run_cli("detect", "--main", main_dir, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["detected"]["version"], "2.0.10.4229")

    def test_plan_json(self) -> None:
        main_dir = REAL_INSTALLS["2.1.0.4419"]
        if not os.path.isdir(main_dir):
            self.skipTest("缺少 4419 解包目录")
        proc = self._run_cli("plan", "--main", main_dir, "--features", "no_third_party_block,force_scan", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual({item["id"] for item in payload["items"]}, {"no_third_party_block", "force_scan"})

    def test_validate_json(self) -> None:
        proc = self._run_cli("validate", "--json")
        payload = json.loads(proc.stdout)
        for version, errors in payload["rules"].items():
            self.assertEqual(errors, [], version)


def setUpModule() -> None:
    for name in ("_all_rules", "_get_rules", "_rule_versions"):
        _ORIGINAL_ENGINE_FUNCS[name] = getattr(engine, name)

if __name__ == "__main__":
    unittest.main(verbosity=2)
