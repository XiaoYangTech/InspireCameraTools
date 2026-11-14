# 一键相机：从"发送快捷键"改为"模拟机身拍照动作"的分析与实现

> 背景：用户指出 **希沃展台没有拍照快捷键**，原来"按灯键 → SendInput 发送 F12"的方案在真机上不成立；
> 要求改为「模拟展台机身的拍照键」，并考虑"希沃进程占用设备怎么办"。

## 一、结论（先说结果）

**改为：UI 自动化（UIA）直接调用 EasiCamera 界面上的「拍照」按钮。**

- 该按钮绑定 `ECCommands.CaptureImage` —— 与用户点击按钮、按下机身拍照键最终执行的是**同一个命令**；
- 不需要键盘快捷键、不要求 EasiCamera 前台焦点，**不写 HID、不与希沃进程抢设备**；
- HID 只用于**只读监听**开关灯键（Windows 允许多进程同时读 HID；EasiCamera 主程序与 Guardian 本身也各自读同一设备），因此"希沃进程占用"不影响触发；
- 另外实现了 EasiCamera 内部的 .NET Remoting 通道（Guardian 转发机身按键的同一入口），作为**诊断/备用**通道；但它有一个硬限制，见第三节。

## 二、逆向证据

### 2.1 拍照命令链路（静态）

| 证据 | 内容 |
|---|---|
| `EasiCamera.Api.dll`（4419，SHA-256 `6bcab47a…9bb`） | `EasiCamera.ECCommands` 定义 `CaptureImage`、`CaptureAndSendToEasiNote`、`InsertIntoEasiNote` 等命令；`EasiCamera.UiItem`/`DisplayToolBarItem` 是工具栏项的数据模型（含 `Command` 属性） |
| `EasiCamera.UI.dll`（4419，SHA-256 `c80fd035…6f4`） | `EasiCamera.UI.TakePhotoDisplayToolBarItem`：构造函数设置 `base.Command = ECCommands.CaptureImage`、`SortHint=91`、`FunctionModule=MainWindow`，并给 `IsEnabled`/`IsCanClickDisabled` 绑定 `TakePhotoButtonEnableConverter`/`SlideToButtonDisabledConverter`；点击时上报 `tb_captureImage` |
| 定位方法 | REA `open_binary` + `inspect_managed_members`（managed provider）打开上述程序集，类型/成员签名与调用证据已导出；同时用 ILSpy CLI 反编译交叉核对 |
| REA 证据包 | `analysis/capture-trigger/rea_evidence.json`（2 条 Evidence，约 1.47MB，由 `mcp__rea__export_evidence_bundle` 导出） |

因此：**点击界面「拍照」按钮 = 执行 `ECCommands.CaptureImage`**，与机身拍照键触发的最终动作一致。

### 2.2 机身按键注入通道（Remoting，为什么只能作备用）

| 证据 | 内容 |
|---|---|
| `EasiCamera.Communication.dll`（3816/4087/4229/4419 四个版本一致） | `EasiCamera.Communication.Remoting.RemotingCameraServer.Start()` 用 `IpcChannel("e3950283-80cf-4a97-a569-e6110b6e9b82")` 注册 `RemotingNotifyCamera` 单例；`RemotingNotifyCamera.Notify(int pid,int vid,string message)` 调用 `EC.CameraApi.CurrentCameraController.HidComponent.HandleCameraHidMessage(pid,vid,message)` |
| `EasiCameraGuardian.exe` | 机身 HID 帧 `BB CC 01 <n>` → `NotifyRemoting(HidMessage.KeyN)` → 同一 `Notify(pid,vid,message)`；即 Guardian 转发机身按键用的就是这个通道 |
| **关键限制** | `RemotingNotifyCamera` 构造函数启动 25 秒定时器，到点 `_needNotify=false`，`Notify` 变为**静默空操作**（四个版本代码完全相同）。即该通道只在 EasiCamera **启动后约 25 秒内**有效，运行期不可靠 |
| 实测 | 用同名类型做客户端透明代理（`EasiCameraRemotingProxy.dll`），运行期调用 `Notify` 返回 `true`（空操作）；说明通道本身可用，但受 25 秒门控 |

结论：**Remoting 通道语义上最接近"模拟机身按键"，但不能作为运行期主路径**；保留为诊断模式（`EasiCameraTrigger.exe remoting --pid --vid --message Key5`），主路径用 UIA。

### 2.3 运行期验证（本机，无展台硬件）

- 用解包版 `extracted/v2.1.0.4419/.../Main/EasiCamera.exe` 在本机启动（运行完即关闭，未安装）：
  - 主窗口进程 `EasiCamera.exe`、窗口标题「希沃视频展台」，另有 `EasiCameraGuardian.exe` 常驻；
  - `EasiCameraTrigger.exe probe` 通过 UI Automation 枚举到窗口内 62 个可自动化元素（按钮/页签/文本等），说明 UIA 树可访问；
  - 由于**未连接展台**，界面处于"正在查找展台设备…"状态，工具栏不渲染，因此找不到「拍照」按钮（`capture --dry-run` 返回 `capture button not found`，符合预期）；
  - 连接真实展台后工具栏会出现「拍照」按钮，UIA 即可 Invoke（按钮文案来自本地化 `Lang.DisplayToolBar.TakePhoto = 拍照`）。
