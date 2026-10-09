# Agent Monitor — окружение ИИ-разработки на 1С

Две команды.

## Linux
```bash
./setup.sh      # установка и подготовка всего (venv, приложение, PostgreSQL в Docker, конфиг)
./run.sh        # запуск Web UI  →  http://127.0.0.1:8765
```

## Windows (PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

`setup` создаёт `.venv`, ставит приложение (`app`, editable) и зависимости, поднимает
PostgreSQL в Docker (если докер доступен; иначе использует локальный SQLite) и пишет
`.ai1c.env` с `AGENTMON_DSN`. `run` поднимает Web UI на `http://127.0.0.1:8765`.

Подробности и переменные окружения — в [docs/running-web-ui.md](docs/running-web-ui.md).
Фазы развития — в [docs/PHASES.md](docs/PHASES.md).
