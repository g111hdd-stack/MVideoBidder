# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.building.datastruct import Tree
import os
import ast

block_cipher = None
project_dir = Path(os.getcwd())

with open("config.py", "r", encoding="utf-8") as f:
    tree = ast.parse(f.read(), filename="config.py")

VERSION = "0.0.0"
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if getattr(target, "id", None) == "VERSION":
                VERSION = ast.literal_eval(node.value)

data_files = []

if (project_dir / "chrome.png").exists():
    data_files.append((str(project_dir / "chrome.png"), "."))

if (project_dir / "info.png").exists():
    data_files.append((str(project_dir / "info.png"), "."))

hiddenimports = [
    "app.gui_main",
    "app.gui_worker",
    "app.log_window",
    "database.db",
    "database.models",
    "domain.dtos",
    "utils.app_logger",
    "web_driver.wd",
    "web_driver.create_extension_proxy",

    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.common",
    "selenium.webdriver.common.by",
    "selenium.webdriver.common.driver_finder",
    "selenium.webdriver.common.options",
    "selenium.webdriver.common.service",
    "selenium.webdriver.common.selenium_manager",
    "selenium.webdriver.firefox",
    "selenium.webdriver.firefox.webdriver",
    "selenium.webdriver.firefox.options",
    "selenium.webdriver.firefox.service",
    "selenium.webdriver.support",
    "selenium.webdriver.support.ui",
    "selenium.webdriver.support.expected_conditions",
    "selenium.common",
    "selenium.common.exceptions",
]

a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=data_files,
    hiddenimports=hiddenimports,
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
    name="MVideoBidder_" + str(VERSION),
    debug=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    Tree(str(project_dir / "browser"), prefix="browser"),
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MVideoBidder",
)