# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — IRIS.exe thin launcher only (stdlib + subprocess)

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

# 시스템 site-packages 오염 방지 — 런처는 stdlib만 필요
_EXCLUDES = [
    "numpy", "torch", "torchvision", "torchaudio", "cv2", "PIL", "Pillow",
    "matplotlib", "scipy", "pandas", "sklearn", "onnxruntime", "numba",
    "pynput", "comtypes", "PyQt6", "PySide6", "tkinter", "IPython",
    "jupyter", "notebook", "llvmlite", "h5py", "sympy", "cryptography",
    "win32com", "pythoncom", "pywintypes", "setuptools", "pkg_resources",
    "iris",  # frozen에 앱 코드 넣지 않음 — .venv -m iris
]

a = Analysis(
    [str(root / "IRIS_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="IRIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "iris" / "assets" / "iris_icon.ico"),
    version=str(root / "iris" / "assets" / "iris_version_info.txt"),
)
