# EasiCamera 自动更新链分析与「破坏自动更新」实现记录

> 任务：静态分析 EasiCamera 自动更新机制，形成分析记录，并实现 `core/autoupdate.py`
> （检测 / 执行 / 还原，幂等，需管理员时明确提示，不得破坏主程序运行）。
> 对象版本：**2.0.10.4229** 与 **2.1.0.4419**（两版本更新组件架构相同，哈希不同）。
> 本机无 EasiCamera 安装、未运行 EasiCamera；全部结论来自解包目录静态分析 + ILSpy 反编译 +
> strings + 本机已安装的希沃共享更新服务（其它产品）只读观察。**未在真机验证更新阻断效果**。

## 1. 结论摘要

1. EasiCamera 的自动更新链是：**主程序内 AutoUpdateService → 版本目录下 `Updater.exe`
   → 共享 `EasiUpdate` Windows 服务下载官方 NSIS 安装包 → 静默安装新版本目录**。
2. **没有计划任务、没有 EasiCamera 专属 Windows 服务、没有更新器开机启动项**；
   唯一常驻的 `EasiUpdate` 服务是**希沃多产品共用组件**（希沃白板等也在用）。
3. `EasiCameraGuardian.exe`（展台 HID/通信辅助，HKLM Run 自启）与 `sweclauncher.exe`（启动器）
   **与更新无关**，禁用会破坏主程序功能/启动，绝不能动。
4. 因此「破坏自动更新」的正确做法是：**重命名 EasiCamera 自己的更新器可执行文件
   + 清理 EasiCamera 专属更新缓存/配置**（`NginxDownload/<AppKey>`、`%APPDATA%\EasiUpdate\<AppName>`、
   `ConfigDirectory/<AppKey>.ini`），**不动共享服务、不动主程序文件、不动注册表版本信息**。
   更新器缺失后主程序日志会出现 `Updater missing.`，更新链在“检查/下载”前即断。

## 2. 组件清单与静态证据

解包目录：`extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/`（2.0.10.4229 结构相同）。

| 组件（相对版本目录） | 角色（证据） |
|---|---|
| `Main/EasiCamera.exe` | 主程序。`EasiCamera.Shell.AutoUpdateExtension`：`App.Ready` 后 3 秒启动 `AutoUpdateService.Check()`（ILSpy 反编译） |
| `Main/EasiCamera.Business.dll` | `EasiCamera.Business.Services.AutoUpdateService`（529 行）：先查 Myou/官网版本，再 `CheckFromEasiUpdate`；找 `Updater.exe` 并用 `-task check/update -type autostart/userstart -lang … -key … -version …` 启动 |
| `Updater.exe`（根） | `Cvte.Updater.App`：解析 `Update.config`（AppName/AppKey/RegistryKey/RegistryPathKey），通过 `LibEasiUpdate.dll` P/Invoke 请求共享服务下载/安装；更新时 `BeforeUpdate.bat`→杀进程→备份旧目录→替换目录→`AfterUpdate.bat` |
| `LibEasiUpdate.dll`（根） | 原生 DLL，EasiUpdate 客户端（ZMQ `tcp://*:39171`/`39172`，protobuf；路径 `C:\ProgramData\Seewo\Easiupdate\easiupdate`） |
| `Update_Cam2.exe`（根） | `SeewoUpdate` 旧式独立更新 UI（同为 P/Invoke LibEasiUpdate；可更新 `Update_Cam2.exe/LibEasiUpdate.dll/UpdateConfig.xml` 等） |
| `UpdateFix.exe`（根） | 安装后修复：校准防火墙规则、写注册表 `version`/`ActualExePath`/`VersionPath`、删除旧版本目录（保留 2 个）、维护 `Config.ini` 的 `ReservedN` |
| `GuardianUpdater.exe`（根） | 安装后把 HKLM Run 的 `EasiCameraGuardian` 指向新版本 Main 目录 |
| `Main/EasiCamera.UpdateFix.exe` | 主程序目录内的一次性修复任务（`CopyTrapezoidDependenciesTask`、`install` 参数时 `CreateInstallSignFileTask`） |
| `Main/SupportFiles/EasiUpdateSetup.exe` | 2.44 MB NSIS 安装器，释放共享更新服务到 `C:\ProgramData\Seewo\Easiupdate\`（4229/4419/4087/3816 中该文件 SHA-256 完全相同） |
| `After.bat`（根） | 安装收尾：`UpdateFix.exe /S`、`Main\EasiCamera.UpdateFix.exe /S`、`GuardianUpdater.exe /S`、拷贝 ffdshow/ffmpeg 等 |
| `Update.config`（根） | `AppName = EasiCamera`、`AppKey = 827f282f4c551e7c7442f944918a959021c80b81`、`RegistryKey = Seewo\EasiCamera`、`RegistryPathKey = VersionPath` |
| `sweclauncher/sweclauncher.exe` | 启动器：读注册表 `Software[\WOW6432Node]\Seewo\EasiCamera` 的 `ActualExePath` 再启动主程序 —— **不能动** |
| `Main/EasiCameraGuardian.exe` | 常驻展台 HID/通信辅助（`SeewoCamService`、灯光/按键/镜头盖解析、.NET Remoting 通知主程序）—— **不能动** |
| `Main/UpdateConfig.xml` | 更新时需杀进程列表：`<RunningProcess Name="EasiCameraGuardian" KillAny="true"/>`（反证 Guardian 不是更新器） |

更新链（4419，静态分析重建）：

```
EasiCamera.exe ──(3s, AutoUpdateExtension)──> AutoUpdateService.Check()
   ├─ Myou/官网 API 检查新版本（只判断版本号，不下载）
   └─ CheckFromEasiUpdate()
        ├─ 确认服务 EasiUpdate 正在运行（ServiceController，服务名 "EasiUpdate"）
        ├─ 找缓存 <EasiUpdate path>\easiupdate\NginxDownload\<AppKey>\<新版本>.exe
        └─ 没有缓存 → 启动 <VersionPath>\Updater.exe -task check/update -type autostart|userstart ...
             └─ Updater.exe ──LibEasiUpdate(EU_RequestUpdateInfo/EU_DoUpdate)──> EasiUpdate 服务
                   └─ 服务用 Myou 接口下载官方 NSIS 包到 NginxDownload\<AppKey>\
                        └─ Updater 解压/静默安装新版本目录 → After.bat → UpdateFix.exe/GuardianUpdater.exe
                             └─ 注册表 VersionPath/ActualExePath 指向新版本（旧版本保留 2 份）
