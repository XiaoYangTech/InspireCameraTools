# 亿方展台管家（InspireCameraTools）

> 希沃视频展台（EasiCamera）辅助工具箱：**一键补丁**、状态调试、历史版本下载、破坏自动更新、一键相机。
> 配套：希沃 EasiCamera 静态逆向分析记录（4 个版本）+ 可复现的字节级补丁规则 + Python/ttkbootstrap 桌面应用。

> ⚠️ **免责声明**：本项目与希沃（Seewo/CVTE）无关，仅供个人学习、兼容性研究与互操作使用；请勿用于绕过软件授权或商业分发。修改第三方软件可能违反其许可协议。所有补丁均**未在真机/真实展台上运行验证**（本机无展台硬件），请自行评估风险并在使用前备份安装目录。

---

## 下载

- **GitHub Releases**：<https://github.com/XiaoYangTech/InspireCameraTools/releases>
- **CNB Releases**：<https://cnb.cool/InspireWorks/InspireCameraTools/-/releases>
- **源码仓库**：[GitHub](https://github.com/XiaoYangTech/InspireCameraTools) · [CNB](https://cnb.cool/InspireWorks/InspireCameraTools)

当前版本 **v1.1.0**：`InspireCameraTools-1.1.0-win64.zip`（Windows 免安装单目录版，SHA-256 见同 Release 的 `SHA256SUMS.txt`）。

## 1. 目录结构

```
D:\开发\SeewoCamera
├── InspireCameraTools/          # ★ 桌面应用「亿方展台管家」（Python + ttkbootstrap）
│   ├── main.py                  # 入口（高 DPI、bootstrap-light、页面导航）
│   ├── app/                     # 7 个页面：主页/一键补丁/状态调试/历史版本下载/破坏自动更新/一键相机/设置关于
│   ├── core/                    # 补丁引擎、版本规则、HID、下载器、自启、自动更新阻断
│   ├── assets/                  # 自绘图标 + app.ico
│   ├── build/                   # PyInstaller 打包脚本
│   └── dist/                    # 打包产物（Windows exe）
├── analysis/                    # 逆向分析记录与契约
│   ├── CONTRACT.md              # 团队接口契约（规则格式/引擎 API/规范）
│   ├── 00-recon.md              # 环境、版本指纹、安装包哈希
│   ├── dsh-rea-install.md       # DSH-REA 插件安装记录
│   ├── 4087/ 3816/ 4229_4419/   # 各版本分析（README/verify/IL 证据/可用性矩阵）
│   └── app-shots/               # 应用页面截图
├── installers/                  # 官方安装包（4 个版本，仅本地分析用，不随仓库分发）
├── extracted/                   # 7-Zip 解包目录（Main\ 应用文件）
├── seewo-easicamera-analysis/   # 上游分析仓库（XiaoYangTech/seewo-easicamera-analysis）
└── .tools/                      # ILSpy CLI、7-Zip 等工具
```

## 2. 桌面应用

### 运行
```bat
REM 源码运行（依赖：ttkbootstrap、requests、pillow）
cd InspireCameraTools
python main.py

REM 打包产物
dist\InspireCameraTools\InspireCameraTools.exe
```
- Windows only；`bootstrap-light` 主题；启动时按系统 DPI 缩放（Per-Monitor v2 + tk scaling），1200×800 默认、支持缩放拖动。
- 无展台/未安装 EasiCamera/断网时均优雅降级（显示"未连接/未检测到"），不崩溃。

### 功能页面
| 页面 | 功能 |
|---|---|
| **主页** | 顶部展台状态卡片（连接/机型/VID-PID/灯状态/软件版本/补丁状态/MCU 版本）；下方 6 个功能图标入口 |
| **一键补丁** | 自动探测/手选 `Main` 目录 → 识别版本 → 8 项功能复选（不可用置灰+原因、风险提示）→ 应用/恢复备份；应用前检查 EasiCamera 进程 |
| **状态调试** | 展台 HID 设备枚举、开灯（亮度档）、关灯、查询灯态、触摸灯开/关/闪、原始帧日志、物理按键事件、心跳应答 |
| **历史版本下载** | 从「希沃软件历史版本搜集」API 拉取 EasiCamera 全部 Windows 历史版本（97 条/50 Windows），表格展示、搜索、断点下载、打开目录 |
| **破坏自动更新** | 检测更新器文件/专属计划任务/服务/更新缓存/防火墙/hosts；执行=重命名本产品更新器+清理专属缓存+禁用专属任务/服务（不触碰共享 EasiUpdate 服务与主程序）；可还原；需管理员时明确提示 |
| **一键相机** | 开机自启（HKCU Run，仅用户点击时写入）+ 后台监听展台 HID：按下机身**开关灯按键**后，用 **UI 自动化直接触发 EasiCamera 的「拍照」按钮**（等效机身拍照键/`ECCommands.CaptureImage`，无需键盘快捷键、不写 HID、不与希沃进程抢设备；800ms 防抖；页面可「检测拍照按钮」诊断） |
| **设置与关于** | 安装目录探测/手选、数据与日志目录、主题/缩放信息、版本、**亿方智云**（手动检查更新、匿名统计开关、设备标识）、免责声明 |

## 3. 一键补丁：支持的版本与功能矩阵

补丁以**字节级规则**实现：每条规则记录 文件 + 偏移 + 期望原字节 + 补丁字节（等长替换，不改方法体长度/异常表），应用前逐字节校验，失败整体回滚；先备份到 `<Main>\..\_InspirePatchBackup\<时间戳>\`，支持一键恢复。

| 功能（feature id） | 2.0.10.3816 | 2.0.10.4087 | 2.0.10.4229 | 2.1.0.4419 |
|---|:-:|:-:|:-:|:-:|
| 去除新版本不允许使用第三方展台的限制 `no_third_party_block` | — | — | — | ✓ |
| 去除第三方展台不能用扫描的限制 `force_scan` | ✓ | ✓ | — | ✓ |
| 去除登录按钮 `hide_login` | — | ✓ | — | ✓ |
| 去除兆芯/海光锁画面限制 `disable_freeze` | — | — | — | ✓ |
| 为海光处理器加入锁画面功能（修复批注卡顿） `enable_hygon_freeze` | — | — | ✓ | — |
| 去除英文批改 `remove_english` | ✓ | ✓ | — | — |
| 去除 OCR `remove_ocr` | — | ✓ | ✓ | — |
| 禁用展台 AI 按键 `disable_ai_key` | — | ✓ | ✓ | — |

> `—` = 该版本静态分析确认不存在对应入口/逻辑（UI 会置灰并显示原因），不是"未实现"。

> 2026-11-14 修复：`hide_login`（2.1.0.4419）原先只打上游构造函数一处，会被功能模块切换逻辑重新设为可见；现追加第二处 IL 补丁（`0x1EE0C: 0x17→0x16`），并在解包版 EasiCamera 上真机复现验证登录/头像按钮彻底隐藏。2.0.10.4087 的规则原本就包含两处补丁。

### 用户点名功能的核心结论
1. **2.0.10.4087（20240912 安装包）去除 OCR 按钮**：
   - OCR 入口是工具栏「OCR」按钮 `EasiCamera.UI.AIMenuDisplayToolBarItem`（文案 key `DisplayToolBar.AIMenu=OCR`），点击弹 `AIMenu`（口算批改/英文批改）。
   - 补丁：`EasiCamera.UI.dll` 偏移 **0x10CC9** 1 字节 `0x17→0x16`（`FunctionModule=MainWindow(1)`→`None(0)`），工具栏过滤 `GetUiItems` 后该按钮不再进入任何工具栏/更多列表，OCR 菜单整体不可达。
   - 补丁后 `EasiCamera.UI.dll` SHA-256：`b55847ff1427ea918ef95186c00e564ebe65ccba030c1637ce9135bdcb0985fa`
2. **2.0.10.3816 去除英文批改**：
   - 3816 无 OCR/口算批改/智能识别入口；工具栏按钮 `EasiCamera.UI.CompositionCorrectionDisplayToolBarItem` 的界面文案即本地化 key `Lang.DisplayToolBar.CompositionCorrection=**英文批改**`（3816 的 XAML 本地化证据），点击直达 `ScanCompositionControl` → `IEnglishCompositionProvider.GetOcrText`（英语作文智能批改），是该版本唯一批改/AI 入口。
   - 补丁：`EasiCamera.UI.dll` 偏移 **0xF674** 1 字节 `0x17→0x16`（FunctionModule MainWindow→None），工具栏「英文批改」按钮不再被收集/显示。
   - 补丁后 `EasiCamera.UI.dll` SHA-256：`6adf10e8a545adae68a64dc13e0cd10645f4f079a7784238390054ce50268847`

## 4. 验证（可复现）

```bat
REM 补丁引擎单元测试（49 个用例）
cd InspireCameraTools && python -m unittest discover -s tests

REM 全部版本规则合法性
cd InspireCameraTools && python -m core.cli validate --json

REM 版本识别 / 试运行 / 应用 / 恢复（以 4087 为例；请先复制 Main 副本再打补丁）
python -m core.cli detect --main extracted\v20240912161108\EasiCamera_2.0.10.4087\Main --json
python -m core.cli plan   --main <Main副本> --features remove_ocr
python -m core.cli apply  --main <Main副本> --features remove_ocr
python -m core.cli restore --main <Main副本> --backup <备份目录>

REM 各版本独立校验脚本（原版指纹 → 逐 op 校验 → 补丁后哈希/幂等）
python analysis\4087\verify_rules.py          REM 47 项检查
python analysis\3816\verify_rules.py          REM 29 PASS
python analysis\4229_4419\verify_rules.py     REM 17 项检查
```
已完成的独立验收（Lead 复核）：
- 49/49 单测通过；`validate --json` 4 版本 0 错误；三个 verify 脚本全部 0 失败。
- 4087 `remove_ocr` 在临时副本上应用后 UI.dll = `b55847ff…`（与预期逐字节一致），`restore` 恢复原版 `fcaa674b…`。
- 3816 `remove_english` 应用后 UI.dll = `6adf10e8…`。
- 原始 `extracted/` 文件哈希全程校验未变（含一次误写事故的复验：内容已还原）。
- 应用 `--smoke-test`/页面遍历、打包产物启动验证见 `analysis/app-shots/`。

### 一键相机：为什么不是"发快捷键"

EasiCamera 没有拍照快捷键。程序改为在按下展台机身开关灯键后，通过 Windows UI Automation
找到 EasiCamera 的「拍照」工具栏按钮并 Invoke（与按机身拍照键最终执行同一个
`ECCommands.CaptureImage`）；EasiCamera 工具栏按钮在 UIA 控制视图里没有名字，程序用
Raw 视图取按钮内 `TextBlock`（“拍照”）再找可 Invoke 的按钮祖先，已在本机真实 EasiCamera 进程
（解包版 2.0.10.4087）上实测 `capture` 返回 `uia-invoke` 成功。全程不写 HID、不抢设备，
也不依赖窗口焦点；HID 仅用于只读监听灯键。详见 [analysis/capture-trigger/README.md](analysis/capture-trigger/README.md)。

## 4.1 亿方智云（InspireWorksCloud）接入

应用接入「亿方智云」免费运营模式的 3 个接口（`slug=ict`，Base URL `https://api.yfyw.top/apps/ict/api.php`）：

- **匿名上报** `client_ping`：仅随机设备标识 + 系统描述 + 计算机名，启动后一次、之后每 8 分钟一次；可在设置页关闭。
- **启动弹窗公告** `popup`：支持文本/链接公告与「今日不再显示」（客户端本地记录）。
- **传统手动更新** `app_info`：启动时比对最新版本并提示打开下载网页（不做自动下载/安装）；设置页可手动「检查更新」，可跳过指定版本。

所有云请求超时/异常均静默降级，不影响本地功能；不使用 `app_update`（自动更新安装包）。详见 [analysis/cloud-integration.md](analysis/cloud-integration.md)。

## 5. 历史版本下载数据源

- 页面：`https://swapp.57777777.xyz/get_package?uid=c31ab96f4bdb413aaee8fc8e5dd82181`（希沃软件历史版本搜集）
- 应用实际调用其 API：`GET https://swapp-api-cf.57777777.xyz/apix/get_package?uid=<uid>&page=1&page_size=100`
  → `data.<uid>.softInfos`：版本号/`vtype`/大小/发布时间/官方 `downloadUrl`（带签名直链）
- 本机已下载并核对：2.0.10.3816（140,148,216 B）、2.0.10.4087（141,016,888 B）、2.0.10.4229（145,097,192 B）、2.1.0.4419（149,475,088 B）。

## 6. 上游分析与工具
- 上游仓库：`seewo-easicamera-analysis/`（克隆自 `github.com/XiaoYangTech/seewo-easicamera-analysis`，MIT/学习用途），含 HID 灯光协议、VID/PID 白名单、登录/第三方展台限制、AI/OCR 入口、国产化冻结逻辑的分析报告与原型补丁脚本。
- 本仓库在其基础上新增：`2.0.10.4087` 与 `2.0.10.3816` 两个版本的完整逆向（OCR/英文批改等）、4229/4419 规则移植（哈希逐字节核对）、补丁引擎、桌面应用、破坏自动更新模块。

## 7. 已知限制
- 全部补丁为**静态分析 + 字节/IL 反编译验证**，未在真机验证；界面效果、第三方展台扫描成像、登录按钮消失等需真机确认。
- 软件升级/重装会覆盖已打补丁的 DLL，并恢复更新器文件；需重跑补丁与"破坏自动更新"。
- 历史版本下载依赖第三方站点签名直链，链接过期时以站点/官方最新渠道为准。
- 「一键相机」与「状态调试」需要实际展台 HID 设备（无硬件时显示未连接）。
- 部分功能（修复安装/手动双击官方安装包升级）无法在不破坏系统的前提下彻底阻止。
