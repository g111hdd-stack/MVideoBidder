# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.building.datastruct import Tree
import ast
import pkg_resources

block_cipher = None
project_dir = Path(os.getcwd())

# Читаем версию из config.py
with open('config.py', 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read(), filename='config.py')

VERSION = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if getattr(target, "id", None) == "VERSION":
                VERSION = ast.literal_eval(node.value)

data_files = [
    ('chrome.png', '.'),
    ('info.png', '.'),
]

packages = []
with open('requirements.txt', 'r', encoding='utf-8') as f:
    for line in f:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        try:
            req = pkg_resources.Requirement.parse(s)
            packages.append(str(req.project_name))
        except Exception as e:
            print(f"skip {s}: {e}")

a = Analysis(
    ['main.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=data_files,
    hiddenimports=packages,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ProxyBrowser ' + str(VERSION),
    debug=False,
    console=False,   # True -> видеть ошибки в консоли
    icon='chrome.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    Tree(str(project_dir / 'browser'), prefix='browser'),
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ProxyBrowser',
)
