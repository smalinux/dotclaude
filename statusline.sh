#!/bin/bash
input=$(cat)
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)

printf '\033[1;31m[\033[1;33m%s\033[1;32m@\033[1;34m%s \033[1;35m%s\033[1;31m]\033[0m %s%% context' "$(whoami)" "$(hostname)" "$(pwd)" "$PCT"