```

关键反编译证据（可复现：`.tools/ilspycmd` + `-p`/`-t`）：

- `EasiCamera.Business.Services.AutoUpdateService`：常量 `"Updater.exe"`、`"EasiUpdate"`、
  `"VersionPath"`；`TryToGetUpdaterFromRegister` 读 `SOFTWARE[\WOW6432Node]\Seewo\EasiCamera`
  的 `VersionPath` + `\Updater.exe`；`IsEasiUpdateRunning` 检查服务名 `EasiUpdate`；
  `AutoUpdateExtension` 中 `DispatcherTask.Start(3000.0, …)` 后调用 `Check()`。
- `Cvte.Updater.GlobalConfig`：`UpdateService => "EasiUpdate"`、`UpdateLibFile => "LibEasiUpdate.dll"`、
  `BeforeBatFile/AfterBatFile`、日志目录 `%APPDATA%\Seewo\EasiUpdate`。
- `Cvte.Updater.DllWrapper`：`[DllImport("LibEasiUpdate.dll")] EU_*`。
- `Cvte.Updater.UpdateConfig`：读 `Update.config`，注册表键值 `path`/`ExePath`/`version`。
- `SeewoUpdate.EasiUpdater`（Update_Cam2）：更新文件列表
  `Update_Cam2.exe/LibEasiUpdate.dll/BeforeUpdate.bat/AfterUpdate.bat/UpdateConfig.xml`；
  更新缓存 `%APPDATA%\EasiUpdate\<AppName>`。
- `UpdateFix.RegisterUtilities`：写 `SOFTWARE[\WOW6432Node]\Seewo\EasiCamera` 的
  `version`/`ActualExePath`/`ExePath`/`VersionPath`，并同步卸载项 `DisplayVersion`。

## 3. 安装布局、注册表、服务、任务、缓存

### 3.1 安装布局（注册表 + UpdateFix 逻辑推断，本机无 EasiCamera 可验证）

```
C:\Program Files (x86)\Seewo\EasiCamera\           ← 安装根（具体盘符/Program Files 视安装时选择）
├── EasiCamera_2.1.0.4419\                        ← 当前版本目录（注册表 VersionPath）
│   ├── Main\EasiCamera.exe                       ← ActualExePath
│   ├── sweclauncher\sweclauncher.exe             ← 启动器（ExePath，快捷方式指向）
│   ├── Updater.exe / Update_Cam2.exe / UpdateFix.exe / GuardianUpdater.exe / LibEasiUpdate.dll
│   ├── Update.config / Config.ini / After.bat / app-package.json
│   └── Main\EasiCamera.UpdateFix.exe / Main\EasiCameraGuardian.exe / Main\SupportFiles\EasiUpdateSetup.exe
└── EasiCamera_2.0.10.4229\                        ← 旧版本目录（UpdateFix 清理，最多保留 2 个旧版）
```

> 对照本机已安装的希沃白板（EasiNote5）注册表，布局完全同构：
> `HKLM\SOFTWARE\WOW6432Node\Seewo\EasiNote5` 有 `VersionPath`/`ActualExePath`/`ExePath`
> 三个键值，`EasiNote5_5.2.4.11451\Main\EasiNote.exe`。

### 3.2 注册表

| 注册表位置 | 内容 | 本工具是否修改 |
|---|---|---|
| `HKLM\SOFTWARE[\WOW6432Node]\Seewo\EasiCamera` | `version`、`code`（卸载项 GUID）、`path`、`ExePath`、`ActualExePath`、`VersionPath` | **不修改**（主程序/启动器依赖） |
| `HKLM\...\Microsoft\Windows\CurrentVersion\Uninstall\{code}` | 卸载信息 `DisplayVersion` 等 | 不修改 |
| `HKLM\SOFTWARE[\WOW6432Node]\Seewo\EasiUpdate` | 共享更新服务：`appkey`、`path`、`version`、`code` | 只读（共享组件） |
| `HKLM\...\Windows\CurrentVersion\Run` 的 `EasiCameraGuardian` | Guardian（HID 辅助）开机自启 | **不修改**（非更新器） |
| 更新器/启动器开机启动项 | **未发现**任何指向 Updater.exe/Update_Cam2.exe 的 Run 项 | — |

### 3.3 Windows 服务

- **EasiUpdate**（共享）：`C:\ProgramData\Seewo\Easiupdate\easiupdate\EasiUpdate.exe`，
  `AutoStart` + `LocalSystem`，由 `EasiUpdateSetup.exe` 安装（`easi_update_install.bat` 里
  `net stop EasiUpdate; sc delete EasiUpdate; EasiUpdate.exe -run` —— `-run` 自注册服务）。
  本机（未装 EasiCamera）该服务正在运行，证明其为多产品共享基础设施。
- **easiupdate-nginx**（共享，可选下载服务器，端口 9090）：由 `easi_update_uninstall.bat` 引用；
  本机未安装（无该服务）。
- **EasiUpdate3 / EasiUpdate3Protect**：本机存在，属于**其它**希沃产品的新版更新基础设施，与本任务无关，
  绝不处理。
- **EasiCamera 专属服务：无**（服务注册表全表扫描无 `easicamera` 匹配）。
- 结论：`core/autoupdate.py` 只禁用“镜像路径/显示名含 easicamera 的服务”（通常为空），
  共享服务仅展示、不修改；`easiupdate-nginx` 同属共享，不修改。

### 3.4 计划任务

- `schtasks /query` 与字符串分析（Updater/UpdateFix/GuardianUpdater/LibEasiUpdate/`After.bat`/
  `easi_update_install.bat`）**未发现创建计划任务的代码或安装脚本**。
- 注意：`EasiCamera.exe` 字符串里出现的 `TaskScheduler` 是 .NET BCL
  `System.Threading.Tasks.TaskScheduler`（异常处理相关），**不是 Windows 计划任务**。
- `core/autoupdate.py` 仍实现计划任务检测：只处理任务名含 `easicamera` 的“专属任务”，
  含 `easiupdate/seewo` 的任务按共享组件只展示；`apply` 用 `schtasks /change /disable`（需管理员）。

### 3.5 更新缓存 / 配置 / 日志

| 路径 | 内容 | apply 行为 |
|---|---|---|
| `<EasiUpdate path>\easiupdate\NginxDownload\<AppKey>\` | 已下载的 EasiCamera 安装包缓存（AppKey 来自版本目录 `Update.config`） | 重命名为 `*.inspire-disabled`（可还原） |
| `<EasiUpdate path>\easiupdate\ConfigDirectory\<AppKey>.ini` | 更新服务中 EasiCamera 的更新配置（若存在） | 重命名（可还原） |
| `%APPDATA%\EasiUpdate\<AppName>\` | Updater/Update_Cam2 更新工作目录与日志 | 重命名（可还原） |
| `%APPDATA%\Seewo\EasiUpdate\`（Updater 日志） | `Log.txt` 等 | 不动（日志，无更新能力） |
| `C:\ProgramData\Seewo\Easiupdate\easiupdate\logs\` | 共享服务的日志（`EasiUpdate-Server_*.log`、`UpdateFix.log`） | 不动（共享组件日志） |

> 本机只读观察到的真实共享服务日志（`EasiUpdate-Server_info.log`）显示服务每 300 单位
> 检查一次自身更新（`UpdateIntervalTime = 300`，`EasiUpdate.ini`），并用
> `http://myou.cvte.com/api/v1/update?appKey=…&versionCode=…&platform=windows_app&deviceMac=…`
> 判断是否需要更新；这与反编译出的 Myou/EasiUpdate 机制吻合。

