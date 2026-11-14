# 亿方展台管家（InspireCameraTools）项目契约

> 本文件是团队共享的接口与分工契约。所有成员开工前必须阅读；修改契约必须由 Lead 执行并在变更日志记录。
> 工作目录：`D:\开发\SeewoCamera`（即 `.`，下同）

## 0. 最终交付物

1. `seewo-easicamera-analysis/`：上游分析仓库克隆（已完成，只读参考，不改）
2. `analysis/`：本项目的逆向分析记录（每个目标版本一份，含证据/偏移/IL 说明/可用性矩阵）
3. `InspireCameraTools/`：Python + ttkbootstrap 的 Windows 桌面应用「亿方展台管家」，bootstrap-light 主题、适配高 DPI
4. 补丁能力：对 `EasiCamera 2.0.10.3816`、`2.0.10.4087` 以及可选的 `2.0.10.4229`、`2.1.0.4419` 提供一键补丁
5. DSH-REA 插件安装完成（Lead 负责）

## 1. 目录与写入范围（严格）

| 目录/文件 | 所有者 | 说明 |
|---|---|---|
| `installers/`、`extracted/`、`.tools/` | Lead（只读给全员） | 官方安装包、解包目录、7-Zip/ILSpy 工具。**任何人不得修改** |
| `seewo-easicamera-analysis/` | Lead | 上游仓库，只读 |
| `InspireCameraTools/core/patch_engine.py` | patch-core | 补丁引擎 |
| `InspireCameraTools/core/features.py` | patch-core | 功能目录（ID/名称/说明/风险） |
| `InspireCameraTools/core/rules/*` | patch-core | 规则包（各版本由对应 RE 成员写自己的文件） |
| `InspireCameraTools/core/rules/v2_0_10_4087.py` | **re-4087-ocr** | 4087 版本规则（独占） |
| `InspireCameraTools/core/rules/v2_0_10_3816.py` | **re-3816-en** | 3816 版本规则（独占） |
| `InspireCameraTools/core/rules/v2_0_10_4229.py`、`v2_1_0_4419.py` | patch-core | 移植上游仓库补丁 |
| `InspireCameraTools/core/autoupdate.py`、`core/cli.py` | patch-core | 破坏自动更新、CLI |
| `InspireCameraTools/core/hid.py`、`sysinfo.py`、`downloader.py`、`startup.py`、`settings.py` | app-dev | 硬件/系统/下载/自启/配置 |
| `InspireCameraTools/app/**`、`main.py`、`assets/**`、`requirements.txt`、`build/**` | app-dev | UI 与打包 |
| `analysis/4087/**` | re-4087-ocr | 4087 分析记录（子目录独占） |
| `analysis/3816/**` | re-3816-en | 3816 分析记录（子目录独占） |
| `analysis/4229_4419/**` | patch-core | 移植记录 |
| `analysis/00-recon.md`、`analysis/CONTRACT.md`、`docs/**`、顶层 README | Lead | 总纲与最终文档 |

跨成员协作只通过本契约、任务板和 `send_message`。发现别人文件需要修改时，先发消息给对应 owner，不要直接改。

## 2. 工具与环境

- Python：`D:\Software\python314\python.exe`（3.14，已装 `ttkbootstrap 1.20.2`、`requests`、`pillow`；如需新依赖用 `pip install`）
- ILSpy CLI：`cd .tools/ilspycmd && dotnet ilspycmd.dll <assembly> [选项]`
  - `-il` 输出 IL，`-t <TypeFullName>` 反编译单个类型，`-p -o <dir>` 反编译整个程序集为工程，`-l c` 列类型（注意手册：`--help`）
  - 全局类型搜索建议：先用 `-il` 或 `-l` 定位，再 `-t` 精读
- 7-Zip：`.tools/7zip/7z.exe`（可解 NSIS 安装包：`7z x installer.exe -o目录 -y`）
- 反编译注意：目标是 .NET Framework 4.5+ 混合程序集（WPF + BAML）；UI 界面文字多在 `Main/Localizations/zh-CHS/*.yml`，控件在 BAML（ILSpy 可反编译出 XAML）
- 官方安装包版本与解包目录（已就绪）：
  - 2.0.10.4087：`installers/EasiCamera_20240912161108.exe` → `extracted/v20240912161108/EasiCamera_2.0.10.4087/Main/`
  - 2.0.10.3816：`installers/EasiCameraSetup_2.0.10.3816.exe` → `extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main/`
