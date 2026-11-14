# EasiCamera 2.0.10.3816 逆向分析记录

> 目标版本：**EasiCamera 2.0.10.3816**（`EasiCameraSetup_2.0.10.3816.exe`，140,148,216 字节）
> 任务：为「亿方展台管家」（InspireCameraTools）补丁提供 3816 版本规则，核心是**去除英文批改**。
> 分析方式：**纯静态分析**（ILSpy 反编译 + 元数据/字符串核对 + 字节级 IL 补丁）。
> **未安装/未运行 EasiCamera，未在真机/真展台验证。**

---

## 0. TL;DR（结论）

1. **3816 没有 AIMenu、口算批改、英文圈词、智能识别/OCR**（全程序集无 `AIMenu` / `IntelligentIdentification` /
   `StartAiRecognition` / `OpenAIMenu` / `WordCut` 等符号，本地化无「口算」「圈词」「OCR」key）。
2. **工具栏按钮「英文批改」是 3816 唯一的批改/AI 入口**：控件类型
   `EasiCamera.UI.CompositionCorrectionDisplayToolBarItem`，按钮文案由基类规则推导为
   `Lang.DisplayToolBar.CompositionCorrection` = **「英文批改」**（详见 §3 证据链）。
3. `remove_english` 补丁 = 把该控件构造函数里的 `FunctionModule` 由 `MainWindow` 改成 `None`
   （**UI.dll 文件偏移 `0xF674`，1 字节 `17→16`，等长替换**）。FunctionModule=None 后
   `UiItem.IsShowUiItem()` 恒为 false，条目不会被任何 ToolBar ItemsControl 收集 → 按钮从界面消失、命令不可达。
4. 额外可用功能：`force_scan`（UI.dll 偏移 `0xF55E` 起 84 字节 Visibility 白名单绑定整体 NOP → 按钮默认 Visible）。
5. 其余 6 个契约功能在该版本**不存在对应逻辑/入口**，已在规则文件的 `unavailable_reason` 中逐条说明
   （见 [`availability.md`](availability.md)）。
6. 补丁后文件 SHA-256 已用**真实补丁引擎** `simulate_patch` 与独立脚本双重验证；`verify_rules.py` 全绿；
   ILSpy 对补丁后程序集完整反编译成功。**未真机验证。**

---

## 1. 输入与工具

| 项目 | 值 |
|---|---|
| 安装包 | `installers/EasiCameraSetup_2.0.10.3816.exe`（140,148,216 字节，NSIS，7-Zip 解包） |
| 解包目录 | `extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/`（279 个文件） |
| 目标 Main | `extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main/` |
| 验证副本 | `work/re3816/Main/`（原版 Main 的完整副本，**所有写操作/补丁验证只在这里**） |
| 反编译器 | `.tools/ilspycmd`（ILSpy CLI 9.1.0.7988，`dotnet ilspycmd.dll`，`-il`/`-t`/`-p`/`-l`） |
| 辅助 | Python 3.14（`dnfile` + `pefile` 解析方法体 RVA/文件偏移；`work/re3816/pemeta.py`） |

原版关键文件 SHA-256（版本识别指纹，已写入规则 `RULES["files"]`）：

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `EasiCamera.UI.dll` | 749,568 | `f65b7a81a3f23a766de3c775c4885cc0dd4c42d562e073764e795ca9f9ae61ef` |
| `EasiCamera.Business.dll` | 1,778,688 | `2b8aa20512a5d19c2aa87280196caa6c45062b6aea1babe90107a3bd64b6823d` |
| `EasiCamera.exe` | 1,448,064 | `d482c73150ae5ad1995db46f0bd96b2ca346a45226d14ea81b4ade5ce1db34f8` |
| `EasiCamera.Util.dll` | 95,744 | `5d4fe20d443c84e4729d3a5eed985be4fc9bda5184d6c951984f6beb2ef90f92` |

版本特点（与 4087 对比）：无 `Cvte.GurnetUI.dll`；有 `libHexinPaper.dll`（9.7 MB）与 `DirectShowLib-2005.dll`；
`EasiCamera.Business.dll` 1.78 MB（4087 仅 260 KB），两版本架构差异大，补丁不可互抄。

