# AGENTMON_CLAUDE_CMD, обёртки и настройки Strata — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вынести обёртки `claude-ds`/`claude-local` в `deploy/claude/`, читать команду агента из `AGENTMON_CLAUDE_CMD` в `benchmark/test.env`, автоматически писать настройки локальной LLM из `strata connect`.

**Architecture:** Bench-раннеры получают команду так: `--claude-cmd` → `AGENTMON_CLAUDE_CMD` из test.env → ошибка. Команда разбирается на argv и резолвится через `PATH`/`PATHEXT` (чинит `.bat` по короткому имени). `setup_benchmark.py` при `BENCH_STRATA_SETTINGS=1` вызывает `strata connect claude-code --show-key` до пересоздания проекта, разбирает JSON-блок `env` и пишет `.claude/settings.local.json` проекта.

**Tech Stack:** Python ≥ 3.10, stdlib (`json`, `shlex`, `shutil`, `subprocess`), pytest. Скрипты — batch/sh без внешних зависимостей.

**Spec:** `docs/superpowers/specs/2026-11-23-claude-cmd-deploy-design.md`

## Global Constraints

- Все пользовательские сообщения — на русском.
- Токен Strata/DeepSeek не попадает в логи и тексты ошибок.
- `--claude-cmd` имеет приоритет над `AGENTMON_CLAUDE_CMD` из test.env.
- `AGENTMON_CLAUDE_CMD` в test.env читают только bench-раннеры; setup его принимает без предупреждения, но не использует.
- Benchmark-модули (`benchmark/*.py`) остаются stdlib-only и не импортируют `agentmon`.
- `registry._validate_claude_cmd` не меняется.
- Ключи test.env: `AGENTMON_CLAUDE_CMD`, `BENCH_STRATA_SETTINGS` (`0`/`1`), `STRATA_CMD`.
- Обёртки работают на Windows (`.bat`) и POSIX (`.sh`) и **не меняют cwd**.

## Review Focus

- Команда агента с путём в кавычках и пробелами: `"C:\Program Files\...\claude.bat" --flag` должна разбираться в один исполняемый файл и аргумент.
- Команда, целиком являющаяся существующим путём с пробелами (без кавычек): трактуется как исполняемый файл без аргументов.
- Отсутствующий/пустой `AGENTMON_CLAUDE_CMD` в test.env: раннер падает до запуска задач с понятным сообщением.
- Вывод `strata connect` с текстом до/после JSON или без `env`: ошибка `SetupError`, а не запись мусорных настроек.
- Секрет (токен) не появляется в логах setup и в сообщениях об ошибках.

---

### Task 1: Разбор команды агента и резолв `.bat`

**Files:**
- Modify: `benchmark/claude_proc.py` (`run_claude_process`, новые функции)
- Test: `benchmark/tests/test_bench_run.py`

**Interfaces:**
- Produces:
  - `split_command(cmd: str) -> list[str]` — разбор командной строки; на Windows `posix=False`, внешние кавычки снимаются.
  - `resolve_command(cmd: str) -> list[str]` — `[полный путь к исполняемому файлу, *аргументы]`; `FileNotFoundError`, если файл не найден/не исполняем.
  - `run_claude_process(cmd=...)` использует `resolve_command(cmd) + ["-p", "--output-format", "stream-json", "--verbose", *extra_args]`.

- [ ] **Step 1: Написать падающие тесты**

В `benchmark/tests/test_bench_run.py` добавить импорт и тесты:

```python
from claude_proc import resolve_command, split_command


def test_split_command_multitoken():
    assert split_command("claude --dangerously-skip-permissions") == [
        "claude", "--dangerously-skip-permissions"]


def test_split_command_keeps_quoted_path_with_spaces():
    assert split_command(
        r'"C:\Program Files\Claude\claude.bat" --flag') == [
        r"C:\Program Files\Claude\claude.bat", "--flag"]


def test_resolve_command_accepts_whole_path_with_spaces(tmp_path):
    exe = tmp_path / "claude local.bat"
    exe.write_text("@echo off\n", encoding="utf-8")
    assert resolve_command(str(exe)) == [str(exe)]


def test_resolve_command_uses_path_and_pathext(monkeypatch, tmp_path):
    exe = tmp_path / "claude-ds.bat"
    exe.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(
        "claude_proc.shutil.which",
        lambda name: str(exe) if name == "claude-ds" else None)
    assert resolve_command("claude-ds --flag") == [str(exe), "--flag"]


def test_resolve_command_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_command(str(tmp_path / "nope.bat"))


def test_run_claude_resolves_command_from_path(monkeypatch, tmp_path):
    fake = write_fake_claude(tmp_path / "fake", "\n".join([
        "import json",
        "print(json.dumps({'type':'result','is_error':False,'result':'ok',"
        "'session_id':'sid-path'}))",
    ]) + "\n")
    monkeypatch.setenv(
        "PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    run = run_claude(cmd=f"{fake.stem} --extra", prompt="hi", cwd=tmp_path,
                     timeout_sec=10, stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.exit_code == 0
    assert run.stream.session_id == "sid-path"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/Scripts/python.exe -m pytest benchmark/tests/test_bench_run.py -q -k "split_command or resolve_command or resolves_command_from_path"`
