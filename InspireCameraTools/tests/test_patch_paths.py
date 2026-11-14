"""补丁页路径输入规整（normalize_main_dir_input）单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.patch_page import normalize_main_dir_input


def _make_main(root: Path) -> Path:
    main = root / "EasiCamera_2.1.0.4419" / "Main"
    main.mkdir(parents=True)
    (main / "EasiCamera.exe").write_bytes(b"MZ")
    (main / "EasiCamera.UI.dll").write_bytes(b"MZ")
    return main


class NormalizeMainDirTests(unittest.TestCase):
    def test_empty_returns_none(self) -> None:
        self.assertIsNone(normalize_main_dir_input(""))
        self.assertIsNone(normalize_main_dir_input("   "))

    def test_plain_main_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            self.assertEqual(normalize_main_dir_input(str(main)), str(main))

    def test_quoted_and_trailing_backslash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            raw = '"' + str(main) + '\\\\"'
            self.assertEqual(normalize_main_dir_input(raw), str(main))

    def test_forward_slashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            raw = str(main).replace("\\", "/")
            self.assertEqual(normalize_main_dir_input(raw), str(main))

    def test_version_dir_finds_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            version_dir = main.parent
            self.assertEqual(normalize_main_dir_input(str(version_dir)), str(main))

    def test_install_root_finds_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            root = Path(tmp)
            self.assertEqual(normalize_main_dir_input(str(root)), str(main))

    def test_exe_path_finds_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            self.assertEqual(normalize_main_dir_input(str(main / "EasiCamera.exe")), str(main))

    def test_file_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = _make_main(Path(tmp))
            uri = "file:///" + str(main).replace("\\", "/")
            self.assertEqual(normalize_main_dir_input(uri), str(main))

    def test_unknown_existing_dir_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(normalize_main_dir_input(tmp), str(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
