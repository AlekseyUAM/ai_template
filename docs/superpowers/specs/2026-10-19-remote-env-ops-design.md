# Спека: удалённые операции окружения (cf/cfe, tools-install, update-env для ssh/docker)

Дата: 2026-10-19. Фаза: 3 (Удалённый доступ), follow-up. Первая из серии добивающих
спек после завершения основной дорожной карты.

## Контекст и мотивация

После спек ssh/docker/монитор три операции окружения всё ещё работают только локально:

1. **Выгрузка cf/cfe** (`platform_dump.dump`) — при создании гейтится `is_local`
   (`dump_cf and is_local`), т.е. для ssh/docker молча пропускается.
2. **tools-install** (`tools_install.install_tools`) — аналогично гейтится; к тому же
   хардкодит `sys.executable` (python МОНИТОРА) и `run=subprocess` (хост).
3. **update-env** (`project_api.update_env`/`update_env_stream`) — вызывает
   `install_environment(..., run=run)` БЕЗ `prov` → всегда `LocalProvisioner`, поэтому
   обновление ssh/docker-проекта идёт на хосте монитора, а не на цели.

Цель: прогнать эти операции через `Provisioner` на **целевой** машине, сделав
ssh/docker-проекты полноценными. Локальное поведение не меняется.

## Текущее состояние (точка отсчёта)

- `platform_dump.dump(config, kind, *, user, password, run=subprocess.run, sleep,
  clock, max_wait=900, interval=30, prov=None)`: `build_dump_command` уже берёт
  `prov` для поиска бинарника `1cv8`, НО сам DESIGNER исполняется `run(...)`
  (subprocess на хосте) с `timeout=remaining`; при `TimeoutExpired` — ретраибельная
  неудача. Ретраи до `max_wait`, auth-ошибки не ретраятся.
- `tools_install.install_tools(config, *, run=subprocess.run)`: `pip install` скила
  `1c-batch/scripts` и `lxml/Pillow/psutil` через `sys.executable` на хосте.
- `installer.install_environment(..., run=subprocess.run, prov=None)`: шаги `dump-cf`/
  `dump-cfe` зовут `dump(..., run=run, prov=prov)`; шаг `tools-install` зовёт
  `install_tools_fn(config, run=run)` (БЕЗ prov).
- `project_api`:
  - `_install_iter`: `is_local=(backend=="local")`; `dump_cf=... and is_local`,
    `dump_cfe=... and is_local`, `install_tools=... and is_local` → для ssh/docker off.
  - `update_env`/`update_env_stream`: `install_environment(..., run=run)` без prov/бэкенда.
  - `_provisioner_for(backend, conn, path)` уже умеет доставать provisioner из backend
    проекта через `monitor.backends.get(probe)`.
- `Provisioner.run(cmd, cwd=None) -> RunResult` — БЕЗ таймаута. `LocalProvisioner.run`
  = `subprocess.run(capture_output, text)`. `SshProvisioner.run` = exec-канал.
  `DockerProvisioner.run` = `docker exec`.
- Хранение backend/conn существующего проекта — в **ProjectRegistry** (`registry.py`,
  колонки `backend`/`conn`), доступном в роутере как `registry`. P1.1-`store`
  (ProjectRepo) backend/conn НЕ хранит.
- Для docker Xvfb уже поднимается в `ensure` (DESIGNER headless работает). Для ssh
  платформа на удалённом Linux — средовое допущение (как и раньше).

## Архитектура решения

### Часть A — таймаут в `Provisioner.run` (бэкенд-агностичный)

`dump` ретраит и защищается таймаутом от зависшего конфигуратора. Чтобы сохранить это
на удалённой цели, добавить в протокол **опциональный** `timeout`:

```
def run(self, cmd: list[str], cwd: str | None = None,
        timeout: float | None = None) -> RunResult: ...
```

- Семантика таймаута **единообразна**: при истечении `run` НЕ бросает разные
  исключения бэкендов, а возвращает `RunResult` с сигнальным кодом (`returncode=124`)
  и пометкой таймаута в `stderr`. Так `dump` остаётся бэкенд-агностичным (трактует
  ненулевой код как ретраибельную неудачу).
- `LocalProvisioner.run`: `subprocess.run(..., timeout=timeout)`, ловит
  `TimeoutExpired` → `RunResult(124, out_so_far, "...timeout...")`.
- `SshProvisioner.run`: `chan.settimeout(timeout)`; при `socket.timeout`/таймауте чтения
  → `RunResult(124, ..., timeout)`; канал закрыть.
- `DockerProvisioner.run`/`exec_run`: `subprocess.run(..., timeout=timeout)` на
  `docker exec`, та же трансляция в 124.
- `timeout=None` (дефолт) — поведение байт-в-байт как сейчас (без таймаута).

### Часть B — `platform_dump.dump` через `prov.run`

- DESIGNER исполнять через `prov.run(cmd, timeout=remaining)` вместо инъектируемого
  `run`. Параметр `run=` убрать (или оставить как no-op для совместимости тестов —
  предпочтительно убрать и обновить вызовы). Ретраи/дедлайн/auth-логика — без
  изменений; ветку `TimeoutExpired` заменить на проверку `returncode==124`/ненулевого.
- `prov` обязателен (дефолт `LocalProvisioner()` сохраняем для локали/тестов).
- Результат для local — тот же (DESIGNER на хосте через LocalProvisioner.run).

