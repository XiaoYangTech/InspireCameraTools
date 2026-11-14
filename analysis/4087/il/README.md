# IL 证据索引（EasiCamera 2.0.10.4087）

本目录保存补丁定位与验证的 IL/反编译证据摘录。完整 IL 文本较大（UI.dll 约 5.8MB），
保存在工作副本 `work/re4087/il/`（不入库），本目录只保留方法级摘录。

## 原版 / 补丁后 IL（ILSpy 9.1.0.7988 `-il` 输出，GBK 已转 UTF-8）

| 文件 | 方法 | 说明 |
|---|---|---|
| `AIMenuDisplayToolBarItem_ctor.orig.il.txt` | `EasiCamera.UI.AIMenuDisplayToolBarItem::.ctor`（RVA 0x12AC8） | 原版：`IL_0018: ldc.i4.1` → `FunctionModule = MainWindow` |
| `AIMenuDisplayToolBarItem_ctor.patched.il.txt` | 同上 | 补丁后：`IL_0018: ldc.i4.0` → `FunctionModule = None`（remove_ocr） |
| `DisplayToolbar_ctor_tail.orig.il.txt` | `EasiCamera.UI.DisplayToolbar::.ctor` 尾部（RVA 0x2039C，IL_01B0 起） | 原版：`ProfileButton.DataContext = EC.Account` |
| `DisplayToolbar_ctor_tail.patched.il.txt` | 同上 | 补丁后：`ProfileButton.Visibility = Collapsed`（hide_login #1） |
| `DisplayToolbar_BoardApiOnFunctionModuleChanged.orig.il.txt` | `DisplayToolbar::BoardApiOnFunctionModuleChanged`（RVA 0x20614） | 原版：`IL_009C: ldc.i4.1`（flag = 是否显示登录按钮） |
| `DisplayToolbar_BoardApiOnFunctionModuleChanged.patched.il.txt` | 同上 | 补丁后：`IL_009C: ldc.i4.0` → flag 恒 false（hide_login #2） |
| `ImageEnhanceDisplayToolBarItem_ctor.orig.il.txt` | `EasiCamera.UI.ImageEnhanceDisplayToolBarItem::.ctor`（RVA 0x129AC） | 原版：Visibility 绑定 + `SeewoCameraButtonVisibilityConverter` + 掩码 108636 |
| `ImageEnhanceDisplayToolBarItem_ctor.patched.il.txt` | 同上 | 补丁后：84B 绑定构造替换为 `SetValue(VisibilityProperty, Visible)` + nop（force_scan） |
| `AIMenu_Connect.orig.il.txt` | `EasiCamera.UI.AIMenu::IComponentConnector.Connect`（RVA 0x17324） | 原版：case 2 `CompositionCorrectionButton.Click += …` |
| `AIMenu_Connect.patched.il.txt` | 同上 | 补丁后：`Visibility = Collapsed; ret`（remove_english） |
| `CommonHidComponent_DataProcess_cmd13.orig.il.txt` | `EasiCamera.Business.CommonHidComponent::DataProcess` 尾部（RVA 0x2CE8） | 原版：cmd 13 → `call ECCommands.get_OpenAIMenu` |
| `CommonHidComponent_DataProcess_cmd13.patched.il.txt` | 同上 | 补丁后：`ldnull` → 判空直接返回（disable_ai_key） |

## 补丁后反编译（C#，来自完整依赖的 Main 副本）

| 文件 | 说明 |
|---|---|
| [decompiled_patched/AIMenuDisplayToolBarItem.ctor.cs](decompiled_patched/AIMenuDisplayToolBarItem.ctor.cs) | `FunctionModule = (FunctionModule)0`（None） |
| [decompiled_patched/ImageEnhanceDisplayToolBarItem.ctor.cs](decompiled_patched/ImageEnhanceDisplayToolBarItem.ctor.cs) | `SetValue(VisibilityProperty, Visibility.Visible)`，原绑定已移除 |
| [decompiled_patched/AIMenu.Connect.cs](decompiled_patched/AIMenu.Connect.cs) | case 2：`CompositionCorrectionButton.Visibility = Visibility.Collapsed` |
| [decompiled_patched/DisplayToolbar.ctor_tail.cs](decompiled_patched/DisplayToolbar.ctor_tail.cs) | 构造函数末尾 `ProfileButton.Visibility = Visibility.Collapsed` |
| [decompiled_patched/DisplayToolbar.BoardApiOnFunctionModuleChanged.cs](decompiled_patched/DisplayToolbar.BoardApiOnFunctionModuleChanged.cs) | `flag = … && false` → 恒 Collapsed |
| [decompiled_patched/CommonHidComponent.DataProcess_tail.cs](decompiled_patched/CommonHidComponent.DataProcess_tail.cs) | cmd 13 分支 `((ICommand)null)?.Execute(null)` |

## 结构验证

| 文件 | 说明 |
|---|---|
| [method_table_check.md](method_table_check.md) | 原版 vs 补丁后方法表对比：RVA/Header/CodeSize 差异 0（UI 2286、Business 880 个方法） |

## 复现

- IL 提取：`work/re4087/tools/il2utf8.py`（GBK→UTF-8）、`work/re4087/tools/extract_il_evidence.py`；
- 方法元信息（RVA/Header/CodeSize）：`work/re4087/tools/ilmeta.py`；
- 反编译：`dotnet .tools/ilspycmd/ilspycmd.dll <dll> -il` / `-t <类型>`。
