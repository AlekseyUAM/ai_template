@echo off
:: Обёртка Claude Code для локальной LLM.
:: Установка: скопируйте в каталог из PATH, например %USERPROFILE%\.local\bin.
:: Настройки модели: <проект>/.claude/settings.local.json (deploy/claude/README.md).
:: Запускайте из каталога проекта: cwd намеренно не меняется.
setlocal

for %%v in (ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL ANTHROPIC_SMALL_FAST_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL) do set "%%v="
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

claude --dangerously-skip-permissions %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
