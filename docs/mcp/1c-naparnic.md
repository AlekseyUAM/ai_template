# 1С:Напарник — `1c_naparnic`

MCP-обёртка над 1С:Напарником — внешним ИИ-ассистентом по платформе и типовым
решениям 1С. Проект:
[SteelMorgan/spring-mcp-1c-copilot](https://github.com/SteelMorgan/spring-mcp-1c-copilot).

- Образ: `copilot-spring-mcp-1c-copilot:latest` (готовится **заранее**: у вида
  нет Dockerfile в репозитории, кнопка только запускает существующий образ)
- Переменные: `ONEC_AI_TOKEN` (токен Напарника), `SSE_PORT` (порт)
- Эндпоинт: `http://<host>:<port>/mcp` (streamable HTTP)
- Нужен **внешний интернет**: сервер ходит к `code.1c.ai`

Токен выдаётся в личном кабинете [code.1c.ai](https://code.1c.ai).

## Поля карточки

| Поле | Значение по умолчанию |
|---|---|
| Наименование | — (обязательно) |
| Имя в `.mcp.json` | `1c_naparnic` |
| Назначение | «Объяснение логики кода, любые вопросы по информационно-технологическому сопровождению 1С» |
| URL | `localhost` |
| Порт | `8003` |
| Токен | — (без него сервер бесполезен) |
| Подключение | `{"1c_naparnic": {"type": "http", "url": "http://<url>:<port>/mcp"}}` |

## Развёртывание кнопкой

Перед первым запуском соберите образ и назовите его так, как ждёт UI:

```bash
git clone https://github.com/SteelMorgan/spring-mcp-1c-copilot.git
cd spring-mcp-1c-copilot
cp env.example .env          # ONEC_AI_TOKEN=..., SSE_PORT=8003
./scripts/prepare-token-secret.sh
docker build -f Dockerfile.build -t copilot-spring-mcp-1c-copilot:latest .
```

После этого «Развернуть в Docker локально» запускает контейнер
`ai1c-mcp-1c_naparnic` с `-e SSE_PORT=<порт>` и `-e ONEC_AI_TOKEN=<токен>`.
На Linux контейнер идёт в сети хоста (`--network=host`) — так решается проблема
внешнего DNS в sandbox; на Docker Desktop используется bridge с публикацией
`127.0.0.1:<порт>`.

## Ручное развёртывание (в том числе на отдельном сервере)

```bash
docker run -d --restart unless-stopped \
  --name ai1c-mcp-1c_naparnic \
  -p 8003:8003 \
  -e SSE_PORT=8003 \
  -e ONEC_AI_TOKEN='<токен>' \
  copilot-spring-mcp-1c-copilot:latest
```

На отдельной машине соберите образ там (или перенесите через
`docker save`/`docker load`) и запустите. Требования:

- исходящий доступ в интернет к `code.1c.ai`;
- если bridge-сеть не резолвит внешний DNS (как в sandbox), используйте
  `--network=host` (порт публиковать не нужно) — либо исправьте DNS демона.

Токен можно передать через `-e` (как делает UI) или через secret-файл/переменную
окружения, как в апстримном `docker compose`.

## Подключение

```json
"1c_naparnic": {
    "type": "http",
    "url": "http://<хост>:8003/mcp"
}
```

## Инструменты

`ask_1c_ai` (вопрос по 1С), `explain_1c_syntax` (объяснение конструкции языка).
Инструмент проверки кода `check_1c_code` в окружении не используется — для
проверки кода применяйте `bsl_ls`.

## Безопасность

- **Токен — секрет.** Не коммитьте его в репозиторий и не публикуйте контейнер
  в интернет: сервер не имеет собственной аутентификации.
- Запросы и фрагменты кода уходят во внешний сервис 1С. Не отправляйте
  конфиденциальные данные без необходимости.

## Проверка

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/mcp
```

Из агента — `ask_1c_ai` с простым вопросом; ошибка авторизации означает
неверный/просроченный токен.
