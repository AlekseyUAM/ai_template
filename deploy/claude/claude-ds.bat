@echo off
:: Обёртка Claude Code для DeepSeek.
:: Установка: скопируйте в каталог из PATH, например %USERPROFILE%\.local\bin.
:: Ключ: переменная DEEPSEEK_API_KEY или файл %USERPROFILE%\.config\deepseek\key.
setlocal

set "KEY_FILE=%USERPROFILE%\.config\deepseek\key"
if defined DEEPSEEK_API_KEY (
    set "TOKEN=%DEEPSEEK_API_KEY%"
) else if exist "%KEY_FILE%" (
    set /p TOKEN=<"%KEY_FILE%"
) else (
    echo Ошибка: не найден ключ. Положите его в %KEY_FILE% или задайте DEEPSEEK_API_KEY 1>&2
    exit /b 1
)

for /f "tokens=* delims=" %%a in ("%TOKEN%") do set "TOKEN=%%a"

set "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic"
set "ANTHROPIC_AUTH_TOKEN=%TOKEN%"
set "ANTHROPIC_MODEL=deepseek-flash[1m]"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-flash[1m]"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-flash[1m]"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-flash[1m]"
set "CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash[1m]"
set "CLAUDE_CODE_EFFORT_LEVEL=max"
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432"

claude --dangerously-skip-permissions %*
endlocal
