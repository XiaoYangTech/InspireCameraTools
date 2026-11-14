# -*- coding: utf-8 -*-
"""EasiCamera 2.1.0.4419 版本规则。

移植自上游仓库 ``seewo-easicamera-analysis/tools/``：

* ``patch_easicamera_business.py``               → ``no_third_party_block``
* ``patch_easicamera_ui.py --hide-login``         → ``hide_login``（上游只有 ctor 一处；本规则追加
  BoardApiOnFunctionModuleChanged 可见性标志补丁，否则真机上按钮会被重新设为 Visible）
* ``patch_easicamera_ui.py --force-scan``         → ``force_scan``
* ``patch_homemaid_freeze.py --disable-freeze``   → ``disable_freeze``

来源与校验（2026-11-14，本机静态验证，**未在真机/真展台运行**）：

* 安装包：``installers/EasiCameraSetup_2.1.0.4419.exe``（142.55 MB，swapp 官方直链下载）
* 解包目录：``extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/Main/``
* 两个目标 DLL 的 SHA-256 与上游脚本内置期望值**逐一完全一致**（见 ``analysis/4229_4419/verify.md``）
* 按本规则在内存中应用补丁后，补丁后 SHA-256 与上游脚本内置值完全一致：
  - UI.dll  hide_login          → 0e7fc83e7b29f63c0c04766b2de33fb202b0eef599f5bb7525063cbb0aad3418
  - UI.dll  force_scan          → 0715d54b7f9d082b61bd1e47d5984cc64d38eba105c485c01ba23756c88087db
  - UI.dll  hide_login + force_scan → 8e900aaa3732672e8d3634e27732c1f3ff0112328f4aa2e35979dad43b0797c6
  - Business.dll no_third_party_block → 4e1ca8bacd5f798fd27e7f312c99830641d4f1d4247412cd680fd7372c01b8c2
  - Business.dll disable_freeze       → 4f42886f8e026eeae95240b5f94baca5e89c8676e255fd4c5107001b5f4120c3
  - Business.dll 两个功能都打（本引擎组合）→ 63d3abff82c50b7c73f31a12d05c3a100b4540dac74d50917a7283901630d7a1

注意：``force_scan`` 的上游补丁用 84 字节（7 字节 IL + 77 个 0x00）替换原来
84 字节的 Binding 构造代码，上游脚本只校验了前 5 字节（``73b502000a``）；
本规则把整段 84 字节原样写入 ``expected``（从官方原版文件读出），
保证引擎"逐字节校验 + 等长替换"约束满足。

文件格式见 ``analysis/CONTRACT.md`` §3.2；本模块只导出 ``RULES``，import 时不访问磁盘/网络。
"""

RULES = {
    "version": "2.1.0.4419",
    "display_name": "V2.1.0.4419",
    "source_installer": "EasiCameraSetup_2.1.0.4419.exe",
    # 原版关键文件 SHA-256（版本识别 + 补丁前指纹校验）
    "files": {
        "EasiCamera.UI.dll": "c80fd035926ea74a5362cc4748a66902e39def5784f46fa96b27928c2e0b06f4",
        "EasiCamera.Business.dll": "37f77a24083bd3c27eb20e8828125fb905b3d3c7dbc175d6a8fbd0b497561bb6",
    },
    "features": {
        # lambda（MethodDef 0x060002D5）里把 get_CancelShieldThirdParty 后的 brfalse.s 改成 pop; nop
        # 让第三方展台无条件落入「加入设备列表」分支
        # 上游：patch_easicamera_business.py，文件偏移 0xCDBE
        "no_third_party_block": [
            {
                "file": "EasiCamera.Business.dll",
                "offset": 0xCDBE,
                "expected": "2c17",
                "patched": "2600",
                "note": "EasiCamera.Business.dll：GlobalDeviceViewModel 设备过滤 lambda 的 brfalse.s → pop; nop，第三方展台/普通 USB 摄像头恢复可用",
            }
        ],
        # DisplayToolbar..ctor 中 ProfileButton.DataContext=Account 替换为 Visibility=Collapsed
        # 上游：patch_easicamera_ui.py，LOGIN_OFF=0x1ECB3
        "hide_login": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x1ECB3,
                "expected": "286303000a6fda01000a",
                "patched": "186fea01000a00000000",
                "note": "EasiCamera.UI.dll：DisplayToolbar 构造函数里把 ProfileButton.DataContext=EC.Account 改为 ProfileButton.Visibility=Collapsed（初始隐藏登录/头像按钮）",
            },
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x1EE0C,
                "expected": "17",
                "patched": "16",
                "note": "EasiCamera.UI.dll：BoardApiOnFunctionModuleChanged 中登录按钮可见性标志（FunctionModule==MainWindow/ContrastView）恒为 false——否则切换功能模块时会把已隐藏的 ProfileButton 重新设为 Visible（真机复现：只打第一处时按钮在启动后重新出现）",
            },
        ],
        # ImageEnhanceDisplayToolBarItem..ctor：把按机型白名单绑定的 Visibility 改为常量 Visible
        # 上游：patch_easicamera_ui.py，SCAN_OFF=0x110A2，84 字节等长替换
        "force_scan": [
            {
                "file": "EasiCamera.UI.dll",
                "offset": 0x110A2,
                "expected": "73b502000a2572c52b00701473c700000a6fb602000a25289701000a6fff01000a6f6402000a6fe002000a2573e50300066fb702000a25205ca801008c700200016fce04000a0a027ec304000a0628b902000a26",
                "patched": "02166fea01000a" + "00" * 77,
                "note": "EasiCamera.UI.dll：扫描/文档增强工具按钮（ImageEnhanceDisplayToolBarItem）Visibility 改为常量 Visible，不再按希沃机型白名单隐藏",
            }
        ],
        # HomeMaidChipHandler.Initialize 直接返回：取消「点画笔自动冻结画面」
        # 上游：patch_homemaid_freeze.py，DISABLE_NEW，文件偏移 0x42C9
        "disable_freeze": [
            {
                "file": "EasiCamera.Business.dll",
                "offset": 0x42C9,
                "expected": "2d01",
                "patched": "262a",
                "note": "EasiCamera.Business.dll：HomeMaidChipHandler.Initialize 直接返回，取消国产化芯片机型进入批注自动冻结画面（恢复实时画面）",
            }
        ],
    },
    # 该版本没有对应功能入口/上游未提供可靠字节补丁
    "unavailable_reason": {
        "enable_hygon_freeze": "2.1.0.4419 已内置海光识别，自动冻结默认启用（海光平台无需启用；如需取消请用 disable_freeze）",
        "remove_english": "上游未提供 2.1.0.4419 的英文批改入口字节补丁，未验证，暂不提供",
        "remove_ocr": "上游未提供 2.1.0.4419 的 OCR/智能识别入口字节补丁，未验证，暂不提供",
        "disable_ai_key": "上游未提供 2.1.0.4419 的 AI 按键字节补丁，未验证，暂不提供",
    },
}
