#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="/Users/xuxu/Documents/Codex/2026-06-23/chrome-plugin-chrome-openai-bundled-file/outputs/a-share-ai-system"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOG_DIR="$HOME/Library/Logs/a-share-ai-system"
LOG_FILE="$LOG_DIR/local_analysis.log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_ROOT"

{
  printf '\n[%s] starting local analysis\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  DESKTOP_OUTPUT=true OUTPUT_DIR="$HOME/Desktop/a-share-ai-system-output" "$VENV_PYTHON" main.py
  printf '[%s] finished local analysis\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
} >> "$LOG_FILE" 2>&1
