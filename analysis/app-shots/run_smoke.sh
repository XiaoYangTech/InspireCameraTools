#!/usr/bin/env bash
# 亿方展台管家 —— 全量自测脚本
# 运行：cd D:/开发/SeewoCamera && bash analysis/app-shots/run_smoke.sh > analysis/app-shots/smoke.log 2>&1
set -u
export PYTHONIOENCODING=utf-8
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/InspireCameraTools"
PY="D:/Software/python314/python.exe"
OUT="$ROOT/analysis/app-shots"
cd "$APP" || exit 1

section() { echo; echo "=================================================================="; echo "## $*"; echo "=================================================================="; }

echo "# 亿方展台管家（InspireCameraTools）全量自测日志"
echo "# 生成时间：$(date '+%Y-%m-%d %H:%M:%S %z')"
echo "# 工作目录：$ROOT"
echo "# Python：$($PY --version 2>&1)"
echo "# 系统：$(cmd //c ver 2>/dev/null | tr -d '\r')"
echo "# 依赖：ttkbootstrap 1.20.2 / requests / pillow（见 requirements.txt）"

section "1. 源码语法编译检查"
$PY -m compileall -q main.py app core assets/gen_assets.py build/build.py && echo "compileall: OK" || echo "compileall: FAIL"

section "2. 冒烟测试 main.py --smoke-test（要求 <8 秒退出码 0）"
start=$(date +%s%N)
$PY main.py --smoke-test
code=$?
end=$(date +%s%N)
echo "退出码：$code，耗时：$(( (end - start) / 1000000 )) ms"

section "3. 自动关闭 / 后台模式"
$PY main.py --auto-close 3; echo "auto-close 退出码：$?"
$PY main.py --background --auto-close 3; echo "background 退出码：$?"
$PY main.py --version

section "4. 七个页面创建/切换/截图"
$PY -X faulthandler ../analysis/app-shots/test_pages.py

section "5. 一键补丁全链路（4229 官方文件临时副本：检测→应用→恢复）"
$PY -X faulthandler ../analysis/app-shots/test_patch_flow.py

section "6. 历史版本下载全链路（官方 API 列表 + 完整下载 + 断点续传）"
$PY -X faulthandler ../analysis/app-shots/test_download.py

section "7. 降级场景：无展台 HID 操作"
$PY -X faulthandler ../analysis/app-shots/test_degrade.py hid

section "8. 降级场景：补丁引擎缺失"
$PY -X faulthandler ../analysis/app-shots/test_degrade.py patch-degrade

section "9. 降级场景：自动更新模块缺失"
$PY -X faulthandler ../analysis/app-shots/test_degrade.py update-degrade

section "10. 降级场景：断网下载页"
$PY -X faulthandler ../analysis/app-shots/test_degrade.py net-degrade

section "11. 破坏自动更新页 UI 集成（检测/执行/还原，本机未安装 EasiCamera）"
$PY -X faulthandler ../analysis/app-shots/test_autoupdate_ui.py

section "12. HID 模块自检 + 当前设备枚举"
$PY - <<'EOF'
import json, sys
sys.path.insert(0, ".")
from core import hid, sysinfo
print("HID_AVAILABLE:", hid.HID_AVAILABLE)
print("HIDP_CAPS sizeof:", __import__("ctypes").sizeof(hid.HIDP_CAPS))
print("frame parse:", hid.parse_input_frame(bytes((0xAA, 0xBB, 0xCC, 0x02, 0x02, 0x02, 0x00, 0x01, 0x32, 0x00))).description)
print("HID selftest:", json.dumps(hid.self_test(), ensure_ascii=False)[:500])
print("camera status:", json.dumps(sysinfo.detect_camera_status().__dict__, ensure_ascii=False, default=str)[:300])
print("EasiCamera dirs:", sysinfo.find_easicamera_dirs())
print("EasiCamera processes:", sysinfo.find_easicamera_processes())
print("startup command:", __import__("core.startup", fromlist=["x"]).get_autostart_command())
print("autostart enabled:", __import__("core.startup", fromlist=["x"]).is_autostart_enabled())
EOF

section "12b. 补丁引擎四版本规则只读检测（不写盘）"
$PY - <<'EOF'
import sys
sys.path.insert(0, ".")
from core import patch_engine
dirs = {
    "2.0.10.4087": "../extracted/v20240912161108/EasiCamera_2.0.10.4087/Main",
    "2.0.10.3816": "../extracted/v2.0.10.3816/EasiCamera_2.0.10.3816/Main",
    "2.0.10.4229": "../extracted/v2.0.10.4229/EasiCamera_2.0.10.4229/Main",
    "2.1.0.4419": "../extracted/v2.1.0.4419/EasiCamera_2.1.0.4419/Main",
}
for label, path in dirs.items():
    detected = patch_engine.detect_version(path)
    if detected is None:
        print(f"{label}: 未识别（FAIL）")
        continue
    avail = patch_engine.list_features(detected.version, path)
    usable = [item.feature.id for item in avail if item.available and not item.already_patched]
    print(f"{label}: {detected.display_name} 可用功能 {len(usable)} 个 -> {usable}")
EOF

section "13. 打包工具检查（PyInstaller 已安装；完整打包日志见 build.log）"
$PY -m PyInstaller --version && echo "PyInstaller 已安装"
echo "打包命令：$PY build/build.py（产物 dist/InspireCameraTools/InspireCameraTools.exe）"

section "14. 注册表 / 系统污染检查（测试期间不应写 HKCU Run）"
$PY - <<'EOF'
import winreg
try:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
    try:
        print("HKCU Run InspireCameraTools =", winreg.QueryValueEx(key, "InspireCameraTools"))
    except FileNotFoundError:
        print("HKCU Run: 未写入 InspireCameraTools 自启项（符合预期）")
except OSError as exc:
    print("读取注册表失败：", exc)
EOF

section "15. 一键相机开机自启命令 + 后台模式/自动恢复监听（不写注册表）"
$PY -X faulthandler ../analysis/app-shots/test_background.py

section "16. 高 DPI 专项：模拟 125% 缩放"
$PY -X faulthandler ../analysis/app-shots/test_highdpi.py 1.25

section "17. 高 DPI 专项：模拟 150% 缩放"
$PY -X faulthandler ../analysis/app-shots/test_highdpi.py 1.5

section "18. PyInstaller 打包产物验证（dist/InspireCameraTools）"
EXE="dist/InspireCameraTools/InspireCameraTools.exe"
if [ -f "$EXE" ]; then
  echo "产物：$EXE（$(stat -c%s "$EXE") 字节，合计 $(du -sh dist/InspireCameraTools | cut -f1)）"
  "$EXE" --version; echo "--version 退出码：$?"
  "$EXE" --self-check; echo "--self-check 退出码：$?"
  "$EXE" --smoke-test; echo "--smoke-test 退出码：$?"
else
  echo "未找到打包产物，请先运行：$PY build/build.py"
fi

section "自测结论"
echo "全部步骤执行完毕；各步骤 PASS/FAIL 见上文与 analysis/app-shots/ 下截图。"
