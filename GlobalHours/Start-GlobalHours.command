#!/bin/bash
# GlobalHours launcher for macOS.
# Creates a local virtual environment, installs the Python dependencies,
# and starts the application.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

pause_and_exit() {
  echo
  echo "$1"
  echo "Press Enter to close this window."
  read -r _ || true
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  cat <<'EOF'
Python 3 was not found.

Install Python 3.10 or later in either of these ways:
  1. Download the macOS installer from https://www.python.org/downloads/macos/
  2. If Homebrew is already installed, run: brew install python

Then double-click Start-GlobalHours.command again.
EOF
  pause_and_exit "Python 3 is required."
fi

PYTHON_BIN="$(command -v python3)"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  pause_and_exit "Python 3.10 or later is required. Please install a current version from python.org."
fi

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "Creating the GlobalHours Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR" || pause_and_exit "Could not create the Python virtual environment."
fi

echo "Checking GlobalHours dependencies..."
"$VENV_PY" -m pip install --upgrade pip || pause_and_exit "Could not update pip. Check the network connection and try again."
"$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements.txt" || pause_and_exit "Could not install the required Python packages. Check the network connection and try again."

exec "$VENV_PY" "$SCRIPT_DIR/app.py"
