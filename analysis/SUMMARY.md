# 项目总结 / 集成验收报告（Lead）

日期：2026-11-14 · 工作目录：`D:\开发\SeewoCamera` · 执行方式：DSH Agent Teams（1 Lead + 4 队员）

## 一、用户 5 项任务完成情况

| # | 任务 | 状态 | 交付物/证据 |
|---|---|---|---|
| 1 | 安装 DSH-REA 插件 | ✅ 已安装、运行时已供给、**已热加载并连接**（229 个 `mcp__rea__*` 工具） | [dsh-rea-install.md](dsh-rea-install.md)；`mcp__rea__binary_session` 返回 rea-agents 6.8.0 + Ghidra 12.1.4 + JDK 21 provider 全绿 |
| 2 | 克隆 `XiaoYangTech/seewo-easicamera-analysis` | ✅ | `seewo-easicamera-analysis/`（git 工作区干净，HEAD `8d181f1`；GitHub 经本地代理 127.0.0.1:7897 克隆） |
| 3 | 逆向 `EasiCamera_(20240912161108).exe`（=2.0.10.4087），补丁增加**去除 OCR 按钮** | ✅ | [rules/v2_0_10_4087.py](../InspireCameraTools/core/rules/v2_0_10_4087.py)；[analysis/4087/README.md](4087/README.md)；核心补丁 UI.dll 0x10CC9 `0x17→0x16`，补丁后 SHA-256 `b55847ff…` |
| 4 | 逆向 `EasiCameraSetup_2.0.10.3816.exe`，补丁增加**去除英文批改** | ✅ | [rules/v2_0_10_3816.py](../InspireCameraTools/core/rules/v2_0_10_3816.py)；[analysis/3816/README.md](3816/README.md)；核心补丁 UI.dll 0xF674 `0x17→0x16`，补丁后 SHA-256 `6adf10e8…` |
| 5 | Python+ttkbootstrap「亿方展台管家 InspireCameraTools」 | ✅ | `InspireCameraTools/`（7 页面 + 打包产物）；截图 [app-shots/](app-shots/) |

## 二、补丁能力矩阵（已实现并逐字节校验）

| feature | 3816 | 4087 | 4229 | 4419 |
|---|:-:|:-:|:-:|:-:|
| no_third_party_block 去除第三方展台限制 | — | — | — | ✓ |
| force_scan 去除扫描限制 | ✓ | ✓ | — | ✓ |
| hide_login 去除登录按钮 | — | ✓ | — | ✓ |
| disable_freeze 去除兆芯/海光锁画面 | — | — | — | ✓ |
| enable_hygon_freeze 海光锁画面（修复卡顿） | — | — | ✓ | — |
| remove_english 去除英文批改 | ✓ | ✓ | — | — |
| remove_ocr 去除 OCR | — | ✓ | ✓ | — |
| disable_ai_key 禁用 AI 按键 | — | ✓ | ✓ | — |

- 4 版本共 14 个可用补丁点；`—` 均经字符串/元数据/反编译证据判定该版本不存在对应逻辑，UI 置灰并给出原因。
- 规则格式（`analysis/CONTRACT.md` §3.2）：文件 + 偏移 + expected 原字节 + patched 字节，等长替换；应用前逐字节校验、任一失败整体不写盘；备份到 `<Main>\..\_InspirePatchBackup\<时间戳>`；支持恢复/幂等/已打补丁状态识别；原子写回+失败回滚。

## 三、验收证据（Lead 独立复核）

| 检查 | 结果 |
|---|---|
| 补丁引擎单测（patch-core 交付） | `Ran 49 tests, OK` |
| `python -m core.cli validate --json` | 4 版本规则 0 错误、`rule_load_errors: []` |
| `analysis/4087/verify_rules.py` | 47 项检查通过，exit 0 |
| `analysis/3816/verify_rules.py` | 29 PASS / 0 FAIL，exit 0 |
| `analysis/4229_4419/verify_rules.py` | 17 项校验 ALL PASS，exit 0 |
| Lead 独立 apply/restore（临时副本） | 4087 `remove_ocr` → UI.dll `b55847ff…`（符合预期）→ restore 回 `fcaa674b…`；3816 `remove_english` → UI.dll `6adf10e8…` |
| 4 版本 detect | 3816/4087/4229/4419 均正确识别（matched_files 2-3 个指纹） |
| 原始解包文件完整性 | 4 个版本关键 DLL SHA-256 全部与 `00-recon.md` 记录一致（含一次硬链接误写事故的还原复验） |
| 上游仓库 | `git status` 干净，未被修改 |
| app 源码/打包产物 `--smoke-test` | 均 3.6s 退出码 0 |
| app `--self-check` | 源码与 dist 均 SELF-CHECK OK（引擎 4 版本、14 补丁点、autoupdate、HID hid.dll/setupapi 绑定、22 个 HID 接口枚举、无展台优雅降级） |
| app 真实链路（app-dev 自测） | 4229 副本识别→应用→is_patched→恢复；swapp API 拉 50 个版本、完整下载 2.1.0.4419（142.6MB，SHA-256 与官方一致）、断点续传；autoupdate detect/apply/restore；4 类降级场景；125%/150% DPI 布局无越界 |
| 系统污染 | HKCU Run 无 InspireCameraTools 项；未安装/运行 EasiCamera；未改 hosts（本机原有 `local.id.seewo.com` 条目与本次无关） |

