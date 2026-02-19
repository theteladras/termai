#!/usr/bin/env bash
# uninstall.sh — Remove termai and clean up shell integration.

set -euo pipefail

CYAN='\033[1;36m'
GREEN='\033[1;32m'
DIM='\033[2m'
RESET='\033[0m'

echo -e "${CYAN}[termai] Uninstalling...${RESET}"

pip uninstall -y termai 2>/dev/null || true

SHELL_NAME=$(basename "$SHELL")
RC_FILE=""
case "$SHELL_NAME" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
esac

if [[ -n "$RC_FILE" ]] && grep -q "termai shell integration" "$RC_FILE" 2>/dev/null; then
    echo -e "${CYAN}[termai] Removing shell integration from $RC_FILE${RESET}"
    sed -i.bak '/# >>> termai shell integration >>>/,/# <<< termai shell integration <<</d' "$RC_FILE"
    rm -f "${RC_FILE}.bak"
fi

echo -e "${GREEN}[termai] Uninstall complete.${RESET}"
echo -e "${DIM}  History is preserved in ~/.termai/history.jsonl${RESET}"
echo -e "${DIM}  Models are preserved in ~/.cache/gpt4all/${RESET}"
echo -e "${DIM}  Delete those directories manually if you want a full cleanup.${RESET}"
