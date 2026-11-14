# EasiCamera 2.0.10.4087 补丁验证记录（verify.md）

> 对应规则：[v2_0_10_4087.py](../../InspireCameraTools/core/rules/v2_0_10_4087.py)
> 校验脚本：[verify_rules.py](verify_rules.py)（可重复运行，只读原版文件）
> 结论：**字节级 / IL 级验证全部通过；未在真机运行 EasiCamera 验证**（项目约束：禁止安装/运行 EasiCamera）。

## 1. 原版文件（补丁前指纹）

| 文件 | 大小 | SHA-256 |
|---|---|---|
| EasiCamera.UI.dll | 1,067,008 | `fcaa674bcc7567df87497d24305ae5e4207d3458ae68d29dd915d01d4a7c2443` |
| EasiCamera.Business.dll | 260,608 | `5345738297bb2e4a6cf7e1126ac8052641d331dbc39304cf40fadd2d54003fcd` |
| EasiCamera.exe（仅版本识别） | 1,475,200 | `50ee51a7ee2527a31f82ed0aa0a3e407eed3107be09dc1f4fc5d898a4b453f36` |

## 2. 补丁点（原字节 → 补丁字节）

| 功能 | 文件 | 偏移 | 长度 | 原字节 | 补丁字节 |
|---|---|---|---|---|---|
| remove_ocr | EasiCamera.UI.dll | 0x10CC9 | 31 | `02161628a604000a0223000000000080594028a704000a021728a804000a2a` | `02161628a604000a0223000000000080594028a704000a021628a804000a2a` |
| hide_login | EasiCamera.UI.dll | 0x1E773 | 16 | `027b18040004285e03000a6fd601000a` | `027b18040004186fe601000a00000000` |
| hide_login | EasiCamera.UI.dll | 0x1E8BC | 4 | `170b2b02` | `160b2b02` |
| force_scan | EasiCamera.UI.dll | 0x10BD6 | 84 | `73b102000a2572172a00701473c300000a6fb202000a25289301000a6ffb01000a6f6002000a6fdc02000a2573cd0300066fb302000a25205ca801008c5c0200016fba04000a0a027ebb04000a0628b502000a26` | `027ebb04000a168c030100016f1001000a` + 67×`00` |
| remove_english | EasiCamera.UI.dll | 0x1556A | 24 | `027bce02000402fe06a804000673b601000a6f8602000a2a` | `027bce020004186fe601000a2a` + 11×`00` |
| disable_ai_key | EasiCamera.Business.dll | 0x12B5 | 5 | `288700000a` | `1400000000` |

规则内 `expected` / `patched` 与上表逐字节一致；同一文件内各功能 op 无重叠（引擎 `detect_overlaps` 通过）。

## 3. 补丁后文件 SHA-256

### 3.1 单功能

| 功能 | 文件 | 补丁后 SHA-256 |
|---|---|---|
| remove_ocr | EasiCamera.UI.dll | `b55847ff1427ea918ef95186c00e564ebe65ccba030c1637ce9135bdcb0985fa` |
| hide_login | EasiCamera.UI.dll | `791aeef8cf69eabfaa8b5fa9bd9a86e2f7ff037717f6d75324b6d61bbf2f7cc9` |
| force_scan | EasiCamera.UI.dll | `65e9bfcc5a514e6236a905c8c89006e14a9e2056a3adfa42a0fafadd7c6e83c0` |
| remove_english | EasiCamera.UI.dll | `ae1d8591cb7d85d4bbf590fdf3605fd38090924d87dbc6a72435f37a3727a968` |
| disable_ai_key | EasiCamera.Business.dll | `50a565decf9c7a847082cc6b6853deb06644ad65a6bc7c517e641aab315358a2` |

### 3.2 全部可用功能合并

| 文件 | 补丁后 SHA-256 |
|---|---|
| EasiCamera.UI.dll | `55e089394ef128ac297fe575b6eafda831890a522d1ff37a5645d4630acbdedd` |
| EasiCamera.Business.dll | `50a565decf9c7a847082cc6b6853deb06644ad65a6bc7c517e641aab315358a2` |

文件大小补丁前后不变（等长替换）。

## 4. 验证命令与结果

### 4.1 规则自动校验

```bash
cd D:/开发/SeewoCamera
D:/Software/python314/python.exe analysis/4087/verify_rules.py
```

结果：**47 项检查全部通过，退出码 0**（完整输出见 [verify_output.txt](verify_output.txt)）。检查项包括：

