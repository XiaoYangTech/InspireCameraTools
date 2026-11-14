# 4229 / 4419 规则验证记录

> 对应契约 §3.4 的 4 条验证要求：
> ① 原字节与整文件 SHA-256 记录；② ILSpy 对补丁后程序集反编译确认结构合法；
> ③ 自动化校验脚本 `verify_rules.py`；④ 明确标注“未在真机验证”。

## 0. 环境与结论

- 验证时间：2026-11-14；环境：Windows 11 + Python 3.14（`D:/Software/python314/python.exe`）+ ILSpy 9.1.0 CLI
- 安装包来自 swapp 官方历史版本 API（见 `README.md` §2），解包目录：
  - `extracted/v2.0.10.4229/EasiCamera_2.0.10.4229/Main/`
  - `extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/Main/`
- **结论：5 个目标 DLL 的原版 SHA-256 与上游脚本内置期望值全部一致；按 RULES 应用后的
  单功能/组合补丁 SHA-256 与上游脚本内置值全部一致；补丁后程序集 ILSpy 反编译正常，
  目标方法 IL 与预期语义一致。**
- **未在真机/真展台验证**：本机无展台硬件，也未安装/运行 EasiCamera。

## 1. 自动化校验脚本

```bash
D:/Software/python314/python.exe analysis/4229_4419/verify_rules.py
```

脚本行为：`validate_rule` 校验规则格式 → 读原版 DLL 校验原版哈希 → 逐功能
`simulate_patch` 后断言补丁后哈希 → 断言同文件多功能的组合补丁哈希。
脚本输出（本次运行）：

```
版本 2.0.10.4229：规则格式通过；UI/Business/Util 原版哈希 OK；remove_ocr/disable_ai_key/
  enable_hygon_freeze 单功能补丁后哈希 OK；三文件组合补丁后哈希 OK
版本 2.1.0.4419：规则格式通过；UI/Business 原版哈希 OK；hide_login/force_scan/
  no_third_party_block/disable_freeze 单功能补丁后哈希 OK；两文件组合补丁后哈希 OK
共校验 17 项，失败 0 项 / 结果: ALL PASS
```

## 2. 原版文件哈希（版本识别与补丁前指纹校验）

见 `README.md` §3 表。补充：`EasiCamera.exe` FileVersion 分别为 `2.0.10.4229` / `2.1.0.4419`；
4419 的 `Main/EasiCameraGuardian.exe` SHA-256 为
`d58c7bdb0339abc2dcb0230af3c9b208b05a290b075ccab03f53e86b41a60511`，
与上游报告引用的同版本 Guardian 哈希一致（佐证安装包版本正确）。

## 3. 补丁操作表（RULES 中的 op）

### 3.1 2.0.10.4229

| 功能 | 文件 | 偏移 | 原字节 | 补丁字节 | 补丁后整文件 SHA-256 |
|---|---|---|---|---|---|
| `remove_ocr` | EasiCamera.UI.dll | 0x10CB9 | `027ec004000a0728b702000a26` | `02186fe801000a000000000000` | `fd8ec805cb10e9733ffd5fe122246a826f1e3d8cc5ed2765cb65f74b3f607f27` |
| `disable_ai_key` | EasiCamera.Business.dll | 0x187D | `28a700000a` | `1400000000` | `d6ef2173ae18dda68819ea91da0a4f0f46063e39a5951aea13ff94089220bf82` |
| `enable_hygon_freeze` | EasiCamera.Util.dll | 0x1A04 | `7f2d000004` | `172a000000` | `231efe7f4fd2a7d0d2e895440902ad3c3ebd83b53be3e7baed991cd2cc8d948d` |

三个文件互不影响，组合补丁后哈希与上表单功能一致（每个文件只有一个功能）。

### 3.2 2.1.0.4419

| 功能 | 文件 | 偏移 | 原字节 | 补丁字节 | 补丁后整文件 SHA-256 |
|---|---|---|---|---|---|
| `no_third_party_block` | EasiCamera.Business.dll | 0xCDBE | `2c17` | `2600` | `4e1ca8bacd5f798fd27e7f312c99830641d4f1d4247412cd680fd7372c01b8c2` |
| `disable_freeze` | EasiCamera.Business.dll | 0x42C9 | `2d01` | `262a` | `4f42886f8e026eeae95240b5f94baca5e89c8676e255fd4c5107001b5f4120c3` |
| `hide_login`（补丁点 1） | EasiCamera.UI.dll | 0x1ECB3 | `286303000a6fda01000a` | `186fea01000a00000000` | 见下 |
| `hide_login`（补丁点 2，2026-11-14 追加） | EasiCamera.UI.dll | 0x1EE0C | `17` | `16` | `0e7fc83e7b29f63c0c04766b2de33fb202b0eef599f5bb7525063cbb0aad3418` |
| `force_scan` | EasiCamera.UI.dll | 0x110A2 | 84 字节，见下 | `02166fea01000a` + 77×`00` | `0715d54b7f9d082b61bd1e47d5984cc64d38eba105c485c01ba23756c88087db` |

