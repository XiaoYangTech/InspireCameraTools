# -*- coding: utf-8 -*-
"""破坏自动更新模块单元自测（unittest）。

在临时目录里伪造一套 EasiCamera 版本目录结构，验证：
* 未安装时 detect 只报告 not_installed，apply/restore 安全返回成功（不做任何修改）
* detect 能列出更新器文件/缓存/共享组件状态
* apply 重命名更新器、清理缓存、写状态文件、幂等
* apply 不破坏主程序/启动器/Guardian 等非更新组件
* restore 反向还原、幂等、清状态文件
* 权限不足时结果标注 requires_admin 且 ok=False

运行（在 ``InspireCameraTools/`` 下）::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from core import autoupdate  # noqa: E402


class FakeInstallTestCase(unittest.TestCase):
    """伪造安装目录 + 隔离所有系统查询的测试基类。"""

    VERSION = "9.9.9.9001"

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="inspire-au-test-")
        self.install_root = os.path.join(self.tmp_dir, "Seewo", "EasiCamera")
        self.version_dir = os.path.join(self.install_root, "EasiCamera_" + self.VERSION)
        self.main_dir = os.path.join(self.version_dir, "Main")
        os.makedirs(os.path.join(self.main_dir, "SupportFiles"))
        os.makedirs(os.path.join(self.version_dir, "sweclauncher"))

        self.app_key = "deadbeef" * 8
        self._write("Update.config", "AppName = EasiCamera\nAppKey = %s\nRegistryKey = Seewo\\EasiCamera\nRegistryPathKey = VersionPath\n" % self.app_key)
        # 更新器文件（apply 应重命名）
        for relative in (
            "Updater.exe",
            "Update_Cam2.exe",
            "GuardianUpdater.exe",
            "UpdateFix.exe",
            "Main/EasiCamera.UpdateFix.exe",
            "Main/SupportFiles/EasiUpdateSetup.exe",
        ):
            self._write(relative, b"fake-updater-binary")
        # 主程序 / 启动器 / Guardian：apply 绝不能动
        self._write("Main/EasiCamera.exe", b"fake-main")
        self._write("Main/EasiCameraGuardian.exe", b"fake-guardian")
        self._write("sweclauncher/sweclauncher.exe", b"fake-launcher")

        # 共享 EasiUpdate 目录与 EasiCamera 专属缓存
        self.easi_root = os.path.join(self.tmp_dir, "ProgramData", "Seewo", "Easiupdate")
        self.nginx_dir = os.path.join(self.easi_root, "easiupdate", "NginxDownload")
        self.config_dir = os.path.join(self.easi_root, "easiupdate", "ConfigDirectory")
        self.appdata_dir = os.path.join(self.tmp_dir, "AppData", "Roaming")
        self.app_cache = os.path.join(self.appdata_dir, "EasiUpdate", "EasiCamera")
        os.makedirs(os.path.join(self.nginx_dir, self.app_key))
        with open(os.path.join(self.nginx_dir, self.app_key, "9.9.9.9002.exe"), "wb") as fp:
            fp.write(b"pkg")
        os.makedirs(self.config_dir)
        with open(os.path.join(self.config_dir, self.app_key + ".ini"), "w", encoding="utf-8") as fp:
            fp.write("[Owner]\nAppKey = %s\n" % self.app_key)
        os.makedirs(self.app_cache)

        self.state_dir = os.path.join(self.tmp_dir, "state")

        # 隔离所有系统查询（避免依赖/污染本机真实状态）
        self._patches = [
            mock.patch.object(autoupdate, "_appdata_dir", return_value=self.appdata_dir),
            mock.patch.object(autoupdate, "_program_data_dir", return_value=os.path.join(self.tmp_dir, "ProgramData")),
            mock.patch.object(autoupdate, "_reg_app_info", return_value={}),
            mock.patch.object(autoupdate, "_reg_easiupdate_info", return_value={"path": self.easi_root, "appkey": "shared"}),
            mock.patch.object(autoupdate, "_service_registry_status", return_value=None),
            mock.patch.object(autoupdate, "_query_scheduled_tasks", return_value=[]),
            mock.patch.object(autoupdate, "_product_services", return_value=[]),
            mock.patch.object(autoupdate, "_firewall_rule_exists", return_value=None),
            mock.patch.object(autoupdate, "_hosts_related_entries", return_value=[]),
            mock.patch.object(autoupdate, "_state_dir_override", self.state_dir),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write(self, relative: str, data) -> str:
        path = os.path.join(self.version_dir, relative) if not os.path.isabs(relative) else relative
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w") as fp:
            fp.write(data)
        return path

    def path(self, relative: str) -> str:
        return os.path.join(self.version_dir, relative)

    def disabled(self, relative: str) -> str:
        return self.path(relative) + autoupdate.DISABLED_SUFFIX


class TestNoInstall(unittest.TestCase):
    def test_detect_not_installed(self) -> None:
        items = autoupdate.detect("Z:/definitely/not/exists")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "not_installed")
        summary = autoupdate.summarize(items)
        self.assertFalse(summary["installed"])

    def test_apply_restore_noop(self) -> None:
        result = autoupdate.apply("Z:/definitely/not/exists")
        self.assertTrue(result["ok"])
        self.assertFalse(result["installed"])
        self.assertEqual(result["changed"], 0)
        restore = autoupdate.restore("Z:/definitely/not/exists")
        self.assertTrue(restore["ok"])
        self.assertEqual(restore["changed"], 0)


class TestDetect(FakeInstallTestCase):
    def test_detect_items(self) -> None:
        items = autoupdate.detect(self.main_dir)
        by_id = {item["id"]: item for item in items}
        self.assertEqual(by_id["install"]["status"], "shared")
        self.assertIn("updater_file:Updater.exe", by_id)
        self.assertEqual(by_id["updater_file:Updater.exe"]["status"], "active")
        self.assertEqual(by_id["cache:nginx_download"]["status"], "active")
        self.assertEqual(by_id["cache:config_ini"]["status"], "active")
        self.assertEqual(by_id["cache:appdata"]["status"], "active")
        self.assertIn("task:none", by_id)
        # 共享组件只展示、不可操作
        shared_items = [item for item in items if item.get("shared")]
        self.assertTrue(shared_items)

    def test_summarize(self) -> None:
        summary = autoupdate.summarize(autoupdate.detect(self.main_dir))
        self.assertTrue(summary["installed"])
        self.assertGreaterEqual(summary["active"], 7)
        self.assertFalse(summary["fully_blocked"])


class TestApplyRestore(FakeInstallTestCase):
    def test_apply_blocks_update_chain(self) -> None:
        result = autoupdate.apply(self.main_dir)
        self.assertTrue(result["ok"], result["message"])
        self.assertGreaterEqual(result["changed"], 6)

        # 更新器全部变成 *.inspire-disabled
        for relative in (
            "Updater.exe",
            "Update_Cam2.exe",
            "GuardianUpdater.exe",
            "UpdateFix.exe",
            "Main/EasiCamera.UpdateFix.exe",
            "Main/SupportFiles/EasiUpdateSetup.exe",
        ):
            self.assertFalse(os.path.exists(self.path(relative)), relative)
            self.assertTrue(os.path.exists(self.disabled(relative)), relative)
        # 缓存被改名保留（可还原）
        self.assertFalse(os.path.exists(os.path.join(self.nginx_dir, self.app_key)))
        self.assertTrue(os.path.exists(os.path.join(self.nginx_dir, self.app_key) + autoupdate.DISABLED_SUFFIX))
        self.assertFalse(os.path.exists(os.path.join(self.config_dir, self.app_key + ".ini")))
        self.assertFalse(os.path.exists(self.app_cache))
        # 状态文件写入
        self.assertTrue(os.path.isfile(os.path.join(self.state_dir, autoupdate.STATE_FILENAME)))

        # 状态检测：可操作项全部 blocked、汇总 fully_blocked
        items = autoupdate.detect(self.main_dir)
        active = [item for item in items if item.get("actionable") and item["status"] == "active"]
        self.assertEqual(active, [])
        self.assertTrue(autoupdate.summarize(items)["fully_blocked"])

    def test_apply_does_not_touch_main_program(self) -> None:
        autoupdate.apply(self.main_dir)
        for relative in ("Main/EasiCamera.exe", "Main/EasiCameraGuardian.exe",
                         "sweclauncher/sweclauncher.exe", "Update.config"):
            self.assertTrue(os.path.exists(self.path(relative)), relative)
            self.assertFalse(os.path.exists(self.disabled(relative)), relative)

    def test_apply_idempotent(self) -> None:
        first = autoupdate.apply(self.main_dir)
        self.assertTrue(first["ok"])
        second = autoupdate.apply(self.main_dir)
        self.assertTrue(second["ok"], second["message"])
        self.assertEqual(second["changed"], 0)
        # 全部是跳过
        self.assertTrue(all(item["skipped"] for item in second["results"]))

    def test_restore(self) -> None:
        autoupdate.apply(self.main_dir)
        restore = autoupdate.restore(self.main_dir)
        self.assertTrue(restore["ok"], restore["message"])
        self.assertGreaterEqual(restore["changed"], 6)
        for relative in ("Updater.exe", "Update_Cam2.exe", "UpdateFix.exe",
                         "Main/EasiCamera.UpdateFix.exe", "sweclauncher/sweclauncher.exe"):
            self.assertTrue(os.path.exists(self.path(relative)), relative)
        self.assertTrue(os.path.exists(os.path.join(self.nginx_dir, self.app_key)))
        self.assertTrue(os.path.exists(os.path.join(self.config_dir, self.app_key + ".ini")))
        self.assertTrue(os.path.exists(self.app_cache))
        self.assertFalse(os.path.exists(os.path.join(self.state_dir, autoupdate.STATE_FILENAME)))
        # 还原后再次检测：更新能力恢复
        summary = autoupdate.summarize(autoupdate.detect(self.main_dir))
        self.assertFalse(summary["fully_blocked"])

    def test_restore_idempotent(self) -> None:
        autoupdate.apply(self.main_dir)
        autoupdate.restore(self.main_dir)
        second = autoupdate.restore(self.main_dir)
        self.assertTrue(second["ok"])
        self.assertEqual(second["changed"], 0)

    def test_apply_permission_denied_marks_requires_admin(self) -> None:
        with mock.patch.object(autoupdate.os, "rename", side_effect=PermissionError(13, "Permission denied")):
            result = autoupdate.apply(self.main_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(result["requires_admin"])
        self.assertIn("管理员", result["message"])
        failed = [item for item in result["results"] if not item["ok"]]
        self.assertTrue(failed)
        self.assertTrue(all(item["requires_admin"] for item in failed))

    def test_include_firewall(self) -> None:
        calls = []

        def fake_run_command(args, timeout=20):
            calls.append(args)
            return 0, "OK"

        with mock.patch.object(autoupdate, "_run_command", side_effect=fake_run_command):
            result = autoupdate.apply(self.main_dir, include_firewall=True)
        self.assertTrue(result["ok"], result["message"])
        firewall_calls = [args for args in calls if "advfirewall" in args]
        self.assertEqual(len(firewall_calls), 2)
        self.assertIn("rule", firewall_calls[0])
        self.assertIn("dir=out", firewall_calls[0])
        state = autoupdate._read_json(os.path.join(self.state_dir, autoupdate.STATE_FILENAME))
        self.assertEqual(len(state.get("firewall_rules") or []), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
