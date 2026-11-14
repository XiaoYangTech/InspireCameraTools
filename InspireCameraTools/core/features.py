# -*- coding: utf-8 -*-
"""亿方展台管家 —— 补丁功能目录（feature catalogue）。

契约：analysis/CONTRACT.md §3.1。8 个功能 ID 固定，任何成员不得新增/改名/删除。

字段说明
--------
id          固定英文 ID，规则文件与 UI 都用它做键
name        UI 中文标题
description 一句话中文说明（UI 悬浮提示/副标题）
risk        None 表示无风险；否则为字符串 ``"warning:中文风险提示"``
default_on  UI 勾选列表的默认状态（仅作建议值，实际应用以用户选择为准）

本模块只依赖 Python 标准库，可在 PyInstaller 打包环境运行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Feature:
    """一个可选补丁功能。"""

    id: str
    name: str
    description: str
    risk: Optional[str] = None
    default_on: bool = False

    def to_dict(self) -> dict:
        """转为可 JSON 序列化的 dict（供 CLI / UI 使用）。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "default_on": self.default_on,
        }


# 注意顺序即 UI 展示顺序（先常用、低风险，再特定平台功能）。
FEATURES: list[Feature] = [
    Feature(
        id="no_third_party_block",
        name="去除新版本不允许使用第三方展台的限制",
        description="解除新版对非希沃展台的屏蔽，让普通 USB 摄像头/第三方展台也能出画面。",
        risk=None,
        default_on=True,
    ),
    Feature(
        id="force_scan",
        name="去除第三方展台不能用扫描的限制",
        description="强制显示「扫描 / 文档增强」工具按钮，不再按希沃机型白名单隐藏。",
        risk=None,
        default_on=True,
    ),
    Feature(
        id="hide_login",
        name="去除登录按钮",
        description="隐藏主界面右上角的登录 / 头像入口（仅隐藏入口，不改变登录逻辑本身）。",
        risk=None,
        default_on=True,
    ),
    Feature(
        id="disable_freeze",
        name="去除兆芯/海光锁画面限制",
        description="取消国产化芯片机器进入批注等模式时自动冻结画面，恢复实时画面。",
        risk="warning:国产化平台（兆芯/海光）可能出现批注卡顿",
        default_on=False,
    ),
    Feature(
        id="enable_hygon_freeze",
        name="为海光处理器加入锁画面功能（修复批注卡顿）",
        description="让程序把本机识别为国产化芯片，启用点击画笔自动冻结画面，缓解海光平台批注卡顿。",
        risk="warning:补丁会强制启用冻结逻辑，非海光/兆芯机器可能出现画面冻结，建议仅在卡顿时使用",
        default_on=False,
    ),
    Feature(
        id="remove_english",
        name="去除英文批改",
        description="移除英文批改相关入口，界面更简洁（不改变其他批改功能）。",
        risk=None,
        default_on=True,
    ),
    Feature(
        id="remove_ocr",
        name="去除OCR（智能识别）",
        description="隐藏「智能识别 / 口算批改」等 OCR 入口，避免误触与弹出。",
        risk=None,
        default_on=True,
    ),
    Feature(
        id="disable_ai_key",
        name="禁用展台AI按键",
        description="屏蔽展台硬件 AI 按键（HID 命令 13）触发智能识别 / AI 菜单。",
        risk=None,
        default_on=True,
    ),
]

#: id -> Feature
FEATURE_MAP: dict[str, Feature] = {f.id: f for f in FEATURES}

#: 固定 ID 顺序元组
FEATURE_IDS: tuple[str, ...] = tuple(f.id for f in FEATURES)


def get_feature(feature_id: str) -> Feature:
    """按 ID 取功能定义；不存在时抛 ``KeyError``（含中文提示）。"""
    try:
        return FEATURE_MAP[feature_id]
    except KeyError:
        raise KeyError("未知功能 ID: %r（可用: %s）" % (feature_id, ", ".join(FEATURE_IDS))) from None


def normalize_feature_ids(feature_ids) -> list[str]:
    """去重并保持输入顺序；未知 ID 抛 ``KeyError``。"""
    result: list[str] = []
    seen: set[str] = set()
    for fid in feature_ids or []:
        fid = str(fid).strip()
        if not fid or fid in seen:
            continue
        get_feature(fid)  # 校验
        seen.add(fid)
        result.append(fid)
    return result