Expected: FAIL — `ImportError: cannot import name 'resolve_command'`.

- [ ] **Step 3: Реализовать в `benchmark/claude_proc.py`**

Добавить импорты `shlex`, `shutil`. Реализация:

```python
def _strip_quotes(arg: str) -> str:
    if len(arg) >= 2 and arg[0] == arg[-1] == '"':
        return arg[1:-1]
    return arg


def split_command(cmd: str) -> list[str]:
    """Разобрать командную строку на argv (backslash-пути Windows целы)."""
    posix = os.name != "nt" and "\\" not in cmd
    argv = shlex.split(cmd, posix=posix)
    if not posix:
        argv = [_strip_quotes(arg) for arg in argv]
    return [arg for arg in argv if arg]


def resolve_command(cmd: str) -> list[str]:
    """Вернуть argv с полным путём к исполняемому файлу.

    Работает с коротким именем (PATH + PATHEXT на Windows), полным путём и
    командой из нескольких слов. Raises FileNotFoundError.
    """
    raw = (cmd or "").strip()
    if not raw:
        raise FileNotFoundError("пустая команда агента")
    if Path(raw).is_file():
        return [raw]
    argv = split_command(raw)
    if not argv:
        raise FileNotFoundError("пустая команда агента")
    exe = argv[0]
    path = Path(exe)
    if path.is_absolute() or os.sep in exe or (os.altsep and os.altsep in exe):
        resolved = str(path)
    else:
        found = shutil.which(exe)
        if not found:
            raise FileNotFoundError(f"команда не найдена: {exe}")
        resolved = found
    if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        raise FileNotFoundError(f"команда не найдена или не исполняема: {cmd}")
    return [resolved, *argv[1:]]
```

В `run_claude_process` заменить первую строку argv:

```python
    argv = resolve_command(cmd) + ["-p", "--output-format", "stream-json",
                                   "--verbose", *extra_args]
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/Scripts/python.exe -m pytest benchmark/tests/test_bench_run.py -q`
Expected: PASS (все тесты файла, включая прежние `test_run_claude_*`).

- [ ] **Step 5: Коммит**

```bash
git add benchmark/claude_proc.py benchmark/tests/test_bench_run.py
git commit -m "feat(bench): запуск обёрток claude по короткому имени и с аргументами

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `AGENTMON_CLAUDE_CMD` как команда bench-раннеров

**Files:**
- Modify: `benchmark/bench_run.py` (`parse_args`, `build_options`, `ensure_claude_cmd`, новая `resolve_claude_cmd`)
- Modify: `benchmark/stage_run.py` (`main`)
- Modify: `app/src/agentmon/env/bench_setup.py` (`OPTIONAL_KEYS`)
- Modify: `benchmark/example.test.env`
- Modify: `benchmark/README.md`
- Test: `benchmark/tests/test_bench_run.py`, `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: `resolve_command` из Task 1.
- Produces:
  - `bench_run.resolve_claude_cmd(explicit: str | None, env_path: Path) -> str` — `explicit` → `AGENTMON_CLAUDE_CMD` → `BenchError("AGENTMON_CLAUDE_CMD не задан в <env>; укажите --claude-cmd")`.
  - `ensure_claude_cmd(cmd)` по-прежнему пишет `BenchError("команда агента не найдена или не исполняема: ...")`.
  - `--claude-cmd` в обоих CLI: `default=None`.

- [ ] **Step 1: Написать падающие тесты**

В `benchmark/tests/test_bench_run.py`:

```python
from bench_run import resolve_claude_cmd  # добавить в существующий импорт


def test_resolve_claude_cmd_from_env(tmp_path):
    env = tmp_path / "test.env"
    env.write_text("AGENTMON_CLAUDE_CMD=claude-ds --flag\n", encoding="utf-8")
    assert resolve_claude_cmd(None, env) == "claude-ds --flag"


def test_resolve_claude_cmd_flag_wins(tmp_path):
    env = tmp_path / "test.env"
    env.write_text("AGENTMON_CLAUDE_CMD=claude-ds\n", encoding="utf-8")
    assert resolve_claude_cmd("claude-local", env) == "claude-local"


def test_resolve_claude_cmd_required(tmp_path):
    env = tmp_path / "test.env"
    env.write_text("BENCH_PROJECT_DIR=/x\n", encoding="utf-8")
    with pytest.raises(BenchError, match="AGENTMON_CLAUDE_CMD"):
        resolve_claude_cmd(None, env)


def test_resolve_claude_cmd_empty_value_is_missing(tmp_path):
    env = tmp_path / "test.env"
    env.write_text("AGENTMON_CLAUDE_CMD=\n", encoding="utf-8")
    with pytest.raises(BenchError, match="AGENTMON_CLAUDE_CMD"):
        resolve_claude_cmd(None, env)
```

