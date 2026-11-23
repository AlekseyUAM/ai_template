#!/usr/bin/env sh
# Обёртка Claude Code для локальной LLM.
# Установка: ~/.local/bin/claude-local (chmod +x).
# Настройки модели: <проект>/.claude/settings.local.json.
# Запускайте из каталога проекта: cwd намеренно не меняется.
set -eu

unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL
unset ANTHROPIC_SMALL_FAST_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL
unset ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

exec claude --dangerously-skip-permissions "$@"
