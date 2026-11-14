import io

BASE = r'D:\开发\SeewoCamera\InspireCameraTools'

# ============ 1) cloud.py：设备标识 ict 前缀（含旧 le_ 迁移）；匿名上报不再可关闭 ============
p = BASE + r'\core\cloud.py'
s = io.open(p, encoding='utf-8').read()

s = s.replace('''隐私：上报内容仅设备随机标识、系统描述、计算机名，不含账号和个人信息；
可在「设置与关于」页关闭匿名统计（关闭后仅不再发 ``client_ping``）。''',
'''隐私：上报内容仅设备随机标识、系统描述、计算机名，不含账号和个人信息。''')

s = s.replace('''#: 设备标识格式（文档要求 ^[A-Za-z0-9_-]{16,100}$）
DEVICE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,100}$")''',
'''#: 设备标识格式（文档要求 ^[A-Za-z0-9_-]{16,100}$）
DEVICE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,100}$")
#: 设备标识前缀（本应用：ict）
DEVICE_KEY_PREFIX = "ict_"


def is_valid_device_key(key: str) -> bool:
    """设备标识必须符合格式且以 ``ict_`` 开头（旧版 le_ 前缀会被迁移）。"""
    return bool(DEVICE_KEY_RE.match(key or "")) and str(key).startswith(DEVICE_KEY_PREFIX)''')

s = s.replace('''def _generate_device_key() -> str:
    """生成随机设备标识：``le_`` + 32 位十六进制（35 字符，符合文档格式）。"""
    return "le_" + secrets.token_hex(16)''',
'''def _generate_device_key() -> str:
    """生成随机设备标识：``ict_`` + 32 位十六进制（36 字符，符合文档格式）。"""
    return DEVICE_KEY_PREFIX + secrets.token_hex(16)''')

s = s.replace('''    key = str(settings.get("cloud_device_key") or "").strip()
    if DEVICE_KEY_RE.match(key):
        return key''',
'''    key = str(settings.get("cloud_device_key") or "").strip()
    if is_valid_device_key(key):
        return key''')

s = s.replace('''def ping() -> bool:
    """匿名上报一次（仅在设置允许时）；成功返回 True。"""
    if not bool(settings.get("cloud_report_enabled", True)):
        return False
    key = ensure_device_key()''',
'''def ping() -> bool:
    """匿名上报一次；成功返回 True（失败静默）。"""
    key = ensure_device_key()''')

s = s.replace('''    return {
        "slug": APP_SLUG,
        "base_url": BASE_URL,
        "device_key": ensure_device_key(),
        "report_enabled": bool(settings.get("cloud_report_enabled", True)),
        "last_ping": int(settings.get("cloud_last_ping") or 0),
        "current_version": settings.APP_VERSION,
    }''',
'''    return {
        "slug": APP_SLUG,
        "base_url": BASE_URL,
        "device_key": ensure_device_key(),
        "last_ping": int(settings.get("cloud_last_ping") or 0),
        "current_version": settings.APP_VERSION,
    }''')
io.open(p, 'w', encoding='utf-8').write(s)
print('cloud.py patched')

# ============ 2) settings.py：去掉 cloud_report_enabled；版本 1.1.1 ============
p = BASE + r'\core\settings.py'
s = io.open(p, encoding='utf-8').read()
s = s.replace('APP_VERSION = "1.1.0"', 'APP_VERSION = "1.1.1"')
s = s.replace('''    # 是否参与匿名统计（仅上报随机设备标识/系统描述/设备名，不含个人信息）
    "cloud_report_enabled": True,
''', '')
io.open(p, 'w', encoding='utf-8').write(s)
print('settings.py patched')

# ============ 3) main.py 版本 ============
p = BASE + r'\main.py'
s = io.open(p, encoding='utf-8').read()
s = s.replace('APP_VERSION = "1.1.0"', 'APP_VERSION = "1.1.1"')
io.open(p, 'w', encoding='utf-8').write(s)
print('main.py patched')
