# 亿方展台管家（InspireCameraTools）

Windows 桌面端「希沃视频展台（EasiCamera）」辅助工具，基于 Python + ttkbootstrap 开发，
提供 **一键补丁、状态调试、历史版本下载、破坏自动更新、一键相机、设置关于** 等功能。

> ⚠️ 本项目为个人学习/研究用途的第三方工具，与希沃（CVTE）官方无关。使用前请阅读文末「免责声明」。

---

## 功能

| 功能 | 说明 |
|---|---|
| **一键补丁** | 自动识别 EasiCamera 版本，按版本规则对 `EasiCamera.UI.dll`、`EasiCamera.Business.dll` 等文件做字节级修补（去除 OCR/英文批改/登录按钮、解除第三方展台限制、国产化冻结逻辑调整等 8 类功能）。应用前自动备份，可一键恢复。 |
| **状态调试** | 通过 HID（hid.dll / SetupAPI，纯 ctypes 实现）枚举希沃展台接口；查询/开关补光灯（多档亮度）、控制触摸指示灯、查询 MCU 版本；实时监听机身按键与原始 HID 帧并自动应答心跳。 |
| **历史版本下载** | 从希沃官方软件包接口拉取 Windows 版本列表（按发布时间倒序），支持版本搜索、断点续传下载、下载进度展示、打开下载目录。 |
| **破坏自动更新** | 检测并阻止 EasiCamera 自动升级覆盖补丁（更新器文件、专属计划任务/服务、更新缓存等），支持一键还原；需要管理员权限时会明确提示。 |
| **一键相机** | 监听展台机身补光灯按键（HID 帧 `BB CC 05` / `BB CC 02`），触发时通过 Windows UI Automation 直接点击 EasiCamera 的「拍照」按钮（与机身拍照键最终执行同一 `ECCommands.CaptureImage`，无需键盘快捷键、不写 HID）。支持 800ms 防抖与开机自启（后台模式），页面可「检测拍照按钮」诊断。 |
| **设置与关于** | EasiCamera 安装目录探测/手选、数据/日志/下载目录快捷打开、主题与 DPI 缩放信息、版本号与免责声明。 |

界面风格：ttkbootstrap `bootstrap-light` 主题（Bootstrap 5 配色，`#0d6efd` / `#6c757d`），
全中文文案，图标资源由 Pillow 本地生成（无外网素材）。

高 DPI 适配：启动时按 `SetProcessDpiAwareness(2)`（回退 `SetProcessDPIAware`）设置进程 DPI 感知，
并按 `winfo_fpixels('1i')/96` 设置 Tk scaling；100% 缩放时默认窗口 1200x800（最小 1000x680），
高缩放比例下窗口尺寸随之放大并限制在屏幕可用区域内，内容较长的页面支持滚动，避免控件重叠/裁切。

---

## 运行要求

- Windows 10 / 11（仅支持 Windows）
- Python 3.10+（开发验证环境：Python 3.14 **32 位**，`D:\Software\python314\python.exe`）
- 依赖（见 `requirements.txt`）：`ttkbootstrap==1.20.2`、`requests==2.33.0`、`pillow==12.2.0`
- 没有展台硬件也可正常启动，部分功能会显示「未连接」并优雅降级

## 启动

```bat
:: 安装依赖（首次）
D:\Software\python314\python.exe -m pip install -r requirements.txt

:: 进入程序目录后启动
cd InspireCameraTools
D:\Software\python314\python.exe main.py
```

开发/自动化用参数：

```bat
python main.py --smoke-test        :: 构建 UI 后 3 秒自动退出（退出码 0）
python main.py --auto-close 5      :: 启动 5 秒后自动关闭
python main.py --background        :: 后台模式（开机自启使用，启动后最小化）
python main.py --self-check        :: 环境自检（资源/主题/补丁规则/HID/自动更新模块）
python main.py --version           :: 显示版本号
```

配置与日志位置：`%APPDATA%\InspireCameraTools\config.json`、`%APPDATA%\InspireCameraTools\logs\app.log`。

---

## 目录结构

```
InspireCameraTools/
├── main.py                 # 入口：Windows 检查 / 高 DPI / 主题 / 参数解析
├── app/                    # 界面层
│   ├── app_window.py       # 主窗口、页面容器、状态栏、导航
│   ├── base_page.py        # 子页面基类（标题栏 + 返回按钮）
│   ├── theme.py            # 配色/字体/图标加载/主题注册/样式
│   ├── common.py           # 卡片、徽标、日志框、线程安全 UI 分发器、对话框封装
│   ├── home.py             # 主页：展台状态卡片 + 功能入口网格
│   ├── patch_page.py       # 一键补丁
│   ├── hid_page.py         # 状态调试
│   ├── download_page.py    # 历史版本下载
│   ├── autoupdate_page.py  # 破坏自动更新
│   ├── camera_page.py      # 一键相机
│   └── settings_page.py    # 设置与关于
├── core/                   # 业务核心
│   ├── hid.py              # HID 枚举/读写/灯控/触摸灯/MCU/监听/心跳（ctypes）
│   ├── sysinfo.py          # 展台识别、安装目录探测、进程检测、SendInput
│   ├── downloader.py       # swapp 版本 API 客户端 + 断点续传下载器
│   ├── startup.py          # HKCU Run 开机自启 + 后台模式参数
│   ├── settings.py         # JSON 配置持久化
│   ├── patch_engine.py     # 补丁引擎（由 patch-core 提供，契约 §3.3）
│   ├── features.py         # 8 个固定补丁功能目录
│   ├── rules/              # 各版本字节级补丁规则（自动发现）
│   ├── autoupdate.py       # 破坏自动更新（由 patch-core 提供）
│   └── cli.py              # 补丁引擎命令行（调试用）
├── assets/                 # 图标资源（gen_assets.py 用 Pillow 生成）
│   ├── app.ico
│   └── icons/*.png
├── build/build.py          # PyInstaller 打包脚本
├── requirements.txt
└── README.md
```