- 无硬件/未开 EasiCamera 时：`trigger_capture()` 返回友好提示「未找到 EasiCamera 窗口：请先打开希沃视频展台（EasiCamera）」，不影响开关监听。

## 三、实现

### 3.1 随包助手（.NET Framework 4.x，本机 csc 编译）

| 文件 | 说明 |
|---|---|
| `InspireCameraTools/assets/bin/EasiCameraTrigger.cs` → `EasiCameraTrigger.exe` | 三种模式：`capture`（UIA 找「拍照」按钮并 Invoke，可用 `--dry-run` 只检测不点击）、`probe`（列出窗口全部可自动化元素）、`remoting`（调用 RemotingNotifyCamera）；输出单行 JSON |
| `InspireCameraTools/assets/bin/EasiCameraRemotingProxy.cs` → `EasiCameraRemotingProxy.dll` | 与服务器端**同名同签名**的 `EasiCamera.Communication.Remoting.RemotingNotifyCamera` 客户端代理类型（.NET Remoting 透明代理要求） |
| `InspireCameraTools/core/capture_trigger.py` | 定位/懒编译助手、调用与结果解析、友好错误信息；`trigger_capture()` / `probe_capture_button()` / `remoting_notify()` |
| `InspireCameraTools/app/camera_page.py` | 触发流程改为「UIA 点击拍照按钮」；新增「检测拍照按钮」诊断按钮；日志显示实际方法（`uia-invoke`）。**2026-11-14 晚：按要求删除兜底热键（默认 F12）及相关设置项，UIA 为唯一触发方式** |

按钮匹配策略（`EasiCameraTrigger.cs`）：

1. **控制视图**：按名称精确匹配「拍照 / Take Photo / TakePhoto / 拍摄 / Capture / Photo / Snapshot」或 AutomationId 包含 `takephoto/take_photo/capture/snapshot`；
2. **Raw 视图兜底（实测必需）**：EasiCamera 工具栏按钮是自绘控件，控制视图里 `Name` 为空（真机实测 1920x1080 下按钮名全是空字符串）。
   Raw 视图能用 `RawViewWalker` 拿到按钮内部的 `TextBlock`（名字就是「拍照/延时拍照/…」），
   再沿 Raw 父链找到支持 `InvokePattern` 的按钮祖先并 Invoke；
3. 排除「延时拍照/连拍/预览」；找不到时返回候选列表供诊断。

**真实进程验证（2026-11-14，本机解包版 EasiCamera 2.0.10.4087）**：

```text
> EasiCameraTrigger.exe capture --dry-run
{"ok":true,...,"element":{"name":"拍照","type":"Text->Button","score":260,...}}
> EasiCameraTrigger.exe capture
{"ok":true,"mode":"capture","method":"uia-invoke","element":{"name":"拍照",...}}
```

即：在没有键盘快捷键的前提下，程序已经能在真实 EasiCamera 进程里**定位并点击「拍照」按钮**（UI 自动化 Invoke），
与按机身拍照键最终执行的 `ECCommands.CaptureImage` 等价。

### 3.2 关于"HID 被希沃进程占用"

- 触发拍照**完全不使用 HID**，因此不存在被希沃进程占用的问题；
- 我们的 HID 只用于**只读**监听开关灯按键：Windows HID 输入报告会分发给每个打开的句柄，EasiCamera 主程序与 Guardian 本身也是各自独立打开同一 HID 设备读取，多进程共享读通常没问题；
- 若极端情况读打开失败（驱动/固件限制），页面日志会给出明确提示，用户可关闭占用进程后重试；
- 一键相机页「检测拍照按钮」可随时确认 UIA 通道是否正常（与 HID 状态无关）。

## 四、验证

```bat
REM 助手自检（无 EasiCamera 时应返回"capture button not found / window not found"）
InspireCameraTools\assets\bin\EasiCameraTrigger.exe capture --dry-run
InspireCameraTools\assets\bin\EasiCameraTrigger.exe probe

REM 模块单元测试（10 个用例：解析/参数/超时/编译回退）
cd InspireCameraTools && python -m unittest tests.test_capture_trigger -v

REM 应用自检（包含拍照触发助手与 Remoting 通道信息）
python main.py --self-check
python main.py --page camera          REM 直接打开一键相机页（截图/演示用）
```

## 五、限制与未验证项

1. **未在真实展台 + 真机 EasiCamera 上验证**（本机无展台硬件）：拍照按钮的 UIA 名称/AutomationId 依据本地化文案与 UI 类推断，需真机确认；按钮找不到时可用「检测拍照按钮」拿到诊断信息反馈调整。
2. UIA 只能点击**当前渲染出的**界面；若 EasiCamera 最小化到托盘且未创建窗口，会提示未找到窗口。
3. Remoting 备用通道受 25 秒门控，仅作诊断；`Key5` 是四个版本服务端 `HandleCameraHidMessage` 中映射到 `CaptureImage` 的 HidMessage 值（代码证据），真机仍以 UIA 为准。
4. 相机页面显示「延时拍照」等按钮已排除，避免误触。
