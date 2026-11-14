# 2.0.10.3816 补丁字节表与验证记录

> 配套：规则 `InspireCameraTools/core/rules/v2_0_10_3816.py`；分析过程见 [`README.md`](README.md)。
> **未在真机/真展台验证。** 所有偏移为**原版文件绝对偏移**；`expected`/`patched` 等长。

## 1. 输入文件（原版，版本识别指纹）

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `EasiCamera.UI.dll` | 749,568 | `f65b7a81a3f23a766de3c775c4885cc0dd4c42d562e073764e795ca9f9ae61ef` |
| `EasiCamera.Business.dll` | 1,778,688 | `2b8aa20512a5d19c2aa87280196caa6c45062b6aea1babe90107a3bd64b6823d` |
| `EasiCamera.exe` | 1,448,064 | `d482c73150ae5ad1995db46f0bd96b2ca346a45226d14ea81b4ade5ce1db34f8` |

## 2. 补丁点明细

### 2.1 remove_english（去除英文批改）

| 项 | 值 |
|---|---|
| 文件 | `EasiCamera.UI.dll` |
| 类型/方法 | `EasiCamera.UI.CompositionCorrectionDisplayToolBarItem::.ctor` |
| 方法 RVA / 方法体偏移 / IL 起始 | `0x11450` / `0xF650`（12 字节 fat header）/ `0xF65C` |
| 文件偏移 | **`0xF674`**（IL_0018） |
| 原字节 `expected` | `17` |
| 补丁字节 `patched` | `16` |
| 长度 | 1 |
| IL 语义 | `ldc.i4.1`（FunctionModule.MainWindow=1）→ `ldc.i4.0`（FunctionModule.None=0） |
| 效果 | 工具栏「英文批改」按钮的 FunctionModule=None，`IsShowUiItem()` 恒 false，条目不再加入 `ImageUiItems`（按钮消失、命令不可达） |

### 2.2 force_scan（第三方展台可用扫描/文档增强）

| 项 | 值 |
|---|---|
| 文件 | `EasiCamera.UI.dll` |
| 类型/方法 | `EasiCamera.UI.ImageEnhanceDisplayToolBarItem::.ctor` |
| 方法 RVA / 方法体偏移 / IL 起始 | `0x11334` / `0xF534`（12 字节 fat header）/ `0xF540` |
| 文件偏移 | **`0xF55E`**（IL_001e） |
| 长度 | **84** |
| 原字节 `expected` | `73af02000a2572c12600701473c100000a6fb002000a25289101000a6ff901000a6f5e02000a6fda02000a2573780300066fb102000a25205ca800008c070100016f8404000a0a027e8504000a0628b302000a26` |
| 补丁字节 `patched` | `000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000`（84 个 `00`） |
| IL 语义 | 删除「Visibility = 白名单绑定（SeewoCameraButtonVisibilityConverter + 掩码 43100/0x1A85C）」序列 → 依赖属性默认 `Visible` |
| 效果 | 第三方展台/普通摄像头也显示「自动扫描」按钮（后续 IsCanClickDisabled 绑定保留） |

## 3. 补丁后文件 SHA-256（脚本断言值）

| 应用组合 | 文件 | 补丁后 SHA-256 | 大小 |
|---|---|---|---|
| `remove_english` | EasiCamera.UI.dll | `6adf10e8a545adae68a64dc13e0cd10645f4f079a7784238390054ce50268847` | 749,568 |
| `force_scan` | EasiCamera.UI.dll | `2678df7291053b8555b1e894b1968c7a45b16b468544f69c869c060259ec1508` | 749,568 |
| `remove_english` + `force_scan` | EasiCamera.UI.dll | `84df05d7ddbd3eef2a2642349c5ad3b75d3ca89ad1fe1704c134e725368e6216` | 749,568 |

上述值已由两条独立路径复算一致：

1. `core.patch_engine.simulate_patch()`（patch-core 引擎，内存应用）；
2. `analysis/3816/verify_rules.py`（本脚本内置最小应用逻辑，逐 op 校验 expected）。

## 4. 自动校验（`verify_rules.py`）

实际命令与完整输出见 [`verify_rules.log.txt`](verify_rules.log.txt)：

```bash
cd D:/开发/SeewoCamera
D:/Software/python314/python.exe analysis/3816/verify_rules.py --ilspy
```

校验项（全部 PASS）：

- 规则结构：`RULES.version=2.0.10.3816`；`files` 3 个指纹；引擎 `validate_rule()` 通过；同文件 op 无重叠。
- 原版指纹：3 个文件 SHA-256 与 `RULES.files` 完全一致（防止在非原版/已补丁文件上误操作）。
- 应用断言：三种组合（单功能 ×2、全功能）的补丁后 SHA-256 与 §3 表一致；文件大小不变；
  **差异只出现在 op 覆盖区间**（remove_english 1 处、force_scan 16 处、全功能 17 处）。
