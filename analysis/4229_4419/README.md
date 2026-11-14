# EasiCamera 2.0.10.4229 / 2.1.0.4419 补丁规则移植记录

> 任务：把上游仓库 `seewo-easicamera-analysis/tools/` 里针对 **2.0.10.4229** 与 **2.1.0.4419**
> 的字节级 IL 补丁，转写为「亿方展台管家」的版本规则 `core/rules/v2_*.py`。
> 本目录（`analysis/4229_4419/`）为移植分析记录；**未在真机/真展台验证**，仅静态字节级验证。

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `analysis/4229_4419/README.md` | 本文件：移植总览、来源、复现方式、规则可用矩阵 |
| `analysis/4229_4419/verify.md` | 验证记录：原版/补丁后 SHA-256、IL 变更证据、复现命令 |
| `analysis/4229_4419/verify_rules.py` | 自动化校验脚本（读原版 DLL → 应用 RULES → 断言哈希） |
| `analysis/4229_4419/autoupdate.md` | 破坏自动更新的静态分析记录 |
| `InspireCameraTools/core/rules/v2_0_10_4229.py` | 4229 规则（3 个可用功能） |
| `InspireCameraTools/core/rules/v2_1_0_4419.py` | 4419 规则（4 个可用功能） |

## 2. 官方安装包来源（swapp 历史版本 API）

按 `analysis/CONTRACT.md` §2 的 API 取下载直链：

```
GET https://swapp-api-cf.57777777.xyz/apix/get_package?uid=c31ab96f4bdb413aaee8fc8e5dd82181&page=1&page_size=100
→ data.<uid>.softInfos 中过滤 vtype == "Windows"，按 softVersion 取 2.0.10.4229 / 2.1.0.4419 的 downloadUrl
```

| 版本 | 安装包（仓库 `installers/`） | 大小 | SHA-256 |
|---|---|---|---|
| 2.0.10.4229 | `EasiCameraSetup_2.0.10.4229.exe` | 145,097,192 | `8886210afd3035d8c72c489b19336dd2b0b31684ebe36560f0c7631063e44250` |
| 2.1.0.4419 | `EasiCameraSetup_2.1.0.4419.exe` | 149,475,088 | `e358b1e7f688a27982e57b996725c0badaada8916395951c33bec88965ac1a07` |

解包（7-Zip 可解 NSIS；**不要安装**）：

```
.tools/7zip/7z.exe x installers/EasiCameraSetup_2.0.10.4229.exe -oextracted/v2.0.10.4229 -y
.tools/7zip/7z.exe x installers/EasiCameraSetup_2.1.0.4419.exe -oextracted/v2.1.0.4419 -y
# Main 目录：
#   extracted/v2.0.10.4229/EasiCamera_2.0.10.4229/Main/
#   extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/Main/
```

版本核对：`Main/EasiCamera.exe` 的 FileVersion 分别为 `2.0.10.4229`、`2.1.0.4419`。
两个安装包（均为 NSIS，LZMA 压缩）解包后文件数 434 / 441。

## 3. 目标 DLL 哈希核对结果（与上游脚本内置期望值逐一致）

上游四个脚本内置了原版 SHA-256 作为“版本严格校验”。本次下载的官方包解包后：

| 版本 | 文件 | 大小 | 原版 SHA-256（与上游期望一致） |
|---|---|---|---|
| 4229 | `EasiCamera.UI.dll` | 1,074,176 | `2821c3a7ef3d7deb68acaeee0475f0ba857bca979f7e0d03ec23098547bb9907` |
| 4229 | `EasiCamera.Business.dll` | 307,712 | `700371fff8c0e41d7308224997359f4d122c5c3bb8cae0025ccebfa3c6d3ae93` |
| 4229 | `EasiCamera.Util.dll` | 72,704 | `b4a40baf8786c06e6eabbabb47c9129c85d91ff2013955cbcb901259ab0fee73` |
| 4419 | `EasiCamera.UI.dll` | 1,107,968 | `c80fd035926ea74a5362cc4748a66902e39def5784f46fa96b27928c2e0b06f4` |
| 4419 | `EasiCamera.Business.dll` | 337,920 | `37f77a24083bd3c27eb20e8828125fb905b3d3c7dbc175d6a8fbd0b497561bb6` |

**结论：全部一致，无需重新定位偏移。** 因此规则直接采用上游脚本的偏移/原字节，只做了
「RULES 格式转写 + 等长约束补全（force_scan 84 字节）+ 功能 ID 映射」。

## 4. 规则可用矩阵

