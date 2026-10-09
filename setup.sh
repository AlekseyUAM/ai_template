#!/usr/bin/env bash
# Единая установка и подготовка окружения Agent Monitor.
# Одна команда: ./setup.sh
#   - создаёт виртуальное окружение .venv
#   - ставит приложение (app, editable) и зависимости
#   - поднимает PostgreSQL в Docker (если докер доступен), иначе использует SQLite
#   - пишет конфиг .ai1c.env (AGENTMON_DSN) для ./run.sh
#   - проверяет наличие нужных инструментов
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/.venv"
ENV_FILE="$ROOT/.ai1c.env"

say()  { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[setup]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[setup]\033[0m %s\n' "$*"; exit 1; }

# 1. Python + виртуальное окружение
command -v python3 >/dev/null || die "python3 не найден — установите Python 3.10+"
if [ ! -d "$VENV" ]; then
  say "создаю виртуальное окружение .venv"
  python3 -m venv "$VENV" 2>/dev/null \
    || die "не удалось создать venv. Установите пакет: sudo apt install python3-venv (или python3-full)"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null

# 2. Приложение
say "устанавливаю приложение (app, editable) и зависимости"
pip install -e "$ROOT/app"

# 3. База данных: PostgreSQL в Docker, иначе локальный SQLite
COMPOSE="docker compose -f $ROOT/deploy/postgres/docker-compose.yml"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  # Подбираем свободный хост-порт начиная с 5432 (на 5432 может уже висеть локальный Postgres).
  AI1C_PG_PORT="$(python - <<'PY'
import socket
for p in range(5432, 5460):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p)); s.close(); print(p); break
    except OSError:
        continue
else:
    print(5432)
PY
)"
  export AI1C_PG_PORT
  say "поднимаю PostgreSQL в Docker (deploy/postgres) на порту $AI1C_PG_PORT"
  $COMPOSE down --remove-orphans >/dev/null 2>&1 || true   # убрать полустартовавший контейнер (volume с данными сохраняется)
  $COMPOSE up -d
  say "устанавливаю драйвер psycopg"
  pip install "psycopg[binary]" >/dev/null
  say "жду готовности PostgreSQL…"
  ready=0
  for _ in $(seq 1 30); do
    if docker exec ai1c-postgres pg_isready -U ai1c >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  [ "$ready" = 1 ] || warn "PostgreSQL не ответил за 30с — проверьте контейнер ai1c-postgres"
  DSN="postgresql://ai1c:ai1c@127.0.0.1:${AI1C_PG_PORT}/ai1c"
else
  warn "Docker недоступен — использую локальный SQLite (без Postgres)"
  DSN="$ROOT/app/agentmon.db"
fi

# 4. Конфиг для run.sh
cat > "$ENV_FILE" <<EOF
# Сгенерировано setup.sh — используется ./run.sh
export AGENTMON_DSN="$DSN"
export AGENTMON_DB="$ROOT/app/agentmon.db"
EOF
say "конфиг записан: .ai1c.env (AGENTMON_DSN=$DSN)"

# 5. Проверка требований (не блокирующая)
for t in git docker claude; do
  if command -v "$t" >/dev/null 2>&1; then say "найдено: $t"; else warn "не найдено (не блокирует работу UI): $t"; fi
done

say "Готово. Поднять Web UI: ./run.sh"
