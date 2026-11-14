# EasiCamera 2.0.10.4087 逆向分析记录（去除 OCR / 智能识别入口 + 全功能规则）

> 目标版本：希沃视频展台 **EasiCamera 2.0.10.4087**（安装包构建时间 2024-09-12 16:11:08）
> 负责人：re-4087-ocr（task-1）
> 状态：**静态逆向 + 字节级补丁 + 内存/副本验证全部完成；未在真机运行 EasiCamera**（按项目约束不安装/不运行）。
> 规则文件：[v2_0_10_4087.py](../../InspireCameraTools/core/rules/v2_0_10_4087.py)（已通过 patch-core 引擎 `validate` / `detect` / `plan` / `apply` / `restore` 全链路）

---

## 1. 结论速览

| 功能 | 可用 | 补丁点 | 说明 |
|---|---|---|---|
| **remove_ocr（去除 OCR/智能识别按钮）** | ✅ | `EasiCamera.UI.dll` 0x10CC9（**1 字节**） | 工具栏「OCR」按钮 `AIMenuDisplayToolBarItem` 的 `FunctionModule` 改为 `None`，不再进入任何工具栏列表 |
| hide_login（去除登录按钮） | ✅ | `EasiCamera.UI.dll` 0x1E773 + 0x1E8BC | `DisplayToolbar.ProfileButton` 恒为 `Collapsed` |
| force_scan（第三方展台强制扫描） | ✅ | `EasiCamera.UI.dll` 0x10BD6（84B 等长替换） | 扫描按钮 `Visibility` 绑定替换为常量 `Visible` |
| remove_english（去除英文批改） | ✅ | `EasiCamera.UI.dll` 0x1556A | OCR 菜单内「英文批改」按钮 `Visibility=Collapsed` |
| disable_ai_key（禁用相机 AI 按键） | ✅ | `EasiCamera.Business.dll` 0x12B5 | HID cmd 13 分支 `call get_OpenAIMenu` → `ldnull`（同 4229 思路） |
| no_third_party_block | ❌ | — | 2.0.10 无云端第三方展台屏蔽开关（`CancelShieldThirdParty` 自 2.1.0 引入） |
| disable_freeze（去除国产化冻结） | ❌ | — | 本版本无 `HomeMaidChipHandler`/`IsHomeMaidChip`（自 2.0.10.4229 起才有） |
| enable_hygon_freeze（海光启用冻结） | ❌ | — | 本版本 `EasiCamera.Util.HardwareRecognizer` 无兆芯/海光识别，无法启用 |

**OCR 入口定位结论（与 4229 不同）**：
- 2.0.10.4229 的入口是 `IntelligentIdentificationDisplayToolBarItem` + `StartAiRecognition`；
- **4087 没有 `IntelligentIdentification` / `StartAiRecognition` 任何字符串**，OCR 入口是工具栏 **「OCR」按钮**：
  - 控件类 `EasiCamera.UI.AIMenuDisplayToolBarItem`（`EasiCamera.UI.dll`）
  - 文案 key `Lang.DisplayToolBar.AIMenu`，中文值 **`OCR`**（`Main/Localizations/zh-CHS/EasiCamera.yml` 第 34 行）
  - 点击后 `AIMenuDisplayToolBarItem.OnNormalClick` → 未登录先弹登录窗 → `ShowOrHideContentPopup(typeof(AIMenu), …)` 弹出 `EasiCamera.UI.AIMenu` 菜单（**口算批改** `OcrCorrectionButton` + **英文批改** `CompositionCorrectionButton`）

---

## 2. 环境与样本

