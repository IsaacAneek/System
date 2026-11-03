#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PY="$SCRIPT_DIR/app.py"

echo "============================================================"
echo "          NFS MOUNT EXPLORER (DEAR IMGUI GUI)               "
echo "============================================================"

# Check if dearpygui is available in the current environment
if ! python3 -c "import dearpygui.dearpygui" 2>/dev/null; then
    echo "[!] DearPyGui not detected in current Python environment."
    echo "[*] Checking for local virtual environment in $SCRIPT_DIR/.venv..."
    
    if [ ! -d "$SCRIPT_DIR/.venv" ]; then
        echo "[*] Creating dedicated virtual environment for DearPyGui..."
        python3 -m venv "$SCRIPT_DIR/.venv"
        "$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip -q
        echo "[*] Installing dearpygui..."
        "$SCRIPT_DIR/.venv/bin/pip" install dearpygui -q
    fi
    
    PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python3"
else
    PYTHON_EXEC="python3"
fi

# Ensure required discovery tools exist
if ! which showmount >/dev/null 2>&1; then
    echo "[*] Notice: 'showmount' tool not found in PATH. Consider installing: sudo apt install nfs-common"
fi

echo "[*] Launching Dear ImGui NFS Explorer (Monkeytype Theme)..."
exec "$PYTHON_EXEC" "$APP_PY"

