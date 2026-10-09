# MCP «Статический анализ BSL» — тонкая обёртка FastMCP над BSL Language Server.
# Экспортирует ровно ОДИН инструмент `check` на эндпоинте /mcp (streamable HTTP):
# принимает текст кода BSL и (необязательно) содержимое .bsl-language-server.json,
# возвращает диагностики. Сервер stateless: настройки приходят в самом вызове,
# доступа к кодовой базе/ФС проектов у контейнера нет. Порт — переменная BSL_PORT.
#
# Multi-stage: сборочная стадия качает jar и ставит venv с `mcp`; рантайм берёт
# только JRE + python3 + готовый venv + jar + сервер (без wget/ca-certificates/
# python3-venv и apt-кэшей). Версия BSL LS — --build-arg BSL_LS_VERSION=<версия>.

# ── Стадия сборки: jar + venv ─────────────────────────────────────────────────
FROM eclipse-temurin:21-jre AS builder

ARG BSL_LS_VERSION=1.1.0-rc.6

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      wget ca-certificates python3 python3-venv; \
    rm -rf /var/lib/apt/lists/*; \
    wget -q -O /opt/bsl-language-server.jar \
      "https://github.com/1c-syntax/bsl-language-server/releases/download/v${BSL_LS_VERSION}/bsl-language-server-${BSL_LS_VERSION}-exec.jar"; \
    python3 -m venv /opt/venv; \
    /opt/venv/bin/pip install --no-cache-dir "mcp>=1.2,<2"
# Пин `mcp<2`: в 2.x класс FastMCP переименован в MCPServer и API изменился —
# сервер написан под стабильный FastMCP из линейки 1.x.

# ── Рантайм: минимальный образ ────────────────────────────────────────────────
FROM eclipse-temurin:21-jre

ENV BSL_PORT=8001

# Только интерпретатор python3 (venv со всеми зависимостями копируется из builder).
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3; \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/bsl-language-server.jar /opt/bsl-language-server.jar
COPY --from=builder /opt/venv /opt/venv
COPY bsl_check_server.py /opt/bsl_check_server.py

# Сервер сам читает BSL_PORT из окружения; слушает 0.0.0.0:${BSL_PORT} на /mcp.
CMD ["/opt/venv/bin/python", "/opt/bsl_check_server.py"]
