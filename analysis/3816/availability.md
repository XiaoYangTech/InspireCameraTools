# 2.0.10.3816 功能可用性矩阵（8 个契约功能）

> 判据：对 `extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main/` 下全部托管程序集做
> 「字符串 / 元数据 / ILSpy 反编译」三重核对；原始输出见
> [`il/10-assembly-symbol-evidence.txt`](il/10-assembly-symbol-evidence.txt)。
> 契约功能 ID 固定（analysis/CONTRACT.md §3.1），不可新增。

## 总表

| # | feature id | 3816 可用 | 规则内容 | 结论/原因（一句话） |
|---|---|---|---|---|
| 1 | `no_third_party_block` | ❌ | `unavailable_reason` | 2.0.10 设备枚举不屏蔽第三方摄像头（该限制 2.1.0 才引入） |
| 2 | `force_scan` | ✅ | UI.dll `0xF55E`，84 字节 NOP | 「自动扫描」按钮 Visibility 白名单绑定移除，第三方展台可用 |
| 3 | `hide_login` | ❌ | `unavailable_reason` | 该版本主界面无登录/头像入口 |
| 4 | `disable_freeze` | ❌ | `unavailable_reason` | 无兆芯/海光国产化自动冻结逻辑 |
| 5 | `enable_hygon_freeze` | ❌ | `unavailable_reason` | 无 HomeMaid/IsHomeMaidChip 自动冻结链路 |
| 6 | `remove_english` | ✅ | UI.dll `0xF674`，`17→16` | 隐藏工具栏「英文批改」按钮（该版本唯一批改入口，文案即「英文批改」） |
| 7 | `remove_ocr` | ❌ | `unavailable_reason` | 无独立 OCR/「智能识别」入口 |
| 8 | `disable_ai_key` | ❌ | `unavailable_reason` | HID 处理无 AI 键（cmd 13）分支 |

## 逐项证据

### 1) no_third_party_block — 不可用

- `GlobalDeviceViewModel._0001()`（Business.dll）设备枚举：遍历 `MultimediaUtil.PhysicsVideoInputDevices`，
  满足条件即 `list.Add(new CameraInfo(dev))`，仅在最后删除 `DisplayName` 含 `virtual` 的虚拟设备；
  **没有** `IsSeewoCamera` 过滤、没有 `CancelShieldThirdParty`、没有「无法识别该展台型号」提示。
- 全程序集 grep：`CancelShieldThirdParty`（无匹配）；`IsSeewoCamera` 虽存在（机型功能判断用），但不参与设备列表裁决。
- 该限制为 2.1.0 起引入（参见上游报告 §3.2）。→ 2.0.10.3816 无需也无法「去除」。

### 2) force_scan — 可用

- `ImageEnhanceDisplayToolBarItem..ctor` 内 Visibility 绑定：
  `Path="Camera"` + `Source=EC.CameraApi.DeviceViewModel.MainPreViewElement` +
  `Converter=SeewoCameraButtonVisibilityConverter` + `ConverterParameter=43100 (0x1A85C)`（希沃机型掩码）。
- 不是希沃机型 → `SeewoCameraType.None(0)` → 转换器返回 `Collapsed` → 第三方展台看不到「自动扫描」按钮。
- 执行链无机型限制：`OnNormalClick → EnhanceModesDialog → ImageDiscernViewModel.EnterImageEnhance(type)
  → EC.ImageEnhanceService.Start(type)`，`Start` 仅检查 `CurrentEnhanceImageTypes`，不检查 `IsSeewoCamera`
  （反编译见 `work/re3816/api_src/EasiCamera/ImageDiscernViewModel.cs:72-93`、
  `work/re3816/biz_src_EasiCamera.Business/EasiCamera.Business/ImageEnhanceService.cs:138`）。
- 本地算法组件齐备：`libHexinPaper.dll`、`libtensorflowlite_c.dll`、`libda_cropper.dll`（无需登录/云端）。
- 补丁：84 字节 Visibility 绑定 NOP → 默认 Visible。详见 [`README.md`](README.md) §5。

### 3) hide_login — 不可用

- 3816 的 `DisplayToolbar` 共 25 个 `DisplayToolBarItem` 子类（含 Menu/Minimize/En/…/More），**没有**
  `ProfileButton`、没有账号/头像/登录相关字段或命令。
- 本地化 `zh-CHS/EasiCamera.xaml` 中「登录」只出现 1 次：`Lang.Update.Login` =「请登录」（升级/更新提示），
  不是登录按钮；无「账号/账户/头像/Profile/User」类 key。
