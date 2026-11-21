# Индексированная кодовая база (локально) — `code_index`

Нативное развёртывание code-index: **без Docker**, одним статическим бинарём
`bsl-indexer` на хосте. Два процесса — демон-индексатор и read-only
MCP-сервер — запускаются прямо на машине. Это **единственный поддерживаемый
вид** code-index: Docker-вариант ([code-index.md](code-index.md)) — legacy.
Поддерживаются платформы, под которые upstream публикует релизы:
**Windows x64, Linux x64, macOS arm64**.

Общее ядро (два процесса, `daemon.toml`, alias = имя проекта) —
[code-index-common.md](code-index-common.md).

## Когда выбирать этот вид

- кодовая база лежит на той же машине, где работает агент (или на сервере,
  доступном по сети);
- нужен быстрый старт и минимум движущихся частей: бинарь + `daemon.toml`.

Docker здесь не нужен и не используется (на Windows bind-mount не даёт
inotify-событий — индекс в контейнере не обновляется). Если кодовая база на
другом сервере — разверните сервис там и ходите к нему по сети/туннелю.

## Поля карточки

| Поле | Значение по умолчанию |
|---|---|
| Наименование | — (обязательно) |
| Имя в `.mcp.json` | `code_index` |
| Назначение | «Полнотекстовый поиск по функциям и классам, граф вызовов, паспорт объекта, смысловой поиск процедур…» |
| URL | `localhost` |
| Порт | `8005` |
| Каталог кодовой базы | — **обязательно** (выгрузка конфигурации) |
| Имя проекта (alias репозитория) | — **обязательно**, = имя проекта |
| Каталог code_index | — **обязательно**: каталог для бинаря, `daemon.toml`, рантайма и логов |
| Подключение | `{"code_index": {"type": "http", "url": "http://<url>:<port>/mcp"}}` |

## Развёртывание из UI

Кнопка «Развернуть локально» (`POST /api/mcp/{id}/deploy-local/stream`):

1. скачивает последний релиз `bsl-indexer` с GitHub Releases под текущую ОС в
   «Каталог code_index» (если бинаря там ещё нет);
2. добавляет в `daemon.toml` этого каталога блок `[[paths]]` с
   `path = <каталог кодовой базы>`, `alias = <имя проекта>` (чужие блоки не
   трогаются) и дополняет секции `[mcp]` / `[[cache_targets]]`;
3. новый сервис (в каталоге ещё нет `service.json`) регистрирует
   **user-level автозапуск** двух процессов и сразу их стартует:
   - Linux — `systemd --user` (имена юнитов `ai1c-code-index-daemon-<id>`,
     `ai1c-code-index-mcp-<id>`);
   - macOS — LaunchAgent;
   - Windows — задание планировщика (`schtasks /SC ONLOGON`);
4. для уже существующего сервиса — `bsl-indexer daemon reload` (демон
   перечитывает `[[paths]]`) и перезапуск `serve`; порт берётся из
   `service.json` (развёртывание с другим портом отклоняется);
5. соединение — `http://localhost:<порт>/mcp` (по умолчанию 8005).

Один сервис (каталог `code_index_dir`) обслуживает **несколько баз**: каждая
новая карточка с тем же «Каталогом code_index» добавляет свой `[[paths]]` —
подробнее в [code-index-common.md](code-index-common.md).

> **Смена «Каталога code_index» — это не миграция.** Сервис привязан к каталогу
> (имя юнита/задания — хеш пути), и старый сервис продолжает держать порт.
> Первое развёртывание в новом каталоге проверяет порт и отказывает
> («порт … уже занят»). Сначала остановите и удалите старый сервис (автозапуск
> `ai1c-code-index-daemon-<id>` / `ai1c-code-index-mcp-<id>`), затем разверните
> заново — или укажите другой порт.

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

Две базы в одном сервисе — по блоку `[[paths]]` на каждую (`alias` = имя
проекта соответствующей карточки), общий порт в `[[cache_targets]]`:

```toml
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"

[[cache_targets]]
url = "http://127.0.0.1:8005"   # порт serve — из service.json

[mcp]
mass_mode_tools = ["get_object_structure"]

[[paths]]
path = "/srv/1c/УправлениеТорговлей"
alias = "УправлениеТорговлей"
language = "bsl"

[[paths]]
path = "/srv/1c/Бухгалтерия"
alias = "Бухгалтерия"
language = "bsl"
```

`path` — абсолютный путь к каталогу кодовой базы на **этом** хосте. Демон
пишет индекс в `<path>/.code-index/index.db`, поэтому каталог нужен на запись.
Порт сервиса agentmon хранит в `service.json` в «Каталоге code_index»
(`{"port": 8005, "version": 1}`) — его же указывают `serve --port` и
`[[cache_targets]]`. После правки `daemon.toml` выполните
`bsl-indexer daemon reload` и перезапустите `serve`: секции `[mcp]` и
`[[cache_targets]]` сервер читает один раз при старте.

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
