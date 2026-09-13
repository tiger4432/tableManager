# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['desktop_wrapper.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# 🔴 ONEDIR, NOT ONEFILE. Onefile packs everything into the exe and unpacks 5,817 files
# (~245 MB) into %TEMP%\_MEI* on EVERY launch. MEASURED 2026-08-25: the onefile build never
# reached a window in four minutes -- the process stayed alive at 12 MB RSS, which is the
# bootloader still unpacking, not Qt starting. `--print-target` returned correctly, so the
# Python inside was fine; only the unpack was fatal. Onedir has no unpack step: the exe sits
# next to its files and starts immediately. It ships as one zip, so the download is unchanged.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AssyManagerClient',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AssyManagerClient',
)
