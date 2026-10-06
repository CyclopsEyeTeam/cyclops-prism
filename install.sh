#!/usr/bin/env bash
# install.sh - One-step installer for Cyclops Prism Antigravity plugin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
PLUGIN_NAME="cyclops-prism"

echo "=========================================="
echo "  Cyclops Prism Plugin Installer (agy)    "
echo "=========================================="

if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling Cyclops Prism..."
    rm -f "${BIN_DIR}/prism"
    rm -f "${BIN_DIR}/gemini-prism"
    rm -f "${BIN_DIR}/agy-prism"
    if [ -f "${HOME}/.bashrc" ]; then
        sed -i '/# Antigravity Cyclops Prism companion launcher/,/}/d' "${HOME}/.bashrc" 2>/dev/null || true
    fi
    if command -v agy &>/dev/null; then
        agy plugin uninstall "${PLUGIN_NAME}" 2>/dev/null || true
    fi
    rm -rf "${HOME}/.gemini/config/plugins/${PLUGIN_NAME}"
    echo "✓ Uninstalled successfully."
    exit 0
fi

# 1. Ensure ~/.local/bin exists
mkdir -p "${BIN_DIR}"

# 2. Symlink launcher binaries into ~/.local/bin
echo "Installing CLI launchers to ${BIN_DIR}..."
ln -sf "${SCRIPT_DIR}/bin/prism" "${BIN_DIR}/prism"
ln -sf "${SCRIPT_DIR}/gemini-prism" "${BIN_DIR}/gemini-prism"
ln -sf "${SCRIPT_DIR}/bin/agy-prism" "${BIN_DIR}/agy-prism"
chmod +x "${SCRIPT_DIR}/bin/prism" "${SCRIPT_DIR}/gemini-prism" "${SCRIPT_DIR}/bin/agy-prism"

# 3. Add shell function to ~/.bashrc if not already present
if [ -f "${HOME}/.bashrc" ] && ! grep -q "agy-prism" "${HOME}/.bashrc"; then
    echo "Configuring 'agy --cyclops-prism' helper in ~/.bashrc..."
    cat << 'EOF' >> "${HOME}/.bashrc"

# Antigravity Cyclops Prism companion launcher
agy() {
    local use_prism=0
    for arg in "$@"; do
        if [ "$arg" = "--cyclops-prism" ] || [ "$arg" = "--prism" ]; then
            use_prism=1
            break
        fi
    done
    if [ "$use_prism" -eq 1 ]; then
        agy-prism "$@"
    else
        command agy "$@"
    fi
}
EOF
fi

# 4. Register as Antigravity plugin
if command -v agy &>/dev/null; then
    echo "Registering plugin in Antigravity (agy)..."
    agy plugin install "${SCRIPT_DIR}" || true
else
    echo "Staging directly into ~/.gemini/config/plugins/${PLUGIN_NAME}..."
    mkdir -p "${HOME}/.gemini/config/plugins"
    ln -sfn "${SCRIPT_DIR}" "${HOME}/.gemini/config/plugins/${PLUGIN_NAME}"
fi

# 5. Check PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo ""
    echo "Notice: ${BIN_DIR} is not in your current PATH."
    echo "Add it by adding this line to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "=========================================="
echo "✓ Cyclops Prism installed successfully!"
echo "=========================================="
echo ""
echo "Launch Antigravity alongside Prism:"
echo "  agy --cyclops-prism  - Launch agy with Prism side-by-side"
echo "  agy-prism            - Direct alias to launch agy + Prism"
echo ""
echo "Commands in Terminal / Tmux:"
echo "  prism                - Live 20 FPS animated companion"
echo "  prism focus          - Expanded telemetry view"
echo "  prism tmux           - Split tmux window with Prism"
echo "  prism once           - Single snapshot for prompt / statusbar"
echo ""
