# -*- coding: utf-8 -*-
"""EasiCamera 2.0.10.3816 版本规则。

来源（2026-11-14，本机纯静态分析，**未安装/未运行 EasiCamera，未在真机验证**）：

* 安装包：``installers/EasiCameraSetup_2.0.10.3816.exe``（140,148,216 字节）
* 解包目录：``extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main/``
* 详细定位过程/IL 证据/偏移表：``analysis/3816/README.md``、``analysis/3816/verify.md``
* 自动校验：``python analysis/3816/verify_rules.py``（读原版 → 应用本 RULES → 断言字节与哈希）

功能可用性（详见 ``analysis/3816/availability.md``）：

* ``remove_english`` 可用：隐藏工具栏「英文批改」按钮（``CompositionCorrectionDisplayToolBarItem``）。
  该版本**没有** ``AIMenu`` / 口算批改 / 英文圈词 / 智能识别（OCR），英文批改是唯一的批改/AI 入口。
* ``force_scan`` 可用：去掉「自动扫描」按钮的希沃机型白名单 Visibility 绑定（默认 Visible）。
* 其余 6 项：该版本架构较老，不存在对应入口/逻辑，见 ``unavailable_reason``。

补丁后文件 SHA-256（供 verify_rules.py 断言，均等长替换、文件大小不变）：

* 仅 remove_english  → 6adf10e8a545adae68a64dc13e0cd10645f4f079a7784238390054ce50268847
* 仅 force_scan      → 2678df7291053b8555b1e894b1968c7a45b16b468544f69c869c060259ec1508
* 两者同时应用       → 84df05d7ddbd3eef2a2642349c5ad3b75d3ca89ad1fe1704c134e725368e6216

文件格式见 ``analysis/CONTRACT.md`` §3.2；本模块只导出 ``RULES``，import 时不访问磁盘/网络。
"""

RULES = {
    "version": "2.0.10.3816",
    "display_name": "V2.0.10.3816",
    "source_installer": "EasiCameraSetup_2.0.10.3816.exe",
    # 原版关键文件 SHA-256（版本识别 + 补丁前指纹校验）
    "files": {
        "EasiCamera.UI.dll": "f65b7a81a3f23a766de3c775c4885cc0dd4c42d562e073764e795ca9f9ae61ef",
        "EasiCamera.Business.dll": "2b8aa20512a5d19c2aa87280196caa6c45062b6aea1babe90107a3bd64b6823d",
        "EasiCamera.exe": "d482c73150ae5ad1995db46f0bd96b2ca346a45226d14ea81b4ade5ce1db34f8",
    },
    "features": {
        # 隐藏工具栏「英文批改」按钮。
        # 定位：EasiCamera.UI.CompositionCorrectionDisplayToolBarItem..ctor（MethodDef，RVA 0x11450，
        #       方法体文件偏移 0xF650，12 字节 fat header，IL 起始 0xF65C）；
        #       IL_0017: ldarg.0 / IL_0018: ldc.i4.1 / IL_0019: call UiItem::set_FunctionModule。
        # 原理：工具栏条目由 DisplayToolBarItemViewModel.RefreshUiItemState 收集，唯一判据是
        #       UiItem.IsShowUiItem() = (FunctionModule & 当前功能模块) != 0；把 FunctionModule
        #       从 MainWindow(1) 改为 None(0) 后该条目不会被加入任何 ToolBar ItemsControl（ImageUiItems），
        #       相当于「不把菜单项加入集合」。命令本身也不再可达。
        "remove_english": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0xF674,
                "expected": "17",
                "patched": "16",
                "note": "EasiCamera.UI.dll：CompositionCorrectionDisplayToolBarItem..ctor 的 IL_0018 `ldc.i4.1`→`ldc.i4.0`，FunctionModule 由 MainWindow 改为 None，工具栏「英文批改」按钮不再被收集/显示",
            }
        ],
        # 强制显示「自动扫描 / 文档增强」按钮（第三方展台可用）。
        # 定位：EasiCamera.UI.ImageEnhanceDisplayToolBarItem..ctor（RVA 0x11334，方法体文件偏移 0xF534，
        #       12 字节 fat header，IL 起始 0xF540）；
        #       IL_001e..IL_0071（84 字节）是 Visibility 绑定序列：
        #       newobj Binding / Path="Camera" / Source=DeviceViewModel.MainPreViewElement /
        #       Converter=SeewoCameraButtonVisibilityConverter / ConverterParameter=43100(0x1A85C 希沃机型掩码) /
        #       stloc.0 / ldarg.0 / ldsfld DisplayToolBarItem.VisibilityProperty / ldloc.0 / call SetBinding / pop
        # 原理：把该 84 字节整体替换为 NOP（等长），不再设置 Visibility 绑定，
        #       DisplayToolBarItem.Visibility 依赖属性默认值即 Visible(0) → 按钮对任意摄像头常显。
        #       后续 IL_0072 起的 IsCanClickDisabled(当前页面) 绑定保留不动。
        # 风险（不影响补丁合法性）：无摄像头时按钮也会显示，此时点击可能无响应/报内部错误；
        #       本功能本意是在接入第三方展台时使用（见 analysis/3816/README.md）。
        "force_scan": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0xF55E,
                "expected": "73af02000a2572c12600701473c100000a6fb002000a25289101000a6ff901000a6f5e02000a6fda02000a2573780300066fb102000a25205ca800008c070100016f8404000a0a027e8504000a0628b302000a26",
                "patched": "00" * 84,
                "note": "EasiCamera.UI.dll：ImageEnhanceDisplayToolBarItem..ctor 中「自动扫描」按钮的 Visibility 绑定（84 字节，希沃机型白名单掩码 0x1A85C）整体 NOP，按钮默认 Visible，第三方展台可用扫描/文档增强",
            }
        ],
    },
    # 该版本没有对应功能入口/逻辑（全部经字符串/元数据/反编译核对）
    "unavailable_reason": {
        "no_third_party_block": "2.0.10.3816 没有第三方展台屏蔽逻辑（GlobalDeviceViewModel 枚举全部物理摄像头，仅过滤名字含 virtual 的虚拟摄像头；该限制自 2.1.0 起引入）",
        "hide_login": "该版本主界面/工具栏无登录或头像入口（DisplayToolbar 仅 25 个工具项，无 ProfileButton；本地化文件也无「登录」类 key，仅更新提示 Lang.Update.Login）",
        "disable_freeze": "该版本没有兆芯/海光国产化自动冻结逻辑（无 Win32_Processor/ProcessorNameString/zhaoxin/IsHomeMaid 等符号；ECCommands.FreezeCamera 仅为手动「画面锁定」功能）",
        "enable_hygon_freeze": "该版本没有国产化芯片自动冻结链路（无 IsHomeMaidChip/HomeMaid；本版本 HardwareRecognizer 仅用于 USB MCU/IWB 设备识别，与 4229/4419 的芯片识别同名但无关），无法启用国产化芯片自动冻结",
        "remove_ocr": "该版本没有独立 OCR/「智能识别」入口（无 IntelligentIdentification/AIMenu/StartAiRecognition 等符号）；AI 批改在此版本仅以「英文批改」工具栏按钮存在，由 remove_english 处理",
        "disable_ai_key": "该版本 Business.dll 的 HID 处理（CommonHidComponent.DataProcess）只解析 cmd=1/2/3/4/5/6，没有 AI 按键（cmd 13）分支，故无需/无法屏蔽该按键",
    },
}
