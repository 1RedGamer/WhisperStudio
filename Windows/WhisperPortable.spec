# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

spec_dir = Path(os.path.abspath(SPECPATH))

datas = [
    (str(spec_dir / 'wispr.png'), '.'),
    (str(spec_dir / 'wispr.ico'), '.'),
    (str(spec_dir / 'app_icon_black.png'), '.')
]
binaries = []
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'faster_whisper',
    'ctranslate2',
    'docx',
    'av',
    'huggingface_hub',
    'psutil'
]

for mod in ['PyQt6', 'docx', 'huggingface_hub', 'faster_whisper', 'ctranslate2', 'av']:
    tmp_ret = collect_all(mod)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# Collect NVIDIA CUDA libraries if available
try:
    import site
    for sp in site.getsitepackages():
        cublas_bin = Path(sp) / "nvidia" / "cublas" / "bin"
        if cublas_bin.is_dir():
            for dll in cublas_bin.glob("*.dll"):
                binaries.append((str(dll), '.'))
except Exception:
    pass

a = Analysis(
    [str(spec_dir / 'whisper_studio.py')],
    pathex=[str(spec_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter', 'tkinterdnd2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WhisperPortable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(spec_dir / 'wispr.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='WhisperPortable',
)
