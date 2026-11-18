#!/bin/bash
# TashikaMail launcher for macOS (source version).
# Double-click this file in Finder to start TashikaMail.
# The first run creates a private Python environment (.venv-mac)
# and installs the required libraries; later runs start immediately.

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
    echo "If a dialog asked you to install the Command Line Tools,"
    echo "install them and run this file again."
    read -r -p "Press Enter to close this window."
    exit 1
  fi
fi
PY="$VENV/bin/python"

if ! "$PY" -c "import PySide6, pypdf, openpyxl, fitz, PIL" >/dev/null 2>&1; then
  echo "Installing required libraries (first run only)..."
  if ! "$PY" -m pip install -r requirements.txt; then
    echo ""
    echo "Library installation failed. Check your network connection"
    echo "and run this file again."
    read -r -p "Press Enter to close this window."
    exit 1
  fi
fi

"$PY" app.py
STATUS=$?
if [ $STATUS -ne 0 ]; then
  echo ""
  echo "TashikaMail stopped with an error (code $STATUS). See above."
  read -r -p "Press Enter to close this window."
fi
exit $STATUS
