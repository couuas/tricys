#!/usr/bin/env bash
# install_dwsim_linux.sh — Install .NET 8 Runtime and DWSIM on Ubuntu/Debian Linux
# Usage: bash script/dwsim/install_dwsim_linux.sh
#
# Prerequisites: sudo access for apt packages
# This script:
#   1. Installs .NET 8 Runtime via apt (if not already installed)
#   2. Downloads DWSIM .deb package and installs via dpkg/apt
#   3. Verifies both are functional
#
# After installation, DWSIM is at /usr/local/lib/dwsim/
# Set DWSIM_DIR=/usr/local/lib/dwsim for Python scripts.

set -euo pipefail

DWSIM_VERSION="9.0.5"
DWSIM_DEB_URL="https://github.com/DanWBR/dwsim/releases/download/v${DWSIM_VERSION}/dwsim_${DWSIM_VERSION}-amd64.deb"
DWSIM_DIR="/usr/local/lib/dwsim"

echo "=== Step 1: Install .NET 8 Runtime ==="
if command -v dotnet &>/dev/null && dotnet --list-runtimes 2>/dev/null | grep -q "NETCore.App 8\."; then
    echo ".NET 8 Runtime already installed."
else
    echo "Installing dotnet-runtime-8.0 via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq dotnet-runtime-8.0
    echo ".NET 8 Runtime installed."
fi

echo ""
echo "=== Step 2: Verify .NET installation ==="
dotnet --info | head -10
echo ""

echo "=== Step 3: Install DWSIM via .deb package ==="
if [[ -f "${DWSIM_DIR}/DWSIM.Automation.dll" ]]; then
    echo "DWSIM already installed at ${DWSIM_DIR}"
else
    TMPFILE=$(mktemp /tmp/dwsim-XXXXXX.deb)
    echo "Downloading DWSIM v${DWSIM_VERSION} .deb package..."
    curl -fSL --progress-bar -o "${TMPFILE}" "${DWSIM_DEB_URL}"
    echo "Installing DWSIM (dpkg + dependency resolution)..."
    sudo dpkg -i "${TMPFILE}" 2>&1 || sudo apt-get install -f -y 2>&1
    rm -f "${TMPFILE}"
    echo "DWSIM installed."
fi

echo ""
echo "=== Step 4: Verify DWSIM installation ==="
if [[ -f "${DWSIM_DIR}/DWSIM.Automation.dll" ]]; then
    echo "✅ DWSIM.Automation.dll found at ${DWSIM_DIR}/DWSIM.Automation.dll"
else
    DLL_PATH=$(find /usr -name "DWSIM.Automation.dll" -type f 2>/dev/null | head -1)
    if [[ -n "${DLL_PATH}" ]]; then
        echo "✅ DWSIM.Automation.dll found at ${DLL_PATH}"
        DWSIM_DIR="$(dirname "${DLL_PATH}")"
    else
        echo "❌ DWSIM.Automation.dll NOT found. Installation may have failed."
        exit 1
    fi
fi

echo ""
echo "=== Summary ==="
echo ".NET Runtime: $(dotnet --list-runtimes 2>/dev/null | grep NETCore | tail -1)"
echo "DWSIM Dir:    ${DWSIM_DIR}"
echo "DWSIM DLLs:   $(ls "${DWSIM_DIR}"/DWSIM.*.dll 2>/dev/null | wc -l) found"
echo ""
echo "To use DWSIM from Python, set:"
echo "  export DWSIM_DIR=${DWSIM_DIR}"
echo ""
echo "Installation complete."
