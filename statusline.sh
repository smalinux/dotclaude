#!/bin/bash
input=$(cat)

IN_TOKENS=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
OUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')
TOTAL_TOKENS=$((IN_TOKENS + OUT_TOKENS))

printf '\033[1;31m[\033[1;33m%s\033[1;32m@\033[1;34m%s \033[1;35m%s\033[1;31m]\033[0m %s tokens' "$(whoami)" "$(hostname)" "$(pwd)" "$TOTAL_TOKENS"
