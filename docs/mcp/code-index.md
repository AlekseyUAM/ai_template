# Индексированная кодовая база (в Docker локально) — `code_index`

Docker-вариант code-index: один контейнер, внутри — демон-индексатор и
read-only MCP-сервер (`bsl-indexer`). Каталог кодовой базы — выгрузка
конфигурации/расширения — монтируется в контейнер, индекс БД пишется рядом с
кодом (`<каталог>/.code-index/index.db`).

Общее ядро (два процесса, `daemon.toml`, alias = имя проекта) —
[code-index-common.md](code-index-common.md).

## Поля карточки

| Поле | Значение по умолчанию |
|---|---|
| Наименование | — (обязательно) |
| Имя в `.mcp.json` | `code_index` |
| Назначение | «Полнотекстовый поиск по функциям и классам, граф вызовов, паспорт объекта, смысловой поиск процедур…» |
| URL | `localhost` |
| Порт | `8004` |
| Каталог кодовой базы | — **обязательно** (выгрузка конфигурации) |
| Имя проекта (alias репозитория) | — **обязательно**, = имя проекта |
| Подключение | `{"code_index": {"type": "http", "url": "http://<url>:<port>/mcp"}}` |

## Развёртывание кнопкой

«Развернуть в Docker локально»:

1. если образа `bsl-indexer:local` нет — клонирует (при отсутствии)
   [Regsorm/code-index-mcp](https://github.com/Regsorm/code-index-mcp) в
   `deps/code-index-mcp` и собирает образ из
   `deps/code-index-mcp/deploy/docker/Dockerfile`;
2. пишет `.ai1c/mcp-state/<id>/daemon.toml` с `alias = <имя проекта>` и
   `path = "/repos/src"`;
3. запускает контейнер `ai1c-mcp-code_index` с `--restart unless-stopped`:
   - `-p 127.0.0.1:<порт>:<порт>`;
   - `-e CODE_INDEX_HOME=/data/code-index-home`;
   - `-e MCP_HTTP_HOST=0.0.0.0`, `-e MCP_HTTP_PORT=<порт>`;
   - `-v <каталог кодовой базы>:/repos/src` (rw);
   - `-v <.ai1c/mcp-state/<id>>:/data/code-index-home`.

Первичная индексация идёт в фоне; до её окончания инструменты возвращают
прогресс, а не ошибку.

## Ручное развёртывание (в том числе на отдельном сервере)

```bash
git clone https://github.com/Regsorm/code-index-mcp.git
cd code-index-mcp

docker build -f deploy/docker/Dockerfile -t bsl-indexer:local .
```

Создайте каталог состояния и `daemon.toml` (alias — **точное имя проекта**,
path — точка монтирования кода внутри контейнера):

```bash
mkdir -p /srv/code-index-home
cat > /srv/code-index-home/daemon.toml <<'EOF'
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"

[[paths]]
path = "/repos/src"
alias = "<имя проекта>"
language = "bsl"
EOF
```

Запуск:

```bash
docker run -d --restart unless-stopped \
  --name ai1c-mcp-code_index \
  -p 8004:8004 \
  -e CODE_INDEX_HOME=/data/code-index-home \
  -e MCP_HTTP_HOST=0.0.0.0 \
  -e MCP_HTTP_PORT=8004 \
  -v /srv/1c-export:/repos/src \
  -v /srv/code-index-home:/data/code-index-home \
  bsl-indexer:local
```

Альтернатива — compose из апстрима
(`deploy/docker/docker-compose.yml`, `REPOS_DIR=<каталог>`), но в его
`daemon.toml` нужно поправить `alias` на имя проекта и путь под свой монтаж.

На **отдельной машине** разверните контейнер там, где доступна выгрузка
конфигурации: индекс пишется в `<каталог>/.code-index/index.db`, поэтому
каталог должен быть локальным/смонтированным на запись. Порт публикуйте в
доверенной сети (аутентификации нет) — или через reverse-proxy.

## Подключение

```json
"code_index": {
    "type": "http",
    "url": "http://<хост>:8004/mcp"
}
```

Агент передаёт `repo="<имя проекта>"` — см. [code-index-common.md](code-index-common.md).

## Обновление

- новые исходники: демон подхватывает изменения сам (file-watcher);
- новая версия `bsl-indexer`: `docker compose ... up -d --build` или
  пересоберите образ и перезапустите контейнер (индекс сохраняется в каталоге
  кода);
- правка `daemon.toml` в контейнере: перезапустите контейнер (или
  `docker exec ... bsl-indexer daemon reload`).

## Проверка

```bash
docker logs -f ai1c-mcp-code_index
docker exec ai1c-mcp-code_index bsl-indexer daemon status --json
curl -s -H 'Accept: text/event-stream' http://127.0.0.1:8004/mcp
```

Из агента: `health`, `get_stats`, затем `search_terms` с `repo="<имя проекта>"`.