| 项 | 值 |
|---|---|
| 安装包 | `installers/EasiCamera_20240912161108.exe`（141,016,888 B，NSIS） |
| 解包目录 | `extracted/v20240912161108/EasiCamera_2.0.10.4087/Main/`（7-Zip 解包，只读，未修改） |
| EasiCamera.UI.dll | 1,067,008 B，SHA-256 `fcaa674bcc7567df87497d24305ae5e4207d3458ae68d29dd915d01d4a7c2443` |
| EasiCamera.Business.dll | 260,608 B，SHA-256 `5345738297bb2e4a6cf7e1126ac8052641d331dbc39304cf40fadd2d54003fcd` |
| EasiCamera.exe | 1,475,200 B，SHA-256 `50ee51a7ee2527a31f82ed0aa0a3e407eed3107be09dc1f4fc5d898a4b453f36` |
| 反编译工具 | ILSpy CLI 9.1.0.7988（`.tools/ilspycmd/ilspycmd.dll`，dotnet 8 运行时） |
| Python | `D:/Software/python314/python.exe`（3.14） |

本版本相比 3816 的新增组件（与 OCR/AI 相关）：`Cvte.GurnetUI.dll`、`libtensorflowlite_c.dll`、`libda_cropper.dll`（本地纸张检测/文档增强用），
无 `libHexinPaper.dll`；`EasiCamera.UI.dll` 内 OCR 控件全部在 `controls_/ocr/**` BAML 资源中。

---

## 3. 定位过程（OCR 按钮）

### 3.1 从本地化文案反查

`Main/Localizations/zh-CHS/EasiCamera.yml` 中与 OCR/AI 相关的 key：

```yaml
DisplayToolBar:
  AIMenu: OCR                     # ← 工具栏按钮文案（本版本就叫 OCR）
AIMenu:
  OcrCorrection: 口算批改
  CompositionCorrection: 英文批改
  OcrRepeat: 英文圈词
OcrRepeat:
  ReadLoud: 朗读
  ...
```