| 功能 ID | 4229 | 4419 | 说明（4229 / 4419） |
|---|---|---|---|
| `no_third_party_block` | ✗ | ✓ | 4419 `EasiCamera.Business.dll` 0xCDBE：`brfalse.s`→`pop;nop`，解除第三方展台屏蔽 |
| `force_scan` | ✗ | ✓ | 4419 `EasiCamera.UI.dll` 0x110A2：84 字节绑定→常量 Visible |
| `hide_login` | ✗ | ✓ | 4419 `EasiCamera.UI.dll` 0x1ECB3：ProfileButton 的 DataContext 绑定→Visibility=Collapsed |
| `disable_freeze` | ✗ | ✓ | 4419 `EasiCamera.Business.dll` 0x42C9：`HomeMaidChipHandler.Initialize` 直接返回 |
| `enable_hygon_freeze` | ✓ | ✗ | 4229 `EasiCamera.Util.dll` 0x1A04：`HardwareRecognizer.IsHomeMaidChip` 恒 true |
| `remove_english` | ✗ | ✗ | 两个版本上游都未提供可靠字节补丁（4229 无独立英文批改入口；4419 未验证） |
| `remove_ocr` | ✓ | ✗ | 4229 `EasiCamera.UI.dll` 0x10CB9：隐藏「智能识别」工具栏按钮 |
| `disable_ai_key` | ✓ | ✗ | 4229 `EasiCamera.Business.dll` 0x187D：忽略相机 AI 键（cmd 13） |

不可用功能均在规则文件的 `unavailable_reason` 中写明原因，UI 会置灰并展示。

功能 ID 映射（上游脚本参数 → 契约 §3.1 固定 ID）：

- `patch_4229_hide_ai.py --hide-ai-button` → `remove_ocr`
- `patch_4229_hide_ai.py --disable-ai-key` → `disable_ai_key`
- `patch_homemaid_freeze.py --enable-freeze` → `enable_hygon_freeze`
- `patch_easicamera_business.py` → `no_third_party_block`
- `patch_easicamera_ui.py --hide-login` → `hide_login`
- `patch_easicamera_ui.py --force-scan` → `force_scan`
- `patch_homemaid_freeze.py --disable-freeze` → `disable_freeze`

## 5. 复现验证

```bash
# 仓库根目录
D:/Software/python314/python.exe analysis/4229_4419/verify_rules.py
```

预期输出：`共校验 17 项，失败 0 项 / 结果: ALL PASS`。

引擎级单测（含真实规则在临时副本上的 detect→apply→is_patched→restore 全链路）：

```bash
cd InspireCameraTools
D:/Software/python314/python.exe -m unittest discover -s tests -v
```

CLI 手工验证：

```bash
cd InspireCameraTools
D:/Software/python314/python.exe -m core.cli detect --main ../extracted/v2.0.10.4229/EasiCamera_2.0.10.4229/Main --json
D:/Software/python314/python.exe -m core.cli plan  --main ../extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/Main \
    --features no_third_party_block,force_scan,hide_login,disable_freeze --json
# apply/restore 请先把 Main 复制到临时目录，不要改 extracted/ 原版：
#   D:/Software/python314/python.exe -m core.cli apply --main <临时副本>/Main --features ... --json
```

## 6. 风险与未验证项

1. **未在真机/真展台验证**：全部结论来自字节级校验、ILSpy 反编译与上游报告的 JIT 校验记录。
2. `force_scan` 上游脚本把 84 字节绑定序列替换成 84 字节常量代码；上游脚本只校验了前 5 字节，
   本规则把完整 84 字节写入 `expected`（覆盖整段），避免“只校验一部分”的隐患。
3. 软件自动更新会覆盖 `Main/` 下 DLL，补丁需要重打（可用本工具的「破坏自动更新」阻止被覆盖）。
4. 上游报告提示：这些补丁只改 UI/门禁/按键分支，**未改变登录/云端权限**；例如 AI 功能是否可用
   还受学校权限、算力服务、云端开关影响。
5. 4229 的 AI/OCR 上游结论是：`AIMenu` 是未接线的遗留控件，真正入口是「智能识别」工具栏按钮
   与相机 AI 键（两个补丁均已移植）。

## 7. 引用的上游资料

- `seewo-easicamera-analysis/docs/EasiCamera_分析报告.md` §7.3（隐藏登录）、§7.4（强制扫描）、
  §7.6（国产化自动冻结：4229/4419 芯片识别差异）、§7.7（4229 AI/OCR 入口定位）
- `seewo-easicamera-analysis/tools/patch_4229_hide_ai.py`
- `seewo-easicamera-analysis/tools/patch_easicamera_ui.py`
- `seewo-easicamera-analysis/tools/patch_easicamera_business.py`
- `seewo-easicamera-analysis/tools/patch_homemaid_freeze.py`
