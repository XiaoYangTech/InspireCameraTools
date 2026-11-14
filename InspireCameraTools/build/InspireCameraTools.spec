# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('D:/开发/SeewoCamera/InspireCameraTools/assets', 'assets')]
hiddenimports = ['PIL._tkinter_finder']
datas += collect_data_files('ttkbootstrap')
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('core')
hiddenimports += collect_submodules('core.rules')


a = Analysis(
    ['D:/开发/SeewoCamera/InspireCameraTools/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InspireCameraTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:/开发/SeewoCamera/InspireCameraTools/assets/app.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='InspireCameraTools',
)
