#!/bin/bash
# MatchDetective - macOS launcher (source version).
# Double-click this file to run MatchDetective.
# First launch creates a private Python environment (.venv) in this
# folder and installs the libraries it needs; later launches are fast.
cd "$(dirname "$0")" || exit 1

if [ ! -f app.py ]; then
  echo "app.py not found. Extract the ZIP first, then run this file"
  echo "from inside the extracted MatchDetective folder."
  read -r -p "Press Enter to close."
  exit 1
fi

# A working python3 is required. /usr/bin/python3 on a fresh Mac is a
# stub that asks to install the Command Line Tools; treat a failed
# run the same as "not installed" and explain how to get Python.
if ! python3 -c "import sys" >/dev/null 2>&1; then
  echo "Python 3 was not found (or is not installed yet)."
  echo ""
  echo "Please install Python 3 first - either way works:"
  echo "  1) Download the macOS installer from https://www.python.org/downloads/"
  echo "     and run it (this is the simplest way), or"
  echo "  2) If a dialog just asked to install the Command Line"
  echo "     Developer Tools, accept it and run this file again."
  echo ""
  echo "After installing Python, double-click this file again."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Preparing the app environment (first launch only)..."
  python3 -m venv .venv || {
    echo "Could not create the Python environment (.venv)."
    read -r -p "Press Enter to close."
    exit 1
  }
fi
# shellcheck disable=SC1091
. .venv/bin/activate

if ! python -c "import PySide6, openpyxl" >/dev/null 2>&1; then
  echo "Installing libraries (first launch only)..."
  python -m pip install --upgrade pip >/dev/null 2>&1
  python -m pip install PySide6 openpyxl || {
    echo "Library installation failed. Check your network connection"
    echo "and run this file again."
    read -r -p "Press Enter to close."
    exit 1
  }
fi

python app.py
