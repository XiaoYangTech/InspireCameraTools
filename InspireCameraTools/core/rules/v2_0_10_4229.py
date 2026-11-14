# -*- coding: utf-8 -*-
"""EasiCamera 2.0.10.4229 版本规则。

移植自上游仓库 ``seewo-easicamera-analysis/tools/``：

* ``patch_4229_hide_ai.py --hide-ai-button`` → ``remove_ocr``
* ``patch_4229_hide_ai.py --disable-ai-key``  → ``disable_ai_key``
* ``patch_homemaid_freeze.py --enable-freeze`` → ``enable_hygon_freeze``

来源与校验（2026-11-14，本机静态验证，**未在真机/真展台运行**）：

* 安装包：``installers/EasiCameraSetup_2.0.10.4229.exe``（138.38 MB，swapp 官方直链下载）
* 解包目录：``extracted/v2.0.10.4229/EasiCamera_2.0.10.4229/Main/``
* 三个目标 DLL 的 SHA-256 与上游脚本内置期望值**逐一完全一致**（见 ``analysis/4229_4419/verify.md``）
* 按本规则在内存中应用补丁后，单功能补丁后 SHA-256 与上游脚本内置值完全一致：
  - UI.dll  remove_ocr          → fd8ec805cb10e9733ffd5fe122246a826f1e3d8cc5ed2765cb65f74b3f607f27
  - Business  disable_ai_key    → d6ef2173ae18dda68819ea91da0a4f0f46063e39a5951aea13ff94089220bf82
  - Util.dll  enable_hygon_freeze → 231efe7f4fd2a7d0d2e895440902ad3c3ebd83b53be3e7baed991cd2cc8d948d

文件格式见 ``analysis/CONTRACT.md`` §3.2；本模块只导出 ``RULES``，import 时不访问磁盘/网络。
"""

RULES = {
    "version": "2.0.10.4229",
    "display_name": "V2.0.10.4229",
    "source_installer": "EasiCameraSetup_2.0.10.4229.exe",
    # 原版关键文件 SHA-256（版本识别 + 补丁前指纹校验）
    "files": {
        "EasiCamera.UI.dll": "2821c3a7ef3d7deb68acaeee0475f0ba857bca979f7e0d03ec23098547bb9907",
        "EasiCamera.Business.dll": "700371fff8c0e41d7308224997359f4d122c5c3bb8cae0025ccebfa3c6d3ae93",
        "EasiCamera.Util.dll": "b4a40baf8786c06e6eabbabb47c9129c85d91ff2013955cbcb901259ab0fee73",
    },
    "features": {
        # 隐藏工具栏「智能识别」按钮（等价于原 ProfileButton Visibility 绑定替换为常量 Collapsed）
        # 上游：patch_4229_hide_ai.py，UI_PATCH，文件偏移 0x10CB9
        "remove_ocr": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x10CB9,
                "expected": "027ec004000a0728b702000a26",
                "patched": "02186fe801000a000000000000",
                "note": "EasiCamera.UI.dll：把「智能识别」工具栏按钮的 Visibility 绑定替换为常量 Collapsed（隐藏 OCR/AI 识别入口）",
            }
        ],
        # 忽略相机硬件 AI 键（HID cmd 13），不再执行 OpenAIMenu / StartAiRecognition
        # 上游：patch_4229_hide_ai.py，BIZ_PATCH，文件偏移 0x187D
        "disable_ai_key": [
            {
                "file": "EasiCamera.Business.dll",
                "offset": 0x187D,
                "expected": "28a700000a",
                "patched": "1400000000",
                "note": "EasiCamera.Business.dll：CommonHidComponent.DataProcess 收到 AI 键（cmd 13）时直接返回，不再触发 AI 识别",
            }
        ],
        # 让 HardwareRecognizer.IsHomeMaidChip 恒为 true，启用「点画笔自动冻结画面」（海光平台修复批注卡顿）
        # 上游：patch_homemaid_freeze.py，ENABLE_OLD，文件偏移 0x1A04
        "enable_hygon_freeze": [
            {
                "file": "EasiCamera.Util.dll",
                "offset": 0x1A04,
                "expected": "7f2d000004",
                "patched": "172a000000",
                "note": "EasiCamera.Util.dll：HardwareRecognizer.IsHomeMaidChip 恒为 true，启用国产化芯片自动冻结画面（缓解海光平台批注卡顿）",
            }
        ],
    },
    # 该版本没有对应功能入口/上游未提供可靠字节补丁
    "unavailable_reason": {
        "no_third_party_block": "2.0.10.4229 没有「云端第三方展台屏蔽」逻辑（该限制从 2.1.0 起引入）",
        "force_scan": "该版本未提供扫描按钮白名单补丁（上游仅有 2.1.0.4419 的字节补丁）",
        "hide_login": "该版本登录入口布局与 2.1.0.4419 不同，上游未提供可靠字节补丁",
        "disable_freeze": "该版本默认不启用自动冻结（HardwareRecognizer 仅识别兆芯），无需去除；如需反向启用请用 enable_hygon_freeze",
        "remove_english": "该版本 UI 无独立「英文批改」入口（AI/OCR 入口见 remove_ocr）",
    },
}
