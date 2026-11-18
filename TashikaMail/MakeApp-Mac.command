#!/bin/bash
# Build TashikaMail.app for macOS with PyInstaller.
#
# The build first tries a universal2 app (runs on both Intel and
# Apple Silicon Macs). If that is not possible in this environment
# (for example when Python itself is a single-architecture build),
# it automatically falls back to a native build for this Mac.
# The finished app appears as dist/TashikaMail.app.
#
# The app is NOT code-signed. On first launch, right-click
# TashikaMail.app and choose "Open" to pass the Gatekeeper prompt.

cd "$(dirname "$0")" || exit 1

if [ ! -f app.py ]; then
  echo "app.py not found. Please extract the whole ZIP first."
  read -r -p "Press Enter to close this window."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found on this Mac."
  echo ""
  echo "Install Python 3 in one of these ways, then run this file again:"
  echo "  1) Download the macOS installer from"
  echo "     https://www.python.org/downloads/macos/"
  echo "  2) Or, if you use Homebrew:  brew install python"
  echo ""
  read -r -p "Press Enter to close this window."
  exit 1
fi

VENV=".venv-mac"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating a Python environment (first run only)..."
  if ! python3 -m venv "$VENV"; then
    echo ""
    echo "Failed to create the Python environment."
    read -r -p "Press Enter to close this window."
    exit 1
  fi
fi
PY="$VENV/bin/python"

echo "Installing required libraries and PyInstaller..."
if ! "$PY" -m pip install -r requirements.txt pyinstaller; then
  echo ""
  echo "Installation failed. Check your network connection"
  echo "and run this file again."
  read -r -p "Press Enter to close this window."
  exit 1
fi

ARCH_LABEL=""
echo ""
echo "Trying a universal2 build (Intel + Apple Silicon)..."
if "$PY" -m PyInstaller --noconfirm --windowed \
      --name TashikaMail --icon assets/icon.icns --target-arch universal2 app.py; then
  ARCH_LABEL="universal2 (Intel + Apple Silicon)"
else
  echo ""
  echo "The universal2 build did not work in this environment."
  echo "Falling back to a native build for this Mac ($(uname -m))..."
  rm -rf build dist TashikaMail.spec
  if "$PY" -m PyInstaller --noconfirm --windowed \
        --name TashikaMail --icon assets/icon.icns app.py; then
    ARCH_LABEL="native ($(uname -m)) - runs on this kind of Mac only"
  fi
fi

echo ""
if [ -d "dist/TashikaMail.app" ] && [ -n "$ARCH_LABEL" ]; then
  echo "Done: dist/TashikaMail.app"
  echo "Architecture: $ARCH_LABEL"
  echo ""
  echo "The app is not code-signed. On first launch, right-click"
  echo "TashikaMail.app and choose \"Open\" (Gatekeeper)."
else
  echo "The build failed. See the messages above."
  read -r -p "Press Enter to close this window."
  exit 1
fi
read -r -p "Press Enter to close this window."