### 3.6 防火墙 / hosts

- 共享服务安装脚本会创建放行规则：`EasiUpdate`、`EasiUpdate-39171`、`EasiUpdate-39172`、
  `easiupdate-nginx*` 等 —— 属于共享组件，不删除。
- `hosts`：本工具**只读展示**相关条目，不修改。原因：修改 hosts 会同时影响希沃其它产品
  （登录/云服务/白板）的联网，且容易被安全软件还原，与“不得破坏主程序运行”冲突。
- `apply(include_firewall=True)` 可选：为 EasiCamera 的 `Updater.exe` / `Update_Cam2.exe`
  添加**出站拦截**规则（`netsh advfirewall firewall add rule dir=out action=block program=...`），
  需管理员；失败会在结果中标注 `requires_admin=True`。

## 4. 实现说明（`InspireCameraTools/core/autoupdate.py`）

### 4.1 接口

```python
detect() -> list[dict]      # 状态项：installed / updater_file / cache / task / service / registry / firewall / hosts
summarize(items) -> dict    # 汇总：已安装、已阻断/仍可用数量、是否需管理员、fully_blocked
apply(main_dir=None, include_firewall=False) -> dict
restore(main_dir=None) -> dict
is_admin() -> bool
```

- `detect()` 无安装时只返回一条 `status="not_installed"`；`apply()/restore()` 无安装时直接返回
  `ok=True, installed=False`，**不做任何写操作与系统命令**（可在任意机器安全运行）。
