#!/bin/bash
# PurePaste - macOS launcher (source version)
# Double-click this file in Finder to run PurePaste.
# First launch creates a private Python environment (.venv) next to this
# file and installs the required libraries; later launches are fast.
# PurePaste lives in the menu bar (tray). Closing the window keeps it
# running; quit from the tray icon's menu.
set -u
cd "$(dirname "$0")"

echo "==============================================="
echo " PurePaste (macOS launcher)"
echo "==============================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "Python 3 was not found on this Mac."
  echo "Please install Python 3 first, then double-click this file again:"
  echo "  1. Open https://www.python.org/downloads/macos/"
  echo "  2. Download and run the macOS installer (universal2)."
  echo "     (Or, if a dialog offers to install the Command Line"
  echo "      Developer Tools, you may install those instead.)"
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

if [ ! -x .venv/bin/python ]; then
  echo "First launch: creating the Python environment (.venv)..."
  python3 -m venv .venv || {
    echo "Failed to create the Python environment."
    echo "Press Enter to close this window."
    read -r _
    exit 1
  }
fi

PY=.venv/bin/python

if ! "$PY" -c "import PySide6" >/dev/null 2>&1; then
  echo "Installing libraries (first launch only)..."
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1
  "$PY" -m pip install -r requirements.txt || {
    echo "Failed to install libraries. Check your network connection."
    echo "Press Enter to close this window."
    read -r _
    exit 1
  }
fi

echo "Starting PurePaste..."
exec "$PY" app.py
