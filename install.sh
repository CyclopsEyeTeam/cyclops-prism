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
echo "Installing CLI launcher to ${BIN_DIR}/prism..."
ln -sf "${SCRIPT_DIR}/bin/prism" "${BIN_DIR}/prism"
ln -sf "${SCRIPT_DIR}/gemini-prism" "${BIN_DIR}/gemini-prism"
chmod +x "${SCRIPT_DIR}/bin/prism" "${SCRIPT_DIR}/gemini-prism"

# 3. Register as Antigravity plugin
if command -v agy &>/dev/null; then
    echo "Registering plugin in Antigravity (agy)..."
    agy plugin install "${SCRIPT_DIR}" || true
else
    echo "Staging directly into ~/.gemini/config/plugins/${PLUGIN_NAME}..."
    mkdir -p "${HOME}/.gemini/config/plugins"
    ln -sfn "${SCRIPT_DIR}" "${HOME}/.gemini/config/plugins/${PLUGIN_NAME}"
fi

# 4. Check PATH
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
echo "Commands in Antigravity (agy):"
echo "  /prism        - Show Prism status in chat"
echo "  /focus        - Show expanded optical telemetry"
echo "  /tmux         - Open Prism in tmux side pane"
echo ""
echo "Commands in Terminal / Tmux:"
echo "  prism         - Live 20 FPS animated companion"
echo "  prism focus   - Expanded telemetry view"
echo "  prism tmux    - Split tmux window with Prism"
echo "  prism once    - Single snapshot for prompt / statusbar"
echo ""