- 网络：GitHub/NPM 直连不通，需要代理 `http://127.0.0.1:7897`（`export https_proxy=...`）。seewo/swapp 域名直连可用（curl 加 `--ssl-no-revoke`）
- 历史版本 API（app 下载功能用）：
  - `GET https://swapp-api-cf.57777777.xyz/apix/get_package?uid=c31ab96f4bdb413aaee8fc8e5dd82181&page=1&page_size=100` → `data.<uid>.softInfos` 字典，值为版本信息（`softVersion`、`vtype`、`softSize`(MB)、`softPublishtime`(ms)、`downloadUrl`、`softName`）
  - 过滤 `vtype == "Windows"`；当前共 97 条（Windows 50 条）
  - 全局版本搜索：`GET .../apix/get_global_version_records?page=1&page_size=100&system=all&sort=collected_desc&search=EasiCamera`
  - 下载链接为带签名的直链，可直接 GET；注意 TLS 吊销检查离线时会失败，Python requests 需在 Session 上关闭吊销检查或忽略（`requests` 默认不校验吊销，通常没问题）

## 3. 补丁引擎契约（patch-core 实现，全员遵守）

### 3.1 功能目录（feature catalogue）固定 ID

`core/features.py`：

```python
FEATURES = [
  Feature(id="no_third_party_block", name="去除新版本不允许使用第三方展台的限制",
          description="...", risk="none", default_on=True),
  Feature(id="force_scan", name="去除第三方展台不能用扫描的限制", ...),
  Feature(id="hide_login", name="去除登录按钮", ...),
  Feature(id="disable_freeze", name="去除兆芯/海光锁画面限制", risk="warn:可能导致卡顿", ...),
  Feature(id="enable_hygon_freeze", name="为海光处理器加入锁画面功能（修复批注卡顿）", ...),
  Feature(id="remove_english", name="去除英文批改", ...),
  Feature(id="remove_ocr", name="去除OCR（智能识别）", ...),
  Feature(id="disable_ai_key", name="禁用展台AI按键", ...),
]
```

字段：`id`(固定)、`name`(UI 中文)、`description`(一句话)、`risk`(None 或 `"warning:xxx"`)、`default_on`(bool)。
**不要新增/改名 ID**；版本可用性由规则文件决定。

### 3.2 规则文件格式

每个版本一个模块 `core/rules/v2_0_10_4087.py` 等，只导出 `RULES`：

```python
RULES = {
    "version": "2.0.10.4087",          # 版本号（EasiCamera.exe 文件版本一致）
    "display_name": "V2.0.10.4087",     # UI 显示
    "source_installer": "EasiCamera_(20240912161108).exe",
    # 原版关键文件 SHA-256；用于版本识别与补丁前校验（只写参与补丁与识别的文件）
    "files": {
        "EasiCamera.UI.dll": "fcaa67...",
        "EasiCamera.Business.dll": "5345...",
        ...
    },
    # 版本识别指纹：给出若干文件的 sha256；运行时 Main 目录里匹配 >=2 个即可判定（见 engine）
    "features": {
        "remove_ocr": [
            {   "file": "EasiCamera.UI.dll",
                "offset": 0x10CB9,                  # 字节偏移
                "expected": "027EC004000A0728B702000A26",  # 原字节 hex（小写、无空格）
                "patched":  "02186FE801000A" + "00"*6,    # 补丁后字节 hex，长度必须与 expected 相同
                "note": "把「智能识别」按钮 Visibility 绑定替换为 Collapsed",
            },
        ],
        "disable_ai_key": [ ... ],
        # 可用功能键才出现；不可用功能不写（UI 自动显示不可用）
    },
    "unavailable_reason": {          # 该版本为什么没有某功能（UI 展示，可省略）
        "no_third_party_block": "2.0.10 无云端第三方展台开关",
    },
}
```

