# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['argon2.low_level'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cryptography.x509', 'cryptography.openssl', 'cryptography.hazmat.primitives.serialization.ssh', 'tkinter', 'pygame', 'numpy', 'matplotlib', 'pandas', 'scipy', 'PIL', 'PyQt5', 'PyQt6', 'PySide2', 'hermes_agent'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SafeNotes',
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
    icon=['assets/icon.ico'],
)