> 注意：3816 的界面文案**不是** `Localizations/zh-CHS/EasiCamera.yml`，而是
> `Main/Localizations/zh-CHS/EasiCamera.xaml`（UTF-8 XAML，408 行）；`en/EasiCamera.xaml` 是同结构英文资源。

---

## 2. 版本架构侦察（与补丁相关的部分）

- **工具栏机制**：`DisplayToolbar`（UI.dll）的 XAML 里有 5 个 `ItemsControl`：
  `LeftItemsControl / DefaultToolItemsControl / ImageItemsControl / ExtentionItemsControl / SidebarUiItem`，
  分别绑定 `DisplayToolBarItemViewModel` 的 `LeftUiItems / DefaultToolUiItems / ImageUiItems / ExtentionUiItems / SidebarUiItems`。
- **工具栏条目来源**：`UIModule` 调 `UiItemExtension.InitDisplayToolBarUiItems(typeof(MenuDisplayToolBarItem).Assembly)`
  （**反射**遍历 UI.dll 全部导出类型，凡继承 `DisplayToolBarItem` 且有 `UiItemKeysGroup[Key]` 的即实例化加入 `AllUiItems`）。
- **显示过滤**（remove_english 的语义依据）：
  `UiItemExtension.GetUiItems()` → `UiItem.IsShowUiItem(functionModule)`；
  `DisplayToolBarItem.IsShowUiItem` = `(FunctionModule & functionModule) != 0`；
  `DisplayToolBarItemViewModel.RefreshUiItemState()` 每个功能模块切换时按此过滤后填充上述集合。
- **按钮文案来源**：`DisplayToolBarItem` 基类构造函数：
  `Key = 类型名.Replace("DisplayToolBarItem","")` → `Text = Lang.TryGet("Lang.DisplayToolBar." + Key)`
  → `IconKey = "Geometry." + Key`（见 [`il/05-DisplayToolBarItem-base.IL.txt`](il/05-DisplayToolBarItem-base.IL.txt)）。
- **图片/结果资源**：`EasiCamera.exe` 资源里有 `Image.CompositionCorrection.*` / `Geometry.CompositionCorrection*`
  图标键（英文批改按钮图标），不是第二个入口。
- **本地化加载**：`zh-CHS/EasiCamera.xaml` 为 `s:String x:Key="Lang.*"` 资源字典；`Lang.Get/TryGet` 按 key 取值。

---

## 3. 「英文批改」定位证据链（回答 Lead 的三个核实点）

### 3.1 本地化全部含「批改 / 英文」的 key（共 11 条）

来源 `Main/Localizations/zh-CHS/EasiCamera.xaml`（完整输出见
[`il/09-localization-correction-keys.txt`](il/09-localization-correction-keys.txt)）：

| 行 | Key | 值 |
|---|---|---|
| L43 | `Lang.DisplayToolBar.CompositionCorrection` | **英文批改**（工具栏按钮文案） |
| L60 | `Lang.DisplayToolBar.Recorrect` | 再次批改 |
| L61 | `Lang.DisplayToolBar.ExitCorrection` | 退出批改（CompositionToolBar 内） |
| L240 | `Lang.ImageEnhance.PleaseUseEnglishComposition` | 请选择英文作文进行批改 |
| L319 | `Lang.ScanComposition.CorrectNotice1` | 正在批改，请勿移动 |
| L320 | `Lang.ScanComposition.FinishCorrection` | 批改完成 |
| L325 | `Lang.ScanComposition.Exit` | 退出批改 |
| L326 | `Lang.ScanComposition.Recorrect` | 重新批改 |
| L329 | `Lang.CompositionResult.GeneralCorrection` | 批改汇总 |
| L330 | `Lang.CompositionResult.ViewDetail` | 查看批改详情 |
| L337 | `Lang.CompositionResult.ResultImageTitle` | 希沃视频展台 · **英语作文智能批改** |

**没有**「口算」「圈词」「OCR」「智能识别」等任何 key（`grep` 无匹配）。

### 3.2 按钮实际显示的就是「英文批改」

