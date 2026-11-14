import io

# 1) 修掉 patch_page.py docstring 里的非法转义（用原始字符串拼装，避免层层转义）
p = r'D:\开发\SeewoCamera\InspireCameraTools\app\patch_page.py'
s = io.open(p, encoding='utf-8').read()
bad_line = [ln for ln in s.splitlines() if 'EasiCamera_2.1.0.4419' in ln]
assert bad_line, 'target line not found'
old = bad_line[0]
new = r'    * 粘贴版本目录（...\EasiCamera_2.1.0.4419）或安装根目录（自动向下找 Main）；'
s = s.replace(old, new)
io.open(p, 'w', encoding='utf-8').write(s)
print('docstring line:', new)

# 2) camera_page 移除未使用的 sysinfo 导入（热键已删除）
p = r'D:\开发\SeewoCamera\InspireCameraTools\app\camera_page.py'
s = io.open(p, encoding='utf-8').read()
s = s.replace('from core import capture_trigger, hid, settings, startup, sysinfo',
              'from core import capture_trigger, hid, settings, startup')
io.open(p, 'w', encoding='utf-8').write(s)
print('camera_page import cleaned')
