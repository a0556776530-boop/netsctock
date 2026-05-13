# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for NetStock — single-file Windows EXE.

Build with:
    pyinstaller --clean netstock.spec
"""

import sys
from pathlib import Path

block_cipher = None

# ── Data files (templates + static assets) ──────────────────────────────────
# Destination paths must match what Flask expects when __name__ == 'app':
#   Flask root  = sys._MEIPASS/app/
#   templates   = sys._MEIPASS/app/templates/
#   static      = sys._MEIPASS/app/static/
datas = [
    ('app/templates', 'app/templates'),
    ('app/static',    'app/static'),
]

# ── Hidden imports ────────────────────────────────────────────────────────────
# PyInstaller static analysis misses these — list them explicitly.
hidden_imports = [
    # SQLAlchemy
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.dialects.sqlite.pysqlite',
    'sqlalchemy.ext.baked',
    # Flask ecosystem
    'flask_sqlalchemy',
    'flask_migrate',
    'flask_login',
    'flask_bcrypt',
    'flask_mail',
    'flask_wtf',
    'flask_wtf.csrf',
    'wtforms',
    'wtforms.validators',
    'wtforms.fields',
    'wtforms.fields.core',
    'wtforms.fields.simple',
    # Email validation
    'email_validator',
    'dns',
    'dns.resolver',
    # Jinja2 / Werkzeug internals
    'jinja2.ext',
    'werkzeug.routing',
    'werkzeug.middleware.proxy_fix',
    # python-dotenv
    'dotenv',
    # itsdangerous (used by Flask session / CSRF)
    'itsdangerous',
    # click (used by Flask CLI)
    'click',
    # bcrypt
    'bcrypt',
    # alembic (Flask-Migrate)
    'alembic',
    'alembic.runtime.migration',
    'alembic.operations',
]

a = Analysis(
    ['netstock_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Test frameworks — not needed at runtime
        'pytest', 'unittest', '_pytest',
        # GUI toolkits
        'tkinter', 'PyQt5', 'PyQt6', 'wx',
        # Heavy scientific libs sometimes pulled in transitively
        'numpy', 'pandas', 'matplotlib',
    ],
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
    name='NetStock',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # compress with UPX if available, shrinks EXE size
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # keep console so the user can see server logs / errors
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # set to 'app/static/favicon.ico' if you have one
)