Обновить существующий `test_build_options`: в env добавить
`AGENTMON_CLAUDE_CMD=claude-ds` и проверить
`assert opts.claude_cmd == "claude-ds"`.

В `app/tests/env/test_bench_setup.py`:

```python
def test_load_config_accepts_agentmon_claude_cmd(tmp_path):
    warnings = []
    load_config(write_env(tmp_path, AGENTMON_CLAUDE_CMD="claude-ds"),
                repo_root=tmp_path, warn=warnings.append)
    assert warnings == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/Scripts/python.exe -m pytest benchmark/tests/test_bench_run.py app/tests/env/test_bench_setup.py -q -k "resolve_claude_cmd or build_options or accepts_agentmon"`
Expected: FAIL — нет `resolve_claude_cmd`; в `test_build_options` падает проверка команды; в app-тесте — предупреждение о неизвестном ключе.

- [ ] **Step 3: Реализовать**

`benchmark/bench_run.py`:

```python
from claude_proc import resolve_command, run_claude_process

def resolve_claude_cmd(explicit: str | None, env_path: Path) -> str:
    """Команда агента: --claude-cmd → AGENTMON_CLAUDE_CMD из test.env → ошибка."""
    cmd = (explicit or "").strip()
    if not cmd:
        cmd = (read_env_file(env_path).get("AGENTMON_CLAUDE_CMD") or "").strip()
    if not cmd:
        raise BenchError(
            f"AGENTMON_CLAUDE_CMD не задан в {env_path}; укажите --claude-cmd")
    return cmd

def ensure_claude_cmd(cmd: str) -> None:
    """Проверить, что команда агента существует и исполняема."""
    try:
        resolve_command(cmd)
    except FileNotFoundError:
        raise BenchError(
            f"команда агента не найдена или не исполняема: {cmd}") from None
```

В `parse_args`: `--claude-cmd`, `default=None`,
`help="команда агента (по умолчанию — AGENTMON_CLAUDE_CMD из test.env)"`.
В `build_options` заменить проверку и присваивание:

```python
    cmd = resolve_claude_cmd(ns.claude_cmd, env_path)
    return RunOptions(..., claude_cmd=cmd, ...)
```

`benchmark/stage_run.py`:

```python
from bench_run import (BenchError, ensure_claude_cmd, read_env_file,
                       resolve_claude_cmd, resolve_project_dir)
...
    parser.add_argument("--claude-cmd", default=None,
                        help="команда агента (по умолчанию — "
                             "AGENTMON_CLAUDE_CMD из test.env)")
...
    try:
        project = resolve_project_dir(args.project, env_path, repo_root)
        cmd = resolve_claude_cmd(args.claude_cmd, env_path)
        ensure_claude_cmd(cmd)
        ...
        "claude_cmd": cmd,
        ...
        run_stage(..., claude_cmd=cmd, ...)
```

`app/src/agentmon/env/bench_setup.py`: в `OPTIONAL_KEYS` добавить
`"AGENTMON_CLAUDE_CMD"`.

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/Scripts/python.exe -m pytest benchmark/tests app/tests/env/test_bench_setup.py -q`
Expected: PASS, включая `test_e2e_rejects_missing_claude_cmd`.

- [ ] **Step 5: Обновить `benchmark/example.test.env` и README**

В `example.test.env` после секции «Проект»:

```ini
# ─── Агент ───────────────────────────────────────────────────────────────────
# Команда запуска агента для run_benchmark.py/stage_run.py (обязательна).
# --claude-cmd на командной строке переопределяет. Варианты:
#   claude-ds, claude-local, claude --dangerously-skip-permissions
# Для запуска через AgentMon Web UI задайте то же значение в .ai1c.env.
AGENTMON_CLAUDE_CMD=claude-ds
```

В `benchmark/README.md`:
- в миграционную заметку шага 1 добавить: «Если `benchmark/test.env` уже
  существует, добавьте `AGENTMON_CLAUDE_CMD=claude-ds` — без него
  `run_benchmark.py`/`stage_run.py` остановятся с ошибкой»;
- строки про «по умолчанию `claude-ds`» заменить на «команда из
  `AGENTMON_CLAUDE_CMD` в `test.env`; `--claude-cmd` переопределяет».

- [ ] **Step 6: Коммит**

```bash
git add benchmark/bench_run.py benchmark/stage_run.py benchmark/claude_proc.py \
        benchmark/tests/test_bench_run.py benchmark/example.test.env \
        benchmark/README.md app/src/agentmon/env/bench_setup.py \
        app/tests/env/test_bench_setup.py
