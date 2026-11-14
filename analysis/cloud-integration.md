# 亿方智云（InspireWorksCloud）接入说明

> 依据：`D:\开发\InspireWorksCloud\docs\api-reference.md`（亿方智云 客户端 API 参考）
> 应用：亿方展台管家（`slug = ict`）· Base URL：`https://api.yfyw.top/apps/ict/api.php`
> 接入范围（按需求）：**传统手动更新**（`app_info`）、**启动弹窗公告**（`popup`）、**匿名上报**（`client_ping`）。
> 不接入：`app_update`（自动更新安装包）、例程 `routines`、轮播 `banners`、以及附录 B 已下线条目。

## 一、实现位置

| 文件 | 内容 |
|---|---|
| `InspireCameraTools/core/cloud.py` | 云客户端：请求封装、设备标识、匿名上报循环、弹窗去重、版本比较、状态查询 |
| `InspireCameraTools/app/app_window.py` | 启动后 1.2s 后台拉取 `popup`/`app_info`；弹窗公告与更新提示对话框；匿名上报循环随窗口关闭停止 |
| `InspireCameraTools/app/settings_page.py` | 「亿方智云（更新与公告）」卡片：当前版本/最新版本/匿名统计开关/设备标识/手动「检查更新」 |
| `InspireCameraTools/core/settings.py` | 新增配置：`cloud_device_key`、`cloud_report_enabled`、`cloud_popup_seen`、`cloud_skip_version`、`cloud_last_ping` |
| `InspireCameraTools/tests/test_cloud.py` | 13 个离线单测（版本比较、设备标识、弹窗去重、上报字段、失败降级） |

## 二、接口行为

### 1. 匿名上报 `client_ping`
- 启动后延迟 3s 首次上报，之后每 **8 分钟**一次（文档建议值，小于后台在线判定 10 分钟）；失败静默重试，不阻塞界面。
- 请求体仅：`device_key`（`le_` + 32 位十六进制，首次生成后持久化，符合 `^[A-Za-z0-9_-]{16,100}$`）、`os`（系统描述 ≤80 字符）、`device_name`（计算机名 ≤80 字符）。
- 「设置与关于」页可关闭匿名统计（`cloud_report_enabled=false`），关闭后不再发送 `client_ping`；公告与更新检查不受影响。
- 实测：`client_ping` 返回 `{"ok":true,"data":{"online":true,...}}`。

### 2. 启动弹窗公告 `popup`
- 启动后后台获取，返回 0 或 1 条；文本型显示正文，链接型提供「打开链接」按钮（系统浏览器）。
- 「今日不再显示」由客户端记录：`cloud_popup_seen = {弹窗id: 日期}`，同一天同一条不再弹（保留 30 条）。
- 实测（2026-11-14）：`popup` 返回 `[]`（后台暂无弹窗公告），应用不会弹窗。

### 3. 传统手动更新 `app_info`
- 启动后后台比对 `latest_version`（忽略 `v` 前缀、按数字段比较），有新版本才提示；提示只提供「前往下载」打开网页（`latest_download_url`，缺省回退 GitHub Releases 页），**不做自动下载/安装**。
- 可选择「跳过此版本」（`cloud_skip_version`），同一版本不再重复提示。
- 「设置与关于 → 亿方智云」卡片提供手动「检查更新」，显示云端最新版本；云端无版本记录时提示「已是最新」。
- 实测（2026-11-14）：`app_info` 返回 `{"id":5,"name":"亿方展台管家","slug":"ict","latest_version":"","latest_release_date":null}`，当前无版本记录 → 不提示更新。

## 三、发布版本（让更新检查生效）

后台「版本管理」新增版本记录（或走 CI/CD `ci_publish`），只做手动更新时填 `version` + `page_url` 即可，例如：

```bash
curl -sS -X POST "https://api.yfyw.top/api.php?route=ci_publish" \
  -H "Content-Type: application/json" \
  -H "X-Release-Token: <后台设置里的发布令牌>" \
  -d '{
    "slug": "ict",
    "version": "v1.1.0",
    "release_date": "2026-11-14",
    "changelog": "接入亿方智云：匿名统计、启动公告、手动检查更新；一键相机改为 UI 自动化触发拍照；修复登录按钮补丁与补丁页粘贴路径检测。",
    "page_url": "https://github.com/XiaoYangTech/InspireCameraTools/releases/tag/v1.1.0"
  }'
```

> 只传 `version` + `page_url`（不传 `assets`）= 传统手动更新流程；客户端会提示新版本并打开该网页。

## 四、隐私与容错

- 上报内容不含账号、个人信息、文件内容；接口免登录、无令牌、无配额。
- 所有云请求 4s/8s 超时并捕获全部异常；接口不可用（404 网关页、连接关闭、非 JSON）均按「不可用」静默降级，绝不影响主功能。
- `smoke-test` / `--self-check` 不发起网络请求；自检只校验模块可导入、Base URL 与设备标识格式。

## 五、验证记录

```bat
REM 单元测试（离线）
cd InspireCameraTools && python -m unittest tests.test_cloud -v

REM 应用自检（联网检查包含在 cloud 模块单测中；自检本身不联网）
python main.py --self-check

REM 真实接口冒烟（本机已执行，2026-11-14）
python -c "from core import cloud; print(cloud.get_popup(), cloud.get_app_info(), cloud.check_update('1.0.1'), cloud.ping())"
```
