# Спека: Docker-поверх-SSH — контейнер проекта на удалённом демоне

Дата: 2026-10-19. Фаза: 3 follow-up, спека 3 (последняя). Самый крупный из follow-up.

## Контекст и мотивация

Docker-бэкенд поднимает контейнер проекта на **локальном** демоне. Этот шаг добавляет
**удалённый** демон: контейнер проекта живёт на другом хосте, docker-команды идут туда
по SSH. Так один монитор обслуживает проекты на нескольких docker-хостах.

**Ключ решения:** `docker` CLI умеет `docker -H ssh://user@host …` (connection
helper поверх ssh). Весь docker-бэкенд уже ходит через инъектируемый `run`/`docker`
CLI — значит docker-over-ssh сводится к **добавлению `-H <docker_host>` к каждой
docker-команде**. Контейнер, `docker exec`, чтение JSONL, PTY агента — всё уходит на
удалённый демон прозрачно (CLI туннелирует tty/stdio по ssh).

## Решения

- **Локальный docker-бэкенд не меняется**: `docker_host=None` → команды как сейчас
  (без `-H`).
- Удалённый демон задаётся в `conn` docker-проекта: либо явный `conn.docker_host`
  (например `"ssh://user@host:22"`), либо поля `conn.host`/`user`/`port` → строим
  `ssh://[user@]host[:port]`. Аутентификация ssh — через ssh-agent/`~/.ssh/config`
  (docker ssh-helper использует системный ssh; отдельный `key_path` в URL не кладём —
  документируем требование agent/config; это согласуется с тем, как работает
  `docker -H ssh://`).
- Образ-тулкит должен существовать **на удалённом демоне** (собирается там из
  `deps/docker_1c_sandbox`); `ensure` при отсутствии бросает понятную ошибку (как
  локально).
- Внешние ресурсы (сервер 1С, лицензии, MCP) должны быть достижимы **из сети
  удалённого хоста/его контейнера** (как в ssh-бэкенде). `--add-host=
  host.docker.internal:host-gateway` указывает на удалённый docker-хост.

## Текущее состояние

- `_DockerContainer` строит docker-команды напрямую списками `["docker", …]` в 8
  местах: `inspect` (status), `run`, `start`, `exec -d` (Xvfb), `exec_run`,
  `exec_input`, `exec_run_bytes`, `rm`. Плюс проверка образа — через
  `mcp_docker.image_exists(image, run)` (строит локальную `docker images -q`).
- `DockerRunner.start` спавнит строку `f"docker exec -it -w {workdir} {name} {cmd}"`
  через `pty_process.spawn` (cwd — валидный ХОСТОВЫЙ каталог).
- `DockerBackend.__init__(project_path, *, claude_cmd, image, workdir, run, spawn_fn,
  home)` выводит `name`/`volume`/`claude_volume`, `key=f"docker||{project_path}"`,
  строит container+runner+files+provisioner. Не знает про conn/host.
- `factory`: `docker_factory` по умолчанию `DockerBackend(project.path,
  claude_cmd=..., image=(conn or {}).get("image") or DEFAULT_IMAGE)`; `key_for(docker)`
  → `f"docker||{project.path}"`. conn в factory пока используется только для image.
- `models.Project.key` = `f"{backend}|{host or ''}|{path}"`, где `host=conn.get("host")`
  — уже различает хосты, если conn.host задан.

## Архитектура решения

### Часть A — `_DockerContainer` с `-H <docker_host>`

- `__init__(..., docker_host: str | None = None)`; хранить `self._docker_host`.
- Хелпер `_argv(tail: list[str]) -> list[str]` → `["docker"] + (["-H",
  self._docker_host] if self._docker_host else []) + tail`. Заменить все 8
  `["docker", …]` на `self._argv([...])`.
- Проверку образа делать **самим контейнером** через `_argv(["images","-q",image])`
  (чтобы целиться в нужный демон), а не `mcp_docker.image_exists` (строит локальную
  команду). `_build` остаётся хуком-исключением.
- Публичное свойство `docker_host` (для `DockerRunner`).
- `docker_host=None` → argv байт-в-байт как сейчас (регрессия локального режима).

### Часть B — `DockerRunner` с `-H`

- `start`: вставить `-H <docker_host>` в спавн-строку, когда контейнер удалённый:
  `host_flag = f" -H {shlex.quote(dh)}" if dh else ""`; команда
  `f"docker{host_flag} exec -it -w {shlex.quote(workdir)} {shlex.quote(name)} {cmd}"`.
  `dh = self._container.docker_host`. Локально (`dh=None`) — строка как сейчас.

### Часть C — `DockerBackend` + factory