### 一键补丁说明

- 支持的版本取决于 `core/rules/` 下已提供的规则文件（当前包括 2.0.10.4229、2.1.0.4419，
  以及逆向成员后续提交的 2.0.10.4087、2.0.10.3816）。
- 应用补丁前会 **自动备份** 原文件到 `<Main>/../_InspirePatchBackup/<时间戳>/`，可用「恢复最新备份」还原。
- 应用前会检查 `EasiCamera.exe` / `EasiCameraGuardian.exe` 是否运行，运行中会提示先关闭。
- 补丁为字节级修改，会随官方升级被覆盖；升级后需重新检测与应用。
- 详细规则与字节证据见仓库 `analysis/` 下各版本分析记录。

### 状态调试 / HID 协议

命令统一以 `AA BB CC` 开头，输出帧示例：

| 功能 | 帧 |
|---|---|
| 查询灯光状态 | `AA BB CC 02` |
| 开灯 | `AA BB CC 02 02 02 00 01 <level>`（0x19=25 / 0x32=50 / 0x46=70） |
| 关灯 | `AA BB CC 02 02 02 00 00 00` |
| 触摸灯开/关/闪 | `AA BB CC 03 02 01 00 01/00/02` |
| 查询触摸灯 | `AA BB CC 03` |
| 查询 MCU 版本 | `AA BB CC 06` |
| 心跳应答 | `AA BB CC 04 00` |

输入帧解析：`BB CC 02`（灯状态）、`BB CC 05`（机身灯按键）、`BB CC 01 <n>`（按键 1~5）、
`BB CC 04 01`（心跳，自动应答）、`BB CC 06`（MCU 版本）、`BB CC 0C`（镜头盖）等。
VID 兜底识别 `vid_1ff7` / `vid_254a`；机型白名单见 `core/hid.py::MODELS`。

### 一键相机使用说明

1. 连接希沃展台并打开 EasiCamera 拍照界面（保持 EasiCamera 在前台）；
2. 打开「一键相机」开关（可同时开启开机自启）；
3. 按下展台机身上的补光灯按键即可触发目标按键完成拍照。

注意：同一按键 800ms 内只触发一次；若 EasiCamera/Guardian 同时占用展台 HID，可能收不到输入帧。

---

## 打包（PyInstaller，单目录分发）

```bat
:: 首次安装打包工具
D:\Software\python314\python.exe -m pip install pyinstaller

:: 打包（在 InspireCameraTools/ 下或任意目录执行均可）
D:\Software\python314\python.exe build\build.py
```

产物：`dist\InspireCameraTools\InspireCameraTools.exe`，把整个 `dist\InspireCameraTools\` 目录复制给用户即可。
脚本会自动收集动态导入的 `app`、`core`、`core.rules` 子模块（否则规则文件会缺失）并复制 `assets` 资源。
可选参数：`--onefile`（单文件）、`--console`（保留控制台调试）、`--no-verify`（跳过产物自检）。

## 自测

```bat
:: 冒烟：3 秒自动退出，退出码 0
D:\Software\python314\python.exe main.py --smoke-test

:: 补丁引擎 CLI（与 UI 等价，手工验证用）
python -m core.cli detect --main <Main目录>
python -m core.cli list --version 2.0.10.4229
python -m core.cli plan --main <Main目录> --features remove_ocr
python -m core.cli apply --main <Main目录> --features remove_ocr
python -m core.cli restore --main <Main目录> --backup <备份目录>
```

本文件夹交付时的自测记录见仓库 `analysis/app-shots/`（页面截图、smoke 日志、补丁/下载全链路测试输出）。

## 已知限制

- 本工具未在连接真实希沃展台的机器上验证过 HID 灯控/按键监听（开发环境无硬件，命令按上游分析报告的协议实现）。
- 补丁规则只对规则文件中登记的精确版本有限；官方升级后需重新定位偏移。
- 「破坏自动更新」与部分注册表/服务操作需要管理员权限，普通权限下会提示。
- 历史版本下载依赖希沃官方公开接口，接口变更或网络受限时页面会提示失败并可重试。
- 一键相机通过注入键盘事件实现，仅在 EasiCamera 前台且处于拍照界面时有效。

---

## 免责声明

1. 本工具是个人学习与研究用途的第三方辅助工具，与希沃（CVTE）官方无关，未获得官方授权。
2. 「一键补丁」通过字节级修改 EasiCamera 程序文件实现功能调整，存在导致程序异常的风险；应用前请自行备份原始安装包/文件，并承担使用风险。
3. 官方升级会覆盖补丁，升级后需要重新检测与应用；请遵守软件许可协议与当地法律法规。
4. 历史版本下载仅展示官方公开接口提供的下载链接，安装包版权归原厂商所有。
5. 「破坏自动更新」「一键相机」等功能可能影响软件正常行为，请在了解后果的前提下使用。
6. 使用本工具造成的一切直接或间接损失，作者不承担任何责任。