`CompositionCorrectionDisplayToolBarItem` 自身未设置 Text，文案由基类 `DisplayToolBarItem..ctor` 推导
（IL 证据：`il/05-DisplayToolBarItem-base.IL.txt`，关键指令 `ldstr "Lang.DisplayToolBar."` + `call Lang.TryGet`）：

```
类型名: CompositionCorrectionDisplayToolBarItem
  → Key  = "CompositionCorrection"                        (Replace("DisplayToolBarItem",""))
  → Text = Lang.TryGet("Lang.DisplayToolBar.CompositionCorrection")
  → zh-CHS 资源 L43: "英文批改"   ← 按钮显示文案
```

因此 **UI 上该按钮名为「英文批改」**（不是「作文批改」，也不是「批改」总入口）。
英文资源 `en/EasiCamera.xaml` 缺该 key（`grep` 无匹配），英文界面会 fallback 为 Key 字符串。

### 3.3 全程序集只有这一个批改入口

`grep -la "CompositionCorrection" *.dll *.exe` → 仅 `EasiCamera.Api.dll` / `EasiCamera.UI.dll` / `EasiCamera.exe`：

- `EasiCamera.UI.dll`：
  - `CompositionCorrectionDisplayToolBarItem`（工具栏条目，把 `new ScanCompositionControl()` 加进 `EC.UiService.TheMainGrid`）；
  - `DisplayToolbar.UniversalUiItem_OnClick` 里一个 `is CompositionCorrectionDisplayToolBarItem` 类型判断（点击后恢复侧边栏状态）；
  - `ScanCompositionControl` / `CorrectionResultElement` 等**流程内**控件；
  - `Math CompositionCorrection` 相关的是 `GetOcrTextRequest`/结果模型字段，不是入口。
- `EasiCamera.Api.dll`：数据模型/接口（`CompositionCorrection`、`DisplayToolBarSortHints.CompositionCorrection=102`、`FunctionModule.CompositionCorrection`）。
- `EasiCamera.exe`：BAML 资源里的图标键（`Image.CompositionCorrection.*`）。

**没有任何 AIMenu**（`grep -la AIMenu` 全程序集无匹配）；没有 `IntelligentIdentification` / `StartAiRecognition` /
`OpenAIMenu` / `AiKeyTip` 等 4229/4419 的 AI 符号；没有 `WordCut`/`Homework`/「口算」「圈词」字符串。

### 3.4 点击后进入的是「英语作文批改」整条链路（无子菜单/无口算/无圈词）

`CompositionCorrectionDisplayToolBarItem..ctor` 的命令 = 创建 `ScanCompositionControl` 并隐藏侧边栏；
`ScanCompositionControl.StartRequest()`（IL 见 `il/07-ScanCompositionControl-StartRequest.IL.txt`）：

```
IEnglishCompositionProvider.GetOcrText(imageBase)                  // OCR 识别英文作文
IEnglishCompositionProvider.GetCorrectEnglishCompositionByTextResult(text)  // 英文作文批改
→ CorrectionResultElement / CorrectionResultImageElement
```

`EnglishCompositionProvider`（Business.dll）请求模型为 `CorrectEnglishCompositionByImageRequest` /
`CorrectEnglishCompositionByTextRequest`（英文作文批改云 OCR）；界面提示「请选择英文作文进行批改」
「希沃视频展台 · 英语作文智能批改」。**没有口算批改 / 英文圈词 / 学科选择的子命令。**

### 3.5 结论（语义定稿）

> **2.0.10.3816 不存在独立的「英文批改」子菜单或按钮，也不存在口算批改/英文圈词；`CompositionCorrection`
> 按钮的界面文案本身就是「英文批改」，点击即进入英语作文批改流程。**
> 因此 `remove_english` 移除 `CompositionCorrectionDisplayToolBarItem` 就是**精准地**移除「英文批改」入口，
> 覆盖该版本英文批改的全部 UI 路径（也是唯一路径）。

---

## 4. remove_english 补丁（核心）

### 4.1 目标方法

- 文件：`EasiCamera.UI.dll`
- 类型/方法：`EasiCamera.UI.CompositionCorrectionDisplayToolBarItem::.ctor`
- 元数据：RVA `0x11450`，方法体文件偏移 `0xF650`，fat header（12 字节），IL 起始文件偏移 `0xF65C`，`CodeSize=0x49`
- 原 IL 关键片段（完整见 [`il/01-remove_english-orig.IL.txt`](il/01-remove_english-orig.IL.txt)）：

