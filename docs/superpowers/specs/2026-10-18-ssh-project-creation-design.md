# Спека: Provisioner за backend + создание проекта по SSH

Дата: 2026-10-18. Фаза: 3 (Удалённый доступ). Первая из серии спек по удалённому
выполнению.

## Контекст и мотивация

Драйвер — многопользовательность/масштаб. Три целевые топологии Фазы 3 (монитор в
Docker; проект в Docker-контейнере; проект на удалённом хосте по SSH) — опциональные
режимы поверх существующего локального. **Локальный режим остаётся дефолтом и не
меняется по поведению.**

Общая модель — три плоскости:

- **Control plane** — сам AgentMon (FastAPI + БД, держит PTY агентов, читает JSONL,
  пускает MCP через `docker`).
- **Execution plane** — каталог проекта + платформа 1С + агент `claude`.
- **Внешние ресурсы** (общие, «снаружи») — тестовая база 1С, сервер лицензирования,
  MCP-серверы.

Зафиксированные вводные среды (решения пользователя):

- Платформа 1С — **Linux**.
- Лицензии — **сетевой сервер лицензирования** (TCP), не USB, не программная привязка.
- Тестовая база — **клиент-серверная** (сервер 1С), доступ по TCP.

Следствие: все «внешние ресурсы» сводятся к **сетевой достижимости host:port** плюс
проброс конфига. Проброс железа (USB) и шаринг файловой базы — вне скоупа.

Эта спека покрывает **первый** шаг дорожной карты Фазы 3:

1. **(эта спека)** Рефакторинг: вынести scaffold/deploy за backend-интерфейс
   (`Provisioner`) + реализовать создание проекта по SSH.
2. (следующая спека) Backend `docker` — контейнер на проект.
3. (следующая спека) Упаковка монитора в Docker.

Порядок выбран так, чтобы дешёвый рефакторинг-костяк разблокировал и SSH, и Docker, а
SSH (наименьшая дельта — backend уже умеет PTY+JSONL) обкатал этот костяк на минимуме.

## Текущее состояние (точка отсчёта)

- Backend-абстракция: `backends/__init__.py` — два протокола `AgentRunner`
  (управление процессами) и `SessionFiles` (чтение JSONL). Реализации: `local`, `ssh`.
- `ssh`-backend (`backends/ssh.py`) уже умеет: PTY агента по SSH, чтение JSONL по SFTP,
  устойчивость к обрыву (`is_broken`, окно повторных попыток). Чего он **не** умеет —
  **создавать проект** (scaffold + deploy окружения).
- Создание проекта (`env/scaffold.py`, `env/content.py`, `env/project_api.py`) жёстко
  завязано на **локальную ФС** (`pathlib.Path`, `shutil`, `open`) и **локальный
  `subprocess`** (`provision_venv`, `git init`).
- Валидации мастера (`env/project_checks.py`): `is_empty_dir`, `platform_binary`,
  `requirements`, `build_check_db_command` — работают с локальными путями и локальным
  `subprocess.run`.
- Конфиг проекта (`env/config_schema.py::EnvConfig`): уже есть `platform_dir`,
  `platform_version`, `db_kind` (`server|file`), `db_connection` (строка `srvr=/ref=`
  для клиент-сервера). Поля адреса сервера лицензий **нет**.
- Модель проекта (`models.py`): `backend` (`local|ssh`), `conn` (`{host,port,user,
  key_path}`).

## Архитектура решения

### Часть A — Provisioner за backend (рефакторинг-предпосылка)

Ввести **третий протокол** backend'а — `Provisioner` — рядом с `AgentRunner` и
`SessionFiles`. Он описывает операции над **целевой** файловой системой и выполнение
команд **на целевой машине**:

```
class Provisioner(Protocol):
    def mkdirs(self, paths: list[str]) -> None: ...
    def exists(self, path: str) -> bool: ...
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, content: str) -> None: ...
    def put_tree(self, local_src: str, dst: str, *, skip=None) -> None: ...
    def run(self, cmd: list[str], cwd: str | None = None) -> RunResult: ...
```

- `put_tree` — копирование дерева **с хоста монитора на целевую машину** (шаблон
  `template/` живёт рядом с монитором; для local это та же машина). `skip` — отсев
  cruft (как сейчас `_is_cruft`).
- `run` — замена локального `subprocess.run` в `provision_venv`/`git init`/`chmod`;
  возвращает код возврата + stdout/stderr.
- `RunResult` — маленький dataclass `(returncode, stdout, stderr)`.

`Backend` получает поле `provisioner: Provisioner` (как уже есть `runner`, `files`).

**Переписать на `provisioner.*`** (прямые `Path`/`open`/`shutil`/`subprocess` убрать
из слоя развёртывания):

- `scaffold.py`: `scaffold_layout`, `write_json`, `write_preserving`, `write_env_files`.
- `content.py`: `deploy_content`, `_copy_tree` → `put_tree`, `provision_venv`,
  `_deploy_vscode`, `_rewrite_python_invocations`, `_render_*` (рендер в память →
  `write_text`).
- `project_api.py`: путь установки (`_prepare_install`/`_install_iter`) получает
  `provisioner` из backend'а выбранного проекта и работает через него.

**Инвариант регрессии:** для `local` результат байт-в-байт тот же, что сейчас.
`LocalProvisioner` — тонкие обёртки над текущими `Path`/`shutil`/`subprocess`.