- 每个状态项字段：`id / name / category / status / label / detail / requires_admin / actionable / shared`；
  `status` 取值：`active`（更新能力可用）、`blocked`（已阻止）、`missing`（不存在）、
  `not_installed`、`shared`（共享组件仅展示）、`unknown`。
- `apply()/restore()` 返回 `ok / message / is_admin / installed / requires_admin / changed /
  needs_restart_hint / results[]`；`results[]` 每项含 `ok / skipped / requires_admin / message`。
- 幂等：重复 `apply` 全部 `skipped`、`changed=0`；重复 `restore` 同理。
- 权限：写 Program Files/ProgramData、改计划任务/服务/防火墙失败时翻译为中文错误并标
  `requires_admin=True`；不改任何注册表。

### 4.2 apply 的具体动作（只动 EasiCamera 自己的东西）

1. 版本目录下重命名（加 `.inspire-disabled` 后缀）：
   `Updater.exe`、`Update_Cam2.exe`、`GuardianUpdater.exe`、`UpdateFix.exe`、
   `Main/EasiCamera.UpdateFix.exe`、`Main/SupportFiles/EasiUpdateSetup.exe`。
2. 清理 EasiCamera 专属缓存：`NginxDownload/<AppKey>`、`ConfigDirectory/<AppKey>.ini`、
   `%APPDATA%\EasiUpdate\<AppName>`（均为重命名保留，可一键还原）。
3. 禁用任务名含 `easicamera` 的专属计划任务（通常为空）。
4. 禁用镜像/显示名含 `easicamera` 的专属服务（通常为空）。
5. 可选防火墙出站拦截（`include_firewall=True`）。
6. 状态文件 `%LOCALAPPDATA%\InspireCameraTools\autoupdate_state.json` 记录任务/服务/防火墙变更，
   `restore` 按状态文件精确还原（文件重命名则按后缀逆操作，即使状态文件丢失也能还原）。

**明确不做**：不改注册表（版本/路径/Run）、不禁用/不停止 `EasiUpdate`/`EasiUpdate3*`/`easiupdate-nginx`
共享服务、不删共享服务缓存/配置/日志、不动主程序 `EasiCamera.exe`、`sweclauncher.exe`、
`EasiCameraGuardian.exe`、`Main`/`Localizations` 等业务文件。

### 4.3 安全性设计

- 所有系统命令（`schtasks`/`sc`/`netsh`）用 `subprocess.run` + 超时 + `CREATE_NO_WINDOW`，
  异常捕获后转中文错误，不抛栈、不阻塞 UI；
- 所有注册表读取 `try/except` 容错，非 Windows 下检测返回“未安装/不支持”而不是崩溃；
- 更新器文件/缓存均为“重命名”而非删除，保证可还原且幂等；
- 状态文件写入用临时文件 + `os.replace` 原子替换。