- 全程序集 grep：`ProfileButton`、`TryAutoLoginWithSso`、`SaveUserInfoToLocalSso` 均无匹配
  （这些是 2.1.0/4229 的实现）。
- 结论：该版本主程序没有登录入口可隐藏（不排除云端/白板 SSO 集成在其它进程）。

### 4) disable_freeze — 不可用

- 全程序集 grep：`Win32_Processor`、`ProcessorNameString`、`zhaoxin`、`Zhaoxin`、`hygon`（除原生库里巧合字节外）、
  `KX-6000`、`MT71` 均无匹配。
- `Freeze` 相关代码只是手动功能：`ECCommands.FreezeCamera = new DelegateCommand(...)`（Business.BusineseModule），
  相机 `IsFreeze` 状态用于拍照/批注前提示，**没有**按 CPU 型号自动冻结画面的逻辑
  （4229/4419 的 HomeMaid 链路在该版本不存在）。

### 5) enable_hygon_freeze — 不可用

- grep：`HomeMaid`、`IsHomeMaidChip` 无匹配。
- 名称陷阱：3816 确有 `EasiCamera.Util.HardwareRecognizer`，但反编译（`work/re3816/biz_src_EasiCamera.Util/
  EasiCamera.Util/HardwareRecognizer.cs`）其成员为 `IsIwb`（桌面 `iwb.txt` 或 McuHunter 判定一体机）与
  USB MCU 操作（`FindAll/Find/Confirm/GetDeviceList/Write/Read`），被 FlatFrogBoardModule /
  Generation6OrCompatibleDeviceBoardModule / SmartBoardModule / MyouService 使用；与 4229/4419 的
  「国产化芯片识别」同名不同物。
- 结论：无自动冻结可启用/禁用。

### 6) remove_english — 可用（核心）

- 3816 **没有** AIMenu/口算批改/英文圈词/智能识别：grep `AIMenu`、`IntelligentIdentification`、
  `StartAiRecognition`、`OpenAIMenu`、`AiKeyTip`、`WordCut`、`Homework`、中文「口算」「圈词」全部无匹配。
- 唯一批改入口 = 工具栏按钮控件 `CompositionCorrectionDisplayToolBarItem`：
  - 文案：基类推导 `Lang.DisplayToolBar.CompositionCorrection` = **「英文批改」**（本地化 L43）；
  - 点击：`new ScanCompositionControl()` 加入主 Grid → `IEnglishCompositionProvider.GetOcrText` /
    `GetCorrectEnglishCompositionByTextResult`（英语作文批改云 OCR）；
  - 全程序集无第二个引用/实例化点（除 `DisplayToolbar` 的类型判断与流程内控件）。
- 补丁：`FunctionModule.MainWindow(1) → None(0)`（1 字节），条目不再被 `IsShowUiItem` 过滤进任何工具栏集合。
  详见 [`README.md`](README.md) §3/§4。

### 7) remove_ocr — 不可用

- 无 `IntelligentIdentification` / `StartAiRecognition` / `AIMenu` / `AiKeyTip` / `IsShowIntelligentIdentification`
  符号；无 OCR 相关本地化 key。
- 3816 的「英文批改」本身就是一项云 OCR 批改（作文批改），但它不是契约里「OCR（智能识别）」所指的独立入口；
  该入口已由 `remove_english` 覆盖，故 `remove_ocr` 在 3816 标记不可用并在原因中说明。

### 8) disable_ai_key — 不可用

- `CommonHidComponent.DataProcess`（Business.dll，行 634-719 反编译）只处理：
  `data[2]==1`（Key1–5：拍照/旋转/唤起/缩小/放大）、`==2`（LED 状态）、`==3`（触摸灯）、
  `==4`（心跳）、`==5`（补光灯按键）、`==6`（MCU 版本）。
- 没有 4229 中的 `cmd 13 → ECCommands.OpenAIMenu` 分支（`OpenAIMenu` 全程序集无匹配）。
- 结论：该版本不存在「展台 AI 按键」触发逻辑，无需/无法屏蔽。

## 与契约验收的对应关系

- 契约 §9：「3816：`remove_english` 规则可应用，补丁后 ILSpy 反编译正常，按钮/入口被去除（有 IL 证据）」
  → 已满足：`RULES` 可应用（引擎实测）、ILSpy 反编译正常、IL 证据（FunctionModule=None + IsShowUiItem 判据）、
  按钮不再被收集；**未真机验证**（如实标注）。
- 契约 §3.4：`expected/patched` 等长、偏移为原版绝对偏移、补丁后哈希与 ILSpy 验证均已记录于
  [`verify.md`](verify.md)，并有自动化脚本 [`verify_rules.py`](verify_rules.py)。
