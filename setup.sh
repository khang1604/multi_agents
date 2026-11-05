#!/bin/sh
# Multi Agents — POSIX launcher setup
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.11+ is required. Install it before running setup." >&2
    exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "Python 3.11+ is required")'

# 1. Install 'ma' launcher silently
python3 "$SCRIPT_DIR/cli/ma.py" install-command >/dev/null

BIN_DIR="$HOME/.local/share/MultiAgents/runtime/bin"

# 2. Silently ensure PATH is configured in shell profiles
add_to_profile() {
    profile="$1"
    if [ -f "$profile" ] || [ "$profile" = "$HOME/.bashrc" ]; then
        if ! grep -qs "MultiAgents/runtime/bin" "$profile" 2>/dev/null; then
            echo "" >> "$profile"
            echo '# Multi Agents CLI' >> "$profile"
            echo 'export PATH="$HOME/.local/share/MultiAgents/runtime/bin:$PATH"' >> "$profile"
        fi
    fi
}

add_to_profile "$HOME/.bashrc"
if [ -f "$HOME/.zshrc" ]; then
    add_to_profile "$HOME/.zshrc"
fi

# Optional: symlink to ~/.local/bin/ma if directory exists
if [ -d "$HOME/.local/bin" ]; then
    ln -sf "$BIN_DIR/ma" "$HOME/.local/bin/ma" 2>/dev/null || true
fi

# Symlink detected AI CLIs into runtime bin so they are accessible on PATH
if [ -f "$HOME/.gemini/bin/agy" ] && [ ! -e "$BIN_DIR/agy" ]; then
    ln -sf "$HOME/.gemini/bin/agy" "$BIN_DIR/agy" 2>/dev/null || true
fi
if [ -f "$HOME/.codex/plugins/.plugin-appserver/codex" ] && [ ! -e "$BIN_DIR/codex" ]; then
    ln -sf "$HOME/.codex/plugins/.plugin-appserver/codex" "$BIN_DIR/codex" 2>/dev/null || true
fi

# 3. Completion message
echo "Setup complete!"