### Часть C — `tools_install.install_tools` через `prov`

- Сигнатура `install_tools(config, *, prov=None)`; `prov = prov or LocalProvisioner()`.
- Python цели: `prov.venv_python(config.project_dir)` (а не `sys.executable`), т.к. скил
  ставится в `.venv` проекта на целевой машине. `pip install` исполнять
  `prov.run([venv_python, "-m", "pip", "install", <scripts>], ...)` и для
  `lxml/Pillow/psutil`. Пути — целевые (POSIX для ssh/docker). rc≠0 → `RuntimeError`.
- Убрать `run=subprocess`/`sys.executable`; local-результат эквивалентен (venv_python
  локального проекта = тот же интерпретатор).

### Часть D — installer: прокинуть prov в tools-install, снять is_local-гейт

- `install_environment` шаг `tools-install` → `install_tools_fn(config, prov=prov)`.
- Гейтинг операций больше **не** завязан на `is_local`: `dump_cf`/`dump_cfe`/
  `install_tools` выполняются для любого backend, раз пользователь их выбрал — через
  `prov` на цели. (Параметр `run=` у `install_environment`/`dump` удаляем за
  ненадобностью; выгрузка идёт через prov.)

### Часть E — project_api: ungate + backend-aware update-env

- `_install_iter`: убрать `and is_local` у `dump_cf`/`dump_cfe`/`install_tools`
  (остаются только галки пользователя + `not update` где было). Для local/ssh/docker
  операции идут через уже выбранный `prov`.
- `update_env`/`update_env_stream`: стать backend-aware:
  - найти проект в `registry` по `path` (из `_build_update_config`), взять его
    `backend`/`conn`;
  - `prov = _provisioner_for(backend, conn, project_path)`;
  - `install_environment(config, update=True, register=..., dump_cf/dump_cfe/
    install_tools=<из body, как сейчас>, prov=prov)` (прокинуть `prov`!).
  - Если проект в registry не найден (нет backend) — дефолт `local` (как сейчас).

## Границы (YAGNI)

- Не меняем, ЧТО делает DESIGNER/pip — только ГДЕ (через prov на цели).
- Таймаут ssh/docker — best-effort (канал/subprocess), не гарантируем мгновенное
  убийство удалённого 1cv8 (у ретраев есть внешний дедлайн).
- Windows-цель вне скоупа удалённых сценариев (как и раньше: ssh/docker-цель — Linux).
- update-env остаётся без выгрузки cf/cfe по умолчанию в стриминговом эндпоинте, если
  так было (сохранить текущие дефолты body; меняем только prov-aware резолв).

## Обработка ошибок

- Таймаут DESIGNER на цели → `RunResult(124)` → ретрай до дедлайна → при исчерпании
  `RuntimeError` с логом (как сейчас).
- rc≠0 pip на цели → `RuntimeError(stderr)` → шаг установки `error` в логе.
- Недоступность ssh/docker при update-env/dump → `SshUnavailable`/docker-ошибка →
  текст в лог операции (как при создании).

## Тестируемость

- `Provisioner.run(timeout=...)`: Local — мок subprocess с `TimeoutExpired` → 124;
  Ssh/Docker — фейки проверяют проброс таймаута и трансляцию в 124; `timeout=None` —
  прежнее поведение.
- `dump`: фейковый `prov.run` отдаёт rc (0/занят/auth/timeout=124) → проверяем
  ретраи, дедлайн, не-ретрай auth, успех; команда строится через prov (binary из
  prov).
- `install_tools`: фейковый prov — проверяем `venv_python`-python и обе pip-команды
  через `prov.run`, rc≠0 → RuntimeError.
- `installer`: шаг tools-install получает prov; dump-шаги идут через prov; без
  `is_local`.
- `project_api`: создание ssh/docker с `dump_cf/install_tools=true` → операции НЕ
  пропускаются (прошли через prov фейкового бэкенда); update-env ssh/docker-проекта
  резолвит prov из registry (а не LocalProvisioner) — смоук с фейковым бэкендом.
- Регрессия local: создание/обновление local — результат прежний.

## Единицы (модульность)

- `backends/__init__.py` — `Provisioner.run` + `timeout` (сигнатура протокола).
- `backends/local.py`/`ssh.py`/`docker.py` — `run(..., timeout=None)` с трансляцией
  таймаута в `RunResult(124)`.
- `env/platform_dump.py` — `dump`/`build_dump_command` через `prov.run(timeout=...)`,
  убрать `run=`.
- `env/tools_install.py` — `install_tools(config, *, prov=None)` через `prov`.
- `env/installer.py` — `tools-install` с `prov`; `run=` убрать.
- `env/project_api.py` — снять `is_local`-гейт; `update_env*` backend-aware (prov из
  registry по path).
- `docs/PHASES.md` — убрать соответствующие пункты из «Следующих шагов».
- Тесты: обновить `test_installer`/`test_platform_dump`(если есть)/`test_tools_install`/
  `test_ssh_create`/`test_docker_create`/`test_provisioner_*`; + новые для timeout и
  update-env backend-aware.

## Открытые вопросы

Нет. Таймаут — единообразный `RunResult(124)` (без разнобоя исключений); tools-install
через `venv_python` цели; update-env берёт backend/conn из `registry` по пути; гейт
`is_local` снимается (операции идут через prov на цели).
