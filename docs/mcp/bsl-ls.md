# Статический анализ BSL — `bsl_ls`

Тонкая FastMCP-обёртка над BSL Language Server: **один инструмент `check`**,
который принимает текст модуля (и обязательный SHA-256 файла) и возвращает
диагностики и сырые счётчики `counts`. Сервер **stateless**: доступа к кодовой
базе и файловой системе проекта у него нет — настройки передаются содержимым
`.bsl-language-server.json` прямо в вызове.

- Образ: `ai1c/mcp-bsl-ls:local`
- Dockerfile: `app/docker/mcp/bsl-ls.Dockerfile` (контекст `app/docker/mcp`)
- Внутри: JRE 21 + `bsl-language-server-<версия>-exec.jar` + FastMCP-сервер
  (`app/docker/mcp/bsl_check_server.py`)
- Эндпоинт: `http://<host>:<port>/mcp` (streamable HTTP)
- Версия BSL LS задаётся build-arg `BSL_LS_VERSION` (по умолчанию `1.1.0-rc.6`)

## Поля карточки

| Поле | Значение по умолчанию |
|---|---|
| Наименование | — (обязательно) |
| Имя в `.mcp.json` | `bsl_ls` |
| Назначение | «Статический анализ кода на соответствие стандартам 1С» |
| URL | `localhost` |
| Порт | `8001` |
| Подключение | `{"bsl_ls": {"type": "http", "url": "http://<url>:<port>/mcp"}}` |

## Развёртывание кнопкой

«Развернуть в Docker локально»:

1. если образа нет — собирает его из `app/docker/mcp/bsl-ls.Dockerfile`;
2. запускает контейнер `ai1c-mcp-bsl_ls` с `--restart unless-stopped`,
   `-e BSL_PORT=<порт>` и публикацией `-p 127.0.0.1:<порт>:<порт>`.

## Ручное развёртывание (в том числе на отдельном сервере)

Сборка из корня репозитория `ai_template` (нужен интернет: Dockerfile
скачивает jar BSL LS с GitHub Releases):

```bash
docker build \
  --build-arg BSL_LS_VERSION=1.1.0-rc.6 \
  -t ai1c/mcp-bsl-ls:local \
  -f app/docker/mcp/bsl-ls.Dockerfile app/docker/mcp
```

Запуск:

```bash
docker run -d --restart unless-stopped \
  --name ai1c-mcp-bsl_ls \
  -p 8001:8001 \
  -e BSL_PORT=8001 \
  ai1c/mcp-bsl-ls:local
```

На отдельной машине повторите сборку/запуск там (или перенесите образ через
`docker save`/`docker load`). Порт публикуйте только в доверенной сети:
**аутентификации у сервера нет**. Для публикации наружу поставьте
reverse-proxy с авторизацией.

Если нужен другой путь к jar внутри образа, его можно переопределить
переменной `BSL_JAR` (по умолчанию `/opt/bsl-language-server.jar`).

## Подключение

В карточке укажите `URL` и `Порт`, либо впишите адрес вручную в «Подключение»:

```json
"bsl_ls": {
    "type": "http",
    "url": "http://<хост-BSL-LS>:8001/mcp"
}
```

## Как пользоваться

Агент вызывает инструмент `check(sha256, code|file_path, config, filename)`
(в Claude Code — `mcp__bsl_ls__check`).

- **`sha256` — обязателен** (64 hex). Вычисли его по самому файлу, а не по
  перепечатанному тексту:

  ```bash
  sha=$(sha256sum src/cf/CommonModules/Модуль/Ext/Module.bsl | cut -d' ' -f1)
  # macOS/BSD: shasum -a 256 src/cf/CommonModules/Модуль/Ext/Module.bsl
  ```

  Без `sha256` вызов отклоняется; если хэш текста не совпал с хэшем файла —
  `ok=false` с обоими значениями и java не запускается. Модуль не перепечатывай
  вручную — передавай его точный текст как есть.
  **BOM:** сервер срезает ведущий UTF-8 BOM перед анализом (BSL LS на нём падает
  с `ParseError`). Принимается `sha256` как файла с BOM (`sha256sum`), так и
  нормализованного текста без BOM — поэтому обычный `sha256sum` работает.
- **Ровно один источник:** `code` (текст модуля) или `file_path`. `file_path`
  работает, только если путь виден из контейнера (сервер проект не монтирует);
  в стандартном Docker-развёртывании используйте `code`+`sha256`. При `file_path`
  сервер сам читает файл, срезает BOM и проверяет его хэш; `filename` по
  умолчанию — basename пути.
- Перед вызовом агент читает `.bsl-language-server.json` из корня проекта и
  передаёт его содержимое в `config`; файл разворачивается в проект из шаблона
  окружения (`template/.bsl-language-server.json`). Если файла нет — анализ идёт
  с правилами BSL LS по умолчанию.

Ответ: `{ok, count, counts, diagnostics, summary, sha256, source, bytes,
bom_removed[, raw_sha256]}`. `counts` — сырые счётчики по уровням: `Error`,
`Warning`, `Information`, `Hint`; `source` — `code` или `file`; `bytes` —
размер исходного присланного текста в UTF-8; `sha256` — хэш нормализованного
текста (без BOM); при срезанном BOM дополнительно возвращаются
`bom_removed: true` и `raw_sha256` — хэш исходного текста.

## Проверка

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/mcp
```

Из агента — `check` на заведомо «грязном» коде (например, строка длиннее
140 символов) должен вернуть диагностику `LineLength`.