约束：
- `expected`/`patched` 必须等长，字节级精确；`offset` 为原版文件绝对偏移。
- 一个功能可包含多条 op（多文件/多补丁点），引擎按顺序应用，任一校验失败则整体回滚（内存级）。
- 同一文件被多个功能同时选中时，引擎按文件合并所有 op 后统一校验：**patch 写回前必须验证每个 op 的 expected 字节**；不同功能 op 不允许重叠偏移。
- 规则文件必须能被 `python -c "import core.rules.v2_0_10_4087"` 导入且不访问磁盘/网络。

### 3.3 引擎 API（`core/patch_engine.py`，app-dev 按此调用）

```python
# 数据类
@dataclass
class DetectedVersion:
    version: str
    display_name: str
    rule: dict            # RULES
    matched_files: dict   # 文件名 -> sha256

@dataclass
class PatchResult:
    ok: bool
    message: str
    applied: list[str]        # 成功的 feature id
    failed: list[tuple[str, str]]  # (feature id, 原因)
    backup_dir: str | None
    needs_restart_hint: bool

def detect_version(main_dir: str) -> DetectedVersion | None
    """按规则指纹识别 Main 目录。未识别返回 None。"""

def list_features(version: str) -> list[FeatureAvailability]
    """FeatureAvailability(feature, available: bool, reason: str|None, already_patched: bool)"""

def plan(main_dir: str, feature_ids: list[str]) -> list[PatchPlanItem]
    """dry-run：不写盘，返回每个功能的可用性与操作说明。"""

def apply_patches(main_dir: str, feature_ids: list[str], backup_root: str | None = None) -> PatchResult
    """备份原文件到 <backup_root or main_dir/../_InspirePatchBackup/YYYYmmdd-HHMMSS/>，
    原子写回（先写 .tmp 再 os.replace）。要求 EasiCamera 未运行（调用方检查/提示）。"""

def restore_backup(main_dir: str, backup_dir: str) -> PatchResult
def is_patched(main_dir: str) -> dict[str, bool]   # feature id -> 是否已应用（按 expected/patched 判断）
DEFAULT_MAIN_DIRS = [...]   # 常见安装目录搜索：C:\Program Files\Seewo\EasiCamera\Main 等
def find_main_dir(explicit: str | None = None) -> str | None
```

`core/cli.py` 提供等价的命令行（供成员手工验证，app 不依赖）：
```
python -m core.cli detect --main <dir>
python -m core.cli list [--version 2.0.10.4087]
python -m core.cli plan --main <dir> --features remove_ocr,disable_ai_key
python -m core.cli apply --main <dir> --features ...
python -m core.cli restore --main <dir> --backup <dir>
```
需支持 `--json`。`CWD` 约定：所有命令在 `InspireCameraTools/` 目录下执行。

### 3.4 验证要求（所有规则必须）

1. 对原版文件应用规则后，`expected` 位置字节和整文件 SHA-256 记录在 `analysis/<version>/verify.md`（或规则文件旁边注释）。
2. 用 ILSpy 对**补丁后文件**重新反编译目标方法/资源，确认结构合法、行为符合预期，把关键 IL 片段写进分析记录。
3. 至少有一个自动化校验脚本：`analysis/<version>/verify_rules.py`（读原版 DLL→应用 RULES→断言哈希；可复现）。
4. 明确标注“未在真机验证”。

## 4. 逆向分析方法建议（RE 成员）

- 先读 `seewo-easicamera-analysis/docs/EasiCamera_分析报告.md` 第 3、4.2、5、7 节，了解 UI/BAML、登录按钮、扫描、AI/OCR 的既有定位思路（针对 2.1.0.4419 / 2.0.10.4229，差分迁移到目标版本）。
- 定位 UI 按钮：`EasiCamera.UI.dll`（4087/3816 都是 WPF BAML 资源）反编译出 XAML/View，找 `Visibility`、`Binding`、`ToolBarItem`；文案在 `Localizations/zh-CHS/EasiCamera.yml`，用文案 key 反查控件。
- 隐藏/去除按钮的两种可靠补丁法（按可验证性优先）：
  1. 把 XAML/BAML 中按钮的 `Visibility` 直接改为 `Collapsed`（改 BAML 需重新压缩资源，谨慎）；
  2. IL 补丁：控件构造后强制 `Visibility = Collapsed`，或把绑定值替换为常量（上游仓库的 `ldc.i4.8; call set_Visibility` 思路，`02 7E C0 04 00 0A 07 28 B7 02 00 0A 26` → `02 18 6F E8 01 00 0A` 即此类）；或让命令/菜单项不被加入（集合 Add 前短路）。
  - 上游 `tools/patch_4229_hide_ai.py`、`patch_easicamera_ui.py` 有具体字节级样例，可参照其“IL 反汇编核对 + 偏移替换”的工作流。
