#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$PROJECT_DIR/app"
VENV_DIR="$APP_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

install_os_package() {
    local package="$1"
    local distro_id="${2:-}"

    echo
    echo "A-Team Android Root Patcher needs a native Linux package: ${package}"
    echo "This is a system library required by Qt; it cannot be installed with pip."
    read -r -p "Install it now using your system package manager? [Y/n] " answer
    answer="${answer:-Y}"
    if [[ ! "$answer" =~ ^([Yy]|[Yy][Ee][Ss])$ ]]; then
        echo "Dependency installation skipped. The application cannot start without it."
        return 1
    fi

    case "$distro_id" in
        debian|ubuntu|linuxmint|pop|elementary|zorin)
            sudo apt-get update
            sudo apt-get install -y "$package"
            ;;
        fedora)
            sudo dnf install -y xcb-util-cursor
            ;;
        arch|manjaro|endeavouros|garuda)
            sudo pacman -Sy --needed --noconfirm xcb-util-cursor
            ;;
        *)
            echo "Automatic installation is not configured for this distribution."
            echo "Please install the package providing libxcb-cursor.so.0 and rerun this launcher."
            return 1
            ;;
    esac
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python 3 was not found. Install Python 3 and your distribution's venv support."
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating isolated application environment in app/.venv..."
    if ! python3 -m venv "$VENV_DIR"; then
        echo "Could not create the virtual environment. On Mint/Ubuntu/Debian run:"
        echo "  sudo apt update && sudo apt install python3-venv python3-full"
        exit 1
    fi
fi

if [[ ! -x "$VENV_PY" ]]; then
    echo "ERROR: app/.venv is incomplete. Remove app/.venv and rerun this launcher."
    exit 1
fi

"$VENV_PY" -m pip install --disable-pip-version-check -r "$APP_DIR/requirements.txt"

# PySide6 requires native desktop libraries in addition to Python packages.
# Detect the XCB plugin dependencies and offer to install the known cursor
# library through the host distribution's package manager when it is missing.
if command -v ldd >/dev/null 2>&1; then
    QT_PLUGIN="$("$VENV_PY" -c 'from PySide6.QtCore import QLibraryInfo; from pathlib import Path; print(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platforms" / "libqxcb.so")' 2>/dev/null || true)"
    if [[ -n "$QT_PLUGIN" && -f "$QT_PLUGIN" ]]; then
        MISSING_LIBS="$(ldd "$QT_PLUGIN" 2>/dev/null | awk '/not found/ {print $1}' | sort -u)"
        if grep -q '^libxcb-cursor\.so\.0$' <<< "$MISSING_LIBS"; then
            DISTRO_ID="$(. /etc/os-release 2>/dev/null; printf '%s' "${ID:-unknown}")"
            install_os_package libxcb-cursor0 "$DISTRO_ID"
            MISSING_LIBS="$(ldd "$QT_PLUGIN" 2>/dev/null | awk '/not found/ {print $1}' | sort -u)"
        fi
        if [[ -n "$MISSING_LIBS" ]]; then
            echo
            echo "ERROR: Qt still has missing native Linux libraries:"
            while IFS= read -r lib; do
                [[ -n "$lib" ]] && echo "  - $lib"
            done <<< "$MISSING_LIBS"
            echo "Install the distribution packages providing these libraries, then rerun this launcher."
            exit 1
        fi
    fi
fi

echo "Starting A-Team Android Root Patcher..."
exec "$VENV_PY" "$APP_DIR/app.py"
