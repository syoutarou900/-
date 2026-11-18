#!/bin/bash
# ContextStruct - build a standalone macOS app (ContextStruct.app)
#
# How to use (this is the standard way to get the Mac app):
#   1. Download the ContextStruct source ZIP and extract it.
#   2. Double-click this file:  MakeApp-Mac.command
#      (First time only: macOS may block it because it is unsigned.
#       Right-click the file -> "Open" -> "Open" to run it once.)
#   3. When the build finishes, the app appears in the "dist" folder:
#         dist/ContextStruct.app
#   4. From then on, just double-click ContextStruct.app to use it.
#      (The .app is also unsigned, so the first launch of the app
#       itself needs the same right-click -> "Open" once.)
#
# Notes:
#   * The bundled vlm_runtime/ in this package is the Windows llama.cpp
#     build and is NOT embedded into the Mac app (it cannot run on
#     macOS). The rule engine, OCR and all other features work in the
#     Mac app; only the built-in local VLM needs a macOS llama.cpp
#     build placed manually (see the README Mac chapter).
cd "$(dirname "$0")" || exit 1

echo "=== ContextStruct - build the macOS app ==="

# --- Python 3 check ------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "Python 3 was not found on this Mac."
  echo "Building the app needs Python 3. Please install it in one of"
  echo "these ways, then double-click this file again:"
  echo ""
  echo "  1) Download the installer from https://www.python.org/downloads/macos/"
  echo "     and run it (recommended for most users)."
  echo "  2) If you use Homebrew:  brew install python"
  echo "  3) Or run this in Terminal:  xcode-select --install"
  echo "     (installs Apple's Command Line Tools, which include Python 3)."
  echo ""
  read -r -p "Press Enter to close this window."
  exit 1
fi

PY=python3
echo "Using: $($PY --version 2>&1)"

# --- Virtual environment + build tools -----------------------------------
if [ ! -x ".venv-build/bin/python" ]; then
  echo "Preparing the build environment (first run only)..."
  $PY -m venv .venv-build || { echo "Failed to create the environment."; read -r -p "Press Enter to close."; exit 1; }
  .venv-build/bin/python -m pip install --upgrade pip >/dev/null 2>&1
  .venv-build/bin/python -m pip install -r requirements.txt pyinstaller || { echo "Failed to install the build tools. Check your network connection."; read -r -p "Press Enter to close."; exit 1; }
fi

HOST_ARCH="$(uname -m)"
echo "This Mac's chip: $HOST_ARCH"
echo "Building ContextStruct.app (this can take a few minutes)..."

# Try a universal2 build first (one app that runs on both Apple
# Silicon and Intel Macs). The python.org Python and PySide6 are
# universal2, so this normally succeeds. If this Mac's Python is
# single-architecture, the universal build fails and we fall back to
# a native build for this Mac's chip automatically.
BUILT_ARCH=""
if .venv-build/bin/python -m PyInstaller --noconfirm --windowed --name ContextStruct --icon assets/icon.icns --target-arch universal2 app.py; then
  BUILT_ARCH="universal2 (Apple Silicon + Intel)"
else
  echo ""
  echo "The universal2 build did not work on this Mac, so the app"
  echo "is being built for this Mac's chip only ($HOST_ARCH)."
  echo ""
  rm -rf dist build ContextStruct.spec
  if .venv-build/bin/python -m PyInstaller --noconfirm --windowed --name ContextStruct --icon assets/icon.icns app.py; then
    BUILT_ARCH="native ($HOST_ARCH only)"
  else
    echo "The build failed. See the messages above."
    read -r -p "Press Enter to close."
    exit 1
  fi
fi

echo ""
echo "Done! Your app is here:"
echo "  $(pwd)/dist/ContextStruct.app"
echo "Architecture of the built app: $BUILT_ARCH"
echo "Supported systems: macOS 11 (Big Sur) or later."
echo ""
echo "Double-click ContextStruct.app to use it."
echo "First launch only: if macOS blocks it, right-click the app"
echo "and choose \"Open\" once (the app is unsigned)."
echo ""
read -r -p "Press Enter to close this window."
