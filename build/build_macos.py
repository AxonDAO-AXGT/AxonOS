#!/usr/bin/env python3
"""
Build script for creating AxonOS Launcher DMG package for macOS
"""

# MIT License
#
# Copyright (c) 2025 Avimanyu Bandyopadhyay
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

def check_macos():
    """Check if we're running on macOS"""
    if platform.system() != "Darwin":
        print("Error: This script must be run on macOS")
        sys.exit(1)

def install_dependencies():
    """Install required dependencies"""
    try:
        import PyInstaller
        print("✓ PyInstaller already installed")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller installed")
    
    # Check for create-dmg
    if shutil.which('create-dmg') is None:
        print("Installing create-dmg...")
        subprocess.check_call(['brew', 'install', 'create-dmg'])
        print("✓ create-dmg installed")

def build_macos_app():
    """Build the macOS .app bundle"""
    print("Building macOS app bundle...")
    
    # Create spec file for macOS
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['axonos_launcher/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('axonos_launcher/README.md', '.'),
    ],
    hiddenimports=['yaml', 'yaml.loader', 'yaml.dumper'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='axonos',
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
)

app = BUNDLE(
    exe,
    name='AxonOS Launcher.app',
    icon=None,
    bundle_identifier='org.axonos.launcher',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleDisplayName': 'AxonOS Launcher',
        'CFBundleName': 'AxonOS Launcher',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'AxonOS Configuration',
                'CFBundleTypeIconFile': 'MyDocument.icns',
                'LSItemContentTypes': ['org.axonos.config'],
                'LSHandlerRank': 'Owner'
            }
        ]
    },
)'''
    
    with open("axonos_launcher.spec", "w") as f:
        f.write(spec_content)
    
    # Build with PyInstaller
    cmd = ["pyinstaller", "--clean", "--noconfirm", "axonos_launcher.spec"]
    
    try:
        subprocess.check_call(cmd)
        print("✓ macOS app bundle built successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Build failed: {e}")
        return False
    finally:
        # Clean up spec file
        if os.path.exists("axonos_launcher.spec"):
            os.remove("axonos_launcher.spec")

def create_dmg():
    """Create DMG package"""
    print("Creating DMG package...")
    
    app_path = "dist/AxonOS Launcher.app"
    dmg_name = "AxonOS-Launcher-0.1.0-macOS-x86_64.dmg"
    
    if not os.path.exists(app_path):
        print(f"✗ App bundle not found at {app_path}")
        return False
    
    # Create DMG using create-dmg
    cmd = [
        'create-dmg',
        '--volname', 'AxonOS Launcher',
        '--window-pos', '200', '120',
        '--window-size', '600', '400',
        '--icon-size', '100',
        '--icon', 'AxonOS Launcher.app', '175', '120',
        '--hide-extension', 'AxonOS Launcher.app',
        '--app-drop-link', '425', '120',
        dmg_name,
        app_path
    ]
    
    try:
        subprocess.check_call(cmd)
        print(f"✓ DMG package created: {dmg_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ DMG creation failed: {e}")
        return False

def create_install_instructions():
    """Create installation instructions for macOS"""
    instructions = """AxonOS Launcher - macOS Installation
=====================================

1. Download the DMG file
2. Double-click to mount the DMG
3. Drag "AxonOS Launcher.app" to your Applications folder
4. Launch from Applications or Spotlight

Alternative installation:
- Right-click the app and select "Open" to bypass Gatekeeper
- Or run: sudo spctl --master-disable (not recommended)

Requirements:
- macOS 10.14 or later
- Python 3.6+ (included)
- Docker Desktop for Mac
- Git (for auto-clone feature)

Usage:
- Launch from Applications folder
- Or run from terminal: /Applications/AxonOS\\ Launcher.app/Contents/MacOS/axonos
"""
    
    with open("dist/MACOS_INSTALL.txt", "w") as f:
        f.write(instructions)

def main():
    """Main build function"""
    print("🍎 AxonOS Launcher macOS Build System")
    print("=" * 40)
    
    # Check if we're on macOS
    check_macos()
    
    # Check if we're in the right directory
    if not os.path.exists("axonos_launcher/main.py"):
        print("✗ Error: axonos_launcher/main.py not found")
        print("Please run this script from the AxonOS root directory")
        sys.exit(1)
    
    # Install dependencies
    install_dependencies()
    
    # Build the app
    if not build_macos_app():
        sys.exit(1)
    
    # Create DMG
    if not create_dmg():
        sys.exit(1)
    
    # Create installation instructions
    create_install_instructions()
    
    print("\n🎉 macOS build completed successfully!")
    print("Files created:")
    print("- dist/AxonOS Launcher.app (App bundle)")
    print("- AxonOS-Launcher-0.1.0-macOS.dmg (DMG package)")
    print("- dist/MACOS_INSTALL.txt (Installation instructions)")

if __name__ == "__main__":
    main() 