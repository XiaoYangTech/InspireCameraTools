"""capture_trigger 模块单元测试（无展台/EasiCamera 环境下可运行）。

覆盖：
- 助手缺失时的编译回退（mock csc 调用）；
- 助手输出解析与友好错误信息；
- trigger_capture / probe / remoting 的参数与结果映射（mock 子进程）。
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from core import capture_trigger


class CaptureTriggerParseTests(unittest.TestCase):
    def test_to_result_ok(self) -> None:
        data = {
            "ok": True,
            "mode": "capture",
            "method": "uia-invoke",
            "element": {"name": "拍照", "type": "Button", "automationId": ""},
        }
        result = capture_trigger._to_result(data)
        self.assertTrue(result.ok)
        self.assertEqual(result.method, "uia-invoke")
        self.assertIn("拍照", result.describe())

    def test_to_result_window_not_found(self) -> None:
        result = capture_trigger._to_result(
            {"ok": False, "mode": "capture", "error": "EasiCamera window not found"}
        )
        self.assertFalse(result.ok)
        self.assertIn("EasiCamera", result.message)
        self.assertIn("打开", result.message)

    def test_to_result_button_not_found_with_candidates(self) -> None:
        result = capture_trigger._to_result(
            {
                "ok": False,
                "mode": "capture",
                "error": "capture button not found in EasiCamera window",
                "candidates": [{"name": "拍照", "automationId": "TakePhotoButton"}],
            }
        )
        self.assertFalse(result.ok)
        self.assertIn("拍照按钮未出现", result.message)
        self.assertIn("拍照", result.message)

    def test_to_result_malformed(self) -> None:
        result = capture_trigger._to_result(None)  # type: ignore[arg-type]
        self.assertFalse(result.ok)


class CaptureTriggerRunnerTests(unittest.TestCase):
    def _fake_completed(self, payload: dict, returncode: int = 0):
        completed = mock.Mock()
        completed.stdout = json.dumps(payload, ensure_ascii=False) + "\n"
        completed.stderr = ""
        completed.returncode = returncode
        return completed

    def test_trigger_capture_parses_helper_output(self) -> None:
        payload = {"ok": True, "mode": "capture", "method": "uia-invoke", "element": {"name": "拍照"}}
        with mock.patch.object(capture_trigger, "ensure_helper", return_value="fake.exe"), mock.patch.object(
            capture_trigger.subprocess, "run", return_value=self._fake_completed(payload)
        ) as run:
            result = capture_trigger.trigger_capture()
        self.assertTrue(result.ok)
        args = run.call_args[0][0]
        self.assertEqual(args[0], "fake.exe")
        self.assertEqual(args[1], "capture")

    def test_trigger_capture_wait_ms_argument(self) -> None:
        payload = {"ok": False, "mode": "capture", "error": "EasiCamera window not found"}
        with mock.patch.object(capture_trigger, "ensure_helper", return_value="fake.exe"), mock.patch.object(
            capture_trigger.subprocess, "run", return_value=self._fake_completed(payload, returncode=2)
        ) as run:
            result = capture_trigger.trigger_capture(wait_ms=1500)
        self.assertFalse(result.ok)
        args = run.call_args[0][0]
        self.assertIn("--wait-ms", args)
        self.assertEqual(args[args.index("--wait-ms") + 1], "1500")

    def test_probe_capture_button_dry_run(self) -> None:
        payload = {"ok": True, "mode": "capture", "dryRun": True, "method": "uia-candidate"}
        with mock.patch.object(capture_trigger, "ensure_helper", return_value="fake.exe"), mock.patch.object(
            capture_trigger.subprocess, "run", return_value=self._fake_completed(payload)
        ) as run:
            data = capture_trigger.probe_capture_button()
        self.assertTrue(data["ok"])
        self.assertIn("--dry-run", run.call_args[0][0])

    def test_remoting_notify_arguments(self) -> None:
        payload = {"ok": True, "mode": "remoting", "pid": 1, "vid": 2, "message": "Key5"}
        with mock.patch.object(capture_trigger, "ensure_helper", return_value="fake.exe"), mock.patch.object(
            capture_trigger.subprocess, "run", return_value=self._fake_completed(payload)
        ) as run:
            data = capture_trigger.remoting_notify(1, 2)
        self.assertTrue(data["ok"])
        args = run.call_args[0][0]
        self.assertEqual(args[1], "remoting")
        self.assertEqual(args[args.index("--message") + 1], "Key5")

    def test_timeout_is_friendly(self) -> None:
        with mock.patch.object(capture_trigger, "ensure_helper", return_value="fake.exe"), mock.patch.object(
            capture_trigger.subprocess, "run", side_effect=__import__("subprocess").TimeoutExpired("x", 1)
        ):
            result = capture_trigger.trigger_capture()
        self.assertFalse(result.ok)
        self.assertIn("超时", result.message)

    def test_compile_fallback_used_when_bundled_missing(self) -> None:
        with mock.patch.object(capture_trigger, "helper_path", return_value=capture_trigger.Path("missing.exe")), \
             mock.patch.object(capture_trigger, "proxy_path", return_value=capture_trigger.Path("missing.dll")), \
             mock.patch.object(capture_trigger, "_compile_to", return_value="compiled.exe") as compile_mock, \
             mock.patch.object(capture_trigger, "local_bin_dir", return_value=capture_trigger.Path("cache")):
            path = capture_trigger.ensure_helper()
        self.assertEqual(path, "compiled.exe")
        compile_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
