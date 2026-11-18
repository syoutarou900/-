#!/bin/bash
# Build GlobalHours.app for macOS with PyInstaller.
# A universal2 build is attempted first. If the installed Python or
# libraries cannot produce universal2, the script retries for this Mac's
# native CPU architecture and reports which one was built at the end.

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

Then double-click MakeApp-Mac.command again.
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

echo "Installing application and build dependencies..."
"$VENV_PY" -m pip install --upgrade pip || pause_and_exit "Could not update pip. Check the network connection and try again."
"$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements.txt" || pause_and_exit "Could not install the required Python packages. Check the network connection and try again."
"$VENV_PY" -m pip install --upgrade pyinstaller || pause_and_exit "Could not install PyInstaller. Check the network connection and try again."

COMMON_ARGS=(
  --noconfirm
  --clean
  --windowed
  --name GlobalHours --icon assets/icon.icns
  --add-data "fonts:fonts"
  --add-data "assets:assets"
  --collect-all holidays
  --collect-all tzdata
  --collect-all babel
  --exclude-module tkinter
  --exclude-module unittest
  --exclude-module pytest
)

BUILD_ARCH=""
echo
echo "Trying a universal2 build for Intel and Apple Silicon Macs..."
if "$VENV_PY" -m PyInstaller "${COMMON_ARGS[@]}" --target-arch universal2 "$SCRIPT_DIR/app.py"; then
  BUILD_ARCH="universal2 (Intel and Apple Silicon)"
else
  echo
  echo "The universal2 build did not succeed. Retrying for this Mac's native architecture..."
  NATIVE_ARCH="$(uname -m)"
  if "$VENV_PY" -m PyInstaller "${COMMON_ARGS[@]}" "$SCRIPT_DIR/app.py"; then
    BUILD_ARCH="native ($NATIVE_ARCH)"
  else
    pause_and_exit "PyInstaller could not build GlobalHours.app."
  fi
fi

APP_PATH="$SCRIPT_DIR/dist/GlobalHours.app"
if [ ! -d "$APP_PATH" ]; then
  pause_and_exit "The build finished without creating dist/GlobalHours.app."
fi

echo
echo "Build complete."
echo "Created: $APP_PATH"
echo "Architecture: $BUILD_ARCH"
echo
echo "This app is unsigned. The first time you open it, use Finder:"
echo "right-click GlobalHours.app, choose Open, and confirm Open."
echo
echo "Press Enter to close this window."
read -r _ || true
