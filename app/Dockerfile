# Debian-окружение для прогона agent-monitor.
FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Системные пакеты + Node.js (для реального claude CLI).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv python-is-python3 \
        git curl ca-certificates procps nano less \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Реальный claude CLI (для боевого прогона; fake-claude ставится ниже).
RUN npm install -g @anthropic-ai/claude-code || \
    echo "WARN: не удалось поставить claude CLI — доступен только fake-claude"

# Python-зависимости приложения (ставим по requirements для кэша слоёв).
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt

# fake-claude — заглушка для прогона без токенов.
COPY docker/fake-claude /usr/local/bin/claude-fake
RUN chmod +x /usr/local/bin/claude-fake

WORKDIR /app
EXPOSE 8765

# Контейнер живёт, пользователь заходит через `docker compose exec`.
CMD ["sleep", "infinity"]
