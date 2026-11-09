# Статический анализ BSL — `bsl_ls`

Тонкая FastMCP-обёртка над BSL Language Server: **один инструмент `check`**,
который принимает текст модуля и возвращает диагностики. Сервер **stateless**:
доступа к кодовой базе и файловой системе проекта у него нет — настройки
передаются содержимым `.bsl-language-server.json` прямо в вызове.

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

Агент вызывает инструмент `check(code, config, filename)` (в Claude Code —
`mcp__bsl_ls__check`). Перед вызовом он читает `.bsl-language-server.json`
из корня проекта и передаёт его содержимое в `config`; файл разворачивается
в проект из шаблона окружения (`template/.bsl-language-server.json`).
Если файла нет — анализ идёт с правилами BSL LS по умолчанию.

## Проверка

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/mcp
```

Из агента — `check` на заведомо «грязном» коде (например, строка длиннее
140 символов) должен вернуть диагностику `LineLength`.
