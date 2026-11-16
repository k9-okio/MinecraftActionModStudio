from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "run_studio.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "standalone_studio" / "templates"), "standalone_studio/templates"),
        (str(root / "standalone_studio" / "blender_extract.py"), "standalone_studio"),
    ],
    hiddenimports=[
        "OpenGL.platform.win32",
        "pyqtgraph.opengl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtPdf",
        "PySide6.QtMultimedia",
        "PySide6.QtQuick3D",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MinecraftActionModStudio",
    icon=str(root / "standalone_studio" / "assets" / "studio.ico"),
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MinecraftActionModStudio",
)
