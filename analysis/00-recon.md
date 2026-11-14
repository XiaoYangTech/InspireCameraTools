# 00 侦查结论（Lead 维护）

## 环境
- 工作目录：`D:\开发\SeewoCamera`；D 盘剩余 ~45GB，C 盘 ~5.6GB（勿写 C）
- Python 3.14：`D:\Software\python314\python.exe`；已装 `ttkbootstrap 1.20.2`、`requests 2.33.0`、`pillow 12.2.0`
- dotnet 运行时 8.0.23（无 SDK，但足够跑 ILSpy CLI）
- 工具：`.tools/ilspycmd/`（ILSpy 9.1.0.7988 CLI，`dotnet ilspycmd.dll`）、`.tools/7zip/7z.exe`（可解 NSIS）
- 网络：GitHub/npm 需代理 `http://127.0.0.1:7897`；seewo/swapp 直连；curl 访问 swapp API 需 `--ssl-no-revoke`
- 宿主：DeepSeek Harness 桌面版 0.2.1-rc.5（asar 内实现），插件系统 cordis，profile 在 `C:\Users\Admin\.dsh\profiles\desktop`；**禁止重启宿主**

## 目标安装包（已下载并解包）
| 版本 | 安装包 | 大小 | SHA-256(安装包) | 解包目录 | Main 目录 |
|---|---|---|---|---|---|
| 2.0.10.4087 | `installers/EasiCamera_20240912161108.exe` | 141,016,888 | 待补 | `extracted/v20240912161108/EasiCamera_2.0.10.4087/` | `.../Main/` |
| 2.0.10.3816 | `installers/EasiCameraSetup_2.0.10.3816.exe` | 140,148,216 | 待补 | `extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/` | `.../Main/` |

安装包均为 NSIS（7-Zip 解包出 391/279 个文件）。

## 关键程序集 SHA-256（原版，用于版本规则）
### 2.0.10.4087（Main/）
```
EasiCamera.exe             50ee51a7ee2527a31f82ed0aa0a3e407eed3107be09dc1f4fc5d898a4b453f36  1475200
EasiCamera.UI.dll          fcaa674bcc7567df87497d24305ae5e4207d3458ae68d29dd915d01d4a7c2443  1067008
EasiCamera.Business.dll    5345738297bb2e4a6cf7e1126ac8052641d331dbc39304cf40fadd2d54003fcd   260608
EasiCamera.Util.dll        35169cc0c3e19f98b3f4819c92f8a113becf7721aca9bda2d138bb41922ad65c    72192
EasiCamera.Api.dll         b0f804d3f88f96e716575e44a1a3c374a0aa1612d577d4c7f018afe3296a1a62   230400
EasiCamera.Control.dll     b98fad1391540a562db51a1f80af9c449dc8c8ac2d906d9f9a7e324ba2bbce2c    55296
EasiCamera.Communication.dll 53fc95db0c2d6048b0d21aaad9719f50bc5123869389311f61e22af6c6a8d350   54272
EasiCameraGuardian.exe     4f0583c2c42b4a5a93f70a893417b52083b61ee3d6551529255a831b080f01fe    80000
EasiCamera.UpdateFix.exe   010e0501a83d38c4fa9f034ec4e976ad7d3037d7d872437f9507636f47639a9a    42624
Cvte.EasiUI.dll            dd1fcc8e85c47f30ef9a2c0d2a41f49c54f458195ea45afe5e2d94eec523e0e8   876160
Cvte.GurnetUI.dll          d6251ccec981b5ed83746b167cd7db0a4a9bad2c6ea6a0225ac4d5db4b70fd7e   382080
Cvte.Paint.Shell.dll       2c063c48aa2c8d9ca7556635ea1609c70c29f67cd5080c68a084b688de31c42c  1400960
```
### 2.0.10.3816（Main/）
```
EasiCamera.exe             d482c73150ae5ad1995db46f0bd96b2ca346a45226d14ea81b4ade5ce1db34f8  1448064
EasiCamera.UI.dll          f65b7a81a3f23a766de3c775c4885cc0dd4c42d562e073764e795ca9f9ae61ef   749568
EasiCamera.Business.dll    2b8aa20512a5d19c2aa87280196caa6c45062b6aea1babe90107a3bd64b6823d  1778688
EasiCamera.Util.dll        5d4fe20d443c84e4729d3a5eed985be4fc9bda5184d6c951984f6beb2ef90f92    95744
EasiCamera.Api.dll         6376f2cc4cd7d3acfb1ad0942f5a484775b879dc73fdd7dd174ce834a5af8ff7   205824
EasiCamera.Control.dll     75cffd4188b25dd31ed2709c8ce1b9b0ad12a7d9bdede87c649fa330dfd6a01a    51712
EasiCamera.Communication.dll a6ae0ee03ba60eb2eba1c4a9e5358266c1039f29a06cf5ba2045312eb2520a63   51200
EasiCameraGuardian.exe     6cf2a1786101dc5dd245e3d8d6affb89c590128192eff877d96c2ddcae94cf83    72832
EasiCamera.UpdateFix.exe   9ca04ff4de7aa83b3d3e1defd1df53edbfaafc141dd70ad34932b1740c012441    42624
Cvte.EasiUI.dll            0dd8a5330ca8fe6d48cc43aa26359f4ca15706ef683cb4d18b619cd5307fd61b   831104
Cvte.Paint.Shell.dll       fa4a3bfa47d4e6e950c0d4b629a4a94b3e320d533450edbbb1a5dc74e44fd711  1340544
```
### 两版本差异要点（Lead 初步）
- 4087 有 `Cvte.GurnetUI.dll`（3816 无）、`libtensorflowlite_c.dll`、`libda_cropper.dll`（18.7MB）
- 3816 有 `libHexinPaper.dll`（9.7MB，学科/英文批改相关原生库）、`DirectShowLib-2005.dll`
- 3816 的 `EasiCamera.Business.dll` 1.78MB 远大于 4087 的 260KB，两版本架构差异大，规则不可互抄
- 定位批改/OCR 文案：`Main/Localizations/zh-CHS/*.yml`（两版本都有）

