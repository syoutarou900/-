#!/bin/bash
export WINEPREFIX="$HOME/workspace/wine-prefix"
export WINEDEBUG=-all
export DISPLAY=:99
WINE64="$HOME/workspace/exe-build/wine-local/usr/lib/wine/wine64"
cd "$HOME/workspace/wine-prefix/drive_c/clip-history" || exit 1
"$WINE64" "C:\\Python312\\python.exe" -m PyInstaller --noconfirm ClipStock.spec
echo "BUILD_EXIT=$?"