```il
IL_0000: ldarg.0
IL_0001: ldc.i4.0
IL_0002: ldc.i4.0
IL_0003: call instance void EasiCamera.DisplayToolBarItem::.ctor(bool, ItemType)
IL_0008: ldarg.0
IL_0009: ldc.r8 102
IL_0012: call instance void EasiCamera.UiItem::set_SortHint(float64)
IL_0017: ldarg.0
IL_0018: ldc.i4.1                                   ← 补丁点：MainWindow(1)
IL_0019: call instance void EasiCamera.UiItem::set_FunctionModule(FunctionModule)
IL_001e: ldarg.0
...（构造 DelegateCommand，点击 = new ScanCompositionControl 加入 MainGrid）
IL_0048: ret
```

### 4.2 补丁

| 项目 | 值 |
|---|---|
| 文件偏移 | **`0xF674`**（= 0xF65C + IL_0018） |
| 原字节 `expected` | `17`（`ldc.i4.1`） |
| 补丁字节 `patched` | `16`（`ldc.i4.0`） |
| 长度 | 1 字节，等长替换；方法头 `CodeSize`/异常表/元数据**完全不变** |
| 效果 | `base.FunctionModule = FunctionModule.None`（`FunctionModule.MainWindow=1 → None=0`） |

### 4.3 为什么这样就「去除」了按钮

`InitDisplayToolBarUiItems` 仍会反射创建该条目（Key `CompositionCorrection` 在 `UiItemKeysGroup` 中，分组
`DefaultGroup+"2"`），但每次刷新集合时：

```csharp
// DisplayToolBarItemViewModel.RefreshUiItemState()
ImageUiItems ← CurrentFunctionUiItems.GetUiItems(DefaultGroup + "2")
             ← x.IsShowUiItem(functionModule)
             ← DisplayToolBarItem.IsShowUiItem: return (this.FunctionModule & functionModule) != 0;
// FunctionModule = None(0) → 0 & 任何值 == 0 → false → 条目永远不会被加入 ImageUiItems
```

即：**按钮/菜单项不被加入集合**（契约 §4 推荐做法之一），UI 上不再出现「英文批改」按钮，
其 `DelegateCommand` 也不会被任何 UI 触发。命令对象仍在、但不可达。

### 4.4 验证

- `verify_rules.py` 断言：`0xF674` 原字节为 `17`；应用后整文件 SHA-256 =
  `6adf10e8a545adae68a64dc13e0cd10645f4f079a7784238390054ce50268847`，大小仍为 749,568。
- 补丁后 ILSpy 反编译（依赖程序集齐备）：`base.FunctionModule = FunctionModule.None;`，结构合法
  （见 `il/02-remove_english-patched.IL.txt`、`il/08-decompiled/CompositionCorrectionDisplayToolBarItem.patched.cs.txt`）。

---

## 5. force_scan 补丁（额外补齐）

### 5.1 目标

- 文件/类型/方法：`EasiCamera.UI.dll`，`EasiCamera.UI.ImageEnhanceDisplayToolBarItem::.ctor`
- RVA `0x11334`，方法体文件偏移 `0xF534`，fat header 12 字节，IL 起始 `0xF540`，`CodeSize=0xB2`
- 原 IL：`IL_001e..IL_0071`（**84 字节**）为「自动扫描」按钮 Visibility 白名单绑定：

```
newobj Binding
  set_Path "Camera"; set_Source DeviceViewModel.MainPreViewElement
  set_Converter SeewoCameraButtonVisibilityConverter
  set_ConverterParameter 43100 (0x1A85C = SC03|SC05|SC07|SC03C|SC06|SC07E|SC07F)
  stloc.0
ldarg.0; ldsfld DisplayToolBarItem.VisibilityProperty; ldloc.0; call BindingOperations.SetBinding; pop
```

### 5.2 补丁

