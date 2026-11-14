"""亿方智云客户端（core/cloud.py）单元测试（全部离线，mock 网络）。"""

from __future__ import annotations

import unittest
from unittest import mock

from core import cloud


class VersionTests(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(cloud.parse_version("v1.2.3"), [1, 2, 3])
        self.assertEqual(cloud.parse_version("1.0"), [1, 0])
        self.assertEqual(cloud.parse_version(""), [])
        self.assertEqual(cloud.parse_version("v1.0.1-beta"), [1, 0, 1])

    def test_is_newer(self) -> None:
        self.assertTrue(cloud.is_newer("v1.1.0", "1.0.1"))
        self.assertTrue(cloud.is_newer("1.0.10", "1.0.9"))
        self.assertFalse(cloud.is_newer("1.0.1", "1.0.1"))
        self.assertFalse(cloud.is_newer("v1.0.0", "1.0.1"))
        self.assertFalse(cloud.is_newer("", "1.0.1"))
        self.assertTrue(cloud.is_newer("2", "1.9.9"))


class DeviceKeyTests(unittest.TestCase):
    def test_generated_key_matches_pattern(self) -> None:
        key = cloud._generate_device_key()
        self.assertTrue(cloud.DEVICE_KEY_RE.match(key), key)
        self.assertTrue(key.startswith("ict_"), key)
        self.assertTrue(cloud.is_valid_device_key(key))
        self.assertNotEqual(key, cloud._generate_device_key())

    def test_legacy_le_key_is_migrated(self) -> None:
        legacy = "le_" + "a" * 32
        with mock.patch.object(cloud.settings, "get", return_value=legacy), mock.patch.object(
            cloud.settings, "set"
        ) as setter:
            key = cloud.ensure_device_key()
        self.assertTrue(key.startswith("ict_"))
        self.assertNotEqual(key, legacy)
        setter.assert_called_once_with("cloud_device_key", key)

    def test_ensure_device_key_persists(self) -> None:
        with mock.patch.object(cloud.settings, "get", return_value=""), mock.patch.object(
            cloud.settings, "set"
        ) as setter:
            key = cloud.ensure_device_key()
        self.assertTrue(cloud.DEVICE_KEY_RE.match(key))
        setter.assert_called_once_with("cloud_device_key", key)

    def test_ensure_device_key_reuses_existing(self) -> None:
        existing = "ict_" + "a" * 32
        with mock.patch.object(cloud.settings, "get", return_value=existing), mock.patch.object(
            cloud.settings, "set"
        ) as setter:
            self.assertEqual(cloud.ensure_device_key(), existing)
        setter.assert_not_called()


class PopupSeenTests(unittest.TestCase):
    def test_popup_once_per_day(self) -> None:
        today = "2026-11-14"
        seen = cloud.mark_popup_seen(12, today, {})
        self.assertTrue(cloud.popup_seen_today(12, today, seen))
        self.assertFalse(cloud.popup_seen_today(12, "2026-11-15", seen))
        self.assertFalse(cloud.popup_seen_today(13, today, seen))

    def test_mark_keeps_at_most_30(self) -> None:
        seen = {str(i): "2026-01-01" for i in range(40)}
        result = cloud.mark_popup_seen(999, "2026-11-14", seen)
        self.assertLessEqual(len(result), 30)
        self.assertIn("999", result)


class UpdateTests(unittest.TestCase):
    def test_check_update_returns_info_only_when_newer(self) -> None:
        info = {"latest_version": "v1.2.0", "latest_release_date": "2026-11-01", "latest_changelog": "修复若干问题"}
        with mock.patch.object(cloud, "get_app_info", return_value=info):
            self.assertEqual(cloud.check_update("1.1.0"), info)
            self.assertIsNone(cloud.check_update("1.2.0"))
            self.assertIsNone(cloud.check_update("1.10.0"))

    def test_check_update_handles_empty_version(self) -> None:
        with mock.patch.object(cloud, "get_app_info", return_value={"latest_version": ""}):
            self.assertIsNone(cloud.check_update("1.1.0"))
        with mock.patch.object(cloud, "get_app_info", return_value=None):
            self.assertIsNone(cloud.check_update("1.1.0"))

    def test_update_url_and_summary(self) -> None:
        info = {
            "latest_version": "v1.2.0",
            "latest_download_url": "https://example.com/dl",
            "latest_release_date": "2026-11-01",
            "latest_changelog": "1. 新功能\n2. 修复",
        }
        self.assertEqual(cloud.update_download_url(info), "https://example.com/dl")
        self.assertEqual(cloud.update_download_url({}), cloud.FALLBACK_UPDATE_PAGE)
        summary = cloud.update_summary(info, "1.1.0")
        self.assertIn("1.1.0", summary)
        self.assertIn("v1.2.0", summary)
        self.assertIn("修复", summary)


class RequestTests(unittest.TestCase):
    def test_ping_posts_required_fields(self) -> None:
        with mock.patch.object(cloud.settings, "get", return_value=True), mock.patch.object(
            cloud, "ensure_device_key", return_value="ict_1234567890abcdef"
        ), mock.patch.object(cloud, "_json_request", return_value={"online": True}) as request, mock.patch.object(
            cloud.settings, "set"
        ):
            self.assertTrue(cloud.ping())
        route = request.call_args[0][0]
        body = request.call_args[1]["body"]
        self.assertEqual(route, "client_ping")
        self.assertEqual(body["device_key"], "ict_1234567890abcdef")
        self.assertTrue(body["os"])
        self.assertTrue(body["device_name"])

    def test_get_popup_handles_empty_and_list(self) -> None:
        with mock.patch.object(cloud, "_json_request", return_value=[]):
            self.assertIsNone(cloud.get_popup())
        with mock.patch.object(cloud, "_json_request", return_value=[{"id": 1, "title": "t"}]):
            self.assertEqual(cloud.get_popup()["id"], 1)
        with mock.patch.object(cloud, "_json_request", return_value=None):
            self.assertIsNone(cloud.get_popup())


if __name__ == "__main__":
    unittest.main()
