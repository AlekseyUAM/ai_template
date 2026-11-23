#!/usr/bin/env sh
# Обёртка Claude Code для DeepSeek.
# Установка: ~/.local/bin/claude-ds (chmod +x).
# Ключ: DEEPSEEK_API_KEY или ~/.config/deepseek/key.
set -eu

KEY_FILE="${HOME}/.config/deepseek/key"
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    TOKEN="$DEEPSEEK_API_KEY"
elif [ -f "$KEY_FILE" ]; then
    TOKEN="$(cat "$KEY_FILE")"
else
    echo "Ошибка: не найден ключ. Положите его в $KEY_FILE или задайте DEEPSEEK_API_KEY" >&2
    exit 1
fi

export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$TOKEN"
export ANTHROPIC_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-flash[1m]"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-flash[1m]"
export CLAUDE_CODE_EFFORT_LEVEL=max
export CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432

exec claude --dangerously-skip-permissions "$@"