| 项目 | 值 |
|---|---|
| 文件偏移 | **`0xF55E`**（= 0xF540 + IL_001e） |
| 长度 | **84 字节**，等长替换 |
| 原字节 `expected` | `73af02000a2572c12600701473c100000a6fb002000a25289101000a6ff901000a6f5e02000a6fda02000a2573780300066fb102000a25205ca800008c070100016f8404000a0a027e8504000a0628b302000a26` |
| 补丁字节 `patched` | `00` × 84（全部 NOP） |
| 效果 | 不再设置 Visibility 绑定 → `DisplayToolBarItem.Visibility` 依赖属性默认值 `Visible` → 「自动扫描」按钮对任何摄像头常显（第三方展台可用） |

后续 `IL_0072` 起的 `IsCanClickDisabled`（当前页面）绑定保留不动；方法头/locals/异常表不变。

**风险**：无摄像头时按钮也会显示，点击可能无响应/内部异常（该补丁本意是接入第三方展台时使用）。
补丁后 SHA-256 = `2678df7291053b8555b1e894b1968c7a45b16b468544f69c869c060259ec1508`；
与 remove_english 同时应用 = `84df05d7ddbd3eef2a2642349c5ad3b75d3ca89ad1fe1704c134e725368e6216`。

> 说明：上游 4419 的同类补丁是替换为常量 `Visibility=Visible`（`callvirt set_Visibility`）。3816 的
> `EasiCamera.UI.dll` 中没有指向 `DisplayToolBarItem::set_Visibility` 的 MemberRef（唯一 `set_Visibility`
> MemberRef 属于 `UIElement`，而 `DisplayToolBarItem` 继承自 `DependencyObject`，不能调用 UIElement 方法），
> 因此采用更稳妥的「NOP 掉绑定，依赖 DP 默认 Visible」方案，避免引入无效/越权的成员引用。

---

## 6. 其余 6 项功能排查结论（摘要）

| 功能 | 可用性 | 原因（证据见 [`availability.md`](availability.md) / `il/10-assembly-symbol-evidence.txt`） |
|---|---|---|
| `remove_english` | ✅ | 本文件 §3/§4 |
| `force_scan` | ✅ | 本文件 §5 |
| `no_third_party_block` | ❌ | 2.0.10 设备枚举 `GlobalDeviceViewModel._0001()` 加入全部物理摄像头，仅过滤名字含 `virtual` 的虚拟设备；无 `CancelShieldThirdParty` 云端开关（2.1.0 才引入） |
| `hide_login` | ❌ | 无 `ProfileButton`/登录账号代码；本地化只有 `Lang.Update.Login`（更新提示「请登录」），主界面/工具栏无登录入口 |
| `disable_freeze` | ❌ | 无 `Win32_Processor`/`ProcessorNameString`/`zhaoxin` 等国产化识别；`ECCommands.FreezeCamera` 只是手动「画面锁定」 |
| `enable_hygon_freeze` | ❌ | 无 `IsHomeMaidChip`/`HomeMaid`；本版本 `HardwareRecognizer` 是 USB MCU/IWB 设备识别（`iwb.txt`/McuHunter），与 4229/4419 的芯片识别同名不同物 |
| `remove_ocr` | ❌ | 无 OCR/「智能识别」入口（无 `IntelligentIdentification`/`AIMenu`/`StartAiRecognition`）；AI 批改在此版本只有「英文批改」按钮，由 `remove_english` 覆盖 |
| `disable_ai_key` | ❌ | HID 处理 `CommonHidComponent.DataProcess` 只解析 `cmd=1/2/3/4/5/6`（按键 1–5、灯、触摸灯、心跳、补光灯键、MCU），没有 AI 键（cmd 13）分支 |

---

## 7. 功能可用性矩阵

| feature id | 3816 可用 | RULES 中 | 补丁文件/偏移 | 说明 |
|---|---|---|---|---|
| `remove_english` | ✅ | 有 | UI.dll `0xF674` `17→16` | 隐藏「英文批改」工具栏按钮（唯一批改入口） |
| `force_scan` | ✅ | 有 | UI.dll `0xF55E` 84 字节 NOP | 「自动扫描」按钮常显，第三方展台可用 |
| `no_third_party_block` | ❌ | `unavailable_reason` | – | 无该限制逻辑 |
| `hide_login` | ❌ | `unavailable_reason` | – | 无登录入口 |
| `disable_freeze` | ❌ | `unavailable_reason` | – | 无国产化自动冻结 |
| `enable_hygon_freeze` | ❌ | `unavailable_reason` | – | 无 HomeMaid 冻结链路 |
| `remove_ocr` | ❌ | `unavailable_reason` | – | 无 OCR/智能识别入口 |
| `disable_ai_key` | ❌ | `unavailable_reason` | – | 无 AI 按键 cmd 13 分支 |