## 四、团队分工与产出

| 成员 | 任务 | 主要交付 |
|---|---|---|
| Lead | 侦察/契约/安装包下载解包/DSH-REA/集成验收/文档 | `analysis/CONTRACT.md`、`00-recon.md`、`dsh-rea-install.md`、`README.md`、本报告、最终验收 |
| re-4087-ocr | 2.0.10.4087 逆向 | 4087 规则（remove_ocr 等 5 项可用）、47 项自动校验、12 份 IL 证据、补丁后方法表逐方法核对（2286+880 方法 RVA/CodeSize 差异 0） |
| re-3816-en | 2.0.10.3816 逆向 | 3816 规则（remove_english、force_scan）、英文批改本地化证据链（`Lang.DisplayToolBar.CompositionCorrection=英文批改`）、29 项校验、20 份 IL/反编译证据 |
| patch-core | 补丁引擎 + 4229/4419 移植 + 破坏自动更新 | 引擎/CLI（契约 §3.3 全部实现）、4229/4419 规则（5 个 DLL 哈希与上游逐一一致）、`core/autoupdate.py`、49 个单测、更新链静态分析 |
| app-dev | 桌面应用 | 7 页面 UI、HID/下载/自启/配置模块、图标资源、PyInstaller 打包（41MB 单目录）、4 项降级、高 DPI 适配、多轮真实链路自测 |

## 五、风险与未验证项（如实记录）

1. **全部补丁未在真机/真实展台验证**（本机无展台硬件，按约束未安装/运行 EasiCamera）；界面效果、第三方展台扫描成像、登录按钮实际消失等需真机确认。
2. OCR/英文批改等采用「工具栏项 FunctionModule=0 过滤式隐藏」：静态 IL 核对 + 补丁后 ILSpy 全量反编译成功、方法体等长/方法表不变；若官方改渲染/收集逻辑需重新定位。
3. `force_scan` 后无摄像头时扫描按钮也会显示，点击可能无响应（规则注释与文档已注明）。
4. 软件升级/修复安装会覆盖补丁 DLL、恢复更新器文件：需重跑一键补丁与破坏自动更新；手动双击官方安装包升级无法在不破坏系统的前提下彻底阻止。
5. 「破坏自动更新」管理员权限分支、真实 EasiCamera 安装场景未实测（本机未安装 EasiCamera，仅验证"未安装空操作"与接口）。
6. 历史版本下载依赖第三方站点签名直链，链接失效时需以站点/官方渠道为准。
7. 无真实展台：HID 灯控/按键监听按上游报告协议实现，未真机验证。
8. DSH-REA：Windows 上原生 macOS 工具不可用（插件正常限制）；REA 对 .NET 仅静态元数据/CIL（本项目的 .NET 深度反编译使用 ILSpy CLI，REA 作辅助与规范化证据）。

## 六、复现命令

```bat
REM 补丁引擎
cd InspireCameraTools
python -m unittest discover -s tests
python -m core.cli validate --json
python -m core.cli detect --main ..\extracted\v20240912161108\EasiCamera_2.0.10.4087\Main --json

REM 各版本静态校验
python ..\analysis\4087\verify_rules.py
python ..\analysis\3816\verify_rules.py
python ..\analysis\4229_4419\verify_rules.py

REM 应用
python main.py
python main.py --self-check
dist\InspireCameraTools\InspireCameraTools.exe
```

## 七、真机复现与修复记录（2026-11-14 晚，Lead）

用户在解包版 EasiCamera 2.1.0.4419 上实测「去除登录按钮」反馈：按钮没去掉，只去掉了文字。
本机启动解包版 EasiCamera 复现并修复：

1. **根因**：上游 `hide_login` 只在 `DisplayToolbar..ctor` 把 `ProfileButton.Visibility` 设为 Collapsed；
   但 `BoardApiOnFunctionModuleChanged` 在模块切换（启动即发生）时按 `FunctionModule.MainWindow` 重新设为 Visible，
   导致按钮恢复显示。UIA 探针实测补丁后 `ProfileButton` 仍为可见（rect 222,1014,72,60）。
2. **修复**：2.1.0.4419 规则追加第二处 1 字节 IL 补丁（UI.dll 0x1EE0C, `0x17→0x16`：可见性标志恒 false）。
   修复后 UIA 探针 `ProfileButton` 变为 Collapsed/离屏，工具栏自动重排无空洞；
   证据：`analysis/capture-trigger/login-fix-compare.png`（前后对比）、`login-4419-patched.png`、`login-4419b-patched.png`、`probe-*.json`。