- Хелпер разбора conn → docker_host: `conn.docker_host` если задан; иначе если задан
  `conn.host` → `ssh://` + (`{user}@` если user) + host + (`:{port}` если port);
  иначе `None` (локальный демон).
- `DockerBackend.__init__(project_path, *, claude_cmd, image, workdir, run, spawn_fn,
  home, docker_host=None)` — прокинуть `docker_host` в `_DockerContainer`;
  `key=f"docker|{host_part}|{project_path}"` где host_part выводится из docker_host
  (или пусто для локального — сохранить `docker||{path}` для локали, чтобы не ломать
  существующий кеш/тесты).
- `factory`: `docker_factory` вычисляет `docker_host` из `project.conn` и передаёт в
  `DockerBackend`; `key_for(docker)` → `f"docker|{project.host or ''}|{project.path}"`
  (для локали host пуст → `docker||{path}`, как сейчас).

### Часть D — мастер (web) + project_api

- Мастер, docker-раздел: добавить необязательные поля удалённого демона — хост, порт,
  пользователь (или одно поле «docker_host (ssh://…)»). Пусто → локальный демон.
  `readConn` docker → `{image?, host?, user?, port?}` (или `{docker_host?}`).
- `project_api`: создание/валидации уже идут через provisioner выбранного backend —
  для удалённого docker это `DockerProvisioner`, нацеленный на удалённый демон
  (работает «из коробки» после Частей A–C). Доп. кода в project_api, скорее всего,
  не требуется (проверить). `platform_dir`-дефолт `/opt/1cv8/current` остаётся.

## Границы (YAGNI)

- Аутентификация ssh — только agent/`~/.ssh/config` (docker ssh-helper); `key_path` в
  URL не поддерживаем (ограничение docker CLI; документируем).
- Не поднимаем демон/туннель сами — используем штатный `docker -H ssh://`.
- Сборку тулкит-образа на удалённом демоне не делаем (ответственность пользователя,
  как и локально).
- Windows-монитор как клиент `docker -H ssh://` — не прорабатываем (Linux-монитор).

## Обработка ошибок

- Удалённый демон недоступен / ssh не поднялся → docker-команда даёт ненулевой код /
  stderr-маркер → `_is_container_down`/`ensure` → `mark_broken`/`RuntimeError` (как
  локально; `list_files` пометит broken).
- Нет образа на удалённом демоне → `ensure` бросает с инструкцией собрать образ там.

## Тестируемость

- `_DockerContainer` с `docker_host="ssh://u@h"` → каждая команда (inspect/run/start/
  xvfb/exec_run/exec_input/exec_run_bytes/rm/images) содержит `-H ssh://u@h` сразу
  после `docker`; с `docker_host=None` — argv как раньше (регресс всех ensure-тестов).
- Проверка образа идёт на нужный демон (`docker -H … images -q`).
- `DockerRunner.start` с удалённым контейнером → спавн-строка `docker -H ssh://u@h
  exec -it …`; локально — без `-H`.
- Разбор conn: `{docker_host}` → как есть; `{host,user,port}` → `ssh://user@host:port`;
  `{host}` → `ssh://host`; пусто → None.
- factory/key: удалённый docker → `docker|{host}|{path}`; локальный → `docker||{path}`
  (регресс). Два проекта на одном пути, но разных демонах → разные ключи/бэкенды.
- Мастер: docker-поля демона присутствуют; `readConn` отдаёт их; пусто → локальный.
- Регрессия: локальные docker/ssh/local-сценарии не меняются.

## Единицы

- `backends/docker.py` — `_DockerContainer._argv`/`docker_host`; замена 8 сайтов;
  image-check через `_argv`; `DockerRunner.start` `-H`; `DockerBackend` docker_host +
  key; conn→docker_host хелпер.
- `backends/factory.py` — docker_factory вычисляет docker_host; `key_for(docker)` с
  host.
- `env/project_api.py` — проверить, что удалённый docker проходит (вероятно без правок).
- `app/web/project-wizard.html`/`.js` — поля удалённого демона в docker-разделе.
- `docs/PHASES.md` — «Docker-поверх-SSH» → «Реализовано»; `docs/DEPLOY-DOCKER.md` —
  заметка про удалённый демон (`docker_host`/host, образ на удалённом демоне, ssh-agent).
- Тесты: `test_backend_docker.py`, `test_backend_factory.py`/registry, wizard-тест.

## Открытые вопросы

Нет. `docker -H ssh://` (agent/config-аутентификация); conn задаёт `docker_host` или
`host/user/port`; локальный режим (`docker_host=None`) неизменен; образ — на удалённом
демоне.
