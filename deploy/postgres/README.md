# Развертывание PostgreSQL

## Запуск контейнера

Поднимите PostgreSQL:

```bash
docker compose -f deploy/postgres/docker-compose.yml up -d
```

## Конфигурация подключения

Установите переменную окружения `AGENTMON_DSN`:

```bash
export AGENTMON_DSN=postgresql://ai1c:ai1c@127.0.0.1:5432/ai1c
```

## Установка драйвера

Для подключения к PostgreSQL установите драйвер psycopg:

```bash
pip install "psycopg[binary]"
```

## Примечание

Для разработки и тестирования DSN не требуется — по умолчанию используется SQLite-файл `agentmon.db`. Переменная окружения `AGENTMON_DSN` нужна только при использовании PostgreSQL.