**组合补丁后整文件 SHA-256**（本引擎按 RULES 合并应用后计算）：

| 文件 | 组合（两个功能都打） |
|---|---|
| EasiCamera.UI.dll（hide_login + force_scan） | `8e900aaa3732672e8d3634e27732c1f3ff0112328f4aa2e35979dad43b0797c6` |
| EasiCamera.Business.dll（no_third_party_block + disable_freeze） | `63d3abff82c50b7c73f31a12d05c3a100b4540dac74d50917a7283901630d7a1` |

> `force_scan` 的上游脚本用 84 字节常量代码替换原 84 字节的 `newobj Binding … SetBinding`
> 序列（`new` 82 字节 + 前置 5 字节校验区）。上游脚本只校验前 5 字节
> （`73b502000a`），本规则把**完整 84 字节**原样写入 `expected`：
>
> ```
> 73b502000a2572c52b00701473c700000a6fb602000a25289701000a6fff01000a6f6402000a
> 6fe002000a2573e50300066fb702000a25205ca801008c700200016fce04000a0a027ec304000a
> 0628b902000a26
> ```
>
> `patched` = `02 16 6F EA 01 00 0A` + 77 个 `00`（`ldarg.0; ldc.i4.0; callvirt
> set_Visibility`，即 Visibility=Visible；其余为 NOP），整段等长替换。

## 4. ILSpy 反编译验证（契约 §3.4 第 2 条）

方法：把 RULES 应用到原版 DLL 的副本（`work/patchcore/ilverify/`，**不修改 extracted 原版**），
用 ILSpy CLI 分别输出原版/补丁后的 IL（`-il`），diff 定位变更方法；再用 `-p` 反编译工程确认
结构合法（无加载错误、目标类型/方法反编译正常）。

> 反编译全部使用：`dotnet .tools/ilspycmd/ilspycmd.dll -il <dll>` / `-p -o <目录> <dll>`。

### 4.1 4229 `EasiCamera.UI.dll` — `EasiCamera.UI.IntelligentIdentificationDisplayToolBarItem::.ctor`

- 变更：原来对 `VisibilityProperty` 调 `BindingOperations.SetBinding`（绑定到
  `IsShowIntelligentIdentification` + `IsShowIntelligentIdentificationToVisibilityConverter`），
  改为常量 `Collapsed`（枚举值 2）：

```
; 原版（方法 RVA 0x129d8 内）
IL_00d5: ldarg.0
IL_00d6: ldsfld class [WindowsBase]System.Windows.DependencyProperty [EasiCamera.Api]EasiCamera.DisplayToolBarItem::VisibilityProperty
IL_00db: ldloc.1
IL_00dc: call class [PresentationFramework]System.Windows.Data.BindingExpressionBase [PresentationFramework]System.Windows.Data.BindingOperations::SetBinding(...)
IL_00e1: pop

; 补丁后
IL_00d5: ldarg.0
IL_00d6: ldc.i4.2
IL_00d7: callvirt instance void [PresentationCore]System.Windows.UIElement::set_Visibility(valuetype [PresentationCore]System.Windows.Visibility)
IL_00dc: nop
...（共 6 个 nop）
```

反编译 C# 预览（`IntelligentIdentificationDisplayToolBarItem.cs`）：

```csharp
Binding binding2 = new Binding { Path = ..., Source = ..., Converter = new IsShowIntelligentIdentificationToVisibilityConverter() };
((UIElement)(object)this).Visibility = Visibility.Collapsed;   // ← 补丁点
if (EC.AppConfig.ConfigData.IsShowIntelligentIdentification) { ... }
```

### 4.2 4229 `EasiCamera.Business.dll` — `EasiCamera.Business.CommonHidComponent::DataProcess`

- 变更位置：HID 命令解析分支 `data[2]==1 && data[3]==13`（相机 AI 键）且 `data.Length>=7` 时，
  原来 `call ECCommands.get_OpenAIMenu()` 后 `ICommand.Execute(null)`；补丁把调用替换为
  `ldnull` + 4×`nop`，随后 `dup; brtrue.s` 判空后直接 `pop; ret`（不再执行 AI 菜单）。

