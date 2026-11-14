"""历史版本下载功能真实网络自测。

验证：
1. swapp API 拉取 Windows 版本列表（数量、发布时间倒序）
2. 完整下载最新版本安装包（校验大小）
3. 模拟断点续传：用下载文件的前 8MB 构造 .part，重新调用下载器，
   验证服务器 Range 续传后得到完整文件且 SHA-256 一致
4. 清理测试大文件

运行（在 InspireCameraTools/ 下）：
    D:/Software/python314/python.exe -u ../analysis/app-shots/test_download.py
"""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "InspireCameraTools"
OUT = ROOT / "analysis" / "app-shots"
TEST_DIR = OUT / "download-test"

sys.path.insert(0, str(APP_DIR))

from core import downloader  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    print("[1] 拉取版本列表…", flush=True)
    client = downloader.SwappClient()
    versions = client.fetch_versions()
    print(f"    获取 Windows 版本 {len(versions)} 个", flush=True)
    if len(versions) < 10:
        print("FAIL 版本数量异常")
        return 1
    for item in versions[:3]:
        print(f"    {item.version}  {item.size_text}  {item.publish_text}")
    sorted_ok = all(versions[i].publish_ts >= versions[i + 1].publish_ts for i in range(len(versions) - 1))
    print("    发布时间倒序：", "OK" if sorted_ok else "FAIL")
    if not sorted_ok:
        return 1

    target = versions[0]
    file_path = TEST_DIR / target.filename
    part_path = file_path.with_name(file_path.name + ".part")
    for stale in (file_path, part_path):
        if stale.exists():
            stale.unlink()
    print(f"[2] 下载 {target.version}（{target.size_text}）→ {file_path.name}", flush=True)
    start = time.time()
    result = downloader.download_file(target.download_url, file_path)
    elapsed = time.time() - start
    print(f"    ok={result.ok} 耗时 {elapsed:.1f}s 消息：{result.message}", flush=True)
    if not result.ok:
        print("FAIL 完整下载失败")
        return 1
    full_size = file_path.stat().st_size
    full_hash = sha256(file_path)
    print(f"    完整文件：{downloader.format_size(full_size)} sha256={full_hash[:16]}… 平均 {downloader.format_size(full_size / max(elapsed, 0.01))}/s")

    # 构造 .part（前 8MB）测试续传
    print("[3] 构造 8MB 断点文件，验证 Range 续传…", flush=True)
    prefix = 8 * 1024 * 1024
    with open(file_path, "rb") as src, open(part_path, "wb") as dst:
        remaining = prefix
        while remaining > 0:
            chunk = src.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            dst.write(chunk)
            remaining -= len(chunk)
    file_path.unlink()
    print(f"    .part 大小 {downloader.format_size(part_path.stat().st_size)}", flush=True)
    start = time.time()
    result = downloader.download_file(target.download_url, file_path)
    elapsed = time.time() - start
    print(f"    续传 ok={result.ok} 耗时 {elapsed:.1f}s 消息：{result.message}", flush=True)
    if not result.ok:
        print("FAIL 续传下载失败")
        return 1
    resumed_size = file_path.stat().st_size
    resumed_hash = sha256(file_path)
    print(f"    续传后文件：{downloader.format_size(resumed_size)} sha256={resumed_hash[:16]}…", flush=True)
    if resumed_size != full_size or resumed_hash != full_hash:
        print("FAIL 续传文件与完整下载不一致")
        return 1
    print("    续传结果与完整下载一致（SHA-256 相同）")

    file_path.unlink()
    if part_path.exists():
        part_path.unlink()
    print(f"[4] 已清理测试文件，保留目录 {TEST_DIR}", flush=True)
    print("RESULT: PASS 列表拉取 + 完整下载 + 断点续传 全链路通过", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
