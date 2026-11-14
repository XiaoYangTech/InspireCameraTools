# -*- coding: utf-8 -*-
"""EasiCamera 2.0.10.4087（2024-09-12 构建）版本规则。

目标：去除 OCR（智能识别）按钮，并补齐本版本可定位的其它补丁能力。

逆向结论（详见 ``analysis/4087/``，**本机纯静态验证，未在真机/EasiCamera 运行**）：

* 本版本没有 4229 的 ``IntelligentIdentificationDisplayToolBarItem``，OCR 入口是工具栏
  「OCR」按钮 ``EasiCamera.UI.AIMenuDisplayToolBarItem``（文案 key ``Lang.DisplayToolBar.AIMenu`` = OCR），
  点击后弹出 ``EasiCamera.UI.AIMenu``（口算批改 / 英文批改）。
* 工具栏项由 ``EasiCamera.Api.UiItemExtension.InitDisplayToolBarUiItems`` 反射创建，
  ``DisplayToolBarItemViewModel.RefreshUiItemState`` 用 ``FunctionModule & CurrentFunctionModule`` 过滤；
  把该按钮的 ``FunctionModule`` 改为 ``None(0)`` 后它不会进入任何工具栏/更多列表（1 字节等长补丁）。
* 相机 AI 键走 ``CommonHidComponent.DataProcess`` 的 HID cmd 13 分支，与 4229 相同。
* 第三方展台「扫描/文档增强」白名单与本版本一致（``SeewoCameraButtonVisibilityConverter`` + 掩码 108636）。
* 登录按钮是 ``DisplayToolbar.ProfileButton``（``Cvte.GurnetUI.Controls.Button``）。
* 英文批改入口在 OCR 菜单 ``AIMenu.CompositionCorrectionButton``（仅当未移除 OCR 时单独隐藏）。

不支持的功能（见 ``unavailable_reason``）：本版本无云端第三方展台屏蔽开关、
无国产化芯片自动冻结逻辑（HomeMaid 自 2.0.10.4229 起引入），故对应补丁不可用。

文件格式见 ``analysis/CONTRACT.md`` §3.2；本模块只导出 ``RULES``，import 时不访问磁盘/网络。
"""

RULES = {
    "version": "2.0.10.4087",
    "display_name": "V2.0.10.4087",
    "source_installer": "EasiCamera_20240912161108.exe",
    # 原版关键文件 SHA-256（版本识别 + 补丁前指纹校验）；EasiCamera.exe 只参与版本识别
    "files": {
        "EasiCamera.UI.dll": "fcaa674bcc7567df87497d24305ae5e4207d3458ae68d29dd915d01d4a7c2443",
        "EasiCamera.Business.dll": "5345738297bb2e4a6cf7e1126ac8052641d331dbc39304cf40fadd2d54003fcd",
        "EasiCamera.exe": "50ee51a7ee2527a31f82ed0aa0a3e407eed3107be09dc1f4fc5d898a4b453f36",
    },
    "features": {
        # 去除 OCR（智能识别）按钮：AIMenuDisplayToolBarItem 不属于任何功能模块 → 整体不显示
        "remove_ocr": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x10CC9,
                "expected": "02161628a604000a0223000000000080594028a704000a021728a804000a2a",
                "patched": "02161628a604000a0223000000000080594028a704000a021628a804000a2a",
                "note": "EasiCamera.UI.dll：AIMenuDisplayToolBarItem 构造函数里把 FunctionModule 从 MainWindow(1) 改成 None(0)，该「OCR」工具栏项不再进入任何功能模块的工具栏列表（按钮及其弹窗入口整体移除）",
            },
        ],
        # 去除登录按钮：DisplayToolbar.ProfileButton 恒为 Collapsed
        "hide_login": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x1E773,
                "expected": "027b18040004285e03000a6fd601000a",
                "patched": "027b18040004186fe601000a00000000",
                "note": "EasiCamera.UI.dll：DisplayToolbar..ctor 末尾把 ProfileButton.DataContext=EC.Account 改为 ProfileButton.Visibility=Collapsed（初始隐藏右上角登录按钮）",
            },
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x1E8BC,
                "expected": "170b2b02",
                "patched": "160b2b02",
                "note": "EasiCamera.UI.dll：DisplayToolbar.BoardApiOnFunctionModuleChanged 里「是否显示登录按钮」的 flag 恒为 false，切换功能模块时登录按钮也保持 Collapsed",
            },
        ],
        # 第三方展台强制显示「扫描/文档增强」按钮：Visibility 绑定改为常量 Visible
        "force_scan": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x10BD6,
                "expected": "73b102000a2572172a00701473c300000a6fb202000a25289301000a6ffb01000a6f6002000a6fdc02000a2573cd0300066fb302000a25205ca801008c5c0200016fba04000a0a027ebb04000a0628b502000a26",
                "patched": "027ebb04000a168c030100016f1001000a00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
                "note": "EasiCamera.UI.dll：ImageEnhanceDisplayToolBarItem..ctor 里把「扫描/文档增强」按钮的 SeewoCameraButtonVisibilityConverter 绑定替换为 Visibility=Visible 常量（第三方展台也显示扫描按钮）",
            },
        ],
        # 去除英文批改入口：OCR 菜单里的「英文批改」按钮恒为 Collapsed
        "remove_english": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x1556A,
                "expected": "027bce02000402fe06a804000673b601000a6f8602000a2a",
                "patched": "027bce020004186fe601000a2a0000000000000000000000",
                "note": "EasiCamera.UI.dll：AIMenu.Connect 里把 OCR 菜单的「英文批改」按钮 Visibility 设为 Collapsed（不显示 CompositionCorrectionButton；口算批改/OCR 菜单其它入口不受影响）",
            },
        ],
        # 禁用相机 AI 按键：HID cmd 13 不再触发 OCR 菜单
        "disable_ai_key": [
            {
                "file": "EasiCamera.Business.dll",
                "offset": 0x12B5,
                "expected": "288700000a",
                "patched": "1400000000",
                "note": "EasiCamera.Business.dll：CommonHidComponent.DataProcess 收到相机 AI 键（HID cmd 13）时 call get_OpenAIMenu 改为 ldnull，后续 brtrue 判空直接返回，不再触发 OCR 菜单",
            },
        ],
    },
    # 该版本确实不存在对应入口/逻辑，规则不可用（UI 会置灰并显示原因）
    "unavailable_reason": {
        "no_third_party_block": "2.0.10.4087 没有云端「第三方展台屏蔽」开关（CancelShieldThirdParty 自 2.1.0 起引入），本版本设备列表不按该开关过滤，无需补丁",
        "disable_freeze": "2.0.10.4087 没有国产化芯片自动冻结逻辑（HomeMaidChipHandler / IsHomeMaidChip 自 2.0.10.4229 起才有），无自动冻结可去除",
        "enable_hygon_freeze": "2.0.10.4087 的 EasiCamera.Util.HardwareRecognizer 无国产化芯片识别（无 ZhaoXin/HaiGuang 判定），无法启用自动冻结；需 2.0.10.4229 及以上",
    },
}