```
; 原版
IL_03b4: ldloc.0
IL_03b5: ldc.i4.2
IL_03b6: ldelem.u1
IL_03b7: ldc.i4.s 13
IL_03b9: bne.un.s IL_03d1
IL_03bb: ldloc.0
IL_03bc: ldlen
IL_03bd: conv.i4
IL_03be: ldc.i4.7
IL_03bf: blt.s IL_03d1
IL_03c1: call class [System]System.Windows.Input.ICommand [EasiCamera.Api]EasiCamera.ECCommands::get_OpenAIMenu()

; 补丁后
IL_03c1: ldnull
IL_03c2: nop
IL_03c3: nop
IL_03c4: nop
IL_03c5: nop
IL_03c6: dup
IL_03c7: brtrue.s IL_03cb
IL_03c9: pop
IL_03ca: ret
IL_03cb: ldnull
IL_03cc: callvirt instance void [System]System.Windows.Input.ICommand::Execute(object)
IL_03d1: ret
```

### 4.3 4229 `EasiCamera.Util.dll` — `EasiCamera.Util.HardwareRecognizer::get_IsHomeMaidChip`

- 变更：`IsHomeMaidChip` 由读取 `Nullable<bool> _isHomeMaidChip`（仅兆芯识别）改为恒 `true`：

```
; 补丁后（RVA 0x37f8，CodeSize 44）
IL_0000: ldc.i4.1
IL_0001: ret
IL_0002: nop ×4
IL_0007: ...（原有判断逻辑保留为不可达代码）
```

### 4.4 4419 `EasiCamera.UI.dll` — `EasiCamera.UI.DisplayToolbar::.ctor`

- 变更：`ProfileButton.DataContext = EC.Account` → `ProfileButton.Visibility = Collapsed`：

```
; 原版
IL_01b5: ldarg.0
IL_01b6: ldfld class [Cvte.GurnetUI]Cvte.GurnetUI.Controls.Button EasiCamera.UI.DisplayToolbar::ProfileButton
IL_01bb: call class [EasiCamera.Api]EasiCamera.IAccountInfo [EasiCamera.Api]EasiCamera.EC::get_Account()
IL_01c0: callvirt instance void [PresentationFramework]System.Windows.FrameworkElement::set_DataContext(object)

; 补丁后
IL_01b5: ldarg.0
IL_01b6: ldfld class [Cvte.GurnetUI]Cvte.GurnetUI.Controls.Button EasiCamera.UI.DisplayToolbar::ProfileButton
IL_01bb: ldc.i4.2
IL_01bc: callvirt instance void [PresentationCore]System.Windows.UIElement::set_Visibility(valuetype [PresentationCore]System.Windows.Visibility)
IL_01c1: nop ×4
```

反编译 C# 预览（`EasiCamera.UI/DisplayToolbar.cs`）：

```csharp
((UIElement)(object)ProfileButton).Visibility = Visibility.Collapsed;   // ← 补丁点
```

### 4.5 4419 `EasiCamera.UI.dll` — `EasiCamera.UI.ImageEnhanceDisplayToolBarItem::.ctor`

- 变更：84 字节 `newobj Binding … SetBinding(VisibilityProperty, binding)` 整段替换为
  `ldarg.0; ldc.i4.0; set_Visibility`（Visible=0） + 77×NOP（等长替换）：

```
; 原版（片段）
IL_001e: newobj instance void [PresentationFramework]System.Windows.Data.Binding::.ctor()
IL_0023: dup
...
IL_004a: newobj instance void EasiCamera.UI.SeewoCameraButtonVisibilityConverter::.ctor()
IL_004f: callvirt instance void Binding::set_Converter(...)
IL_0054: dup
IL_0055: ldc.i4 108636                      ; SeewoCameraType 掩码白名单
IL_005a: box [EasiCamera.Api]EasiCamera.SeewoCameraType
IL_005f: callvirt instance void Binding::set_ConverterParameter(object)
IL_0064: stloc.0
IL_0065: ldarg.0
IL_0066: ldsfld ... DisplayToolBarItem::VisibilityProperty
IL_006b: ldloc.0
IL_006c: call BindingOperations::SetBinding(...)
IL_0071: pop

; 补丁后
IL_001e: ldarg.0
IL_001f: ldc.i4.0
IL_0020: callvirt instance void [PresentationCore]System.Windows.UIElement::set_Visibility(valuetype [PresentationCore]System.Windows.Visibility)
; 之后为 NOP 填充
```

### 4.6 4419 `EasiCamera.Business.dll` — 两处

`EasiCamera.Business.HomeMaidChipHandler::Initialize`（RVA 0x60B8）：
`brtrue.s`（芯片为国产化才继续初始化）→ `pop; ret`（无条件返回，取消自动冻结）：

```
; 原版
IL_0000: call bool [EasiCamera.Util]EasiCamera.Util.HardwareRecognizer::get_IsHomeMaidChip()
IL_0005: brtrue.s IL_0008

; 补丁后
IL_0000: call bool ...get_IsHomeMaidChip()
IL_0005: pop
IL_0006: ret
IL_0007: ret
```