在全部托管程序集里用 UTF-16 (#US 堆) 搜索，只命中 `EasiCamera.UI.dll` 的 OCR 控件（`AIMenu`、`OcrCorrection`、`CompositionCorrection`、`OcrRepeat`、`dispaly_/aimenu.baml` 等），
**没有任何 4229 的 `IntelligentIdentification*` / `StartAiRecognition`**，说明本版本 OCR/AI 入口就是 `AIMenu` 这一套。

### 3.2 类型与调用链

`ilspycmd -l c EasiCamera.UI.dll` 得到关键类型：

```
EasiCamera.UI.AIMenuDisplayToolBarItem   ← 工具栏 OCR 按钮（DisplayToolBarItem 派生）
EasiCamera.UI.AIMenu                     ← OCR 弹窗菜单（UserControl）
EasiCamera.UI.OcrCorrectionViewModel / Controls_.Ocr.CompositionCorrection.ScanCompositionViewModel
EasiCamera.UI.Ocr.* / Controls_.Ocr.*    ← 口算批改 / 英文批改 / 英文圈词控件
```

`AIMenuDisplayToolBarItem.OnNormalClick`（`EasiCamera.UI.dll`，RVA 0x12AE8）核心逻辑（ILSpy 反编译）：

```csharp
protected override void OnNormalClick(object sender, RoutedEventArgs e) {
    base.OnNormalClick(sender, e);
    if (string.IsNullOrEmpty(EC.Account.Token)) {
        await Container.Current.Get<IWindowManager>().ShowLoginWindowAsync();   // 未登录先弹登录
    }
    if (!string.IsNullOrEmpty(EC.Account.Token) && e.OriginalSource is FrameworkElement element) {
        element.ShowOrHideContentPopup(typeof(AIMenu), PopupHelper.TryGetPopupPlacementTarget(sender));  // 弹 OCR 菜单
    }
}
```

`AIMenu` 弹窗的两个按钮（`AIMenu.Connect`，case 1/2）：

- case 1 `OcrCorrectionButton_OnClick` → `new ScanProcessControl(new OcrCorrectionViewModel())`（口算批改）
- case 2 `CompositionCorrectionButton_OnClick` → `new ScanProcessControl(new ScanCompositionViewModel())`（英文批改）
- `AIMenu.OcrRepeatButton_OnClick` 存在但 `Connect` 中没有对应 case（**死代码**，本版本菜单里没有「英文圈词」按钮）

### 3.3 工具栏项注册/过滤机制（选择补丁方案的关键）

- `EasiCamera.Api.UiItemExtension.InitDisplayToolBarUiItems(Assembly)`（`EasiCamera.Api.dll`，RVA 0xADD8）
  对 `assembly.GetExportedTypes()` 反射，把每个可赋值给 `DisplayToolBarItem` 的类型 `Activator.CreateInstance` 成工具栏项；
- `UiItemExtension..cctor` 的 `UiItemKeysGroup` 字典把 key `"AIMenu"` 分到组 `DefaultGroup + "2"`；
- 渲染时 `EasiCamera.DisplayToolBarItemViewModel.RefreshUiItemState()`/`GetUiItems(...)` 的过滤条件（`EasiCamera.Api.dll`）：
  ```csharp
  // <>c__DisplayClass1_0::<GetUiItems>b__0
  return group.Equals(item.Group) && (item.FunctionModule & EC.BoardApi.CurrentFunctionModule) != 0;
  ```
  即 **`FunctionModule == 0(None)` 的项不会进入任何功能模块的栏目/「更多」列表**。

另外 `DisplayToolbar.FrameworkElement_OnLoaded` 里对 `AIMenuDisplayToolBarItem` 有特殊处理：项加载时把
`ECCommands.OpenAIMenu = new DelegateCommand(() => item.OnClick(...), ...)` 赋给全局命令，供**相机硬件 AI 键**（HID cmd 13）调用。

### 3.4 相机 AI 键路径（disable_ai_key）

`EasiCamera.Business.CommonHidComponent.DataProcess`（RVA 0x2CE8，972B IL）末尾：

```
if (data[2] == 13 && data.Length >= 7) {
    ECCommands.OpenAIMenu?.Execute(null);      // 空引用安全
}
```

与 4229 的 `--disable-ai-key` 完全同构，可复用同一字节补丁法。

---

## 4. 补丁方案（全部为等长原地 IL 替换，不改方法体长度/元数据布局）

### 4.1 remove_ocr（核心，1 字节）

- 目标方法：`EasiCamera.UI.AIMenuDisplayToolBarItem::.ctor`（RVA 0x12AC8，Tiny 方法头 1B，CodeSize 0x1F）
- 代码起始文件偏移：`0x10CC9`
- IL 前后对比（`IL_0018`）：

```
; IL ...
IL_0000: ldarg.0
IL_0001: ldc.i4.0                 ; base ctor 参数
IL_0002: ldc.i4.0
IL_0003: call DisplayToolBarItem::.ctor(bool, ItemType)
IL_0008: ldarg.0
IL_0009: ldc.r8 102.0
IL_0012: call UiItem::set_SortHint(float64)
IL_0017: ldarg.0
IL_0018: ldc.i4.1   ← 原：FunctionModule.MainWindow(1)     ★ 1 字节补丁：0x17 → 0x16
IL_0019: call UiItem::set_FunctionModule(FunctionModule)
IL_001e: ret
```

- 原字节（整个 31B 方法体，作为 expected，避免误匹配）：
  `02161628a604000a0223000000000080594028a704000a021728a804000a2a`
- 补丁字节：
  `02161628a604000a0223000000000080594028a704000a021628a804000a2a`
- 效果：该项 `FunctionModule = None(0)` → 被 `GetUiItems` 过滤 → 「OCR」按钮从工具栏 / 更多列表消失，
  `AIMenu` 弹窗不可达；同时 `ECCommands.OpenAIMenu` 不再被赋值（该项 Loaded 事件不会发生），
  相机 AI 键点击也不再有动作（与「去除 OCR」语义一致，等价于同时禁用 AI 键入口）。
- 为什么不用「Visibility 绑定替换」：本版本该按钮**没有绑定 Visibility**（默认可见，只有登录态判断在点击时），
  绑定式补丁在此版本不适用；改 `FunctionModule` 更小且行为等价（直接不生成 UI 元素）。

### 4.2 补丁点总表

> 偏移=原版文件绝对偏移；原字节/补丁字节均可由 [verify_rules.py](verify_rules.py) 复现校验。
> 规则文件中的 `expected`/`patched` 与下表完全一致。

| 功能 | 文件 | 偏移 | 长度 | 原字节 | 补丁字节 |
|---|---|---|---|---|---|
| remove_ocr | EasiCamera.UI.dll | 0x10CC9 | 31 | `02161628a604000a0223000000000080594028a704000a021728a804000a2a` | `02161628a604000a0223000000000080594028a704000a021628a804000a2a` |
| hide_login #1 | EasiCamera.UI.dll | 0x1E773 | 16 | `027b18040004285e03000a6fd601000a` | `027b18040004186fe601000a00000000` |
| hide_login #2 | EasiCamera.UI.dll | 0x1E8BC | 4 | `170b2b02` | `160b2b02` |
| force_scan | EasiCamera.UI.dll | 0x10BD6 | 84 | `73b102000a2572172a00701473c300000a6fb202000a25289301000a6ffb01000a6f6002000a6fdc02000a2573cd0300066fb302000a25205ca801008c5c0200016fba04000a0a027ebb04000a0628b502000a26` | `027ebb04000a168c030100016f1001000a` + 67×`00` |
| remove_english | EasiCamera.UI.dll | 0x1556A | 24 | `027bce02000402fe06a804000673b601000a6f8602000a2a` | `027bce020004186fe601000a2a` + 11×`00` |
| disable_ai_key | EasiCamera.Business.dll | 0x12B5 | 5 | `288700000a` | `1400000000` |

各补丁点的 RVA / IL 偏移（用于日后升级重新定位）：

| 功能 | 程序集 | 方法 | RVA | 方法头 | CodeSize | IL 偏移 |
|---|---|---|---|---|---|---|
| remove_ocr | EasiCamera.UI.dll | `AIMenuDisplayToolBarItem::.ctor` | 0x12AC8 | Tiny(1B) | 0x1F | IL_0018 |
| hide_login #1 | EasiCamera.UI.dll | `DisplayToolbar::.ctor` | 0x2039C | Fat(12B) | 476 | IL_01CB（末尾 `ProfileButton.DataContext = EC.Account`） |
| hide_login #2 | EasiCamera.UI.dll | `DisplayToolbar::BoardApiOnFunctionModuleChanged` | 0x20614 | Fat(12B) | 176 | IL_009C（`flag = (newModule==MainWindow\|\|==ContrastView)` 的 `ldc.i4.1`） |
| force_scan | EasiCamera.UI.dll | `ImageEnhanceDisplayToolBarItem::.ctor` | 0x129AC | Fat(12B) | 178 | IL_001E..IL_0071（Visibility 的 `newobj Binding`…`SetBinding`…`pop` 共 84B） |
| remove_english | EasiCamera.UI.dll | `AIMenu::Connect` | 0x17324 | Fat(12B) | 90 | IL_003A..IL_0051（case 2：`CompositionCorrectionButton.Click += …`） |
| disable_ai_key | EasiCamera.Business.dll | `CommonHidComponent::DataProcess` | 0x2CE8 | Fat(12B) | 978 | IL_03C1（cmd 13 分支 `call get_OpenAIMenu`） |

### 4.3 各补丁的 IL 语义

- **hide_login #1**：`ldarg.0; ldfld ProfileButton; call EC.get_Account; callvirt set_DataContext`
  → `ldarg.0; ldfld ProfileButton; ldc.i4.2(Collapsed); callvirt UIElement.set_Visibility` + 4×nop。
- **hide_login #2**：`BoardApiOnFunctionModuleChanged` 里计算「是否显示登录按钮」的 `flag` 末尾 `ldc.i4.1` → `ldc.i4.0`，
  使 `flag` 恒为 false → `Visibility = Collapsed` 恒成立（否则用户切换功能模块后登录按钮会重新出现）。
- **force_scan**：`ImageEnhanceDisplayToolBarItem..ctor` 里 84 字节的 Visibility 绑定构造（`newobj Binding` → `BindingOperations.SetBinding(VisibilityProperty)` → `pop`）
  整体替换为 `ldarg.0; ldsfld DisplayToolBarItem::VisibilityProperty; ldc.i4.0(Visible); box Visibility; callvirt DependencyObject::SetValue` + 67×nop。
  原有第二个绑定（`IsCanClickDisabledProperty`）保留。只影响「扫描/文档增强」按钮，不影响补光灯按钮（后者是另一个类，未改）。
- **remove_english**：`AIMenu::Connect` case 2 的 `CompositionCorrectionButton.Click += handler` 序列替换为
  `ldarg.0; ldfld CompositionCorrectionButton; ldc.i4.2(Collapsed); callvirt UIElement.set_Visibility; ret` + 11×nop，
  即「英文批改」按钮直接不可见（口算批改按钮不受影响）。
- **disable_ai_key**：`call [EasiCamera.Api]ECCommands::get_OpenAIMenu()`（5 字节）→ `ldnull` + 4×nop；
  后续 `dup; brtrue` 判空后 `pop; ret`，即收到 HID cmd 13 时直接返回。

### 4.4 不可用功能的原因（已用全程序集字符串检索确认）

| 功能 | 不可用原因 | 证据 |
|---|---|---|
| no_third_party_block | 2.0.10 无云端第三方展台屏蔽开关；设备列表不按 `CancelShieldThirdParty` 过滤 | 全部 `Main/*.dll`、`*.exe` 搜 `CancelShieldThirdParty`/`ShieldThirdParty`/`RecognizeUnmatchedDeviceCantUse` 无命中；`EasiCamera.Business.GlobalDeviceViewModel` 无第三方过滤分支（与上游报告 §3.2 一致） |
| disable_freeze | 本版本无国产化芯片自动冻结逻辑 | 全程序集搜 `HomeMaid`/`zhaoxin`/`hygon` 无命中；`EasiCamera.Util.HardwareRecognizer` 只有 `IsIwb`/USB 枚举，无 `IsHomeMaidChip`/`IsZhaoXinChip`/`IsHaiGuangChip` |
| enable_hygon_freeze | 同上，无国产化芯片识别可改 | 同上；`MakeFreezeAsStopForNoneSeewo03Cam`/`CamFreezeIntervalInMillisecond` 仅存在于 `EasiCamera.Api.AppConfigData` 定义（无消费者），改配置无效 |

---

## 5. 验证（全部静态/字节级；**未真机运行**）

### 5.1 规则自动校验：`verify_rules.py`

```bash
D:/Software/python314/python.exe analysis/4087/verify_rules.py
# 47 项检查全部通过，退出码 0
```

覆盖：规则格式（engine validate）、原版 3 个文件 SHA-256 指纹、逐 op 原字节断言、
5 个功能各自补丁后 SHA-256、全功能合并补丁后 SHA-256、重复应用幂等、不可用功能原因覆盖。
完整输出见 [verify_output.txt](verify_output.txt)。

### 5.2 ILSpy 对补丁后程序集复反编译

把补丁后 DLL 放回**完整 Main 副本**（依赖齐全，避免缺引用假警报）后：

- `ilspycmd -il` 全程序集反编译**成功**（UI.dll 2286 个方法、Business.dll 880 个方法全部可解析）；
- 补丁前后方法表逐方法比较：**RVA / 方法头大小 / CodeSize 差异数 = 0**
  （证明只改指令字节，未移动方法体/异常表）→ [il/method_table_check.md](il/method_table_check.md)
- 补丁后关键方法反编译结果（摘录见 [il/decompiled_patched/](il/decompiled_patched/)）：
  - `AIMenuDisplayToolBarItem..ctor`：`FunctionModule = FunctionModule.None;` ✅
  - `ImageEnhanceDisplayToolBarItem..ctor`：`SetValue(DisplayToolBarItem.VisibilityProperty, Visibility.Visible);` ✅（原绑定已移除）
  - `AIMenu.Connect`：`case 2: CompositionCorrectionButton.Visibility = Visibility.Collapsed;` ✅
  - `DisplayToolbar..ctor`：`ProfileButton.Visibility = Visibility.Collapsed;` ✅
  - `DisplayToolbar.BoardApiOnFunctionModuleChanged`：`flag = … && false` → 恒 `Collapsed` ✅
  - `CommonHidComponent.DataProcess`：cmd 13 分支为 `((ICommand)null)?.Execute(null);`（空操作）✅
- 补丁前后文件大小完全不变（UI.dll 1,067,008 B / Business.dll 260,608 B）。

### 5.3 补丁引擎全链路（副本 `work/re4087/main/`，extracted 原目录未动）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 识别 | `core.cli detect --main <副本>` | `2.0.10.4087`（3 个指纹文件全匹配） |
| 功能矩阵 | `core.cli list --version 2.0.10.4087 --main <副本>` | 5 可用 / 3 不可用（含原因） |
| dry-run | `core.cli plan --features …` | 5 个可用功能均非已补丁 |
| 应用 | `core.cli apply --features remove_ocr,disable_ai_key,hide_login,force_scan,remove_english` | ok，已应用 5 项，自动备份 |
| 已补丁判定 | `patch_engine.is_patched()` | 上述 5 项 true，其余 false |
| 幂等 | 再次 apply | `所选功能均已应用，无需重复补丁`（不写盘、无备份） |
| 恢复 | `core.cli restore --backup <备份目录>` | 2 个文件恢复为原版 SHA-256 |
| 补丁后哈希 | `sha256sum` | 与规则/verify 内置期望值**逐字节一致** |

补丁后文件 SHA-256：

| 状态 | EasiCamera.UI.dll | EasiCamera.Business.dll |
|---|---|---|
| 原版 | `fcaa674bcc7567df87497d24305ae5e4207d3458ae68d29dd915d01d4a7c2443` | `5345738297bb2e4a6cf7e1126ac8052641d331dbc39304cf40fadd2d54003fcd` |
| 仅 remove_ocr | `b55847ff1427ea918ef95186c00e564ebe65ccba030c1637ce9135bdcb0985fa` | — |
| 仅 hide_login | `791aeef8cf69eabfaa8b5fa9bd9a86e2f7ff037717f6d75324b6d61bbf2f7cc9` | — |
| 仅 force_scan | `65e9bfcc5a514e6236a905c8c89006e14a9e2056a3adfa42a0fafadd7c6e83c0` | — |
| 仅 remove_english | `ae1d8591cb7d85d4bbf590fdf3605fd38090924d87dbc6a72435f37a3727a968` | — |
| 仅 disable_ai_key | — | `50a565decf9c7a847082cc6b6853deb06644ad65a6bc7c517e641aab315358a2` |
| 全部可用功能 | `55e089394ef128ac297fe575b6eafda831890a522d1ff37a5645d4630acbdedd` | `50a565decf9c7a847082cc6b6853deb06644ad65a6bc7c517e641aab315358a2` |

引擎自测原始 JSON 证据：[engine_selftest/](engine_selftest/)（list/plan/apply/restore）。

---

## 6. 风险与注意事项

1. **未真机验证**：所有结论来自静态反编译 + 字节级校验 + CLR 元数据完整性检查；没有在装有展台硬件的机器上运行 EasiCamera（项目约束）。
2. `remove_ocr` 采用「项不属于任何功能模块 → 被列表过滤」实现，依赖 `GetUiItems` 的 `FunctionModule & CurrentFunctionModule` 过滤逻辑；
   IL 静态核对成立，但若未来版本改为直接遍历 `AllUiItems` 渲染，需重新定位。
3. `remove_ocr` 的附带效果：`ECCommands.OpenAIMenu` 不再赋值，相机 AI 键（HID cmd 13）也变为空操作；
   若只想屏蔽按钮而保留 AI 键（在本版本无意义，AI 键也是打开同一 OCR 菜单），可改用 `disable_ai_key` 单独控制。
4. `hide_login` 只隐藏入口，不修改登录/SSO 逻辑；若其它功能（例如未移除 OCR 时点击 OCR）触发未登录流程，仍可能弹出登录窗。
5. `force_scan` 只负责让扫描按钮显示；实际扫描/文档增强效果取决于第三方摄像头分辨率、对焦与光照（本地算法不挑机型，见上游报告 §7.4）。
6. `remove_english` 只隐藏 OCR 菜单内的「英文批改」按钮；若同时选择 `remove_ocr`，整个 OCR 菜单均不可达（两个补丁不冲突、不重叠）。
7. 自动升级会覆盖 DLL，需要重新打补丁（或使用项目「破坏自动更新」功能）。
8. 规则以原版 SHA-256 严格校验；升级/降级到其它版本会识别失败并拒绝补丁（不会误改）。

---

## 7. 复现命令

```bash
cd D:/开发/SeewoCamera

# 1) 规则自检（只读原版，可重复运行）
D:/Software/python314/python.exe analysis/4087/verify_rules.py

# 2) 引擎 CLI 自测（在 InspireCameraTools 下；先复制 Main 到临时目录）
cd InspireCameraTools
D:/Software/python314/python.exe -m core.cli validate --json
D:/Software/python314/python.exe -m core.cli detect --main "../extracted/v20240912161108/EasiCamera_2.0.10.4087/Main" --json
D:/Software/python314/python.exe -m core.cli list --version 2.0.10.4087 --json
D:/Software/python314/python.exe -m core.cli plan --main <临时副本> --features remove_ocr,disable_ai_key,hide_login,force_scan,remove_english --json
D:/Software/python314/python.exe -m core.cli apply --main <临时副本> --features remove_ocr,disable_ai_key,hide_login,force_scan,remove_english --json
D:/Software/python314/python.exe -m core.cli restore --main <临时副本> --backup <备份目录> --json

# 3) ILSpy 复反编译（补丁后 DLL 需放回完整 Main 副本才有完整依赖）
cd D:/开发/SeewoCamera
dotnet .tools/ilspycmd/ilspycmd.dll <Main副本>/EasiCamera.UI.dll -t EasiCamera.UI.AIMenuDisplayToolBarItem
```

工具与中间产物（未入库的大文件）：`work/re4087/`（Main 副本、patched DLL、IL 全文、脚本）。

---

## 8. 文件索引

| 路径 | 说明 |
|---|---|
| [../../InspireCameraTools/core/rules/v2_0_10_4087.py](../../InspireCameraTools/core/rules/v2_0_10_4087.py) | 交付的 4087 规则（RULES 字典） |
| [verify_rules.py](verify_rules.py) | 自动校验脚本（47 项检查） |
| [verify_output.txt](verify_output.txt) | verify_rules.py 完整输出 |
| [il/](il/) | IL 证据（原版/补丁后方法级 IL、补丁后反编译摘录、方法表对比） |
| [engine_selftest/](engine_selftest/) | 补丁引擎 CLI 全链路 JSON 结果 |
| `work/re4087/` | 工作副本：Main 副本、补丁后 DLL、完整 IL 文本、分析/生成脚本（不修改 extracted/） |
