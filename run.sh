#!/usr/bin/env bash
# Запуск Web UI Agent Monitor. Одна команда: ./run.sh
# Требует предварительного ./setup.sh.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

[ -d "$ROOT/.venv" ] || { echo "Сначала выполните ./setup.sh"; exit 1; }
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
# shellcheck disable=SC1091
[ -f "$ROOT/.ai1c.env" ] && source "$ROOT/.ai1c.env"

echo "[run] Agent Monitor: http://127.0.0.1:${AGENTMON_PORT:-8765}  (Ctrl+C для остановки)"
exec python -m agentmon