**Валидации (`project_checks.py`)** тоже параметризуются `Provisioner`/`run`:
`is_empty_dir` → `provisioner.exists`/листинг; `platform_binary` → проверка на целевой
ФС; `requirements` и `build_check_db_command` → запуск через `provisioner.run` на
целевой машине. Построители команд (чистые функции сборки argv) остаются как есть —
меняется только **кто и где** их выполняет.

### Часть B — создание проекта по SSH

Реализовать `SshProvisioner` поверх уже существующего `_Connection` (переиспользуем
SFTP-сессию и exec-канал, не плодим новых соединений):

- `mkdirs/exists/read_text/write_text` → SFTP (`mkdir`, `stat`, `file`).
- `put_tree` → рекурсивная заливка дерева по SFTP (mkdir + put на каждый файл).
- `run` → exec-канал SSH (`exec_command`), сбор rc/stdout/stderr.

После этого путь создания проекта в мастере **начинает работать для `backend="ssh"`**:
scaffold + deploy + `.mcp.json` уезжают на удалённый хост, `provision_venv`/`git init`
выполняются по exec на удалённом хосте.

**Валидации мастера выполняются на удалённом хосте** через `SshProvisioner.run`/SFTP:
пустой ли каталог; есть ли платформа 1С по указанному пути; требования среды (python);
проверка клиент-серверной базы — тест-подключение **с удалённого хоста** (там же
платформа и сетевой доступ к серверу 1С).

**Проброс конфигов внешних ресурсов** (в составе развёртывания, на удалённый хост):

- **Сервер лицензий** — новое поле конфига `license_server` (адрес NETHASP-сервера,
  опциональное). При заданном значении развёртывание кладёт `nethasp.ini` в каталог
  профиля платформы на целевой машине (`conf/nethasp.ini`), секция `[NH_SERVER]
  NH_SERVER_ADDR=<license_server>`. Пусто → файл не пишем (платформа ищет лицензию
  штатно).
- **Сервер 1С** — отдельное поле не нужно: строка уже в `db_connection`
  (`srvr=...;ref=...`). Используется как есть при проверке базы и дальше агентом.

### Границы (YAGNI)

- Backend `docker` и упаковка монитора в Docker — **не здесь** (отдельные спеки).
- **sshfs не делаем** — файлы только по SFTP, локально не монтируются.
- Файловые базы и проброс USB — вне скоупа (решено: клиент-сервер + сетевой сервер
  лицензий).
- `put_tree` заливает `template/` **каждый раз при создании/обновлении** — без кеша на
  хосте. Кеширование — возможная будущая оптимизация, не сейчас.

## Поток данных (создание ssh-проекта)

1. Мастер отправляет конфиг с `backend="ssh"`, `conn={host,port,user,key_path}`,
   `path` (каталог на удалённом хосте), `platform_dir` (удалённый путь), `db_*`,
   `license_server`.
2. `project_api` берёт backend проекта из `BackendRegistry` → его `provisioner`.
3. Валидации через provisioner (пустой каталог, платформа, requirements, check_db) —
   выполняются на удалённом хосте; лог стримится в UI (как сейчас для local).
4. `scaffold_layout` → `deploy_content` → `write_env_files` → `nethasp.ini` — всё через
   `provisioner.*` по SFTP/exec.
5. Проект регистрируется; дальше запуск агентов и чтение JSONL идут уже отлаженными
   `ssh`-раннером и `SessionFiles`.

## Обработка ошибок

- Обрыв SSH при создании: `SshProvisioner` поднимает `SshUnavailable` (как ssh-раннер);
  `project_api` показывает ошибку в логе развёртывания, проект не регистрируется.
- `run` с ненулевым rc (например, `provision_venv` упал на удалённом python): текст
  stderr попадает в лог развёртывания, установка прерывается.
- Валидации-блокеры (непустой каталог, нет платформы) — как сейчас: сообщение в UI,
  создание не стартует.

## Тестируемость

- `Provisioner` мокается так же, как текущие `runner`/`files` (инъекция в backend).
- `LocalProvisioner` — against tmp-каталог; golden-тест «результат как раньше»
  (scaffold+deploy дают тот же набор файлов).
- `SshProvisioner` — против фейкового SFTP/exec (паттерн уже применён для ssh-раннера в
  `tests/`): проверяем, что mkdir/put/exec вызываются с нужными путями и командами.
- Валидации — юнит-тесты построителей команд не меняются; добавляются тесты «валидация
  идёт через provisioner.run».

## Единицы (модульность)

- `backends/__init__.py` — добавить протокол `Provisioner` + `RunResult`.
- `backends/local.py` — `LocalProvisioner`, подключить в `LocalBackend`.
- `backends/ssh.py` — `SshProvisioner` поверх `_Connection`, подключить в `SshBackend`.
- `env/scaffold.py`, `env/content.py`, `env/project_checks.py` — принимать
  `provisioner` вместо прямых обращений к ФС/subprocess.
- `env/project_api.py` — доставать provisioner из backend и прокидывать в установку.
- `env/config_schema.py` — поле `license_server: str | None = None`.
- Мастер (web): поле «Сервер лицензий» в разделе «Платформа»/«База».

## Открытые вопросы

Нет — решения зафиксированы в тексте (одно новое поле `license_server`; `put_tree` без
кеша; 1С-сервер берём из `db_connection`).
