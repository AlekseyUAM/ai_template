# Справка по платформе — `1c_platform`

MCP-сервер `mcp-bsl-platform-context` (проект
[alkoleft/mcp-bsl-platform-context](https://github.com/alkoleft/mcp-bsl-platform-context)):
ищет по встроенной справке платформы 1С — типы, методы, свойства,
конструкторы. Данные берутся из файлов справки установленной платформы, поэтому
контейнеру нужен доступ к каталогу платформы.

- Образ: `mcp-bsl-context:latest`
- Dockerfile: `deps/docker_1c_sandbox/mcp-bsl-context/Dockerfile`
  (в репозитории — [AlekseyUAM/docker_1c_sandbox](https://github.com/AlekseyUAM/docker_1c_sandbox.git),
  клонируется автоматически при сборке из UI)
- Внутри: JRE 17 + `mcp-bsl-context-0.3.2_.jar`
- Транспорт: **SSE**, эндпоинт `http://<host>:<port>/sse`
- Переменные: `MCP_BSL_CONTEXT_PORT` (порт), `ONEC_PLATFORM_PATH` (путь к
  каталогу платформы внутри контейнера)

## Поля карточки

| Поле | Значение по умолчанию |
|---|---|
| Наименование | — (обязательно) |
| Имя в `.mcp.json` | `1c_platform` |
| Назначение | «Справочная информация по встроенным функциям, типам данных, методам и свойствам платформы» |
| URL | `localhost` |
| Порт | `8002` |
| Путь к платформе | — **обязательно**, каталог установленной платформы |
| Подключение | `{"1c_platform": {"type": "sse", "url": "http://<url>:<port>/sse", "transport": "sse"}}` |

## Развёртывание кнопкой

«Развернуть в Docker локально» собирает образ из
`deps/docker_1c_sandbox/mcp-bsl-context` (если каталога `deps` нет —
клонирует репозиторий) и запускает контейнер `ai1c-mcp-1c_platform`:

- `-p 127.0.0.1:<порт>:<порт>`;
- `-e MCP_BSL_CONTEXT_PORT=<порт>`;
- `-e ONEC_PLATFORM_PATH=<путь к платформе>`;
- `-v <путь к платформе>:<путь к платформе>:ro`.

## Ручное развёртывание (в том числе на отдельном сервере)

```bash
git clone https://github.com/AlekseyUAM/docker_1c_sandbox.git
cd docker_1c_sandbox/mcp-bsl-context

docker build -t mcp-bsl-context:latest .

docker run -d --restart unless-stopped \
  --name ai1c-mcp-1c_platform \
  -p 8002:8002 \
  -e MCP_BSL_CONTEXT_PORT=8002 \
  -e ONEC_PLATFORM_PATH=/opt/1cv8/x86_64/8.3.27.1786 \
  -v /opt/1cv8/x86_64/8.3.27.1786:/opt/1cv8/x86_64/8.3.27.1786:ro \
  mcp-bsl-context:latest
```

Путь к платформе должен существовать **на машине, где запущен контейнер**.
Путь внутри контейнера и снаружи в этом рецепте одинаковый (Linux-допущение);
на Windows-хосте это не сработает без отдельной настройки — удобнее поднять
сервер на Linux-машине, где лежит платформа, и указать её адрес в карточке.

Если порт по умолчанию (9001 в Dockerfile) не нужен, переопределяйте его
через `MCP_BSL_CONTEXT_PORT` — как в примере выше.

## Подключение

```json
"1c_platform": {
    "type": "sse",
    "url": "http://<хост>:8002/sse",
    "transport": "sse"
}
```

## Инструменты

`search`, `info`, `getMembers`, `getMember`, `getConstructors` — поиск по API
платформы, карточка элемента, полный список членов типа, конструкторы.

## Проверка

```bash
curl -s -N --max-time 2 http://127.0.0.1:8002/sse
```

Из агента — `search` по известному методу (например, `СтрШаблон`) должен
вернуть карточку. Если ответ пустой, проверьте путь к платформе и версию
(справка должна соответствовать установленной платформе).

## Безопасность

Аутентификации нет: не публикуйте порт в интернет, используйте доверенную
сеть или reverse-proxy с авторизацией.