### 4.4 验证方式

- **单元测试**：`InspireCameraTools/tests/test_autoupdate.py`（11 个用例）在临时目录伪造完整
  版本目录 + 共享 EasiUpdate 目录 + 缓存，隔离所有系统查询（mock 注册表/服务/任务/防火墙/hosts），
  覆盖：未安装时检测/执行/还原安全返回、detect 状态项、apply 阻断链、apply 不破坏主程序/启动器/
  Guardian、幂等、restore、restore 幂等、权限不足 `requires_admin`、可选防火墙。
- **本机只读验证**：本机未安装 EasiCamera 但装有共享 `EasiUpdate` 服务（其它希沃产品），
  `detect()` 正确返回“未安装”且不触碰共享服务；未对真实服务做任何变更。
- 运行：`cd InspireCameraTools && D:/Software/python314/python.exe -m unittest discover -s tests -v`
  （本次全量 49 个测试通过）。

## 5. 风险与注意事项

1. **未在装有 EasiCamera 的真机验证**更新阻断的端到端效果；建议在测试机执行后：
   打开 EasiCamera → 是否仍正常启动/连接展台；`%APPDATA%\Seewo\EasiUpdate\Log.txt`
   是否出现 `Updater missing.`；再执行还原确认更新能力恢复（可手动触发“检查更新”）。
2. 执行/还原需要管理员权限的场景：安装目录在 `Program Files`、共享服务路径 `ProgramData`、
   计划任务/服务/防火墙。非管理员运行会得到 `requires_admin=True` 与中文提示，不会静默失败。
3. 软件重装/修复安装会恢复更新器文件，需要重新执行「破坏自动更新」。
4. 本模块不处理“用户手动双击官方安装包升级”的场景（无法在不破坏系统的前提下彻底阻止）。
5. 共享服务升级（EasiUpdate 自更新）可能重建 `NginxDownload` 目录，但 EasiCamera 的
   `Updater.exe` 已被重命名，更新请求发不出去。
6. 本机观察到的 `EasiUpdate3` 服务属于其它希沃产品，本模块**不处理**；若 EasiCamera 未来迁移到
   EasiUpdate3，需要按同样思路补充「EasiCamera 专属更新器/缓存路径」的检测（共享服务仍不建议禁用）。

## 6. 证据文件与复现命令

临时反编译产物在 `work/patchcore/il/`（不随交付，可由下列命令重建）：

```bash
# 反编译更新组件（示例）
cd extracted/v2.1.0.4419/EasiCamera_2.1.0.4419
dotnet ../../../.tools/ilspycmd/ilspycmd.dll -l c Updater.exe
dotnet ../../../.tools/ilspycmd/ilspycmd.dll -p -o ../../../work/patchcore/il/Updater.exe Updater.exe
dotnet ../../../.tools/ilspycmd/ilspycmd.dll -p -o ../../../work/patchcore/il/Main_EasiCamera.Business.dll Main/EasiCamera.Business.dll
# 提取字符串
D:/Software/python314/python.exe work/patchcore/strings_extract.py LibEasiUpdate.dll /tmp/libeasiupdate.txt
# 解包共享更新服务安装器（只读分析，不执行）
.tools/7zip/7z.exe x Main/SupportFiles/EasiUpdateSetup.exe -o/tmp/easiupdatesetup -y
```

- `EasiCamera.Business.Services/AutoUpdateService.cs`（反编译源码，529 行）
- `Cvte.Updater/{GlobalConfig,UpdateEngine,Updater,DllWrapper,UpdateConfig}.cs`
- `SeewoUpdate/{EasiUpdater,AppInfo,UpdaterHelper}.cs`
- `UpdateFix/{Program,FirewallUtilities,RegisterUtilities,GlobalConfig}.cs`
- `GuardianUpdater/Program.cs`、`Main_EasiCameraGuardian.exe/**`（确认 Guardian 与更新无关）
- `$R0/ProgramData/Seewo/Easiupdate/{easi_update_install.bat,easi_update_uninstall.bat,easiupdate/run.bat,EasiUpdate.ini}`

## 7. 引用

- 上游报告 `seewo-easicamera-analysis/docs/EasiCamera_分析报告.md` §7.1（AI 入口）、§7.2（HID）、
  §7.3/§7.4（UI 补丁）、§7.6（国产化冻结）中关于“软件自动更新可能覆盖补丁”的提示。
- `analysis/CONTRACT.md` §7（破坏自动更新要求）。
- `analysis/4229_4419/README.md` §2（官方安装包来源）与 `verify.md`（补丁校验）。
