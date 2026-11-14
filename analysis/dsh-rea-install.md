# DSH-REA 插件安装记录

> 目标：在**当前** DeepSeek Harness 桌面版中安装 REA（Reverse Engineer Anything）逆向插件。
> 结果：**已安装并热加载成功**，无需重启本体；`rea` MCP 服务已在会话中可用（229 个 `mcp__rea__*` 工具）。

## 环境
- DSH 版本：0.2.1-rc.5（Electron 桌面版，cordis 插件系统）
- Profile：`C:\Users\Admin\.dsh\profiles\desktop`
- 插件包：`dsh-plugin-rea@2.0.18`（npm，作者 czcdr；第三方适配层，把上游 [REA](https://github.com/morluto/rea) MCP 服务接入 DSH）
  - 选择理由：npm 月下载量最高（~9600/月，同类 `dsh-rea` 约 3700），2.x 自带 Node/REA/JDK/Ghidra 运行时供给；engines.dsh `>=0.1.7-rc.2 <0.3.0-0` 与本机 0.2.1-rc.5 兼容。

## 安装步骤（实际执行）
1. **备份** profile 配置：`package.json`、`pnpm-lock.yaml`、`cordis.yml`、`cordis.patch.yml`
   → `C:\Users\Admin\.dsh\profiles\desktop\.plugin-manager\backup-lead-20261114-171650\`
2. **安装 npm 包**（profile 目录内，pnpm 11.28.5，registry=npmmirror）：
   ```
   node <runtime>/pnpm/bin/pnpm.cjs add dsh-plugin-rea@2.0.18 --save-exact
   ```
   结果：`dependencies.dsh-plugin-rea = "2.0.18"`；`node_modules/dsh-plugin-rea`（约 1MB，无依赖闭包）。
3. **启用 bundle**：在 `package.json` 的 `dsh.profile.bundles` 末尾追加 `"dsh-plugin-rea"`（原子写）。
   - DSH 的 HMR 监视 profile 配置，变更后自动重组合；插件 bundle 自带的 `cordis.patch.yml` 插入官方 MCP 客户端行 `mcp-rea`（`serverName: rea`，stdio，命令为当前 Node 可执行文件 + `bin/rea-shim.mjs`）。
4. **供给运行时**（插件 2.x 要求，一次性）：
   ```
   cd C:\Users\Admin\.dsh\profiles\desktop\node_modules\dsh-plugin-rea
   <node> scripts\setup.mjs --reuse
   ```
   - 根目录：`C:\Users\Admin\.dsh\plugins\rea-bundle`（cache + vendor + bundle.json + bin/rea-shim.mjs）
   - 组件：Node 24.22.1、Adoptium JDK 21.0.12.1+1、Ghidra 12.1.4、Apktool 3.0.3、jadx-headless-mcp 0.7.1、Android platform-tools、rea-agents 6.8.0（npm）、Frida 绑定
   - `--reuse` 探测到本机 PATH node v24.14.0 / JAVA_HOME JDK 版本过旧，均未被采纳，使用插件钉住的版本（符合预期）
   - 网络：setup 支持 `HTTPS_PROXY`/系统 WinINET 代理；Ghidra 543MB 官方包下载慢时，先自行用直连下载并按 SHA-256（`ddac49f9…d2d4db`，GitHub Release body 公布值）校验后放入 cache，再重跑 setup 复用（`using cached …`）——**最终所有组件 checksum 校验通过**
   - 完成后 `bundle.json` 记录全部路径/版本/哈希；`rea-shim.mjs --shim-status` 显示 `provisioned: true, bundleUsable: true`
5. **重连 MCP 行**：新增的 `mcp-rea` 行初次启动时 shim 尚未生成（disconnected）。由于 DSH HMR 会监视 profile patch 层，采用「临时禁用/恢复」触发组合重载，使该行用新 shim 重启并连接（无需重启 DSH 本体）。
6. **验证**：`mcp__rea__binary_session` 返回 `rea-agents 6.8.0`、229 个工具、Ghidra 12.1.4 × JDK 21 provider 全绿；`list_mcp_resources(rea)` 连接正常。
7. 清理：删除 `rea-bundle/cache` 下约 840MB 下载缓存（C 盘紧张），vendor 与 bundle.json 保留；最终占用约 1.7GB。

## 最终状态
| 项 | 值 |
|---|---|
| 插件包 | `dsh-plugin-rea@2.0.18`（profile dependencies + bundles 已启用） |
| 运行时根 | `C:\Users\Admin\.dsh\plugins\rea-bundle` |
| REA | rea-agents 6.8.0（MCP catalog：175 CLI / 229 MCP tools / 6 prompts） |
| 引擎 | Ghidra 12.1.4 + JDK 21.0.12.1（.NET/PE、Ghidra 原生、JADX、ADB、Frida、浏览器/Electron 等 provider 可用） |
| MCP 工具 | 本会话已可调用 `mcp__rea__*`（229 个） |
| 重启需求 | **不需要**（已热加载并连接）；若日后升级插件版本，需重跑 `setup.mjs` 并按插件 README 重启/重连 |
| 已知限制 | Windows 上原生 macOS 工具不可用（正常）；REA 对 .NET 只做静态元数据/CIL 分析（本项目 .NET 反编译仍以 ILSpy 为主，REA 作辅助） |

## 回滚方式（如需卸载）
1. 从 `package.json` 的 `dsh.profile.bundles` 移除 `dsh-plugin-rea`，并 `pnpm remove dsh-plugin-rea`
2. （可选）删除 `C:\Users\Admin\.dsh\plugins\rea-bundle`
3. 如需完全恢复配置：用备份目录覆盖 `package.json`、`pnpm-lock.yaml`、`cordis.yml`、`cordis.patch.yml`

## 备注
- 安装全程未重启 DSH 桌面端，未改动 `cordis.patch.yml` 的语义内容（临时触发文件已还原为与备份逐字节一致）。
- 唯一持久配置变化：profile `package.json` 增加 `dsh-plugin-rea` 依赖与 bundle 选择；`pnpm-workspace.yaml` 增加 pnpm 自动记录的 `minimumReleaseAgeExclude` 条目（pnpm 11 行为）。
