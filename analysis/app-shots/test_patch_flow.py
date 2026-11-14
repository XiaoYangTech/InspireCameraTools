"""一键补丁端到端自测（使用 4229 官方解包文件的临时副本，不动原目录）。

流程：复制 3 个规则涉及的 DLL → UI 自动检测版本 → 勾选 remove_ocr → 应用补丁
→ 校验 is_patched 与文件哈希变化 → 恢复最近备份 → 校验文件哈希还原。

运行（在 InspireCameraTools/ 下）：
    D:/Software/python314/python.exe ../analysis/app-shots/test_patch_flow.py
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "InspireCameraTools"
OUT = ROOT / "analysis" / "app-shots"
SRC_MAIN = ROOT / "extracted" / "v2.0.10.4229" / "EasiCamera_2.0.10.4229" / "Main"
WORK = ROOT / "work" / "app-dev-test" / "4229"
TEST_MAIN = WORK / "Main"
NEEDED = ["EasiCamera.UI.dll", "EasiCamera.Business.dll", "EasiCamera.Util.dll"]

sys.path.insert(0, str(APP_DIR))

from core import patch_engine  # noqa: E402
from app import common  # noqa: E402
from app.app_window import MainWindow  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_copy() -> dict[str, str]:
    if TEST_MAIN.is_dir():
        shutil.rmtree(TEST_MAIN)
    TEST_MAIN.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for name in NEEDED:
        src = SRC_MAIN / name
        if not src.is_file():
            raise FileNotFoundError(src)
        shutil.copy2(src, TEST_MAIN / name)
        hashes[name] = sha256(src)
    return hashes


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("准备 4229 测试副本：", TEST_MAIN)
    original_hashes = prepare_copy()

    # 自动确认对话框，避免自动化被模态框阻塞
    confirmations: list[str] = []

    def auto_yes_no(parent, title, message):
        confirmations.append(f"{title}: {message.splitlines()[0]}")
        return True

    def show(kind):
        def _show(parent, title, message):
            confirmations.append(f"[{kind}] {title}: {message.splitlines()[0]}")
            print(f"[dialog:{kind}] {title} / {message[:80]}")
        return _show

    common.ask_yes_no = auto_yes_no  # type: ignore[assignment]
    common.show_warning = show("warning")  # type: ignore[assignment]
    common.show_error = show("error")  # type: ignore[assignment]
    common.show_info = show("info")  # type: ignore[assignment]

    window = MainWindow(smoke_test=True)
    window.geometry("1200x800+60+40")
    window.update()
    result: dict[str, object] = {"ok": False, "steps": []}

    def log_step(text: str) -> None:
        print("[STEP]", text)
        result["steps"].append(text)  # type: ignore[union-attr]

    def finish(ok: bool, message: str = "") -> None:
        result["ok"] = ok
        result["message"] = message
        window.after(200, window._on_close)

    def poll(condition, timeout: float, on_ok, on_timeout, interval: int = 120):
        deadline = time.time() + timeout

        def _check():
            try:
                if condition():
                    on_ok()
                    return
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            if time.time() >= deadline:
                on_timeout()
                return
            window.after(interval, _check)

        window.after(interval, _check)

    def capture(name: str) -> None:
        try:
            from PIL import ImageGrab

            window.update_idletasks()
            window.update()
            x, y = window.winfo_rootx(), window.winfo_rooty()
            image = ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height()))
            image.save(OUT / name)
            print("[capture]", name)
        except Exception as exc:  # noqa: BLE001
            print("[capture] 失败", exc)

    def step_detect() -> None:
        window.show_page("patch")
        page = window.get_page("patch")
        log_step("打开一键补丁页（等待首次自动检测结束）")

        def initial_done() -> bool:
            return not page._busy

        def start_manual() -> None:
            page._path_var.set(str(TEST_MAIN))
            page.refresh_detection()
            log_step("设置 Main 目录并触发重新检测")

            def detected() -> bool:
                return page._detected is not None and not page._busy

            def ok() -> None:
                detected_version = page._detected.version
                log_step(f"检测到版本：{detected_version}")
                window.update()
                capture("patch-detected.png")
                remove_ocr = page._rows["remove_ocr"]
                if str(remove_ocr["check"].cget("state")) != "normal":
                    finish(False, "remove_ocr 复选框不可用")
                    return
                remove_ocr["var"].set(True)
                page._update_count()
                log_step("勾选 remove_ocr，点击应用所选补丁")
                page._on_apply()

                def applied() -> bool:
                    return not page._busy and "应用成功" in _log_text(page)

                def applied_ok() -> None:
                    log_step("补丁应用成功（界面日志出现“应用成功”）")
                    capture("patch-applied.png")
                    patched = patch_engine.is_patched(str(TEST_MAIN))
                    log_step(f"is_patched(remove_ocr)={patched.get('remove_ocr')}")
                    if not patched.get("remove_ocr"):
                        finish(False, "应用后 is_patched 未变成 True")
                        return
                    new_hashes = {name: sha256(TEST_MAIN / name) for name in NEEDED}
                    changed = [n for n in NEEDED if new_hashes[n] != original_hashes[n]]
                    log_step(f"哈希发生变化的文件：{changed}")
                    if not changed:
                        finish(False, "应用后文件哈希未变化")
                        return
                    # 恢复备份
                    log_step("点击恢复最新备份")
                    page._on_restore()

                    def restored() -> bool:
                        return not page._busy and "恢复成功" in _log_text(page)

                    def restored_ok() -> None:
                        log_step("备份恢复成功")
                        capture("patch-restored.png")
                        final_hashes = {name: sha256(TEST_MAIN / name) for name in NEEDED}
                        if final_hashes != original_hashes:
                            finish(False, "恢复后文件哈希与原始文件不一致")
                            return
                        patched_after = patch_engine.is_patched(str(TEST_MAIN))
                        log_step(f"恢复后 is_patched(remove_ocr)={patched_after.get('remove_ocr')}")
                        if any(patched_after.values()):
                            finish(False, "恢复后仍有已打补丁标记")
                            return
                        finish(True, "检测→应用→恢复 全链路通过")

                    poll(restored, 20, restored_ok, lambda: finish(False, "恢复备份超时"))
                    return

                poll(applied, 25, applied_ok, lambda: finish(False, "应用补丁超时"))

            poll(detected, 20, ok, lambda: finish(False, "版本检测超时"))

        poll(initial_done, 20, start_manual, lambda: finish(False, "首次自动检测超时"))

    def _log_text(page) -> str:
        try:
            return page._log.text.get("1.0", "end")
        except Exception:  # noqa: BLE001
            return ""

    window.after(800, step_detect)
    window.mainloop()

    print("=" * 70)
    print("确认对话框调用：", confirmations)
    print("步骤：")
    for item in result["steps"]:  # type: ignore[union-attr]
        print(" -", item)
    ok = bool(result["ok"])
    print("RESULT:", "PASS" if ok else "FAIL", result.get("message", ""))
    if not ok:
        # 输出页面日志便于排查
        print("失败时页面日志不可用（窗口已销毁）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
