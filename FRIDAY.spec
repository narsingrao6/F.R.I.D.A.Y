# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

extra_datas = collect_data_files('onnxruntime') + collect_data_files('speech_recognition')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/dist', 'ui/dist'), ('models', 'models')] + extra_datas,
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.edgehtml',
        'numpy',
        'speech_recognition',
        'pygame',
        'edge_tts',
        'groq',
        'google.genai',
        'ollama',
        'requests',
        'onnxruntime',
        'pyaudio',
        'pyttsx3',
        'pc_control',
        'browser',
        'messaging',
        'tools',
        'tools.computer_use',
        'tools.computer_use.screen',
        'tools.computer_use.ocr',
        'tools.computer_use.vision',
        'tools.computer_use.mouse',
        'tools.computer_use.keyboard',
        'tools.computer_use.agent',
    ],
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
    name='FRIDAY',
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
    name='FRIDAY',
)
