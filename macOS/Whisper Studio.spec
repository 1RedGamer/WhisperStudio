# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

spec_dir = Path(os.path.abspath(SPECPATH))

datas = [
    (str(spec_dir / 'wispr.png'), '.'),
    (str(spec_dir / 'app_icon_black.png'), '.')
]
binaries = [
    (str(spec_dir / 'ffmpeg'), '.'),
    (str(spec_dir / 'libtouchbar.dylib'), '.')
]
hiddenimports = []

for mod in ['PyQt6', 'docx', 'huggingface_hub', 'mlx_whisper', 'mlx', 'psutil']:
    tmp_ret = collect_all(mod)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    [str(spec_dir / 'whisper_studio.py')],
    pathex=[str(spec_dir)],
    binaries=binaries,
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
    name='Whisper Studio',
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
    icon=[str(spec_dir / 'AppIcon.icns')],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Whisper Studio',
)

app = BUNDLE(
    coll,
    name='Whisper Studio.app',
    icon=str(spec_dir / 'AppIcon.icns'),
    bundle_identifier='com.whisperstudio.app',
    info_plist={
        'CFBundleDisplayName': 'Whisper Studio',
        'CFBundleName': 'Whisper Studio',
        'CFBundleIdentifier': 'com.whisperstudio.app',
        'CFBundleVersion': '2.7.5',
        'CFBundleShortVersionString': '2.7.5',
        'CFBundleIconFile': 'AppIcon.icns',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '13.0',
    },
)