`EasiCamera.Business.GlobalDeviceViewModel` 设备列表 lambda（RVA 0xEBA8，上游报告称
MethodDef 0x060002D5 / row 725）：
`get_CancelShieldThirdParty` 后的 `brfalse.s` → `pop; nop`，控制流无条件落入“加入设备列表”，
恢复第三方展台/普通 USB 摄像头：

```
; 原版
IL_0000: call class ...EC::get_CloudConfig()
IL_0005: callvirt instance bool ...ICloudConfigService::get_CancelShieldThirdParty()
IL_000a: brfalse.s IL_0023

; 补丁后
IL_000a: pop
IL_000b: nop
IL_000c: ldarg.0                     ; 继续执行“加入设备列表”
IL_0013: newobj ...CameraInfo::.ctor(...)
IL_001d: callvirt ...List`1<CameraInfo>::Add(!0)
IL_0022: ret
```

反编译 C# 预览（`EasiCamera.Business/GlobalDeviceViewModel.cs`）：
`_ = EC.CloudConfig.CancelShieldThirdParty;` 之后直接 `...CameraInfo` 加入列表。

## 5. 引擎级验证（全链路）

`InspireCameraTools/tests/test_patch_engine.py` 中真实规则用例（`TestRealRule4229` /
`TestRealRule4419`）在**临时目录副本**上执行：

1. 复制规则 `files` 中列出的原版 DLL 到临时 `Main/`；
2. `detect_version` → 版本识别正确；
3. `apply_patches` 应用全部可用功能 → 断言每个文件的组合补丁 SHA-256（见 §3 表）；
4. `is_patched` → 全部为 True；
5. `restore_backup` → 文件 SHA-256 恢复为原版，`is_patched` 全部 False。

运行结果（本次）：`Ran 49 tests ... OK`（含引擎合成夹具、真实规则、CLI、自动更新模块的测试）。

## 6. 上游 JIT 校验记录（引用）

上游报告 §7.3/§7.4/§7.6/§7.7 记录：上述补丁后的方法已用 .NET 4.8
`RuntimeHelpers.PrepareMethod` 做过 JIT 编译校验（32/64 位），IL 合法；**未在真实面板运行验证**。
本项目的验证在此基础上增加了：官方安装包原版哈希逐字节核对、规则格式校验、
补丁后整文件 SHA-256 断言、ILSpy 原版/补丁后 IL diff。

## 7. 未验证 / 风险

- 未在真机/真展台安装运行（无硬件，且按契约不安装 EasiCamera）。
- `force_scan` / `hide_login` 依赖 WPF `Visibility` 常量，还需真机确认按钮行为与布局不受影响。
- 4419 的 `disable_freeze` 与 `enable_hygon_freeze`（4229）是互斥方向的功能，规则按版本分别提供；
  在海光平台上效果需真机确认。
- AI/OCR 是否真正移除还取决于程序内部其它开关/权限（见上游报告 §7.1），本补丁只移除入口。

---

## 补充：`hide_login` 真机复现与修复（2026-11-14，本机运行解包版 EasiCamera）

用户反馈：应用 `hide_login` 后「登录按钮没去掉，只去掉了登录两个字」。
用解包版 EasiCamera 2.1.0.4419（`extracted/.../Main/EasiCamera.exe`）直接启动复现：

1. **旧补丁（仅上游 ctor 一处）**：UIA 探针仍发现 `Button "登录" / ProfileButton / rect=222,1014,72,60` 可见 → 未隐藏。
   根因：`DisplayToolbar.BoardApiOnFunctionModuleChanged` 会在功能模块切换时执行
   `profileButton.Visibility = (flag ? Visible : Collapsed)`，`FunctionModule.MainWindow` 时 `flag=true`，
   把构造函数里设好的 `Collapsed` 又改回 `Visible`（启动阶段即触发）。
2. **修复**：新增第二处补丁 `0x1EE0C: 0x17→0x16`（`flag` 恒为 false）。
   修复后 UIA 探针：`ProfileButton rect=-2147483648,...`（已 Collapsed/离屏），工具栏无空洞、布局自动重排；
   截图证据 `analysis/capture-trigger/login-4419-patched.png`（旧补丁，头像可见）与
   `analysis/capture-trigger/login-4419b-patched.png`（修复后，头像消失）。
3. 2.0.10.4087 的规则原本就包含两处补丁（ctor + `BoardApiOnFunctionModuleChanged` flag），
   真机复现同样验证为彻底隐藏（`login-4087-patched.png` / `probe-4087-patched.json`）。
4. 更新后的哈希：`hide_login` 单打 `0e7fc83e…`；`hide_login+force_scan` `8e900aaa…`
   （`verify_rules.py` / `verify.md` 上表已同步）。