git commit -m "feat(bench): команда агента из AGENTMON_CLAUDE_CMD в test.env

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Разбор и сборка настроек Strata

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py` (константы, функции, `BenchConfig`, `load_config`, `OPTIONAL_KEYS`)
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Produces:
  - `parse_strata_env(output: str) -> dict[str, str]` — `env` из первого JSON-объекта; обязательны `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL`; иначе `SetupError`.
  - `fetch_strata_env(strata_cmd: str = "strata", *, run=subprocess.run, timeout: float = 60.0) -> dict[str, str]` — запускает `<strata_cmd> connect claude-code --show-key`.
  - `build_strata_settings(env: dict[str, str]) -> dict` — env + benchmark-ключи, `permissions.deny`, `claudeMdExcludes`, `modelOverrides`.
  - `write_strata_settings(project_dir: str | Path, settings: dict, *, log=print) -> Path`.
  - `BenchConfig.strata_settings: bool = False`, `BenchConfig.strata_cmd: str = "strata"`.
  - `OPTIONAL_KEYS` += `"BENCH_STRATA_SETTINGS"`, `"STRATA_CMD"`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_bench_setup.py` добавить `import json` и импорты
`build_strata_settings`, `fetch_strata_env`, `parse_strata_env`,
`write_strata_settings`.

```python
STRATA_OUTPUT = """
Claude Code  (messages + tools; tested (Claude Code 2.1.302))

File: ~/.claude/settings.json   (merged with the file if it exists)
  {
    "env": {
      "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080",
      "ANTHROPIC_AUTH_TOKEN": "strata-local",
      "ANTHROPIC_MODEL": "qwen3.8-flash-next-iq3_s",
      "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "262144",
      "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32768"
    }
  }

Environment:
  set ANTHROPIC_BASE_URL=http://127.0.0.1:8080
"""


def test_parse_strata_env_reads_json_block():
    env = parse_strata_env(STRATA_OUTPUT)
    assert env["ANTHROPIC_MODEL"] == "qwen3.8-flash-next-iq3_s"
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8080"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "strata-local"


def test_parse_strata_env_rejects_output_without_json():
    with pytest.raises(SetupError, match="strata connect"):
        parse_strata_env("Environment:\n  set ANTHROPIC_MODEL=x\n")


def test_parse_strata_env_requires_model():
    with pytest.raises(SetupError, match="ANTHROPIC_MODEL"):
        parse_strata_env(
            '{"env": {"ANTHROPIC_BASE_URL": "http://x", '
            '"ANTHROPIC_AUTH_TOKEN": "t"}}')


def test_build_strata_settings_merges_benchmark_defaults():
    settings = build_strata_settings({
        "ANTHROPIC_BASE_URL": "http://x",
        "ANTHROPIC_AUTH_TOKEN": "t",
        "ANTHROPIC_MODEL": "m",
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "262144",
    })
    env = settings["env"]
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "249036"
    assert settings["modelOverrides"] == {"claude-sonnet-4-6": "m"}
    assert "Agent" in settings["permissions"]["deny"]


def test_build_strata_settings_keeps_strata_values():
    settings = build_strata_settings({
        "ANTHROPIC_BASE_URL": "http://x",
        "ANTHROPIC_AUTH_TOKEN": "t",
        "ANTHROPIC_MODEL": "m",
        "PYTHONIOENCODING": "cp1251",
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "100000",
    })
    assert settings["env"]["PYTHONIOENCODING"] == "cp1251"
    assert settings["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "100000"


def test_fetch_strata_env_uses_connect_command(tmp_path, monkeypatch):
    exe = tmp_path / "strata.cmd"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "agentmon.env.bench_setup.shutil.which", lambda name: str(exe))
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, STRATA_OUTPUT, "")

    env = fetch_strata_env("strata", run=run)
    assert calls[0][1:] == ["connect", "claude-code", "--show-key"]
    assert env["ANTHROPIC_MODEL"] == "qwen3.8-flash-next-iq3_s"


def test_fetch_strata_env_reports_bad_exit(tmp_path):
    exe = tmp_path / "strata.cmd"
    exe.write_text("", encoding="utf-8")
    with pytest.raises(SetupError, match="strata connect"):
        fetch_strata_env(
            str(exe),
            run=lambda argv, **kw: subprocess.CompletedProcess(
                argv, 1, "", "server not found"))


def test_fetch_strata_env_reports_missing_cli(tmp_path):
    with pytest.raises(SetupError, match="STRATA_CMD"):
        fetch_strata_env(str(tmp_path / "nope.cmd"))


def test_write_strata_settings_log_has_no_token(tmp_path):
    lines = []
    path = write_strata_settings(
        tmp_path / "project",
        {"env": {"ANTHROPIC_MODEL": "m", "ANTHROPIC_AUTH_TOKEN": "secret",
                 "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000"}},
        log=lines.append)
    assert path == tmp_path / "project" / ".claude" / "settings.local.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["env"]["ANTHROPIC_MODEL"] == "m"
    assert all("secret" not in line for line in lines)


def test_load_config_strata_defaults_off(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    assert cfg.strata_settings is False
    assert cfg.strata_cmd == "strata"


def test_load_config_strata_enabled(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_STRATA_SETTINGS="1",
                  STRATA_CMD="C:/Strata/strata.cmd"),
        repo_root=tmp_path)
    assert cfg.strata_settings is True
    assert cfg.strata_cmd == "C:/Strata/strata.cmd"


def test_load_config_rejects_bad_strata_flag(tmp_path):
    with pytest.raises(SetupError, match="BENCH_STRATA_SETTINGS"):
        load_config(write_env(tmp_path, BENCH_STRATA_SETTINGS="maybe"),
                    repo_root=tmp_path)
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/Scripts/python.exe -m pytest app/tests/env/test_bench_setup.py -q -k "strata"`
Expected: FAIL — `ImportError` на новых функциях.

