"""历史版本下载：希沃 swapp 软件包 API 客户端 + 支持断点续传的文件下载器。

接口（见契约 §2）::

    GET https://swapp-api-cf.57777777.xyz/apix/get_package?uid=<uid>&page=1&page_size=100
    -> {"code": 0, "data": {"<uid>": {"softInfos": {"<id>": {...版本信息...}}}}}

版本信息字段：``softVersion``、``vtype``（Windows/Android/...）、``softSize``(MB)、
``softPublishtime``(毫秒时间戳)、``downloadUrl``、``softName``。

TLS 说明：本机网络环境特殊时 requests 可能抛证书吊销类错误，客户端会自动降级到
「不校验证书」重试一次，并通过 ``ssl_warning`` 提示用户。
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests

#: 希沃视频展台（EasiCamera）软件包 uid
API_UID = "c31ab96f4bdb413aaee8fc8e5dd82181"
API_GET_PACKAGE = "https://swapp-api-cf.57777777.xyz/apix/get_package"
API_PAGE_SIZE = 100
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 InspireCameraTools/1.0"
)
DEFAULT_TIMEOUT = 20


class DownloadError(Exception):
    """下载失败。"""


class DownloadCancelled(Exception):
    """下载被用户取消。"""


@dataclass
class SoftVersion:
    """一个可下载的软件版本。"""

    version: str
    name: str
    vtype: str
    size_mb: float
    publish_ts: int
    download_url: str
    raw: dict = field(repr=False, default_factory=dict)

    # ---------- 展示用格式化 ----------
    @property
    def size_text(self) -> str:
        if not self.size_mb or self.size_mb <= 0:
            return "-"
        return f"{self.size_mb:.2f} MB"

    @property
    def publish_text(self) -> str:
        if not self.publish_ts:
            return "-"
        try:
            dt = datetime.fromtimestamp(self.publish_ts / 1000.0)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return "-"

    @property
    def filename(self) -> str:
        """推断保存文件名（形如 EasiCameraSetup_2.1.0.4419.exe）。"""
        # 优先使用下载 URL 中 response-content-disposition 的 filename
        match = re.search(r"filename%3D%22([^%\"&]+)", self.download_url or "")
        if match:
            name = requests.utils.unquote(match.group(1))
            if name:
                return sanitize_filename(name)
        match = re.search(r'filename="?([^";]+)', self.download_url or "")
        if match:
            return sanitize_filename(match.group(1))
        base = self.name or f"EasiCamera_{self.version}"
        if not base.lower().endswith((".exe", ".zip", ".msi")):
            base += ".exe"
        return sanitize_filename(base)


def sanitize_filename(name: str) -> str:
    """去掉文件名里的非法字符，防止路径穿越。"""
    name = (name or "").strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or "download.exe"


def format_size(num: int | float | None) -> str:
    """把字节数格式化为易读字符串。"""
    if num is None:
        return "-"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


class SwappClient:
    """swapp 软件包 API 客户端（线程内使用，不绑定 UI）。"""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self.ssl_warning: str = ""
        self._session: requests.Session | None = None
        self._lock = threading.Lock()

    # ---------- 内部 ----------
    def _get_session(self) -> requests.Session:
        with self._lock:
            if self._session is None:
                session = requests.Session()
                session.headers.update({"User-Agent": USER_AGENT, "Referer": "https://e.seewo.com/"})
                session.trust_env = True  # 遵循系统代理设置（若用户配置了代理）
                self._session = session
            return self._session

    def _request_json(self, url: str, params: dict | None = None) -> dict:
        session = self._get_session()
        try:
            resp = session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.SSLError as exc:
            # 证书吊销/证书链异常时，退化为不校验证书重试一次（仅本工具内部使用）
            self.ssl_warning = f"TLS 证书校验失败，已降级为忽略证书校验（{exc.__class__.__name__}）。建议检查系统时间/代理设置。"
            try:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:  # noqa: BLE001 - 警告模块不可用不影响主流程
                pass
            resp = session.get(url, params=params, timeout=self.timeout, verify=False)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            raise DownloadError(f"网络请求失败：{exc}") from exc
        except ValueError as exc:
            raise DownloadError(f"接口返回的数据不是合法 JSON：{exc}") from exc

    # ---------- 公开接口 ----------
    def fetch_versions(self, page: int = 1, page_size: int = API_PAGE_SIZE) -> list[SoftVersion]:
        """拉取全部软件包版本，过滤为 Windows 并按发布时间倒序。"""
        payload = self._request_json(
            API_GET_PACKAGE,
            params={"uid": API_UID, "page": page, "page_size": page_size},
        )
        return parse_versions_payload(payload)

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:  # noqa: BLE001
                    pass
                self._session = None


def parse_versions_payload(payload: dict) -> list[SoftVersion]:
    """解析 get_package 接口返回值，容错处理字典/列表两种 softInfos 结构。"""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise DownloadError("接口返回缺少 data 字段")
    package = data.get(API_UID)
    if package is None and len(data) == 1:
        package = next(iter(data.values()))
    if not isinstance(package, dict):
        raise DownloadError("接口返回缺少软件包信息（data.<uid>）")
    infos = package.get("softInfos")
    if infos is None:
        infos = package.get("soft_infos")
    items: list[dict] = []
    if isinstance(infos, dict):
        items = [v for v in infos.values() if isinstance(v, dict)]
    elif isinstance(infos, list):
        items = [v for v in infos if isinstance(v, dict)]
    if not items:
        raise DownloadError("接口未返回任何版本数据（softInfos 为空）")

    versions: list[SoftVersion] = []
    for item in items:
        try:
            size_mb = float(item.get("softSize") or 0)
        except (TypeError, ValueError):
            size_mb = 0.0
        try:
            publish_ts = int(item.get("softPublishtime") or 0)
        except (TypeError, ValueError):
            publish_ts = 0
        versions.append(
            SoftVersion(
                version=str(item.get("softVersion") or "").strip(),
                name=str(item.get("softName") or "").strip(),
                vtype=str(item.get("vtype") or ""),
                size_mb=size_mb,
                publish_ts=publish_ts,
                download_url=str(item.get("downloadUrl") or ""),
                raw=item,
            )
        )
    windows = [v for v in versions if v.vtype.lower() == "windows" and v.download_url]
    windows.sort(key=lambda v: v.publish_ts, reverse=True)
    return windows


# ---------------------------------------------------------------------------
# 文件下载
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[int, int | None, float], None]


@dataclass
class DownloadResult:
    ok: bool
    path: Path | None
    message: str
    total_bytes: int = 0
    cancelled: bool = False


def download_file(
    url: str,
    target_path: str | Path,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = 30.0,
    chunk_size: int = 256 * 1024,
    verify_ssl: bool = True,
) -> DownloadResult:
    """下载文件（阻塞函数，调用方应放在后台线程）。

    - 使用 ``<目标文件>.part`` 作为临时文件，支持断点续传（Range）；
    - 每写入一块调用 ``on_progress(已下载字节, 总字节或 None, 速度 B/s)``；
    - ``cancel_event`` 被 set 时抛出 :class:`DownloadCancelled` 语义并清理，
      返回 ``cancelled=True``；
    - 已存在同名完整文件时直接返回（幂等）。
    """
    target = Path(target_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DownloadResult(False, None, f"无法创建下载目录：{exc}")
    part = target.with_name(target.name + ".part")
    cancel = cancel_event or threading.Event()

    if target.is_file() and target.stat().st_size > 0 and not part.is_file():
        return DownloadResult(True, target, f"文件已存在，无需重复下载：{target}", target.stat().st_size)

    # 断点续传：读取已有 .part 大小
    resume_from = part.stat().st_size if part.is_file() else 0
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    total: int | None = None
    try:
        with requests.get(url, headers=headers, stream=True, timeout=timeout, verify=verify_ssl) as resp:
            if resp.status_code == 416:  # Range 越界：视为 .part 已完整，直接转正
                if part.is_file() and part.stat().st_size > 0:
                    os.replace(part, target)
                    return DownloadResult(True, target, "续传文件已完整，已保存", part.stat().st_size)
                return DownloadResult(False, None, "服务器拒绝续传请求（HTTP 416），请重试")
            if resp.status_code not in (200, 206):
                return DownloadResult(False, None, f"下载失败：HTTP {resp.status_code}")
            if resp.status_code == 200 and resume_from > 0:
                resume_from = 0  # 服务器不支持 Range，从头下载
            length = resp.headers.get("Content-Length")
            if length and length.isdigit():
                total = int(length) + resume_from

            mode = "ab" if resume_from > 0 else "wb"
            downloaded = resume_from
            started = time.monotonic()
            last_report = 0.0
            with open(part, mode) as fh:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if cancel.is_set():
                        return DownloadResult(False, part if part.exists() else None, "下载已取消", downloaded, True)
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if on_progress and (now - last_report > 0.12 or (total and downloaded >= total)):
                        last_report = now
                        speed = downloaded / max(now - started, 1e-6)
                        on_progress(downloaded, total, speed)
            final_size = part.stat().st_size
            if total is not None and final_size < total:
                return DownloadResult(
                    False,
                    part,
                    f"下载不完整：{format_size(final_size)} / {format_size(total)}（可重试续传）",
                    final_size,
                )
            os.replace(part, target)
            if on_progress:
                elapsed = max(time.monotonic() - started, 1e-6)
                on_progress(final_size, total, final_size / elapsed)
            return DownloadResult(True, target, f"下载完成：{target}（{format_size(final_size)}）", final_size)
    except requests.exceptions.RequestException as exc:
        return DownloadResult(False, part if part.exists() else None, f"下载中断：{exc}（已保留 .part 可续传）", resume_from)
    except OSError as exc:
        return DownloadResult(False, part if part.exists() else None, f"写入文件失败：{exc}", resume_from)


def open_in_explorer(path: str | Path) -> None:
    """在资源管理器中打开目录（或选中文件）。"""
    import subprocess

    p = Path(path)
    if p.is_dir():
        os.startfile(str(p))  # type: ignore[attr-defined]  # noqa: S606 - 打开用户指定目录
    elif p.exists():
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        raise FileNotFoundError(str(p))