## 上游仓库要点（`seewo-easicamera-analysis/`）
- 报告 `docs/EasiCamera_分析报告.md`：HID 协议、VID/PID 白名单、登录/第三方展台限制、AI/OCR 入口、国产化冻结逻辑（2.1.0.4419 与 2.0.10.4229）
- 补丁脚本（字节级 IL 补丁 + SHA-256 校验）：
  - `tools/patch_4229_hide_ai.py`：4229 隐藏「智能识别」按钮（UI.dll, 偏移 0x10CB9）、屏蔽相机 AI 键（Business.dll, 偏移 0x187D）
  - `tools/patch_easicamera_ui.py`：4419 `--hide-login` / `--force-scan`
  - `tools/patch_easicamera_business.py`：4419 解除第三方展台限制（Business.dll 偏移 0xCDBE: `2C 17`→`26 00`）
  - `tools/patch_homemaid_freeze.py`：4419 `--disable-freeze`；4229 `--enable-freeze`
- `tools/SeewoCamProbe/SeewoCamProbe.cs`：HID/灯/补丁/芯片检测 C# 参考实现（app 的 HID 逻辑可对照）

## 安装包 SHA-256（补全）
```
fb67e9efc7e23288afde46b79578c7fc788c905c108d5d0067c4b8927de01ca9  EasiCamera_20240912161108.exe        (2.0.10.4087)
eb36ad62b9759374b8d46c94220945bd90c3181de826fee923f84dcc9f6dab76  EasiCameraSetup_2.0.10.3816.exe
8886210afd3035d8c72c489b19336dd2b0b31684ebe36560f0c7631063e44250  EasiCameraSetup_2.0.10.4229.exe
e358b1e7f688a27982e57b996725c0badaada8916395951c33bec88965ac1a07  EasiCameraSetup_2.1.0.4419.exe
```

## 补充版本（patch-core 已下载解包）
- 2.0.10.4229 → `extracted/v2.0.10.4229/EasiCamera_2.0.10.4229/Main/`；UI.dll SHA-256 与上游 4229 脚本期望值一致（2821c3a7…）
- 2.1.0.4419 → `extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/Main/`；Business.dll 与上游 4419 脚本期望值一致（37f77a24…）
- 因此 app 的补丁页可支持 4 个版本：3816 / 4087 / 4229 / 4419

## DSH-REA 插件安装记录（Lead）
- 宿主：DeepSeek Harness 桌面版 0.2.1-rc.5，cordis 插件系统，profile `desktop`
- 选择插件：`dsh-plugin-rea@2.0.18`（npm，作者 czcdr；把上游 REA MCP 接入 DSH，自动供给 Node/REA/JDK/Ghidra）
- 安装：profile 内 `pnpm add dsh-plugin-rea@2.0.18 --save-exact` → `package.json` → `dsh.profile.bundles` 追加 `dsh-plugin-rea`（HMR 已热加载，系统中已出现 `rea` MCP resource server）
- 供给：`node scripts/setup.mjs`（根目录 `C:\Users\Admin\.dsh\plugins\rea-bundle`，缓存 + vendor 约 1.5-2GB）→ 完成后需重启 DSH 使 mcp-rea 行连上
- 备份：`~/.dsh/profiles/desktop/.plugin-manager/backup-lead-<>/`（package.json/pnpm-lock/cordis*.yml）

## 待办侦察（Lead）
- DSH-REA setup 完成后清理 cache、验证 shim/bundle.json、确认 mcp 连接状态并记录
