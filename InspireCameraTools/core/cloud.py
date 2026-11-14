"""亿方智云（InspireWorksCloud）客户端接入。

只接三类「免费运营模式」接口（见 ``D:\\开发\\InspireWorksCloud\\docs\\api-reference.md``）：

1. **匿名上报** ``client_ping``：仅上报随机设备标识 + 系统描述 + 设备名，
   启动后立即一次、之后每 8 分钟一次（文档建议值）；失败静默忽略，不阻塞界面。
2. **启动弹窗公告** ``popup``：返回 0 或 1 条公告；「今日不再显示」由客户端记录。
3. **传统手动更新** ``app_info``：比对最新版本，提示用户打开网页手动下载（不做静默/自动安装）。

Base URL：``https://api.yfyw.top/apps/ict/api.php``（本应用 slug = ``ict``）。
接口免登录、免令牌、无配额；响应 JSON 用 ``ok`` 字段判断成功。

隐私：上报内容仅设备随机标识、系统描述、计算机名，不含账号和个人信息；
可在「设置与关于」页关闭匿名统计（关闭后仅不再发 ``client_ping``）。
"""

from __future__ import annotations

import logging
import os
import platform
import re
import secrets
import socket
import threading
import time

from . import settings

try:  # requests 是应用依赖；缺失时云功能整体降级为不可用
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

#: 应用在亿方智云后台的 slug
APP_SLUG = "ict"
#: 客户端 API Base URL
BASE_URL = f"https://api.yfyw.top/apps/{APP_SLUG}/api.php"
#: 手动更新页兜底（后台未配置 page_url/latest_download_url 时使用）
FALLBACK_UPDATE_PAGE = "https://github.com/XiaoYangTech/InspireCameraTools/releases"

#: 网络超时（连接, 读取）——短超时保证不卡启动
TIMEOUT = (4.0, 8.0)
#: 匿名上报间隔（文档建议 8 分钟；后台在线判定默认 10 分钟）
PING_INTERVAL_SECONDS = 8 * 60
#: 启动后首次上报延迟（等界面就绪）
PING_INITIAL_DELAY_SECONDS = 3.0
#: 设备标识格式（文档要求 ^[A-Za-z0-9_-]{16,100}$）
DEVICE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,100}$")

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION} (Windows; YF-Cloud)",
}