1. 规则版本号 / `validate_rule` 格式（hex、等长、文件指纹、功能 ID、op 重叠）；
2. 原版 3 个文件 SHA-256 指纹匹配；
3. 每个功能逐 op 断言 `expected` 原字节存在，补丁后区域等于 `patched`；
4. 5 个功能各自补丁后 SHA-256 = 3.1 表；
5. 全功能合并补丁后 SHA-256 = 3.2 表；
6. 幂等：对已补丁字节再次应用，结果不变；
7. 不可用功能均在 `unavailable_reason` 中给出原因。

### 4.2 补丁引擎全链路（副本验证，不动 extracted/ 原版）

```bash
cd InspireCameraTools
python -m core.cli detect --main "../extracted/v20240912161108/EasiCamera_2.0.10.4087/Main" --json
# → version = 2.0.10.4087（3/3 指纹文件匹配）

python -m core.cli list --version 2.0.10.4087 --json
# → 可用：remove_ocr / hide_login / force_scan / remove_english / disable_ai_key
# → 不可用：no_third_party_block / disable_freeze / enable_hygon_freeze（均带原因）

# 副本：work/re4087/main（由 extracted 原目录复制）
python -m core.cli apply --main <副本> --features remove_ocr,disable_ai_key,hide_login,force_scan,remove_english --json
# → ok=true，applied=5，备份目录 work/re4087/_InspirePatchBackup/<时间戳>/
# → 补丁后哈希 = 3.2 表（与内置期望完全一致）

# 已补丁判定 / 幂等
patch_engine.is_patched(<副本>)  # → 上述 5 项 True，其余 False
python -m core.cli apply --main <副本> --features ... --json
# → ok=true, message=所选功能均已应用，无需重复补丁（未写盘、无新备份）

# 恢复
python -m core.cli restore --main <副本> --backup <备份目录> --json
# → ok=true，2 个文件恢复，SHA-256 回到 1. 的原版值
```

原始 JSON 证据：[engine_selftest/](engine_selftest/)。

**部分补丁状态测试**（mini 目录，仅放 UI/Business/EasiCamera.exe 三个指纹文件）：

- 只应用 `remove_ocr` → 仍能 `detect` 为 2.0.10.4087（引擎会把已补丁字节回退后再比对原版哈希）；
  `is_patched` 精确报告 `{"remove_ocr": true}`；UI.dll SHA-256 = `b55847ff…`（与 3.1 单功能值一致）；
- 再补齐其余 4 个功能 → UI.dll = `55e08939…`、Business.dll = `50a565de…`（与 3.2 全功能值一致）。

### 4.3 ILSpy 复反编译（补丁后）

- 补丁后 UI.dll / Business.dll 放回**完整 Main 副本**（依赖齐全）后：
  - `ilspycmd -il` 全程序集反编译成功（UI 2286 / Business 880 个方法全部可解析）；
  - 逐方法比较 RVA / 方法头大小 / CodeSize：**差异 0** → 纯等长指令替换，元数据布局不变；
  - 目标方法反编译语义正确（摘录见 [il/decompiled_patched/](il/decompiled_patched/)）：
    - `AIMenuDisplayToolBarItem..ctor` → `FunctionModule = FunctionModule.None`
    - `ImageEnhanceDisplayToolBarItem..ctor` → `SetValue(DisplayToolBarItem.VisibilityProperty, Visibility.Visible)`
    - `AIMenu.Connect` case 2 → `CompositionCorrectionButton.Visibility = Visibility.Collapsed`
    - `DisplayToolbar..ctor` 末尾 → `ProfileButton.Visibility = Visibility.Collapsed`
    - `DisplayToolbar.BoardApiOnFunctionModuleChanged` → `flag = … && false`
    - `CommonHidComponent.DataProcess` cmd 13 → `((ICommand)null)?.Execute(null)`

## 5. 未验证项（明确声明）

1. **未在真机/EasiCamera 运行**：界面是否如预期不再出现 OCR 按钮、第三方展台扫描按钮是否出现、登录按钮是否消失、AI 按键是否无响应，均需真机确认。
2. 未验证自动更新/修复安装后补丁是否被回滚（升级会覆盖 DLL，需重打）。
3. `force_scan` 的实际扫描效果依赖第三方摄像头与现场光照，未评估。
4. `remove_ocr` 通过「工具栏项不属于任何功能模块 → 被列表过滤」实现，依赖 `GetUiItems` 的 FunctionModule 过滤逻辑；
   已在 IL 层核对，但未做运行期动态验证。
5. 登录/SSO 逻辑未改动（hide_login 仅隐藏入口）。
