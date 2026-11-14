"""在 4419 副本上试验「彻底隐藏登录按钮」补丁：
1) 用引擎应用当前 hide_login（ctor Visibility=Collapsed）；
2) 手工追加 BoardApiOnFunctionModuleChanged 的 flag 恒 false 补丁（0x1EE0C: 0x17→0x16）。
找不到 EasiCamera 时也可运行，输出补丁后哈希。
"""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(r"D:\开发\SeewoCamera")
SRC_MAIN = ROOT / "extracted" / "v2.1.0.4419" / "EasiCamera_2.1.0.4419" / "Main"
BACKUP = ROOT / "extracted" / "v2.1.0.4419" / "EasiCamera_2.1.0.4419" / "_InspirePatchBackup" / "20261114-180347"
DST = ROOT / "work" / "login-4419b" / "Main"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC_MAIN, DST)
    # 复原为原版 DLL
    for name in ("EasiCamera.UI.dll", "EasiCamera.Business.dll"):
        shutil.copy2(BACKUP / name, DST / name)
    print("原版 UI.dll:", sha256(DST / "EasiCamera.UI.dll"))

    # 1) 引擎应用 hide_login（当前规则 = ctor 补丁）
    sys.path.insert(0, str(ROOT / "InspireCameraTools"))
    from core import patch_engine

    result = patch_engine.apply_patches(str(DST), ["hide_login"])
    print("引擎结果:", result.ok, result.applied, result.failed)
    print("ctor 补丁后:", sha256(DST / "EasiCamera.UI.dll"))

    # 2) 追加 flag 恒 false 补丁（BoardApiOnFunctionModuleChanged IL_009c）
    ui = DST / "EasiCamera.UI.dll"
    data = bytearray(ui.read_bytes())
    offset = 0x1EE0C
    assert data[offset] == 0x17, f"offset 0x{offset:X} 期望 0x17，实际 0x{data[offset]:02X}"
    data[offset] = 0x16
    ui.write_bytes(bytes(data))
    print("最终 UI.dll:", sha256(ui))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