- 修改 IL 后必须核对：偏移处方法体长度字段不变（等长替换），或同步修正方法头 `CodeSize`/异常表（复杂改动优先选等长替换）。
- 证据留存：IL 反汇编文本存 `analysis/<version>/il/`（可截取关键片段），记录偏移、原字节、补丁字节、含义。

## 5. App 规范（app-dev）

- 名称：**亿方展台管家**，英文 `InspireCameraTools`；窗口标题「亿方展台管家」。
- 主题：`ttkbootstrap` 的 `bootstrap-light`；高 DPI：启动时 `ctypes.windll.shcore.SetProcessDpiAwareness(2)`（回退 `user32.SetProcessDPIAware`），并按 `winfo_fpixels('1i')/96` 设置 tk scaling；布局用 grid 权重自适应窗口缩放。
- 仅 Windows（`sys.platform == 'win32'` 检查，非 Windows 弹窗退出）。
- 主页：
  - 顶部状态卡片：展台连接状态（已连接/未连接、机型名、VID/PID、灯状态、软件版本、补丁状态、MCU 版本若有）
  - 中部/下部：功能图标网格（每项 icon+文字，点击进入子页面）：一键补丁、状态调试、历史版本下载、破坏自动更新、一键相机、设置/关于
- 子页面（内嵌同一窗口切换，不弹新窗口；提供返回按钮）：
  1) 一键补丁：版本信息+补丁状态表格/复选列表（8 项，带说明与风险提示、不可用置灰+原因）、[应用所选补丁][恢复备份][重新检测]；应用前检查 EasiCamera 进程并提示关闭；进度/结果日志区。
  2) 状态调试：展台设备列表、灯状态、开灯(亮度 25/50/70 或默认 50)/关灯/查询、触摸灯、HID 原始帧日志（可开始/停止监听）、心跳应答；显示读取到的物理按键事件。
  3) 历史版本下载：数据源 `swapp` API（见 §2），表格显示版本/大小/发布时间/下载状态，支持筛选 Windows、搜索、下载到用户选择目录（默认 `下载/InspireCameraTools/`），进度条，校验大小；一键打开下载目录。
  4) 破坏展台自动更新：调用 `core.autoupdate`，展示当前状态（计划任务/服务/更新器文件/防火墙/hosts），提供[执行][还原]。
  5) 一键相机：开关（开机自启）、映射按键说明（机身开关灯键→拍照键）、目标键设置（默认 F12/可改）、启动后最小化到托盘/后台；调用 `core.hid` 监听展台 HID 输入帧（`BB CC 05` 灯按键通知），触发时向前台窗口发送按键（SendInput）；说明需在 EasiCamera 拍照界面使用。
  6) 设置/关于：安装目录选择、主题/缩放信息、版本、免责声明、日志目录。
- 图标/图片：`assets/` 下自绘 PNG（Pillow 脚本生成即可，风格扁平线性、蓝灰主题色 `#0d6efd`），必须有 app.ico。
- 线程：所有耗时操作（下载、补丁、HID 监听）在后台线程，UI 用 `after()` 回传；不得阻塞主循环。
- 依赖：`ttkbootstrap`、`requests`、`pillow`（已装）；HID 用 `ctypes` 调 `hid.dll`/`setupapi`（不引第三方 HID 库）。
- 打包（最后阶段）：`build/build.py` 用 PyInstaller one-folder（--windowed --icon），产物 `dist/InspireCameraTools/`；`requirements.txt` 固定。
- 代码质量：中文注释/文案；模块化；异常兜底（不得因单个功能异常崩溃）。

## 6. HID 协议（`core/hid.py`，app-dev）