- [ ] **Step 3: Реализовать в `bench_setup.py`**

Импортировать `shlex`. Константы рядом с `OPTIONAL_KEYS`:

```python
_BENCH_SETTINGS_ENV = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "MAX_MCP_OUTPUT_TOKENS": "8000",
    "BASH_MAX_OUTPUT_LENGTH": "12000",
    "CLAUDE_CODE_TOTAL_TOKENS_REMINDER": "off",
}
_BENCH_SETTINGS_DENY = [
    "Agent", "Task", "SendMessage", "Workflow", "ListAgents",
    "ScheduleWakeup", "mcp__1c-md__execute_query",
]
_BENCH_CLAUDE_MD_EXCLUDES = [
    "**/cyclic-review-workflow.md", "**/run-unit-tests.md",
]
```

Функции (полная реализация; повторяют логику `claude_proc.resolve_command`,
т.к. benchmark не зависит от agentmon):

```python
def _split_command(cmd: str) -> list[str]:
    posix = os.name != "nt" and "\\" not in cmd
    argv = shlex.split(cmd, posix=posix)
    if not posix:
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a
                for a in argv]
    return [a for a in argv if a]


def _resolve_command(cmd: str) -> list[str]:
    raw = (cmd or "").strip()
    if not raw:
        raise FileNotFoundError("пустая команда")
    if Path(raw).is_file():
        return [raw]
    argv = _split_command(raw)
    if not argv:
        raise FileNotFoundError("пустая команда")
    exe = argv[0]
    path = Path(exe)
    if path.is_absolute() or os.sep in exe or (os.altsep and os.altsep in exe):
        resolved = str(path)
    else:
        found = shutil.which(exe)
        if not found:
            raise FileNotFoundError(f"команда не найдена: {exe}")
        resolved = found
    if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        raise FileNotFoundError(f"команда не найдена: {cmd}")
    return [resolved, *argv[1:]]
```

```python
def parse_strata_env(output: str) -> dict[str, str]:
    idx = (output or "").find("{")
    if idx < 0:
        raise SetupError("strata connect: в выводе нет JSON-блока настроек")
    try:
        data, _ = json.JSONDecoder().raw_decode(output[idx:])
    except json.JSONDecodeError as exc:
        raise SetupError(
            f"strata connect: не удалось разобрать JSON: {exc}") from None
    env = data.get("env") if isinstance(data, dict) else None
    if not isinstance(env, dict) or not env:
        raise SetupError("strata connect: в JSON нет непустого блока env")
    result = {str(key): str(value) for key, value in env.items()}
    for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                "ANTHROPIC_MODEL"):
        if not result.get(key):
            raise SetupError(f"strata connect: в env нет {key}")
    return result


def fetch_strata_env(strata_cmd: str = "strata", *,
                     run=subprocess.run,
                     timeout: float = 60.0) -> dict[str, str]:
    try:
        argv = _resolve_command(strata_cmd)
    except FileNotFoundError:
        raise SetupError(
            f"не найдена команда Strata: {strata_cmd} "
            "(укажите STRATA_CMD — путь к strata.cmd)") from None
    argv += ["connect", "claude-code", "--show-key"]
    try:
        result = run(argv, capture_output=True, text=True,
                     encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError:
        raise SetupError(f"не найдена команда Strata: {strata_cmd}") from None
    except subprocess.TimeoutExpired:
        raise SetupError(
            f"strata connect не ответила за {timeout:g} с") from None
    if result.returncode != 0:
        raise SetupError(
            f"strata connect завершилась с ошибкой (код "
            f"{result.returncode}); запустите её вручную для диагностики")
    return parse_strata_env(result.stdout or "")


def build_strata_settings(env: dict[str, str]) -> dict:
    merged = dict(env)
    for key, value in _BENCH_SETTINGS_ENV.items():
        merged.setdefault(key, value)
    try:
        context = int(merged.get("CLAUDE_CODE_MAX_CONTEXT_TOKENS", ""))
    except ValueError:
        context = 0
    if context > 0:
        merged.setdefault("CLAUDE_CODE_AUTO_COMPACT_WINDOW",
                          str(context * 95 // 100))
    settings: dict = {
        "env": merged,
        "permissions": {"deny": list(_BENCH_SETTINGS_DENY)},
        "claudeMdExcludes": list(_BENCH_CLAUDE_MD_EXCLUDES),
    }
    model = merged.get("ANTHROPIC_MODEL")
    if model:
        settings["modelOverrides"] = {"claude-sonnet-4-6": model}
    return settings


def write_strata_settings(project_dir: str | Path, settings: dict, *,
                          log: Callable[[str], None] = print) -> Path:
    path = Path(project_dir) / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    env = settings.get("env", {})
    log(f"✓ настройки Strata: модель {env.get('ANTHROPIC_MODEL', '—')}, "
        f"контекст {env.get('CLAUDE_CODE_MAX_CONTEXT_TOKENS', '—')} → {path}")
    return path
```

