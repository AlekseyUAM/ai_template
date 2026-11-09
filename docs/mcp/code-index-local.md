# Индексированная кодовая база (локально) — `code_index`

Нативное развёртывание code-index: **без Docker**, одним статическим бинарём
`bsl-indexer` на хосте. Те же два процесса, что и в Docker-варианте
(демон-индексатор + read-only MCP-сервер), но оба запускаются прямо на машине.
Поддерживаются платформы, под которые upstream публикует релизы:
**Windows x64, Linux x64, macOS arm64**.

Общее ядро (два процесса, `daemon.toml`, alias = имя проекта) —
[code-index-common.md](code-index-common.md).

## Когда выбирать этот вид

- на машине нет Docker (или не хочется держать контейнер);
- кодовая база лежит на той же машине, где работает агент;
- нужен быстрый старт и минимум движущихся частей: бинарь + `daemon.toml`.

Если кодовая база на другом сервере, а Docker там есть — обычно проще
[code-index.md](code-index.md) (Docker), либо разверните локальный вариант на
том сервере и ходите к нему по сети/туннелю.

## Поля карточки

| Поле | Значение по умолчанию |
|---|---|
| Наименование | — (обязательно) |
| Имя в `.mcp.json` | `code_index` |
| Назначение | как у Docker-вида |
| URL | `localhost` |
| Порт | `8005` |
| Каталог кодовой базы | — **обязательно** (выгрузка конфигурации) |
| Имя проекта (alias репозитория) | — **обязательно**, = имя проекта |
| Каталог code_index | — **обязательно**: каталог для бинаря, `daemon.toml`, рантайма и логов |
| Подключение | `{"code_index": {"type": "http", "url": "http://<url>:<port>/mcp"}}` |

## Развёртывание кнопкой «Развернуть локально»

Кнопка (`POST /api/mcp/{id}/deploy-local/stream`):

1. скачивает последний релиз `bsl-indexer` с GitHub Releases под текущую ОС в
   «Каталог code_index»;
2. пишет `daemon.toml` в этот каталог: `path = <каталог кодовой базы>`,
   `alias = <имя проекта>`;
3. регистрирует **user-level автозапуск** двух процессов и сразу их стартует:
   - Linux — `systemd --user` (имена юнитов `ai1c-code-index-daemon-<id>`,
     `ai1c-code-index-mcp-<id>`);
   - macOS — LaunchAgent;
   - Windows — задание планировщика (`schtasks /SC ONLOGON`);
4. соединение — `http://localhost:<порт>/mcp` (по умолчанию 8005).

Оба процесса получают `CODE_INDEX_HOME=<каталог code_index>`. MCP-сервер
запускается с явными флагами
`--transport http --host 127.0.0.1 --port <порт> --config <каталог>/daemon.toml`
— без них `serve` по умолчанию работает в stdio-режиме.

## Ручное развёртывание

### 1. Скачать бинарь

Нужен именно **`bsl-indexer`** (с поддержкой 1С), а не `code-index` из npm —
публичный `code-index` не умеет BSL.

- GitHub Releases: <https://github.com/Regsorm/code-index-mcp/releases/latest> —
  архив `bsl-indexer` под Windows x64 / Linux x64 / macOS arm64;
- либо собрать из исходников:
  ```bash
  git clone https://github.com/Regsorm/code-index-mcp.git
  cd code-index-mcp
  cargo build --release -p bsl-indexer --features enrichment
  ```

Положите бинарь в каталог, который будет `CODE_INDEX_HOME`, например
`/opt/ai1c/code-index` (Linux/macOS) или `C:\ai1c\code-index` (Windows):

```bash
mkdir -p /opt/ai1c/code-index
cp bsl-indexer /opt/ai1c/code-index/
chmod +x /opt/ai1c/code-index/bsl-indexer
```

### 2. Создать `daemon.toml`

```bash
cat > /opt/ai1c/code-index/daemon.toml <<'EOF'
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"

[[paths]]
path = "/path/to/1c-export"     # реальный путь к выгрузке конфигурации
alias = "<имя проекта>"         # ТОЧНО имя проекта, без slug/транслитерации
language = "bsl"
EOF
```

`path` — абсолютный путь к каталогу кодовой базы на **этом** хосте. Демон
пишет индекс в `<path>/.code-index/index.db`, поэтому каталог нужен на запись.

### 3. Запустить демон и сервер

```bash
export CODE_INDEX_HOME=/opt/ai1c/code-index

# демон-индексатор (единственный писатель)
/opt/ai1c/code-index/bsl-indexer daemon run

# MCP-сервер (read-only HTTP)
/opt/ai1c/code-index/bsl-indexer serve \
  --transport http --host 127.0.0.1 --port 8005 \
  --config /opt/ai1c/code-index/daemon.toml
```

