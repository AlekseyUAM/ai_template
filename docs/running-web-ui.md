# Запуск Web UI (Linux и Windows)

Web UI — это приложение `agentmon` (каталог `app/`): мониторинг и оркестрация
claude-сессий плюс мастера окружения и задач. Шаблон разворачиваемого окружения
лежит в корне репозитория (`template/`) и читается приложением по относительному
пути, поэтому **запускать нужно из репозитория** (editable-установкой или через
`PYTHONPATH=src`), а не ставить пакет в системный site-packages.

## Требования

- **Python 3.10+**
- Зависимости приложения: `fastapi`, `uvicorn[standard]`, `paramiko`; на Windows
  дополнительно `pywinpty` (ставится автоматически вместе с пакетом).
- Для реального прогона агентов — установленный **Claude Code CLI** (`claude`).
- Для MCP-серверов — **Docker** (managed-режим). Для самого Web UI Docker не нужен.

---

## Linux

```bash
cd <путь-к-репозиторию>/app

# Вариант 1 — editable-установка (рекомендуется)
python3 -m pip install -e .
python3 -m agentmon

# Вариант 2 — без установки
python3 -m pip install fastapi "uvicorn[standard]" paramiko
PYTHONPATH=src python3 -m agentmon
```

Если pip ругается на «externally-managed-environment» (PEP 668), используйте
виртуальное окружение:

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -e .
python3 -m agentmon
```

Сервер поднимется на `http://127.0.0.1:8765`.

---

## Windows

В PowerShell:

```powershell
cd <путь-к-репозиторию>\app

# Вариант 1 — editable-установка (рекомендуется)
python -m pip install -e .
python -m agentmon

# Вариант 2 — без установки
python -m pip install fastapi "uvicorn[standard]" paramiko pywinpty
$env:PYTHONPATH = "src"
python -m agentmon
```

Примечания для Windows:
- Используется `python` (не `python3`).
- `pywinpty` нужен для псевдотерминала; при `pip install -e .` ставится сам.
- Путь проекта в UI указывайте в родном виде, например `C:\work\demo`.

Сервер поднимется на `http://127.0.0.1:8765`.

---

## Страницы

Откройте в браузере `http://127.0.0.1:8765`:

| Путь | Назначение |
|------|------------|
| `/` | Монитор сессий и очередь (agentmon) |
| `/create-project` | Мастер «Создать проект» — развернуть/обновить окружение |
| `/create-task` | Мастер «Создать задачу» |
| `/run-tasks` | «Выполнить задачи» — запуск списка задач |

---

## Переменные окружения

| Переменная | Назначение | По умолчанию |
|------------|------------|--------------|
| `AGENTMON_HOST` | адрес прослушивания | `127.0.0.1` |
| `AGENTMON_PORT` | порт | `8765` |
| `AGENTMON_DB` | путь к SQLite-реестру проектов/очереди | `agentmon.db` |
| `AGENTMON_CLAUDE_CMD` | команда запуска агента | `claude --dangerously-skip-permissions .` |

Пример (Linux):

```bash
AGENTMON_PORT=9000 PYTHONPATH=src python3 -m agentmon
```

Пример (Windows PowerShell):

```powershell
$env:AGENTMON_PORT = "9000"; python -m agentmon
```

---

## Доступ с другой машины

Монитор слушает `127.0.0.1`. Чтобы открыть UI сервера с локального компьютера,
пробросьте порт по SSH:

```bash
ssh -L 8765:127.0.0.1:8765 user@server
# затем открыть http://127.0.0.1:8765 локально
```

---

## Остановка

`Ctrl+C` в терминале сервера. Запущенные в этот момент агенты завершаются вместе с
монитором; задачи, бывшие в статусе `running`, при следующем запуске возвращаются в
очередь.