`BenchConfig`: добавить поля
`strata_settings: bool = False`, `strata_cmd: str = "strata"`.
`OPTIONAL_KEYS` += `"BENCH_STRATA_SETTINGS"`, `"STRATA_CMD"`.

В `load_config` перед `return BenchConfig(...)`:

```python
    strata_raw = (data.get("BENCH_STRATA_SETTINGS") or "").strip()
    if strata_raw in ("", "0"):
        strata_settings = False
    elif strata_raw == "1":
        strata_settings = True
    else:
        raise SetupError("BENCH_STRATA_SETTINGS должен быть 0 или 1")
    strata_cmd = (data.get("STRATA_CMD") or "strata").strip() or "strata"
```

и передать `strata_settings=strata_settings, strata_cmd=strata_cmd` в
`BenchConfig(...)`.

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/Scripts/python.exe -m pytest app/tests/env/test_bench_setup.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py
git commit -m "feat(bench): разбор настроек Strata из strata connect

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: `BENCH_STRATA_SETTINGS` в setup_benchmark

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py` (`run_setup`)
- Modify: `benchmark/setup_benchmark.py`
- Modify: `benchmark/example.test.env`
- Modify: `benchmark/README.md`
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: `fetch_strata_env`, `build_strata_settings`,
  `write_strata_settings`, `BenchConfig.strata_settings/strata_cmd` из Task 3.
- Produces: `run_setup(..., strata_env: dict[str, str] | None = None)`;
  при `cfg.strata_settings` пишет `.claude/settings.local.json` после шага
  «окружение проекта». `setup_benchmark.main` получает `strata_env` до
  `run_setup_with_lock_retry`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_bench_setup.py`:

```python
def test_run_setup_writes_strata_settings(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(
        write_env(tmp_path, BENCH_STRATA_SETTINGS="1"), repo_root=root)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    from types import SimpleNamespace

    run_setup(
        cfg, repo_root=root, store=store, registry=registry,
        prov=OrchestratorProv(), tcp_ok=lambda url: True,
        http_ok=lambda url: True, install_env=fake_install_env,
        batch_run=lambda project_dir, args, **kwargs: None,
        launch_index=lambda **kwargs: SimpleNamespace(
            code_index_dir=cfg.code_index_dir),
        wait_index=lambda index, **kwargs: None,
        strata_env={
            "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080",
            "ANTHROPIC_AUTH_TOKEN": "strata-local",
            "ANTHROPIC_MODEL": "local-model",
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "262144",
        },
        log=lambda line: None,
    )
    path = Path(cfg.project_dir) / ".claude" / "settings.local.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["env"]["ANTHROPIC_MODEL"] == "local-model"
    assert data["env"]["PYTHONUTF8"] == "1"
```

В `test_run_setup_happy_path` добавить в конец:

```python
    assert not (Path(cfg.project_dir) / ".claude" /
                "settings.local.json").exists()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/Scripts/python.exe -m pytest app/tests/env/test_bench_setup.py -q -k "strata_settings or happy_path"`
Expected: FAIL — `run_setup() got an unexpected keyword argument 'strata_env'`.

- [ ] **Step 3: Реализовать**

`run_setup` — в сигнатуру добавить
`strata_env: dict[str, str] | None = None`. После блока
`install_env(...)` и перед `log("▶ база 1С")`:

```python
        if cfg.strata_settings:
            settings_env = (strata_env if strata_env is not None
                            else fetch_strata_env(cfg.strata_cmd))
            write_strata_settings(
                cfg.project_dir, build_strata_settings(settings_env), log=log)
```

`benchmark/setup_benchmark.py` — импортировать `fetch_strata_env` из
`agentmon.env.bench_setup` и после `load_config` (до проверки Docker):

```python
    strata_env = None
    if cfg.strata_settings:
        try:
            strata_env = fetch_strata_env(cfg.strata_cmd)
        except SetupError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        print(f"✓ Strata: модель {strata_env.get('ANTHROPIC_MODEL', '—')}, "
              f"контекст "
              f"{strata_env.get('CLAUDE_CODE_MAX_CONTEXT_TOKENS', '—')}")
```