`--config` обязателен: в HTTP-режиме алиасы берутся из `[[paths]]` в
`daemon.toml`. Без `--port` сервер возьмёт 8011.

### 4. Автозапуск (примеры)

**Linux, systemd --user** — два юнита в `~/.config/systemd/user/`:

```ini
# ai1c-code-index-daemon.service
[Unit]
Description=bsl-indexer daemon

[Service]
Environment=CODE_INDEX_HOME=/opt/ai1c/code-index
ExecStart=/opt/ai1c/code-index/bsl-indexer daemon run
Restart=on-failure

[Install]
WantedBy=default.target
```

```ini
# ai1c-code-index-mcp.service
[Unit]
Description=bsl-indexer MCP HTTP
After=ai1c-code-index-daemon.service

[Service]
Environment=CODE_INDEX_HOME=/opt/ai1c/code-index
ExecStart=/opt/ai1c/code-index/bsl-indexer serve --transport http --host 127.0.0.1 --port 8005 --config /opt/ai1c/code-index/daemon.toml
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ai1c-code-index-daemon ai1c-code-index-mcp
loginctl enable-linger "$USER"    # пережить выход из сессии
```

**Windows** — задание планировщика при входе пользователя. Команду с флагами
надёжнее завернуть в `.cmd` (так же делает автозапуск приложения — это
избавляет от проблем с кавычками в `/TR`):

```bat
:: C:\ai1c\code-index\mcp.cmd
@echo off
set "CODE_INDEX_HOME=C:\ai1c\code-index"
C:\ai1c\code-index\bsl-indexer serve --transport http --host 127.0.0.1 --port 8005 --config C:\ai1c\code-index\daemon.toml
```

```bat
schtasks /Create /SC ONLOGON /TN ai1c-code-index-daemon /TR "C:\ai1c\code-index\daemon.cmd" /F
schtasks /Create /SC ONLOGON /TN ai1c-code-index-mcp /TR "C:\ai1c\code-index\mcp.cmd" /F
schtasks /Run /TN ai1c-code-index-daemon
schtasks /Run /TN ai1c-code-index-mcp
```

Аналогичный `daemon.cmd` содержит `set "CODE_INDEX_HOME=…"` и
`bsl-indexer daemon run`. Для демона есть и скрипт upstream
`scripts/install-daemon-autostart.ps1` (он же задаёт `CODE_INDEX_HOME` через
`setx`), но MCP-сервер всё равно нужно зарегистрировать отдельно.

**macOS** — LaunchAgent с двумя `ProgramArguments`
(`daemon run` и `serve --transport http …`), `RunAtLoad=true`,
`KeepAlive=true`.

## Alias репозитория

Для локального вида это особенно важно: `alias` в `daemon.toml` должен быть
**точно равен имени проекта**.

- При развёртывании из UI alias и имя проекта пишутся автоматически.
- В скилле `mcp-usage` плейсхолдер `{{CODE_INDEX_REPO}}` заменяется на имя
  проекта, и агент шлёт `repo="<имя проекта>"` — строки должны совпасть
  побайтово.
- Не применяйте slug, транслитерацию или смену регистра: сервер сравнивает
  алиасы точным равенством.
- Если репозиториев несколько (несколько `[[paths]]`), агент должен передавать
  явный `repo`; при одном репозитории вызов без `repo` тоже работает.

Подробнее — [code-index-common.md](code-index-common.md).

## Подключение

```json
"code_index": {
    "type": "http",
    "url": "http://localhost:8005/mcp"
}
```

Сервер по умолчанию слушает только `127.0.0.1` — с другой машины напрямую не
достучаться. Варианты: SSH-туннель
(`ssh -L 8005:127.0.0.1:8005 user@host`), reverse-proxy с авторизацией или
осознанный `--host 0.0.0.0` в доверенной сети.

## Проверка и диагностика

```bash
export CODE_INDEX_HOME=/opt/ai1c/code-index
/opt/ai1c/code-index/bsl-indexer daemon status --json
/opt/ai1c/code-index/bsl-indexer daemon reload   # после правки daemon.toml

curl -s -H 'Accept: text/event-stream' http://127.0.0.1:8005/mcp
```

Из агента: `health`, `get_stats`, затем `search_terms` с
`repo="<имя проекта>"`. Ответ `daemon_offline` — проверьте, что демон жив и
`CODE_INDEX_HOME` у демона и `serve` одинаковый.