---

## 8. 验证（摘要，详见 [`verify.md`](verify.md)）

- 规则文件：`InspireCameraTools/core/rules/v2_0_10_3816.py`（只导出 `RULES`）。
- 自动校验：`python analysis/3816/verify_rules.py` → **全部 PASS**（原版指纹 → 应用 RULES → 等长/差异区间/
  补丁后哈希/幂等性/回读哈希）；`--ilspy` 加做补丁后程序集完整反编译与结构断言。
- 真实引擎（patch-core）：`python -m core.cli validate/detect/list/plan/apply/restore` 全链路在
  `work/re3816/Main` 副本实测通过（apply → 哈希 84df05… → 重复 apply 幂等 → restore 还原 f65b7a81…）。
- 补丁后哈希与 ILSpy 输出见 §4.4/§5.2 与 `analysis/3816/verify_rules.log.txt`、`cli_roundtrip.log.txt`。

## 9. 风险与未验证项

1. **未在真机/真展台验证**：按钮隐藏属于静态 UI 逻辑（FunctionModule 过滤），逻辑上确定，但未经实际运行确认。
2. `force_scan` 后无摄像头时按钮仍显示，点击可能无响应/异常（见 §5.2）；本功能预期只在接第三方展台时使用。
3. 补丁只隐藏 UI 入口，不删除云 OCR 调用代码；若通过其它非常规手段（如调试器直接实例化控件）仍可进入批改流程。
4. 升级/修复安装会覆盖 DLL，需要重新打补丁（引擎按原版哈希识别，升级后需重新检测）。
5. **未做 JIT/CLR 加载级验证**：本机仅有 .NET 8 运行时（无 .NET Framework 4.8 编译环境），以
   「ILSpy 完整反编译 + 方法头/长度不变 + 引擎逐字节校验」作为合法性证据；两处改动均为「1 字节常量替换」与
   「整段 NOP」，不改变栈平衡/分支目标/异常表。

## 10. 复现

```bash
cd D:/开发/SeewoCamera
# 1) 规则自动校验（读原版 → 应用 → 断言字节/哈希；不写原版）
D:/Software/python314/python.exe analysis/3816/verify_rules.py
# 2) 附带 ILSpy 结构校验
D:/Software/python314/python.exe analysis/3816/verify_rules.py --ilspy
# 3) 引擎 CLI（在 InspireCameraTools/ 下）
cd InspireCameraTools
D:/Software/python314/python.exe -m core.cli validate --json
D:/Software/python314/python.exe -m core.cli detect --main ../extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main --json
# 自测请在 Main 副本上：cp -r ... ../work/re3816/Main 后
D:/Software/python314/python.exe -m core.cli apply --main ../work/re3816/Main --features remove_english,force_scan --json
```

## 11. 交付物

| 路径 | 内容 |
|---|---|
| `InspireCameraTools/core/rules/v2_0_10_3816.py` | 版本规则（只导出 `RULES`，含 `remove_english`/`force_scan` 与 6 项 unavailable_reason） |
| `analysis/3816/README.md` | 本文件（定位过程/IL 证据/补丁原理/风险） |
| `analysis/3816/verify.md` | 偏移·原字节·补丁字节表、补丁后 SHA-256、验证记录 |
| `analysis/3816/availability.md` | 8 功能可用性矩阵与逐项证据 |
| `analysis/3816/verify_rules.py` | 自动校验脚本（可重复；`--ilspy` 可选） |
| `analysis/3816/il/` | IL 反照（原版/补丁后）、反编译源码、本地化 key、全程序集符号取证 |
| `analysis/3816/verify_rules.log.txt`、`cli_roundtrip.log.txt` | 实际验证输出日志 |
| `work/re3816/` | 分析/验证工作区（Main 副本、脚本、补丁产物；非交付接口） |