- 幂等：已是补丁状态时再次应用字节不变（逐功能 + 全功能）。
- 输出：补丁后 DLL 写入 `work/re3816/verify_out/` 并回读哈希。
- `--ilspy`：在硬链接依赖的临时 Main 目录里对补丁后 `EasiCamera.UI.dll` 做 `-p` 完整反编译，断言
  `CompositionCorrectionDisplayToolBarItem` 反编译出 `FunctionModule.None`、`ImageEnhanceDisplayToolBarItem`
  的 `VisibilityProperty` 绑定消失；并复查原版 3 个文件在该步骤后**未被修改**。

ILSpy 补丁后反编译关键输出（`work/re3816/verify_out/ilspy_patched_src/`）：

```csharp
// CompositionCorrectionDisplayToolBarItem（补丁后）
public CompositionCorrectionDisplayToolBarItem()
{
    base.SortHint = 102.0;
    base.FunctionModule = FunctionModule.None;   // ← 原为 FunctionModule.MainWindow
    base.Command = new DelegateCommand(delegate { ... });
}

// ImageEnhanceDisplayToolBarItem（补丁后）
public ImageEnhanceDisplayToolBarItem()
{
    base.SortHint = 101.0;
    base.FunctionModule = FunctionModule.MainWindow;
    Binding binding = new Binding { Path = new PropertyPath("CurrentSlide", null), Source = EC.BoardApi.Board,
                                    Converter = new SlideToButtonDisabledConverter() };
    BindingOperations.SetBinding(this, UiItem.IsCanClickDisabledProperty, binding);
}
```

## 5. 真实补丁引擎 CLI 自测（patch-core）

完整日志：[`cli_roundtrip.log.txt`](cli_roundtrip.log.txt)。测试目录为 `work/re3816/Main`（原版 Main 的副本；
**未对 extracted/ 原版执行 apply**）。

| 步骤 | 命令（在 `InspireCameraTools/` 下） | 结果 |
|---|---|---|
| 规则校验 | `python -m core.cli validate --json` | 3816 无错误 |
| 版本识别 | `python -m core.cli detect --main ../extracted/.../Main --json` | 识别为 `2.0.10.3816`，3/3 文件指纹命中 |
| 功能列表 | `python -m core.cli list --version 2.0.10.3816 --main ... --json` | 8 项：2 可用（remove_english/force_scan）+ 6 不可用（带中文原因） |
| dry-run | `python -m core.cli plan --main ../work/re3816/Main --features remove_english,force_scan --json` | 输出 2 个 op（0xF674 长度 1；0xF55E 长度 84），均 available |
| 应用 | `python -m core.cli apply --main ../work/re3816/Main --features remove_english,force_scan --json` | `ok=true`，备份目录 `work/re3816/_InspirePatchBackup/<ts>/`；打后哈希 `84df05d7…6216` |
| 补丁后识别 | `detect` / `is_patched` | 仍识别为 2.0.10.3816；`remove_english/force_scan=true` |
| 幂等 | 再次 `apply` | `已应用，无需重复补丁`，文件不变 |
| 还原 | `python -m core.cli restore --main ../work/re3816/Main --backup <ts> --json` | 还原后 SHA-256 回到 `f65b7a81…61ef`；`is_patched` 全部 False |

## 6. 事故与修复记录（原版文件保护）

- **现象**：`verify_rules.py --ilspy` 初版用 `os.link` 把原版 Main 的文件硬链接进临时目录，再
  `open("EasiCamera.UI.dll","wb")` 覆盖写补丁后内容 —— 硬链接共享 inode，写入**写穿**改到了
  `extracted/.../Main/EasiCamera.UI.dll`（内容变成两者合计补丁后的 `84df05d7…`）。
- **修复**：1) 恢复脚本 `work/re3816/recover_original.py` 按两个 op 反向写回原字节，恢复后 SHA-256 断言等于
  `f65b7a81a3f23a766de3c775c4885cc0dd4c42d562e073764e795ca9f9ae61ef`（**内容与原版逐字节一致**）；
  2) `verify_rules.py` 的 ILSpy 步骤改为「先 `os.unlink` 断开硬链接再写入」，并在步骤前后对原版 3 个文件做
  SHA-256 回归断言（已纳入 §4 校验项）；3) 清理所有硬链接临时目录。
- **影响**：`extracted/` 下仅 `EasiCamera.UI.dll` 的 **mtime** 发生变化，内容已还原为原版哈希；
  `EasiCamera.Business.dll` / `EasiCamera.exe` 等其它文件未被触碰（校验与 diff 均通过）。
- 教训：临时目录用硬链接做依赖解析时，**任何要写入的文件必须先 unlink 断链**，或直接复制。

## 7. 未验证项

1. 未在真实 EasiCamera 运行环境验证按钮消失/扫描按钮常显的实际表现（无展台硬件，且任务禁止运行安装 EasiCamera）。
2. 未做 .NET Framework CLR 加载 / `RuntimeHelpers.PrepareMethod` JIT 级验证（本机仅有 .NET 8 运行时，无
   csc/4.8 编译环境）；以 ILSpy 完整反编译 + 方法头不变 + 等长替换 + 引擎逐字节校验作为合法性依据。
3. 升级/修复安装覆盖 DLL 后需要重新打补丁。