В вызов `run_setup(...)` внутри lambda добавить `strata_env=strata_env`.

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/Scripts/python.exe -m pytest app/tests/env/test_bench_setup.py benchmark/tests/test_setup_benchmark.py -q`
Expected: PASS.

- [ ] **Step 5: Обновить `example.test.env` и README**

В `example.test.env` после секции «Агент»:

```ini
# ─── Локальная LLM (Strata) ──────────────────────────────────────────────────
# 1 — setup_benchmark.py возьмёт настройки у `strata connect claude-code`
# и запишет <проект>/.claude/settings.local.json. 0/не задано — не трогать.
BENCH_STRATA_SETTINGS=0
# Путь к CLI Strata, если её нет в PATH (см. deploy/claude/README.md).
#STRATA_CMD=C:\Users\user\AppData\Local\Strata\terminal\current\bin\strata.cmd
```

В `benchmark/README.md`, раздел «Настройки из Strata», добавить абзац:

> При `BENCH_STRATA_SETTINGS=1` setup сам выполняет
> `strata connect claude-code --show-key` и пишет
> `<проект>/.claude/settings.local.json` (env, `permissions.deny`,
> `claudeMdExcludes`, `modelOverrides`); токен в лог не попадает. Если
> `strata` нет в `PATH`, укажите `STRATA_CMD`. Сервер должен быть запущен
> (`strata launch`), иначе `strata connect` подставит умолчания.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/bench_setup.py benchmark/setup_benchmark.py \
        benchmark/example.test.env benchmark/README.md \
        app/tests/env/test_bench_setup.py
git commit -m "feat(bench): BENCH_STRATA_SETTINGS в setup_benchmark

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: `deploy/claude/`, инструкция и ссылки

**Files:**
- Create: `deploy/claude/claude-ds.bat`, `deploy/claude/claude-ds.sh`,
  `deploy/claude/claude-local.bat`, `deploy/claude/claude-local.sh`,
  `deploy/claude/README.md`
- Delete: `benchmark/claude-local.bat.example`,
  `benchmark/claude-local.sh.example`
- Modify: `benchmark/README.md` (раздел поэтапного прогона), `README.md`

**Interfaces:**
- Produces: обёртки, устанавливаемые в `PATH`; имена команд — `claude-ds`,
  `claude-local`.

- [ ] **Step 1: Создать `deploy/claude/claude-ds.bat`**

```bat
@echo off
:: Обёртка Claude Code для DeepSeek.
:: Установка: скопируйте в каталог из PATH, например %USERPROFILE%\.local\bin.
:: Ключ: переменная DEEPSEEK_API_KEY или файл %USERPROFILE%\.config\deepseek\key.
setlocal

set "KEY_FILE=%USERPROFILE%\.config\deepseek\key"
if defined DEEPSEEK_API_KEY (
    set "TOKEN=%DEEPSEEK_API_KEY%"
) else if exist "%KEY_FILE%" (
    set /p TOKEN=<"%KEY_FILE%"
) else (
    echo Ошибка: не найден ключ. Положите его в %KEY_FILE% или задайте DEEPSEEK_API_KEY 1>&2
    exit /b 1
)

for /f "tokens=* delims=" %%a in ("%TOKEN%") do set "TOKEN=%%a"

set "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic"
set "ANTHROPIC_AUTH_TOKEN=%TOKEN%"
set "ANTHROPIC_MODEL=deepseek-flash[1m]"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-flash[1m]"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-flash[1m]"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-flash[1m]"
set "CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash[1m]"
set "CLAUDE_CODE_EFFORT_LEVEL=max"
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432"

claude --dangerously-skip-permissions %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
```

- [ ] **Step 2: Создать `deploy/claude/claude-ds.sh`**

```sh
#!/usr/bin/env sh
# Обёртка Claude Code для DeepSeek.
# Установка: ~/.local/bin/claude-ds (chmod +x).
# Ключ: DEEPSEEK_API_KEY или ~/.config/deepseek/key.
set -eu

KEY_FILE="${HOME}/.config/deepseek/key"
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    TOKEN="$DEEPSEEK_API_KEY"
elif [ -f "$KEY_FILE" ]; then
    TOKEN="$(cat "$KEY_FILE")"
else
    echo "Ошибка: не найден ключ. Положите его в $KEY_FILE или задайте DEEPSEEK_API_KEY" >&2
    exit 1
fi

export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$TOKEN"
export ANTHROPIC_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-flash[1m]"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-flash[1m]"
export CLAUDE_CODE_EFFORT_LEVEL=max
export CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432

exec claude --dangerously-skip-permissions "$@"
```

- [ ] **Step 3: Создать `deploy/claude/claude-local.bat`**

```bat
@echo off
:: Обёртка Claude Code для локальной LLM.
:: Установка: скопируйте в каталог из PATH, например %USERPROFILE%\.local\bin.
:: Настройки модели: <проект>/.claude/settings.local.json (deploy/claude/README.md).
:: Запускайте из каталога проекта: cwd намеренно не меняется.
setlocal

for %%v in (ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL ANTHROPIC_SMALL_FAST_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL) do set "%%v="
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

claude --dangerously-skip-permissions %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
```

- [ ] **Step 4: Создать `deploy/claude/claude-local.sh`**

```sh
#!/usr/bin/env sh
# Обёртка Claude Code для локальной LLM.
# Установка: ~/.local/bin/claude-local (chmod +x).
# Настройки модели: <проект>/.claude/settings.local.json.
set -eu

unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL
unset ANTHROPIC_SMALL_FAST_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL
unset ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

exec claude --dangerously-skip-permissions "$@"
```

- [ ] **Step 5: Создать `deploy/claude/README.md`**

Структура и обязательные факты:

1. **Состав**: `claude-ds.*` — DeepSeek; `claude-local.*` — локальная LLM
   (Strata); обёртки не содержат секретов.
2. **Установка в PATH**:
   - Windows: `copy deploy\claude\claude-ds.bat %USERPROFILE%\.local\bin\`
     (каталог уже в `PATH`; проверить `echo %PATH%`);
   - Linux/macOS: `cp deploy/claude/claude-local.sh ~/.local/bin/claude-local
     && chmod +x ~/.local/bin/claude-local`.
3. **DeepSeek**: ключ в `%USERPROFILE%\.config\deepseek\key` (Windows) /
   `~/.config/deepseek/key` или `DEEPSEEK_API_KEY`; проверка
   `claude-ds --version`.
4. **Локальная LLM**: значения печатает `strata connect claude-code`;
   автоматически их пишет `setup_benchmark.py` при
   `BENCH_STRATA_SETTINGS=1`. Запускать из каталога проекта — обёртка не
   меняет cwd, поэтому Claude Code читает `.claude/settings.local.json`
   проекта. Обёртку не класть внутрь benchmark-проекта: setup пересоздаёт
   каталог.
5. **`AGENTMON_CLAUDE_CMD`**:
   - `.ai1c.env` (AgentMon Web UI) — `AGENTMON_CLAUDE_CMD=claude-ds` или
     `claude-local`; перезапустить AgentMon после правки;
   - `benchmark/test.env` (run_benchmark/stage_run) — тот же ключ;
     `--claude-cmd` переопределяет; без значения раннеры падают;
   - допустимо короткое имя (ищется в `PATH`) или полный путь; команда с
     аргументами — в кавычках, если путь содержит пробелы:
     `AGENTMON_CLAUDE_CMD="C:\Program Files\...\claude.bat" --flag`.
6. **Проверка**: `claude-ds --version`, `claude-local --version`;
   для локальной — пробный прогон `benchmark/stage_run.py --dry-run`.

- [ ] **Step 6: Удалить benchmark-примеры и обновить ссылки**

```bash
git rm benchmark/claude-local.bat.example benchmark/claude-local.sh.example
```

В `benchmark/README.md`, раздел «Поэтапный прогон на локальной LLM»,
шаг 2 заменить на: «Установите обёртку в `PATH` из `deploy/claude/` —
см. [`deploy/claude/README.md`](../deploy/claude/README.md)», а в примерах
команд заменить `--claude-cmd <проект>\claude-local.bat` на
`--claude-cmd claude-local`.

В корневом `README.md` в строке таблицы `AGENTMON_CLAUDE_CMD` указать
ссылку:

```markdown
| `AGENTMON_CLAUDE_CMD` | команда запуска агента; обёртки `claude-ds`/`claude-local` и настройка — [deploy/claude/README.md](deploy/claude/README.md) | `claude --dangerously-skip-permissions .` |
```

- [ ] **Step 7: Полная проверка**

Run:
```bash
.venv/Scripts/python.exe -m pytest app/tests/env/test_bench_setup.py benchmark/tests -q
```
Expected: PASS.

Run:
```bash
git grep -n "claude-local.bat.example\|claude-local.sh.example"
```
Expected: пусто.

Run:
```bash
bash -n deploy/claude/claude-local.sh && bash -n deploy/claude/claude-ds.sh
```
Expected: без вывода (синтаксис sh корректен).

- [ ] **Step 8: Коммит**

```bash
git add deploy/claude benchmark/README.md README.md
git add -u benchmark
git commit -m "docs(deploy): обёртки claude-ds/claude-local и инструкция

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage:** скрипты и инструкция — Task 5; `AGENTMON_CLAUDE_CMD` —
  Tasks 2, 5; Strata — Tasks 3, 4; резолв `.bat` — Task 1; README-ссылка —
  Task 5. Пробелов нет.
- **Types:** `resolve_command`/`split_command` (Task 1) используются в Task 2;
  `fetch_strata_env`/`build_strata_settings`/`write_strata_settings`
  (Task 3) — в Task 4; имена совпадают.
- **Review Focus → тесты:** кавычки/пробелы — Task 1
  (`test_split_command_keeps_quoted_path_with_spaces`,
  `test_resolve_command_accepts_whole_path_with_spaces`); отсутствие
  `AGENTMON_CLAUDE_CMD` — Task 2 (`test_resolve_claude_cmd_required`);
  лишний текст/битый вывод strata — Task 3
  (`test_parse_strata_env_rejects_output_without_json`,
  `test_parse_strata_env_requires_model`); отсутствие токена в логе —
  Task 3 (`test_write_strata_settings_log_has_no_token`).
