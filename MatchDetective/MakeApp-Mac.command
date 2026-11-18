#!/bin/bash
# MatchDetective - build a standalone macOS app (MatchDetective.app).
#
# Run this on a Mac: it creates a private Python environment (.venv),
# installs PySide6 / openpyxl / PyInstaller, and builds
#   dist/MatchDetective.app
# It first tries a "universal2" build that runs on both Apple Silicon
# and Intel Macs. If that is not possible with the Python installed on
# this Mac, it automatically retries with a build for this Mac's own
# chip and tells you which kind was made.
#
# The app is unsigned, so the first time you open the built app,
# macOS Gatekeeper will block a plain double-click: right-click the
# app and choose "Open" once (see README.txt).
cd "$(dirname "$0")" || exit 1

if [ ! -f app.py ]; then
  echo "app.py not found. Extract the ZIP first, then run this file"
  echo "from inside the extracted MatchDetective folder."
  read -r -p "Press Enter to close."
  exit 1
fi

if ! python3 -c "import sys" >/dev/null 2>&1; then
  echo "Python 3 was not found (or is not installed yet)."
  echo ""
  echo "Please install Python 3 first - either way works:"
  echo "  1) Download the macOS installer from https://www.python.org/downloads/"
  echo "     and run it (recommended: that Python can build universal2), or"
  echo "  2) If a dialog just asked to install the Command Line"
  echo "     Developer Tools, accept it and run this file again."
  echo ""
  echo "After installing Python, double-click this file again."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Preparing the build environment (first time only)..."
  python3 -m venv .venv || {
    echo "Could not create the Python environment (.venv)."
    read -r -p "Press Enter to close."
    exit 1
  }
fi
# shellcheck disable=SC1091
. .venv/bin/activate

echo "Installing / checking libraries..."
python -m pip install --upgrade pip >/dev/null 2>&1
python -m pip install PySide6 openpyxl pyinstaller || {
  echo "Library installation failed. Check your network connection"
  echo "and run this file again."
  read -r -p "Press Enter to close."
  exit 1
}

EXCLUDES=(
  --exclude-module PySide6.QtWebEngine
  --exclude-module PySide6.QtWebEngineCore
  --exclude-module PySide6.QtWebEngineWidgets
  --exclude-module PySide6.QtQml
  --exclude-module PySide6.QtQuick
  --exclude-module PySide6.QtQuickWidgets
  --exclude-module PySide6.Qt3DCore
  --exclude-module PySide6.Qt3DRender
  --exclude-module PySide6.Qt3DInput
  --exclude-module PySide6.Qt3DLogic
  --exclude-module PySide6.Qt3DAnimation
  --exclude-module PySide6.Qt3DExtras
  --exclude-module PySide6.QtCharts
  --exclude-module PySide6.QtDataVisualization
  --exclude-module PySide6.QtMultimedia
  --exclude-module PySide6.QtMultimediaWidgets
  --exclude-module PySide6.QtNetwork
  --exclude-module PySide6.QtSvg
  --exclude-module PySide6.QtSvgWidgets
  --exclude-module PySide6.QtPrintSupport
  --exclude-module PySide6.QtSql
  --exclude-module PySide6.QtTest
  --exclude-module PySide6.QtXml
  --exclude-module PySide6.QtConcurrent
  --exclude-module PySide6.QtDBus
  --exclude-module PySide6.QtHelp
  --exclude-module PySide6.QtUiTools
  --exclude-module PySide6.QtDesigner
  --exclude-module PySide6.QtPositioning
  --exclude-module PySide6.QtLocation
  --exclude-module PySide6.QtSensors
  --exclude-module PySide6.QtSerialPort
  --exclude-module PySide6.QtBluetooth
  --exclude-module PySide6.QtNfc
  --exclude-module PySide6.QtWebSockets
  --exclude-module PySide6.QtWebChannel
  --exclude-module PySide6.QtRemoteObjects
  --exclude-module PySide6.QtTextToSpeech
  --exclude-module PySide6.QtPdf
  --exclude-module PySide6.QtPdfWidgets
  --exclude-module PySide6.QtOpenGL
  --exclude-module PySide6.QtOpenGLWidgets
  --exclude-module PySide6.QtAsyncio
  --exclude-module tkinter
  --exclude-module _tkinter
  --exclude-module unittest
  --exclude-module pytest
  --exclude-module numpy
  --exclude-module lxml
  --exclude-module pandas
  --exclude-module matplotlib
  --exclude-module IPython
)

build_app() {
  # $1 (optional): value for --target-arch, or empty for native build
  if [ -n "$1" ]; then
    python -m PyInstaller --noconfirm --windowed --name MatchDetective --icon assets/icon.icns \
      --target-arch "$1" "${EXCLUDES[@]}" app.py
  else
    python -m PyInstaller --noconfirm --windowed --name MatchDetective --icon assets/icon.icns \
      "${EXCLUDES[@]}" app.py
  fi
}

KIND=""
echo ""
echo "Trying a universal2 build (runs on Apple Silicon and Intel)..."
if build_app universal2 && [ -d dist/MatchDetective.app ]; then
  KIND="universal2 (Apple Silicon + Intel)"
else
  echo ""
  echo "universal2 is not available with this Python; rebuilding for"
  echo "this Mac's own chip instead..."
  rm -rf build dist MatchDetective.spec
  if build_app "" && [ -d dist/MatchDetective.app ]; then
    KIND="native ($(uname -m)) - runs on Macs with the same chip family"
  fi
fi

echo ""
if [ -n "$KIND" ] && [ -d dist/MatchDetective.app ]; then
  echo "Done: dist/MatchDetective.app"
  echo "Build kind: $KIND"
  if command -v file >/dev/null 2>&1; then
    echo "Binary check:"
    file dist/MatchDetective.app/Contents/MacOS/MatchDetective | sed 's/^/  /'
  fi
  echo ""
  echo "To use it: move MatchDetective.app anywhere you like and open it."
  echo "First open: the app is unsigned, so right-click it and choose"
  echo "\"Open\" once; after that a normal double-click works."
else
  echo "The build did not finish. Please scroll up for the error"
  echo "message, fix the cause (usually a missing library), and run"
  echo "this file again."
fi
read -r -p "Press Enter to close."
