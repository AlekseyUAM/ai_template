# Спека: docker-гигиена — list_files (контейнер-down vs нет сессий) + персистентность ~/.claude

Дата: 2026-10-19. Фаза: 3 follow-up, спека 2 (быстрые фиксы docker-бэкенда).

## Контекст

Два мелких, но важных пункта «Следующих шагов», оба про docker-бэкенд проекта:

1. **`list_files`/`read_from` не отличают «контейнер/демон упал» от «сессий ещё нет».**
   `DockerFiles.list_files` сейчас: `except Exception → mark_broken+[]`, но
   `if res.returncode != 0: return []` — ЛЮБОЙ ненулевой код (включая `125` «контейнер
   не запущен», `126/127` «exec не удался») трактуется как «каталога нет» → `[]` БЕЗ
   `mark_broken`. Значит упавший контейнер выглядит как «просто нет сессий», и монитор
   не показывает недоступность. (ssh уже различает: SFTP `FileNotFoundError`→`[]`,
   прочее→`mark_broken`; правка нужна ТОЛЬКО для docker.)
2. **`~/.claude` контейнера проекта не переживает пересоздание.** `_DockerContainer`
   монтирует volume только под `/workspace`; домашний каталог агента (где лежат
   `~/.claude/projects/*.jsonl` и авторизация claude) — эфемерный. При пересоздании
   контейнера журналы/логин теряются.

## Текущее состояние

- `DockerFiles.list_files`: `exec_run(["find", dir, ...])`; `except Exception`→
  `mark_broken+[]`; `rc!=0`→`[]` (без разбора причины); `rc==0`→парсинг
  `%p\t%s\t%T@`. `read_from`: `exec_run_bytes`; `except`→`mark_broken+(b"",off)`;
  `rc!=0`→`(b"",off)`.
- `_DockerContainer.ensure` docker run: `-v {volume}:{workdir}` + env `DISPLAY=:99` +
  `--add-host` + `sleep infinity`. Нет монтажа home.
- `DockerBackend.__init__(project_path, ...)`: выводит `name=container_name(path)`,
  `volume=f"{name}-work"`; строит `_DockerContainer(name, image, workdir, volume, run)`.
- `DockerFiles` определяет home лениво (`echo $HOME`), дефолт-догадка `/root`. Под
  `docker run`/`docker exec` без `-u` пользователь = USER образа; тулкит-образ
  (`mcr…/devcontainers/base`) по умолчанию root → `HOME=/root`.

## Архитектура решения

### Часть A — docker list_files/read_from: различать down vs нет-сессий

Ввести helper `_is_container_down(rc: int, stderr: str) -> bool`:
- `rc in (125, 126, 127)` — docker-уровневые коды: 125 «контейнер не запущен/демон»,
  126/127 «команда exec не найдена/не исполнима»;
- или `stderr` содержит маркеры недоступности: `"No such container"`,
  `"is not running"`, `"Cannot connect to the Docker daemon"`, `"No such exec"`,
  `"error during connect"`.

`list_files`:
- `except Exception`→`mark_broken+[]` (как сейчас — питонья ошибка запуска docker).
- `rc==0`→парсинг.
- `rc!=0 and _is_container_down(rc, stderr)`→`mark_broken()+[]`.
- иначе (например `find` rc=1 «нет каталога»)→`[]` без `mark_broken`.

`read_from`: аналогично — `_is_container_down`→`mark_broken()+(b"",off)`; прочий
`rc!=0`→`(b"",off)` без mark_broken. (У `exec_run_bytes` есть и rc, и stderr — если
stderr не возвращается bytes-вариантом, опираться на rc-коды 125/126/127; при нужде
`exec_run_bytes` вернуть и stderr — минимально.)

### Часть B — персистентный `~/.claude` контейнера проекта

- `_DockerContainer.__init__`: добавить `claude_volume: str | None` и
  `claude_home: str = "/root/.claude"`. Если `claude_volume` задан — в `docker run`
  добавить `-v {claude_volume}:{claude_home}`.
- `DockerBackend.__init__`: `claude_volume = f"{name}-claude"`, передать в
  `_DockerContainer`. Так `~/.claude` (журналы сессий + авторизация) живёт в
  именованном томе и переживает пересоздание/рестарт контейнера.
- `DockerFiles` home — дефолт-догадку синхронизировать с `claude_home`/root (под root
  `HOME=/root`, `home_projects_dir`=`/root/.claude/projects` — внутри тома). Лениво
  определённый `$HOME` должен совпасть с точкой монтирования; для нашего образа это
  `/root`. Если образ использует не-root пользователя — `claude_home` настраивается.

## Границы (YAGNI)

- ssh `list_files` не трогаем (уже различает).
- Не вводим произвольный маппинг пользователь→home: дефолт root (`/root/.claude`),
  параметр `claude_home` на случай иного образа.
- Персистентность для ssh/local не нужна (local — хостовый `~/.claude`; ssh — удалённый
  хостовый, уже персистентный).

## Обработка ошибок / поведение

- Упавший docker-контейнер при обходе журналов → `list_files` помечает backend
  `broken` → монитор показывает недоступность (как ssh при обрыве), а не «нет задач».
- «Каталог сессий ещё не создан» (свежий контейнер, агент не стартовал) → `[]` без
  ложного broken.

## Тестируемость

- `_is_container_down`: таблица (125/126/127→True; 1→False; 0→False; stderr-маркеры→
  True; обычный stderr→False).
- `list_files`: фейк-контейнер отдаёт rc=125/«No such container»→`mark_broken` вызван,
  `[]`; rc=1→`[]` без mark_broken; rc=0→парсинг (регресс).
- `read_from`: rc=125→`mark_broken`+`(b"",off)`; rc=1→`(b"",off)` без mark_broken.
- Персистентность: `DockerBackend`/`_DockerContainer` с `claude_volume` →
  `docker run` содержит `-v {name}-claude:/root/.claude` (фейк-run проверяет argv);
  без регресса существующих ensure-тестов (добавился один `-v`).

## Единицы

- `backends/docker.py` — `_is_container_down`; правки `DockerFiles.list_files`/
  `read_from`; `_DockerContainer.__init__`/`ensure` (claude-том); `DockerBackend`
  (вывод `claude_volume`); при нужде `exec_run_bytes` возвращает stderr.
- Тесты: `app/tests/test_backend_docker.py`.
- `docs/PHASES.md` — убрать пункты list_files и персистентность ~/.claude из
  «Следующих шагов».

## Открытые вопросы

Нет. Разбор down по docker-кодам 125/126/127 + маркерам stderr; `~/.claude` — именованный
том на `/root/.claude` (дефолт root образа), путь настраивается `claude_home`.
