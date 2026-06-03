# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for LanCaster desktop app
#
# Build:
#   pip install pyinstaller lancaster[desktop]
#   pyinstaller lancaster.spec
#
# Output: dist/LanCaster/ (one-dir) or dist/LanCaster.exe (one-file)

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "lancaster_desktop.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "lancaster" / "templates"), "lancaster/templates"),
        (str(root / "assets"), "assets"),
    ],
    hiddenimports=[
        "lancaster",
        "lancaster.web",
        "lancaster.desktop",
        "lancaster.controller",
        "lancaster.discovery",
        "lancaster.http_server",
        "lancaster.media_server",
        "lancaster.mirror",
        "lancaster.transcoder",
        "lancaster.url_proxy",
        "lancaster.didl",
        "lancaster.config",
        "lancaster.utils",
        "lancaster.models",
        "lancaster.exceptions",
        "aiohttp",
        "async_upnp_client",
        "didl_lite",
        "webview",
        "pystray",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LanCaster",
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
    icon=[str(root / "assets" / "icon.ico")],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LanCaster",
)