# ---------------------------------------------------------------------------
# 基础请求
# ---------------------------------------------------------------------------
def _json_request(route: str, params: dict | None = None, body: dict | None = None) -> dict | None:
    """请求 ``?route=...``；成功返回 ``data``，失败返回 None（全部静默降级）。"""
    if requests is None:
        return None
    query = {"route": route}
    if params:
        query.update({k: v for k, v in params.items() if v is not None})
    try:
        if body is None:
            resp = requests.get(BASE_URL, params=query, headers=_HEADERS, timeout=TIMEOUT)
        else:
            resp = requests.post(BASE_URL, params=query, json=body, headers=_HEADERS, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - 网络异常静默忽略
        log.debug("云接口 %s 请求失败：%s", route, exc)
        return None
    if resp.status_code != 200:
        # 404 是网关页面（应用不存在/入口缺失），其它错误一般也是 JSON；都不影响主功能
        log.debug("云接口 %s HTTP %s", route, resp.status_code)
        return None
    try:
        payload = resp.json()
    except ValueError:
        log.debug("云接口 %s 返回非 JSON（HTTP %s）", route, resp.status_code)
        return None
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error") if isinstance(payload, dict) else None
        log.debug("云接口 %s 返回失败：%s", route, error)
        return None
    return payload.get("data")


# ---------------------------------------------------------------------------
# 匿名上报
# ---------------------------------------------------------------------------
def _generate_device_key() -> str:
    """生成随机设备标识：``le_`` + 32 位十六进制（35 字符，符合文档格式）。"""
    return "le_" + secrets.token_hex(16)


def ensure_device_key() -> str:
    """读取/生成并持久化匿名设备标识（安装后仅生成一次）。"""
    key = str(settings.get("cloud_device_key") or "").strip()
    if DEVICE_KEY_RE.match(key):
        return key
    key = _generate_device_key()
    try:
        settings.set("cloud_device_key", key)
    except Exception:  # noqa: BLE001 - 配置写失败时至少本次可用
        log.debug("保存设备标识失败", exc_info=True)
    return key


def os_description() -> str:
    """系统描述（≤80 字符），例如 ``Windows 11 10.0.26200``。"""
    try:
        text = f"{platform.system()} {platform.release()} {platform.version()}".strip()
    except Exception:  # noqa: BLE001
        text = "Windows"
    return text[:80]


def device_name() -> str:
    """设备名（≤80 字符）；仅用于后台区分设备，不含个人信息。"""
    try:
        name = socket.gethostname()
    except Exception:  # noqa: BLE001
        name = ""
    return (name or "Windows-PC")[:80]


def ping() -> bool:
    """匿名上报一次（仅在设置允许时）；成功返回 True。"""
    if not bool(settings.get("cloud_report_enabled", True)):
        return False
    key = ensure_device_key()
    data = _json_request(
        "client_ping",
        body={"device_key": key, "os": os_description(), "device_name": device_name()},
    )
    if data is None:
        return False
    try:
        settings.set("cloud_last_ping", int(time.time()))
    except Exception:  # noqa: BLE001
        pass
    return True


class PingLoop:
    """后台匿名上报循环：启动后延迟一次，之后固定间隔；stop() 可随时结束。"""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="cloud-ping", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if self._stop.wait(PING_INITIAL_DELAY_SECONDS):
            return
        while not self._stop.is_set():
            try:
                ping()
            except Exception:  # noqa: BLE001 - 上报失败绝不影响主流程
                log.debug("匿名上报异常", exc_info=True)
            if self._stop.wait(PING_INTERVAL_SECONDS):
                return

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# 公告弹窗
# ---------------------------------------------------------------------------
def get_popup() -> dict | None:
    """获取启动弹窗公告（0 或 1 条）；没有则返回 None。"""
    data = _json_request("popup")
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            return item
    return None


def popup_seen_today(popup_id: int | str, today: str, seen: dict | None = None) -> bool:
    """判断该弹窗今天是否已展示过（纯函数，便于测试）。"""
    seen = seen if isinstance(seen, dict) else {}
    return str(seen.get(str(popup_id)) or "") == today


def mark_popup_seen(popup_id: int | str, today: str, seen: dict | None = None) -> dict:
    """记录「今日已展示」并返回新字典（保留最多 30 条记录）。"""
    result = dict(seen) if isinstance(seen, dict) else {}
    result[str(popup_id)] = today
    if len(result) > 30:
        for key in list(result.keys())[: len(result) - 30]:
            result.pop(key, None)
    return result


# ---------------------------------------------------------------------------
# 传统手动更新
# ---------------------------------------------------------------------------
def parse_version(text: str) -> list[int]:
    """把 ``v1.2.3`` / ``1.2`` 解析为数字段列表。"""
    cleaned = re.sub(r"[^0-9.]", "", str(text or ""))
    parts: list[int] = []
    for chunk in cleaned.split("."):
        if chunk == "":
            continue
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return parts


def is_newer(latest: str, current: str) -> bool:
    """版本比较：latest 是否严格大于 current（忽略 v 前缀，按数字段比较）。"""
    a = parse_version(latest)
    b = parse_version(current)
    if not a:
        return False
    for index in range(max(len(a), len(b))):
        left = a[index] if index < len(a) else 0
        right = b[index] if index < len(b) else 0
        if left > right:
            return True
        if left < right:
            return False
    return False


def get_app_info() -> dict | None:
    """获取版本信息（手动更新用）。"""
    data = _json_request("app_info")
    return data if isinstance(data, dict) else None


def check_update(current_version: str | None = None) -> dict | None:
    """检查是否有新版本；有则返回 app_info 数据，无/失败返回 None。"""
    current = current_version or settings.APP_VERSION
    info = get_app_info()
    if not info:
        return None
    latest = str(info.get("latest_version") or "").strip()
    if latest and is_newer(latest, current):
        return info
    return None


def update_download_url(info: dict | None) -> str:
    """更新提示里「前往下载」应打开的 URL（手动更新页优先）。"""
    info = info or {}
    for key in ("latest_download_url", "page_url", "download_url"):
        value = str(info.get(key) or "").strip()
        if value:
            return value
    return FALLBACK_UPDATE_PAGE


def update_summary(info: dict | None, current_version: str | None = None) -> str:
    """生成更新提示正文（版本 + 日期 + 更新说明摘要）。"""
    info = info or {}
    current = current_version or settings.APP_VERSION
    latest = str(info.get("latest_version") or "").strip()
    date = str(info.get("latest_release_date") or "").strip()
    changelog = str(info.get("latest_changelog") or "").strip()
    lines = [f"当前版本：{current}", f"最新版本：{latest}" + (f"（{date}）" if date else "")]
    if changelog:
        excerpt = changelog if len(changelog) <= 600 else changelog[:600] + "…"
        lines.append("")
        lines.append("更新内容：")
        lines.append(excerpt)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 状态（给「设置与关于」页展示）
# ---------------------------------------------------------------------------
def cloud_status() -> dict:
    """返回云服务状态（只读本地配置，不发网络请求）。"""
    return {
        "slug": APP_SLUG,
        "base_url": BASE_URL,
        "device_key": ensure_device_key(),
        "report_enabled": bool(settings.get("cloud_report_enabled", True)),
        "last_ping": int(settings.get("cloud_last_ping") or 0),
        "current_version": settings.APP_VERSION,
    }