3. 2.0.10.4087 规则原本就含 ctor + flag 两处补丁，真机复现同样彻底隐藏（`login-4087-unpatched.png` vs `login-4087-patched.png`）。
4. 受影响哈希已同步更新：`hide_login` 单打 `0e7fc83e…`、`hide_login+force_scan` `8e900aaa…`；
   `verify_rules.py`/`verify.md`/单元测试/规则文档全部更新，59 个单测 + 3 个版本校验脚本全通过。

同时「一键相机」按用户要求改为**不依赖键盘快捷键**：通过 UI Automation 直接 Invoke EasiCamera「拍照」按钮
（= 机身拍照键最终执行的 `ECCommands.CaptureImage`）。真实 EasiCamera 进程实测：
`EasiCameraTrigger.exe capture --dry-run` 找到「拍照」按钮（Raw 视图 TextBlock→按钮祖先），`capture` 返回 `uia-invoke` 成功。
不写 HID、不与希沃进程抢设备；Remoting（Guardian 同款通道）经分析有 25 秒门控，仅作诊断备用。
详见 `analysis/capture-trigger/README.md`。应用版本升至 1.0.1 并重新打包。

## 八、1.0.1 后续反馈修复（2026-11-14 晚）

1. **删除一键相机"兜底快捷键"**：EasiCamera 没有拍照快捷键，该兜底无意义。
   `app/camera_page.py` 移除目标按键下拉框、按键校验、失败回退 SendInput 逻辑与相关说明；
   一键相机页现在只有「防抖 / 开机自启 / 检测拍照按钮」，拍照触发唯一路径为 UI 自动化点击「拍照」按钮。
2. **修复「手动粘贴目录后应用按钮不亮」**：补丁页原先只在「浏览…/自动探测/重新检测」时触发检测，
   输入框粘贴没有任何事件绑定，`_detected` 始终为空 → 应用按钮置灰。
   修复（`app/patch_page.py`）：
   - 输入框绑定 `StringVar` 写入事件（450ms 防抖）+ `<Return>` + `<FocusOut>`，粘贴/输入后自动检测；
   - 新增 `normalize_main_dir_input()`：兼容带引号、尾部反斜杠、正斜杠、`file:///`、exe 文件路径、
     版本目录、安装根目录、Main 目录（自动定位到含 `EasiCamera.exe` + `EasiCamera.UI.dll` 的 Main）；
   - 新增输入提示文案；检测成功后自动填充规范化路径，避免重复检测。
   - 验证：真实 UI 粘贴 `...\EasiCamera_2.1.0.4419\Main` → 自动识别 V2.1.0.4419、3 项默认勾选、
     「应用所选补丁」按钮变为可用（截图 `analysis/app-shots/paste-after.png`）；
   - 新增 `tests/test_patch_paths.py`（9 个路径规整用例），全套 68 个单测通过；重新打包并验证 smoke/self-check。


## 九、亿方智云接入（2026-11-14）

按 `D:\开发\InspireWorksCloud\docspi-reference.md` 接入 `slug=ict`，范围仅：匿名上报 `client_ping`、
启动弹窗公告 `popup`、传统手动更新 `app_info`（不接 `app_update` 自动更新）。

- `core/cloud.py`：请求封装（4s/8s 超时、异常静默）、设备标识（`le_`+32hex 持久化）、上报循环（启动后一次 + 每 8 分钟）、
  弹窗本地去重（每日一次）、版本比较（忽略 v 前缀按段比较）、更新提示文案。
- `app/app_window.py`：启动 1.2s 后后台拉公告/版本 → 自定义模态对话框（公告「今日不再显示」、更新「前往下载/跳过此版本」）；
  上报线程随窗口关闭停止；`smoke-test` 下不联网。
- `app/settings_page.py`：新增「亿方智云（更新与公告）」卡片（当前/最新版本、匿名统计开关、设备标识、检查更新按钮）。
- 实测（2026-11-14）：`app_info` 返回应用 id=5/name=亿方展台管家/slug=ict（暂无版本记录）；`popup`、`announcements` 空；
  `client_ping` 返回 `online:true`。
- 测试：新增 `tests/test_cloud.py` 13 个离线用例；全套 81 个单测通过；应用自检/打包 smoke 通过。
- 版本升至 **1.1.0**。


## 十、v1.1.1 用户反馈修复（2026-11-14）

1. 设置页「亿方智云」卡片删除 API 地址文本、删除匿名上报开关（匿名上报固定启用）；
2. 匿名设备标识前缀改为 `ict_`（旧 `le_` 标识自动迁移重新生成，符合文档 `^[A-Za-z0-9_-]{16,100}$`）；
3. 修复界面滚轮：`app/common.py::ScrollFrame` 由 `<Enter>` + `bind_all` 改为递归给内容区全部子控件绑定 `<MouseWheel>`（内容变化自动重绑），
   解决「不先拖滚动条滚轮就无效」的问题；在进程内验证 125 个控件已绑定、滚轮事件可立即滚动，且跳过 Text/Listbox/Treeview 保留其原生滚动；
4. 版本升至 **1.1.1**，重新打包并重新发布 GitHub / CNB Release（附 zip + SHA256SUMS）。
