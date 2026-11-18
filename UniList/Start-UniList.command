#!/bin/bash
# UniList - macOS source launcher
# Double-click this file to run UniList from the source code.
# First launch only: if macOS blocks it, right-click the file and
# choose "Open" once.
cd "$(dirname "$0")" || exit 1

echo "=== UniList (macOS, from source) ==="

# --- Python 3 check ------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "Python 3 was not found on this Mac."
  echo "UniList needs Python 3. Please install it in one of"
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

# --- Virtual environment + dependencies (first run only) -----------------
if [ ! -x ".venv/bin/python" ]; then
  echo "Preparing the app environment (first run only)..."
  $PY -m venv .venv || { echo "Failed to create the environment."; read -r -p "Press Enter to close."; exit 1; }
  .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1
  .venv/bin/python -m pip install -r requirements.txt || { echo "Failed to install the required libraries. Check your network connection."; read -r -p "Press Enter to close."; exit 1; }
fi

exec .venv/bin/python app.py
