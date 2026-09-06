# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

qt_excludes = [
    'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
    'PyQt5.sip', 'tkinter', '_tkinter'
]

hidden_imports = [
    'win32com.client', 'dns', 'tqdm', 'bs4', 'fitz', 'pytesseract',
    'striprtf', 'patoolib', 'pptx', 'docx', 'pandas', 'openpyxl',
    'lxml', 'lxml.etree', 'lxml.objectify', 'pdfminer', 'pypdfium2',
    'requests', 'urllib3', 'certifi'
]

# ========== 1. ENGINE ==========
a_eng = Analysis(
    ['tender_auto.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('templates', 'templates'),
        ('license', 'license'),
        ('brands_extra.txt', '.'),
        ('secrets.txt', '.')
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_eng = PYZ(a_eng.pure, a_eng.zipped_data, cipher=block_cipher)
exe_eng = EXE(
    pyz_eng,
    a_eng.scripts,
    [],
    exclude_binaries=True,
    name='tender_auto',
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
coll_eng = COLLECT(
    exe_eng,
    a_eng.binaries,
    a_eng.zipfiles,
    a_eng.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='app_engine',
    contents_directory='engine_internal'
)

# ========== 2. SAMPLER ==========
a_samp = Analysis(
    ['sampler.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_samp = PYZ(a_samp.pure, a_samp.zipped_data, cipher=block_cipher)
exe_samp = EXE(
    pyz_samp,
    a_samp.scripts,
    [],
    exclude_binaries=True,
    name='sampler',
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
coll_samp = COLLECT(
    exe_samp,
    a_samp.binaries,
    a_samp.zipfiles,
    a_samp.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='app_sampler',
    contents_directory='sampler_internal'
)

# ========== 3. GUI ==========
a_gui = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports + ['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name='TenderAuto',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)
coll_gui = COLLECT(
    exe_gui,
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='app_gui',
    contents_directory='gui_internal'
)