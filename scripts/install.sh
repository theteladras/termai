#!/usr/bin/env bash
# install.sh — Install termai and configure shell integration.
#
# Usage:
#   bash scripts/install.sh
#
# What it does:
#   1. Installs termai in editable mode (pip install -e .)
#   2. Adds a shell function to your .bashrc / .zshrc so that `termai`
#      is always on your PATH and can update the working directory.

set -euo pipefail

CYAN='\033[1;36m'
GREEN='\033[1;32m'
DIM='\033[2m'
RESET='\033[0m'

echo -e "${CYAN}[termai] Installing...${RESET}"

pip install -e "$(dirname "$0")/.." 2>&1 | tail -1

SHELL_NAME=$(basename "$SHELL")
RC_FILE=""
case "$SHELL_NAME" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    *)    RC_FILE="" ;;
esac

MARKER="# >>> termai shell integration >>>"

if [[ -n "$RC_FILE" ]]; then
    if grep -q "$MARKER" "$RC_FILE" 2>/dev/null; then
        echo -e "${DIM}[termai] Shell integration already present in $RC_FILE${RESET}"
    else
        echo -e "${CYAN}[termai] Adding shell integration to $RC_FILE${RESET}"
        cat >> "$RC_FILE" << 'SHELL_BLOCK'

# >>> termai shell integration >>>
# Quick aliases for termai
alias ai='termai'
alias ai-chat='termai --chat'
# <<< termai shell integration <<<
SHELL_BLOCK
    fi
fi

echo -e "${GREEN}[termai] Installation complete!${RESET}"
echo -e "${DIM}  Run:  termai \"your instruction here\"${RESET}"
echo -e "${DIM}  Chat: termai --chat${RESET}"

if [[ -n "$RC_FILE" ]]; then
    echo -e "${DIM}  Restart your shell or run: source $RC_FILE${RESET}"
fi
