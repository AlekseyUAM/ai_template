# Самодостаточный образ агента: платформа 1С + рантайм Claude Code.
# Дистрибутив платформы кладётся в build-контекст как distr.zip
# (см. agentmon.env.docker_image.build_agent_image).
FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

# Node.js 20 LTS + системные зависимости платформы 1С + headless-дисплей
RUN apt-get update -o Acquire::ForceIPv4=true -o Acquire::Retries=3 \
  && apt-get install -y --no-install-recommends curl ca-certificates \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends \
    locales \
    xvfb \
    libglib2.0-0 \
    libgsf-1-114 \
    libwebkit2gtk-4.0-37 \
    libfontconfig1 \
    libfreetype6 \
    libcups2 \
    libsm6 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxinerama1 \
    libxrandr2 \
    libatk1.0-0 \
    libgtk-3-0 \
    libglu1-mesa \
    libodbc2 \
    fonts-dejavu \
    fonts-liberation \
    nodejs \
    unzip \
    python3 \
    python3-pip \
    python-is-python3 \
  && echo "ru_RU.UTF-8 UTF-8" >> /etc/locale.gen \
  && locale-gen \
  && printf 'LANG=ru_RU.UTF-8\nLC_ALL=ru_RU.UTF-8\n' > /etc/default/locale \
  && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (агент запускается командой `claude` внутри контейнера)
RUN npm install -g @anthropic-ai/claude-code

# Установить платформу 1С из дистрибутива build-контекста
COPY distr.zip /tmp/distr/distr.zip
RUN set -eux; \
  unzip -q /tmp/distr/distr.zip -d /tmp/distr/unpacked; \
  run_file="$(find /tmp/distr/unpacked -name '*.run' | head -1)"; \
  chmod +x "$run_file"; \
  "$run_file" --mode unattended --enable-components server,server_admin,client_full,ru; \
  rm -rf /tmp/distr

# Симлинк /opt/1cv8/current -> установленная версия
RUN arch_dir="$(ls /opt/1cv8 | grep -E 'x86_64|amd64' | head -n1)"; \
    ver="$(ls /opt/1cv8/${arch_dir} | sort -V | tail -n1)"; \
    ln -sfn "/opt/1cv8/${arch_dir}/${ver}" /opt/1cv8/current

ENV PATH="/opt/1cv8/current:${PATH}" \
    LANG="ru_RU.UTF-8" \
    LC_ALL="ru_RU.UTF-8"
