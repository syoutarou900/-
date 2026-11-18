#!/bin/bash
# FormatPassport - build a macOS .app with PyInstaller
# Double-click this file in Finder on a Mac. The app is built into
#   dist/FormatPassport.app
# It first tries a universal2 build (runs on both Apple silicon and
# Intel Macs). If that fails, it retries for this Mac's own CPU only
# and tells you which kind was produced.
#
# Note: the built app is unsigned. To open it the first time,
# right-click (Control-click) the app and choose "Open".
set -u
cd "$(dirname "$0")"

echo "==============================================="
echo " FormatPassport - build macOS app"
echo "==============================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "Python 3 was not found on this Mac."
  echo "Please install Python 3 first, then run this file again:"
  echo "  https://www.python.org/downloads/macos/"
  echo "  (Download the universal2 macOS installer.)"
  echo ""
  echo "Press Enter to close this window."
  read -r _
  exit 1
fi

if [ ! -f app.py ]; then
  echo "app.py not found next to this file."
  echo "Please extract the whole ZIP first, then try again."
  echo "Press Enter to close this window."
  read -r _
  exit 1
fi

if [ ! -x .venv-build/bin/python ]; then
  echo "Creating the build environment (.venv-build)..."
  python3 -m venv .venv-build || {
    echo "Failed to create the Python environment."
    echo "Press Enter to close this window."
    read -r _
    exit 1
  }
fi

PY=.venv-build/bin/python

echo "Installing / updating build libraries..."
"$PY" -m pip install --upgrade pip >/dev/null 2>&1
"$PY" -m pip install PySide6 openpyxl pyinstaller || {
  echo "Failed to install libraries. Check your network connection."
  echo "Press Enter to close this window."
  read -r _
  exit 1
}

ARCH="$(uname -m)"
echo "This Mac's CPU: $ARCH"

build_app() {
  # $1 = extra target-arch args (may be empty)
  "$PY" -m PyInstaller --noconfirm --windowed --name FormatPassport --icon assets/icon.icns \
    --exclude-module tkinter $1 app.py
}

echo ""
echo "Trying a universal2 build (Apple silicon + Intel)..."
if build_app "--target-arch universal2" && [ -d dist/FormatPassport.app ]; then
  echo ""
  echo "==============================================="
  echo " Done: dist/FormatPassport.app"
  echo " Build type: universal2 (Apple silicon + Intel)"
  echo "==============================================="
else
  echo ""
  echo "universal2 build failed. Retrying for this Mac only ($ARCH)..."
  rm -rf build dist
  if build_app "" && [ -d dist/FormatPassport.app ]; then
    echo ""
    echo "==============================================="
    echo " Done: dist/FormatPassport.app"
    echo " Build type: $ARCH only (this Mac's CPU)"
    echo "==============================================="
  else
    echo ""
    echo "Build failed. See the messages above for details."
    echo "Press Enter to close this window."
    read -r _
    exit 1
  fi
fi

echo ""
echo "First launch of the built app: it is unsigned, so macOS may"
echo "block a plain double-click. Right-click (Control-click)"
echo "FormatPassport.app and choose \"Open\" once."
echo ""
echo "Press Enter to close this window."
read -r _
