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
    rm -f "${BIN_DIR}/agy-prismtop"
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
ln -sf "${SCRIPT_DIR}/bin/agy-prismtop" "${BIN_DIR}/agy-prismtop"
chmod +x "${SCRIPT_DIR}/bin/prism" "${SCRIPT_DIR}/gemini-prism" "${SCRIPT_DIR}/bin/agy-prism" "${SCRIPT_DIR}/bin/agy-prismtop"

# 3. Add shell function to ~/.bashrc
if [ -f "${HOME}/.bashrc" ]; then
    # Remove older variant if present to keep bashrc clean
    sed -i '/# Antigravity Cyclops Prism companion launcher/,/}/d' "${HOME}/.bashrc" 2>/dev/null || true
    echo "Configuring 'agy --prism' & 'agy --prismtop' helpers in ~/.bashrc..."
    cat << 'EOF' >> "${HOME}/.bashrc"

# Antigravity Cyclops Prism companion launcher
agy() {
    local use_prism=0
    local prism_top=0
    for arg in "$@"; do
        if [ "$arg" = "--prismtop" ] || [ "$arg" = "--cyclops-prismtop" ]; then
            prism_top=1
            use_prism=1
            break
        elif [ "$arg" = "--prism" ] || [ "$arg" = "--cyclops-prism" ]; then
            use_prism=1
            break
        fi
    done
    if [ "$prism_top" -eq 1 ]; then
        agy-prismtop "$@"
    elif [ "$use_prism" -eq 1 ]; then
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
echo "  agy --prism        - Side view (split companion pane on right)"
echo "  agy --prismtop     - Top view (wide companion banner on top)"
echo "  agy-prism          - Shorthand alias for side view"
echo "  agy-prismtop       - Shorthand alias for top view"
echo ""
echo "Commands in Terminal / Tmux:"
echo "  prism                - Live 20 FPS animated companion"
echo "  prism focus          - Expanded telemetry view"
echo "  prism tmux [side|top]- Split tmux window with Prism (side or top)"
echo "  prism once           - Single snapshot for prompt / statusbar"
echo ""