来源：`seewo-easicamera-analysis/docs/EasiCamera_分析报告.md` §1.2/§2.1/§4.1。
- 设备：希沃展台复合设备（UVC+HID）。HID 侧 VID/PID 白名单与兜底：目录路径含 `vid_1ff7` 或 `vid_254a` 视为希沃设备；灯 HID 常在 `0x1FF7/0x0F16`(SC03) 等 PID（详见报告表格）。
- 输出帧（WriteFile 原样写，报告 ID 0）：查询 `AA BB CC 02`；开灯 `AA BB CC 02 02 02 00 01 <level>`；关灯 `AA BB CC 02 02 02 00 00 00`；触摸灯开/关/闪 `AA BB CC 03 02 01 00 01/00/02`；查询触摸灯 `AA BB CC 03`；MCU 版本 `AA BB CC 06`；心跳应答 `AA BB CC 04 00`。
- 输入帧解析：`BB CC 02`（LED 状态，payload[6]=亮灭, payload[7]=亮度）、`BB CC 05`（机身补光灯按键）、`BB CC 03`（触摸灯）、`BB CC 04 01`（心跳→回应）、`BB CC 01 <n>`（按键 1..5：拍照/旋转/唤起/缩小/放大）、`BB CC 06`（MCU 版本 ASCII）、`BB CC 0C`（镜头盖）。
- 读取时注意 HidLibrary 会剥掉首字节：收到 `AA BB CC...` 则跳过 0xAA，收到 `BB CC...` 直接解析。建议两种都兼容。
- 一键相机逻辑：监听 `BB CC 05`（或 `BB CC 02` 状态变化）→ 判定为物理灯键按下 → `SendInput` 发送配置的拍照键到前台窗口（注意注入键与物理键去抖，默认 800ms 防抖）。

## 7. 破坏自动更新（`core/autoupdate.py`，patch-core）

目标：阻止 EasiCamera 自动升级覆盖补丁。先静态分析 `EasiCamera.UpdateFix.exe`、`Suite\`/`Update\` 目录、计划任务/服务、`sweclauncher`，形成分析记录 `analysis/4229_4419/autoupdate.md`，再实现：
- 检测项：更新器进程/计划任务/服务/更新缓存目录/注册表自启项
- 执行：重命名/禁用更新器可执行文件（备份文件名）、删除/清空更新缓存、禁用相关计划任务（`schtasks /change /disable`）与服务；可选防火墙出站规则（需管理员，失败给出提示）
- 还原：恢复重命名/启用任务
- 必须在 Windows 上真实可执行且幂等；不得破坏展台主程序运行
- 若需管理员权限：给出清晰提示，不要静默失败

## 8. 协作规则

1. 开工先在共享任务板认领任务（`team_task_list` → `team_task_get` → `team_task_update claim`），完成后 complete 并给 Lead 发简报。
2. 只写自己范围内的文件；需要别人改时发消息。
3. **绝对不要重启、关闭或重装正在运行的 DeepSeek Harness 桌面应用/DSH 会话**；不要执行 `taskkill` 掉宿主进程。
4. 不要实际安装/运行 EasiCamera（没有展台硬件；安装会污染系统）；只做静态分析 + 在解包目录副本上验证。验证补丁请复制 Main 目录到自己的临时目录。
5. 下载大文件/装依赖注意磁盘（D 盘剩 ~45GB）；不要重复下载已有安装包。
6. 每完成一个里程碑给 Lead 发 `send_message` 简报（做了什么/证据/风险/下一步），不要等被问。
7. 遇到无法解决的阻塞（工具缺失、格式不识别、权限）：先尝试替代方案，仍不行立即报 Lead，附错误原文。
8. 时间管理：先交付用户点名的核心功能（4087=去除OCR；3816=去除英文批改），再扩面。

## 9. 验收标准

- [ ] `python -m core.cli detect --main extracted/...` 能识别 4087/3816
- [ ] 4087：`remove_ocr` 规则可应用，补丁后 ILSpy 反编译正常，按钮/入口被去除（有 IL 证据）
- [ ] 3816：`remove_english` 规则可应用，同上
- [ ] 各版本规则文件通过自带 `verify_rules.py`
- [ ] app 能启动、主页显示状态、6 个页面可进入且功能可用（无展台时优雅降级显示"未连接"）
- [ ] 一键补丁页对已解包 Main 目录可检测/应用/恢复（Lead 用测试目录验收）
- [ ] 历史版本下载页能从 swapp API 拉到列表并下载一个版本
- [ ] 破坏自动更新与一键相机在无硬件环境下可启动、状态可展示、不崩溃
- [ ] README/分析报告齐全
