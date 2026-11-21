# Исправление окружения по итогам benchmark-прогона — план

> **Superseded (2026-11-21):** обход с перезапуском контейнера
> (`bench_index.py`) удалён — code-index переведён на нативный запуск,
> см. `docs/superpowers/specs/2026-11-21-native-code-index-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить в репозитории дефекты окружения, выявленные прогоном `benchmark/tasks`: stdin-промпты, честные метрики, изоляция аналитика, обновление индекса, `alwaysLoad`, UTF-8 и чеклисты.

**Architecture:** Восемь независимых изменений с собственными тестами. Сначала общий модуль запуска `claude` через stdin; затем метрики и входы аналитика; затем benchmark-индекс и генератор `.mcp.json`; затем настройки/entrypoint'ы и тексты `template/.claude`. Каждый таск завершается зелёными тестами и локальным коммитом в `main`.

**Tech Stack:** Python 3.10+ (stdlib), pytest, JSON/TOML-подобные конфиги, Claude Code CLI (`-p` + stdin), Docker CLI для code_index.

**Spec:** `docs/superpowers/specs/2026-11-21-benchmark-environment-fixes-design.md`

## Global Constraints

- Не трогать `deps/**`, `tmp/**` и конкретный тестовый проект `D:\projects\test`.
- Только stdlib Python; никаких новых зависимостей.
- Кроссплатформенность: `pathlib`, UTF-8, без POSIX-only вызовов; тесты должны проходить на Windows и Linux.
- Тексты `template/.claude/**` — на английском (как остальное окружение).
- Коммиты — локально в `main`, без push. Один логический коммит на таск.
- Тесты из корня: `.venv/bin/python -m pytest ...` (Linux/macOS) или `.venv\Scripts\python.exe -m pytest ...` (Windows).
- Существующий контракт `claude -p` с промптом в stdin: флаги в argv, промпт — UTF-8 в stdin.

## File Structure

```
benchmark/
  claude_proc.py            # новый: общий запуск claude -p со stdin
  bench_index.py            # новый: свежесть и перезапуск code_index
  bench_run.py              # stdin, снимок аналитика, refresh, опции
  bench_analysis.py         # снимок входов, текст промпта
  bench_metrics.py          # счётчики, partial, дайджест
  stage_run.py              # stdin, первый шаг mcp-usage
  README.md                 # Node.js, modelOverrides
  tests/test_bench_run.py
  tests/test_bench_e2e.py
  tests/test_bench_metrics.py
  tests/test_bench_analysis.py
  tests/test_bench_index.py # новый
template/.claude/
  settings.json
  settings.local.json.example
  checklists/developer.md
  skills/mcp-usage/SKILL.md
  skills/query-analyze/SKILL.md
  skills/1c-batch/scripts/1c-batch.py
  tools/run-tests.py, load-config-optimized.py, task_status.py
  hooks/route_to_checklists.py
  hooks/bsl_nudge.py
  hooks/code_index_guard_lib/redirect.py
app/src/agentmon/env/mcp_catalog.py
app/tests/env/test_mcp_catalog.py
app/tests/env/test_mcp_catalog_from_connection.py
app/tests/env/test_content_deploy.py
app/tests/env/test_content_conditions.py
app/tests/env/test_route_hook.py
app/tests/env/test_bsl_nudge.py
```

---

### Task 1: Промпт через stdin для обоих раннеров

**Files:**
- Create: `benchmark/claude_proc.py`
- Modify: `benchmark/bench_run.py:1-30, 150-290`
- Modify: `benchmark/stage_run.py:30-40, 317-360`
- Modify: `benchmark/tests/test_bench_e2e.py:40-95`
- Test: `benchmark/tests/test_bench_run.py`

**Interfaces:**
- Produces: `claude_proc.ProcessResult(exit_code: int|None, timed_out: bool, duration_sec: float)`, `claude_proc.run_claude_process(*, cmd, prompt, cwd, timeout_sec, stdout_path, stderr_path, extra_args=(), env=None) -> ProcessResult`, `claude_proc._kill_group(proc, pgid)`.
- Consumes: ничего.

- [ ] **Step 1: Написать падающий тест**

В `benchmark/tests/test_bench_run.py` добавить:

```python
def test_run_claude_multiline_prompt_via_stdin(tmp_path):
    prompt = "Первая строка\nвторая строка\n" + "x" * 5000
    fake = write_fake_claude(tmp_path / "fake", "\n".join([
        "import json, sys",
        "from pathlib import Path",
        "data = sys.stdin.read()",
        "Path('prompt.txt').write_text(data, encoding='utf-8')",
        "Path('argv.json').write_text(json.dumps(sys.argv), encoding='utf-8')",
        "print(json.dumps({'type':'system','subtype':'init','session_id':'sid-stdin'}))",
        "print(json.dumps({'type':'result','is_error':False,'result':'ok','session_id':'sid-stdin'}))",
    ]) + "\n")
    run = run_claude(cmd=str(fake), prompt=prompt, cwd=tmp_path, timeout_sec=10,
                     stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.exit_code == 0
    assert (tmp_path / "prompt.txt").read_text(encoding="utf-8") == prompt
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert prompt not in argv
    assert "-p" in argv
    assert "--output-format" in argv
    assert "stream-json" in argv
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py::test_run_claude_multiline_prompt_via_stdin -q`
Expected: FAIL — `prompt.txt` не создан (промпт ушёл в argv, stdin = DEVNULL).

- [ ] **Step 3: Создать `benchmark/claude_proc.py`**

```python
"""Запуск `claude -p` с промптом через stdin.

Windows-обёртка `.bat` через cmd.exe искажает argv, если промпт многострочный:
CLI теряет флаги. Поэтому промпт пишем в stdin, а в argv оставляем только флаги.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    duration_sec: float


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _wait_exit(proc: subprocess.Popen, timeout: float) -> bool:
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def _kill_group(proc: subprocess.Popen, pgid: int) -> None:
    """Мягко остановить лидера, затем гарантированно зачистить process group.

    Windows не умеет process group: дерево снимается `taskkill /F /T`.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
            _wait_exit(proc, 5)
        return

    def send(sig: int) -> None:
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            pass

    if proc.poll() is None:
        send(signal.SIGINT)
        _wait_exit(proc, 10)
    if proc.poll() is None:
        send(signal.SIGTERM)
        _wait_exit(proc, 5)
    if _group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
        _wait_exit(proc, 5)


def run_claude_process(*, cmd: str, prompt: str, cwd: Path,
                       timeout_sec: float, stdout_path: Path,
                       stderr_path: Path,
                       extra_args: tuple[str, ...] = (),
                       env: dict[str, str] | None = None) -> ProcessResult:
    """Запустить `claude -p` с промптом в stdin; таймаут убивает группу."""
    argv = [cmd, "-p", "--output-format", "stream-json",
            "--verbose", *extra_args]
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.PIPE, stdout=out, stderr=err,
            env=env, start_new_session=True)
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt.encode("utf-8"))
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            # Ребёнок завершился раньше, чем прочитал stdin.
            pass
        try:
            exit_code = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc, proc.pid)
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                exit_code = proc.poll()
        except BaseException:
            _kill_group(proc, proc.pid)
            raise
    return ProcessResult(exit_code, timed_out,
                         time.monotonic() - started)
```

- [ ] **Step 4: Переключить `bench_run.run_claude` на общий модуль**

В `benchmark/bench_run.py`:
- удалить локальные `_group_exists`, `_wait_exit`, `_kill_group` (строки ~150-250);
- удалить `import signal`, если он больше не нужен;
- добавить `from claude_proc import run_claude_process` рядом с импортами `bench_*`;
- заменить тело `run_claude`:

```python
def run_claude(*, cmd: str, prompt: str, cwd: Path, timeout_sec: float,
               stream_path: Path, stderr_path: Path,
               extra_args: tuple[str, ...] = ()) -> ClaudeRun:
    """Запустить claude в отдельной сессии и вернуть результат."""
    result = run_claude_process(
        cmd=cmd, prompt=prompt, cwd=cwd, timeout_sec=timeout_sec,
        stdout_path=stream_path, stderr_path=stderr_path,
        extra_args=extra_args)
    stream = parse_stream(stream_path)
    session = find_session_files(stream.session_id)
    return ClaudeRun(exit_code=result.exit_code, timed_out=result.timed_out,
                     duration_sec=result.duration_sec, stream_path=stream_path,
                     stderr_path=stderr_path, stream=stream, session=session)
```

- [ ] **Step 5: Переключить `stage_run.run_stage`**

В `benchmark/stage_run.py`:
- заменить импорт `_kill_group` из `bench_run` на `run_claude_process` из `claude_proc`;
- перед запуском оставить `started_epoch = time.time()`;
- заменить блок `argv = ...` + `Popen` + `wait` на:

```python
    process = run_claude_process(
        cmd=claude_cmd, prompt=prompt, cwd=project,
        timeout_sec=limit_min * 60, stdout_path=stream_path,
        stderr_path=stderr_path, env=env)
    exit_code = process.exit_code
    timed_out = process.timed_out
    duration = process.duration_sec
```

- [ ] **Step 6: Обновить фейковый CLI в e2e**

В `benchmark/tests/test_bench_e2e.py` в строке `FAKE` заменить:

```python
args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args else ""
```

на:

```python
prompt = sys.stdin.read()
```

- [ ] **Step 7: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest benchmark/tests/test_bench_run.py benchmark/tests/test_bench_e2e.py -q
```
Expected: все зелёные, включая таймаутные тесты и `test_run_claude_multiline_prompt_via_stdin`.

- [ ] **Step 8: Коммит**

```bash
git add benchmark/claude_proc.py benchmark/bench_run.py benchmark/stage_run.py \
        benchmark/tests/test_bench_run.py benchmark/tests/test_bench_e2e.py
git commit -m "fix(bench): передавать промпт claude через stdin"
```

---

### Task 2: Честные счётчики ошибок и метрики дисциплины

**Files:**
- Modify: `benchmark/bench_metrics.py:119-340, 691-818`
- Modify: `benchmark/tests/test_bench_metrics.py`

**Interfaces:**
- Produces: в `summarize_events`: `mcp_errors`, `hook_denials`, `mcp_usage_skill_calls`, `duplicate_calls`; в `aggregate_environment`: `mcp_errors`, `hook_denials`.
- Consumes: `ToolEvent`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `benchmark/tests/test_bench_metrics.py`:

```python
def test_hook_denial_is_not_mcp_error(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "h1", "Bash",
                 {"command": "ls src/cf"}),
        tool_result("2026-01-01T00:00:01+00:00", "h1",
                    "PreToolUse:Bash hook error: use "
                    "mcp__code_index__list_files(repo='ssl2')", True),
    ])
    summary = summarize_events(parse_tool_events(path), tmp_path)
    assert summary["hook_denials"] == 1
    assert summary["mcp_errors"] == 0
    env = aggregate_environment([{"transcript": {"main": summary}}])
    assert env["hook_denials"] == 1
    assert env["mcp_errors"] == 0


def test_mcp_error_and_hook_denial_are_disjoint(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "m1", "mcp__bsl_ls__check", {}),
        tool_result("2026-01-01T00:00:01+00:00", "m1", "server unavailable", True),
        tool_use("2026-01-01T00:00:02+00:00", "h1", "Bash", {"command": "ls"}),
        tool_result("2026-01-01T00:00:03+00:00", "h1",
                    "PreToolUse:Bash hook error: denied", True),
    ])
    summary = summarize_events(parse_tool_events(path), tmp_path)
    assert summary["mcp_errors"] == 1
    assert summary["hook_denials"] == 1


def test_mcp_usage_skill_and_duplicates_counted(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "s1", "Skill",
                 {"skill": "mcp-usage"}),
        tool_result("2026-01-01T00:00:01+00:00", "s1", "ok"),
        tool_use("2026-01-01T00:00:02+00:00", "r1", "Read",
                 {"file_path": "/p/a.bsl"}),
        tool_result("2026-01-01T00:00:03+00:00", "r1", "ok"),
        tool_use("2026-01-01T00:00:04+00:00", "r2", "Read",
                 {"file_path": "/p/a.bsl"}),
        tool_result("2026-01-01T00:00:05+00:00", "r2", "ok"),
    ])
    summary = summarize_events(parse_tool_events(path), tmp_path)
    assert summary["mcp_usage_skill_calls"] == 1
    assert summary["duplicate_calls"] == 1
```

Обновить `test_aggregate_environment_timed_out_and_mcp`: в фейковую сводку добавить `"mcp_errors": 1, "hook_denials": 0`.

- [ ] **Step 2: Убедиться, что новые тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q -k "hook_denial or disjoint or usage_skill"`
Expected: FAIL — `KeyError`/`assert 1 == 0`.

- [ ] **Step 3: Реализовать в `bench_metrics.py`**

Добавить helper рядом с `summarize_events`:

```python
def _is_hook_denial(event: ToolEvent) -> bool:
    return bool(event.is_error and "hook error" in (event.result_text or "").lower())
```

В `summarize_events` после `errors = ...` вычислить:

```python
    hook_denials = sum(1 for event in errors if _is_hook_denial(event))
    mcp_errors = sum(1 for event in errors
                     if event.name.startswith("mcp__")
                     and not _is_hook_denial(event))
    skill_calls = sum(
        1 for event in events
        if event.name == "Skill"
        and str(event.input.get("skill") or "") == "mcp-usage")
    seen_calls: Counter = Counter()
    for event in events:
        seen_calls[(event.name, json.dumps(event.input, ensure_ascii=False,
                                           sort_keys=True, default=str))] += 1
    duplicate_calls = sum(count - 1 for count in seen_calls.values()
                          if count > 1)
```

Добавить в возвращаемый dict:

```python
        "mcp_errors": mcp_errors,
        "hook_denials": hook_denials,
        "mcp_usage_skill_calls": skill_calls,
        "duplicate_calls": duplicate_calls,
```

В `summarize_transcripts` для сабагентов добавить поля:

```python
            "mcp_errors": summary["mcp_errors"],
            "hook_denials": summary["hook_denials"],
```

В `aggregate_environment`:

```python
    mcp_errors = 0
    hook_denials = 0
    ...
            mcp_errors += int(agent.get("mcp_errors") or 0)
            hook_denials += int(agent.get("hook_denials") or 0)
    ...
        "mcp_errors": mcp_errors,
        "hook_denials": hook_denials,
```

Удалить старую строку `"mcp_errors": sum(count for signature, count in signatures.items() if "mcp__" in signature)`.

В `render_digest`:
- после строки об инструментах задачи добавить:

```python
        skill_calls = int(main.get("mcp_usage_skill_calls") or 0)
        lines.append(f"- Skill mcp-usage: {'да' if skill_calls else 'нет'} "
                     f"({skill_calls})")
        duplicates = int(main.get("duplicate_calls") or 0)
        if duplicates:
            lines.append(f"- Повторных вызовов инструментов: {duplicates}")
```

- в блоке `## Окружение` заменить строку `- Ошибок MCP` на:

```python
              f"- Ошибок инструментов: {env.get('tool_errors', 0)} "
              f"(MCP: {env.get('mcp_errors', 0)}, "
              f"хуки: {env.get('hook_denials', 0)}, "
              f"прочие: {max(0, int(env.get('tool_errors', 0)) - int(env.get('mcp_errors', 0)) - int(env.get('hook_denials', 0)))})",
              f"- Ошибок MCP: {env.get('mcp_errors', 0)}",
              f"- Отказов хуков: {env.get('hook_denials', 0)}"]
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: зелёные.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_metrics.py benchmark/tests/test_bench_metrics.py
git commit -m "fix(bench): разделить ошибки MCP и отказы хуков"
```

---

### Task 3: Снимок входов аналитика и его изолированные транскрипты

**Files:**
- Modify: `benchmark/bench_analysis.py:1-35`
- Modify: `benchmark/bench_run.py:597-800`
- Modify: `benchmark/tests/test_bench_analysis.py`
- Modify: `benchmark/tests/test_bench_e2e.py`

**Interfaces:**
- Produces: `bench_analysis.prepare_inputs(*, run_dir: Path, metrics: dict, digest_path: Path) -> dict` с ключами `metrics_path`, `digest_path`.
- Consumes: `bench_metrics.write_json_atomic`, `StreamSummary`.

- [ ] **Step 1: Написать падающий тест**

В `benchmark/tests/test_bench_analysis.py` добавить:

```python
from bench_analysis import prepare_inputs


def test_prepare_inputs_strips_analysis_and_copies_digest(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    digest = run_dir / "digest.md"
    digest.write_text("# digest\n", encoding="utf-8")
    metrics = {"run": {"run_id": "r"}, "analysis": {"performed": False},
               "tasks": []}
    inputs = prepare_inputs(run_dir=run_dir, metrics=metrics,
                            digest_path=digest)
    import json
    saved = json.loads(inputs["metrics_path"].read_text(encoding="utf-8"))
    assert "analysis" not in saved
    assert saved["run"]["run_id"] == "r"
    assert inputs["digest_path"].read_text(encoding="utf-8") == "# digest\n"
    assert inputs["metrics_path"].parent.name == "analysis-inputs"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_analysis.py::test_prepare_inputs_strips_analysis_and_copies_digest -q`
Expected: FAIL — `ImportError: cannot import name 'prepare_inputs'`.

- [ ] **Step 3: Добавить `prepare_inputs` и текст промпта**

В `benchmark/bench_analysis.py`:
- добавить `import copy`, `import shutil`;
- `from bench_metrics import StreamSummary, write_json_atomic`;
- добавить функцию:

```python
def prepare_inputs(*, run_dir: Path, metrics: dict,
                   digest_path: Path) -> dict:
    """Снимок входов аналитика: метрики без `analysis` и копия дайджеста."""
    inputs_dir = run_dir / "analysis-inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    snapshot = copy.deepcopy(metrics)
    snapshot.pop("analysis", None)
    metrics_path = inputs_dir / "metrics.json"
    write_json_atomic(metrics_path, snapshot)
    digest_copy = inputs_dir / "digest.md"
    if digest_path.is_file():
        shutil.copyfile(digest_path, digest_copy)
    return {"metrics_path": metrics_path, "digest_path": digest_copy}
```

В `build_prompt`:
- заменить строку `- Метрики: {metrics_path}` на
  `- Снимок метрик (без поля analysis): {metrics_path}`;
- после блока «Входы» добавить:

```
## Твоё собственное состояние
`analysis.*` и `analysis-transcripts/**` — не вход. Это заглушка раннера и твой
собственный вывод; статус твоей сессии записывается после её завершения.
```

- [ ] **Step 4: Перестроить `execute`**

В `benchmark/bench_run.py`:
- после цикла задач сразу выставить `run_metrics["run"]["finished_at"] = _iso_now()`;
- убрать повторные присваивания `finished_at` в ветках `--skip-analysis` и после аналитика;
- перед `build_prompt` вызвать:

```python
    inputs = prepare_inputs(run_dir=run_dir, metrics=run_metrics,
                            digest_path=digest_path)
```

- передать `metrics_path=inputs["metrics_path"]`, `digest_path=inputs["digest_path"]` в `build_prompt` и в `_inputs_manifest`;
- перенести транскрипты аналитика:

```python
        stream_path=run_dir / "analysis-transcripts" / "analyst.stream.jsonl",
        stderr_path=run_dir / "analysis-transcripts" / "analyst.stderr.log",
```

- в `analysis` финальных метрик добавить `"finished_at": _iso_now()`.
- импортировать `prepare_inputs` из `bench_analysis`.

- [ ] **Step 5: Дополнить e2e-проверку**

В `benchmark/tests/test_bench_e2e.py::test_e2e_success_with_analysis` добавить:

```python
    assert (runs[-1] / "analysis-inputs" / "metrics.json").is_file()
    assert (runs[-1] / "analysis-transcripts" / "analyst.stream.jsonl").is_file()
    assert not (runs[-1] / "transcripts" / "analyst.stream.jsonl").exists()
    snapshot = json.loads(
        (runs[-1] / "analysis-inputs" / "metrics.json").read_text(encoding="utf-8"))
    assert "analysis" not in snapshot
```

- [ ] **Step 6: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest benchmark/tests/test_bench_analysis.py benchmark/tests/test_bench_run.py benchmark/tests/test_bench_e2e.py -q
```
Expected: зелёные.

- [ ] **Step 7: Коммит**

```bash
git add benchmark/bench_analysis.py benchmark/bench_run.py \
        benchmark/tests/test_bench_analysis.py benchmark/tests/test_bench_e2e.py
git commit -m "fix(bench): изолировать входы аналитика от его собственной сессии"
```

---

### Task 4: Неполнота AST-проверок в метриках и Node.js в prerequisites

**Files:**
- Modify: `benchmark/bench_metrics.py:1-15, 588-640, 792-810`
- Modify: `benchmark/tests/test_bench_metrics.py`
- Modify: `benchmark/README.md`

**Interfaces:**
- Produces: `query_analyze["ast"] = {"available": bool, "reason": str|None}`, `query_analyze["partial"]: bool`, в каждом результате `ast_skipped: bool`.
- Consumes: `shutil.which`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `benchmark/tests/test_bench_metrics.py`:

```python
def test_query_analyze_marks_ast_skipped(tmp_path, monkeypatch):
    import bench_metrics
    monkeypatch.setattr(bench_metrics.shutil, "which", lambda name: None)
    project = tmp_path / "project"
    scripts = project / ".claude" / "skills" / "query-analyze" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "extract_queries.py").write_text("print('ВЫБРАТЬ 1')", encoding="utf-8")
    (scripts / "analyze_query.py").write_text(
        "import sys\n"
        "print('ВНИМАНИЕ: структурные (AST) проверки ПРОПУЩЕНЫ - node', "
        "file=sys.stderr)\n",
        encoding="utf-8")
    target = project / "Module.bsl"
    target.write_text("Процедура А()\nКонецПроцедуры\n", encoding="utf-8")
    result = run_static_analyzers(project, ["Module.bsl"], None, tmp_path / "out")
    query = result["query_analyze"]
    assert query["ast"]["available"] is False
    assert query["partial"] is True
    assert query["results"][str(target.resolve())]["ast_skipped"] is True
    text = render_digest({"run": {}, "tasks": [{
        "folder": "task#001", "limit_minutes": 30, "outcome": "success",
        "duration_sec": 1.0, "exit_code": 0, "stages": [], "cycles": {},
        "transcript": {"main": {}}, "analyzers": result}], "environment": {}})
    assert "AST" in text and "неполные" in text
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py::test_query_analyze_marks_ast_skipped -q`
Expected: FAIL — `KeyError: 'ast'`.

- [ ] **Step 3: Реализовать**

В `benchmark/bench_metrics.py`:
- добавить `import shutil`;
- в `run_static_analyzers`:

```python
    node_available = shutil.which("node") is not None
    query_result = {
        "available": extract_script.is_file() and query_script.is_file(),
        "skipped": None if extract_script.is_file() and query_script.is_file()
        else "analyze_query.py/extract_queries.py не найден",
        "ast": {"available": node_available,
                "reason": None if node_available else "node не найден в PATH"},
        "partial": False,
        "results": {},
    }
```

- в цикле обработки запросов после формирования `output`:

```python
            ast_skipped = ("структурные (AST) проверки ПРОПУЩЕНЫ" in output
                           or "AST недоступен" in output)
```

- в результат добавить `"ast_skipped": ast_skipped` и:

```python
            if ast_skipped:
                query_result["partial"] = True
```

- после цикла: если `not node_available and query_result["results"]`, выставить `query_result["partial"] = True`.

В `render_digest` после строки `query-analyze: файлов N`:

```python
        if query.get("partial"):
            lines.append("- ⚠ query-analyze: структурные (AST) проверки "
                         "пропущены — результаты неполные "
                         "(установите Node.js)")
```

В `benchmark/README.md` в раздел «Подготовка окружения» добавить пункт:

```markdown
3. Для структурных проверок `query-analyze` нужен Node.js (LTS) в `PATH`:
   `node --version`. Без него работают только текстовые правила, а метрики
   помечают проверки как неполные.
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: зелёные.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_metrics.py benchmark/tests/test_bench_metrics.py benchmark/README.md
git commit -m "fix(bench): помечать неполные AST-проверки запросов"
```

---

### Task 5: Автоматическое обновление индекса code_index между задачами

**Files:**
- Create: `benchmark/bench_index.py`
- Create: `benchmark/tests/test_bench_index.py`
- Modify: `benchmark/bench_run.py:30-60, 440-510, 597-700`
- Modify: `benchmark/bench_metrics.py:723-745` (дайджест)

**Interfaces:**
- Produces: `bench_index.index_is_stale(project_dir: Path) -> bool`, `bench_index.refresh_index(project_dir: Path, *, enabled: bool = True, container: str = "ai1c-mcp-code_index", run=subprocess.run, sleep=time.sleep, clock=time.monotonic, timeout_sec=900, log=print) -> str` (значения `disabled`, `fresh`, `ready`, `skipped`, `failed`).
- Consumes: `docker` CLI, `bsl-indexer daemon status --json`.

- [ ] **Step 1: Написать падающие тесты**

Создать `benchmark/tests/test_bench_index.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace

from bench_index import index_is_stale, refresh_index


def make_project(tmp_path, *, db_after_sources=True):
    project = tmp_path / "project"
    root = project / "src" / "cf"
    root.mkdir(parents=True)
    (root / "Documents").mkdir()
    src = root / "Documents" / "Анкета.xml"
    src.write_text("<xml/>", encoding="utf-8")
    db_dir = root / ".code-index"
    db_dir.mkdir()
    db = db_dir / "index.db"
    db.write_text("db", encoding="utf-8")
    if db_after_sources:
        import os
        stat = src.stat()
        os.utime(db, (stat.st_atime + 10, stat.st_mtime + 10))
    return project


def test_index_is_stale_detects_newer_sources(tmp_path):
    assert index_is_stale(make_project(tmp_path)) is False
    project = make_project(tmp_path / "stale", db_after_sources=False)
    assert index_is_stale(project) is True


def test_refresh_index_skips_fresh_index(tmp_path):
    project = make_project(tmp_path)
    calls = []
    status = refresh_index(project, run=lambda *a, **k: calls.append(a),
                           sleep=lambda _s: None, clock=lambda: 0.0)
    assert status == "fresh"
    assert calls == []


def test_refresh_index_restarts_and_waits_ready(tmp_path, monkeypatch):
    project = make_project(tmp_path / "stale", db_after_sources=False)
    monkeypatch.setattr("bench_index.shutil.which", lambda name: "docker")
    statuses = [
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="starting"),
        SimpleNamespace(returncode=0, stdout=json.dumps(
            {"paths": [{"path": "/repos/src", "status": "ready"}]}), stderr=""),
    ]
    def fake_run(argv, **kwargs):
        return statuses.pop(0)
    ticks = iter([0.0, 0.0, 0.0, 1.0])
    status = refresh_index(
        project, run=fake_run, sleep=lambda _s: None,
        clock=lambda: next(ticks, 2.0), timeout_sec=30, log=lambda _m: None)
    assert status == "ready"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_index.py -q`
Expected: FAIL — `ModuleNotFoundError: bench_index`.

- [ ] **Step 3: Создать `benchmark/bench_index.py`**

```python
"""Свежесть индекса code_index и его перезапуск между задачами benchmark."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_CONTAINER = "ai1c-mcp-code_index"
_SKIP_DIRS = {".code-index", ".git", "__pycache__", "node_modules"}


def index_db_path(project_dir: Path) -> Path:
    return project_dir / "src" / "cf" / ".code-index" / "index.db"


def newest_source_mtime(root: Path) -> float | None:
    newest = None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            try:
                mtime = (Path(dirpath) / name).stat().st_mtime
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


def index_is_stale(project_dir: Path) -> bool:
    root = project_dir / "src" / "cf"
    db = index_db_path(project_dir)
    if not root.is_dir() or not db.is_file():
        return False
    newest = newest_source_mtime(root)
    if newest is None:
        return False
    try:
        return newest > db.stat().st_mtime
    except OSError:
        return False


def _daemon_status(container: str, run) -> dict | None:
    try:
        result = run(
            ["docker", "exec", container, "env",
             "CODE_INDEX_HOME=/data/code-index-home",
             "bsl-indexer", "daemon", "status", "--json"],
            capture_output=True, text=True)
    except OSError:
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(result, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def refresh_index(project_dir: Path, *, enabled: bool = True,
                  container: str = DEFAULT_CONTAINER,
                  run=subprocess.run, sleep=time.sleep,
                  clock=time.monotonic, timeout_sec: float = 900,
                  log=print) -> str:
    """Обновить индекс, если он отстал от исходников. Возвращает статус."""
    if not enabled:
        return "disabled"
    if not index_is_stale(project_dir):
        return "fresh"
    if shutil.which("docker") is None:
        log("⚠ индекс code_index устарел, но docker не найден — пропускаю")
        return "skipped"
    try:
        restart = run(["docker", "restart", container],
                      capture_output=True, text=True)
    except OSError as exc:
        log(f"⚠ не удалось перезапустить code_index: {exc}")
        return "failed"
    if getattr(restart, "returncode", 1) != 0:
        log("⚠ не удалось перезапустить контейнер code_index: "
            + (getattr(restart, "stderr", "") or "").strip()[:300])
        return "failed"
    deadline = clock() + timeout_sec
    while clock() < deadline:
        data = _daemon_status(container, run)
        paths = (data or {}).get("paths") or []
        if paths and all(item.get("status") == "ready" for item in paths):
            return "ready"
        sleep(5)
    log(f"⚠ code_index не стал ready за {timeout_sec:.0f} с")
    return "failed"
```

- [ ] **Step 4: Подключить в `bench_run`**

- `RunOptions` добавить `index_refresh: bool`.
- `parse_args` добавить:

```python
    parser.add_argument("--no-index-refresh", action="store_false",
                        dest="index_refresh",
                        help="не обновлять индекс code_index между задачами")
```

- `build_options` передать `index_refresh=bool(ns.index_refresh)`.
- импортировать `from bench_index import refresh_index`.
- в начале каждой итерации задач (до `run_claude`):

```python
        index_status = refresh_index(options.project_dir,
                                     enabled=options.index_refresh,
                                     log=log)
```

- в `task_metrics` добавить `"index_refresh": index_status`.
- `log` после задачи или перед: `log(f"  индекс code_index: {index_status}")`.

- [ ] **Step 5: Показать статус в дайджесте**

В `render_digest` в блоке задачи после строки об исходе:

```python
        index_status = task.get("index_refresh")
        if index_status:
            lines.append(f"- Индекс code_index: `{index_status}`")
```

- [ ] **Step 6: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest benchmark/tests/test_bench_index.py benchmark/tests/test_bench_run.py benchmark/tests/test_bench_e2e.py benchmark/tests/test_bench_metrics.py -q
```
Expected: зелёные.

- [ ] **Step 7: Коммит**

```bash
git add benchmark/bench_index.py benchmark/tests/test_bench_index.py \
        benchmark/bench_run.py benchmark/bench_metrics.py
git commit -m "feat(bench): обновлять индекс code_index между задачами"
```

---

### Task 6: `alwaysLoad` для code_index и bsl_ls в `.mcp.json`

**Files:**
- Modify: `app/src/agentmon/env/mcp_catalog.py:85-110`
- Modify: `app/tests/env/test_mcp_catalog.py`
- Modify: `app/tests/env/test_mcp_catalog_from_connection.py`

**Interfaces:**
- Produces: `build_mcp_json` добавляет `"alwaysLoad": True` для серверов с `sel.id` из `{"code-index", "code-index-local", "bsl-ls"}` или именем `code_index`/`bsl_ls`.
- Consumes: `McpSelection`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_mcp_catalog_from_connection.py` заменить ожидание в `test_build_mcp_json_uses_connection_fragment`:

```python
    assert servers == {
        "bsl_ls": {"type": "http", "url": "http://localhost:8001/mcp",
                   "alwaysLoad": True}
    }
```

Добавить:

```python
def test_build_mcp_json_preloads_code_index_and_bsl_ls():
    sel = [
        McpSelection(id="code-index", enabled=True, mode="managed",
                     connection='"code_index": {"type":"http","url":"http://x/mcp"}'),
        McpSelection(id="1c-md", enabled=True, mode="managed",
                     connection='"1c-md": {"type":"http","url":"http://y/mcp"}'),
    ]
    servers = build_mcp_json(sel)["mcpServers"]
    assert servers["code_index"]["alwaysLoad"] is True
    assert "alwaysLoad" not in servers["1c-md"]
```

В `app/tests/env/test_mcp_catalog.py` обновить `test_managed_http_uses_localhost_url`:

```python
    assert out == {"url": f"http://127.0.0.1:{port}", "alwaysLoad": True}
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_catalog.py app/tests/env/test_mcp_catalog_from_connection.py -q`
Expected: FAIL — в словаре нет `alwaysLoad`.

- [ ] **Step 3: Реализовать**

В `app/src/agentmon/env/mcp_catalog.py`:

```python
_PRELOAD_IDS = frozenset({"code-index", "code-index-local", "bsl-ls"})
_PRELOAD_NAMES = frozenset({"code_index", "bsl_ls"})


def _preload_entry(sel_id: str, name: str, value: dict) -> dict:
    if sel_id in _PRELOAD_IDS or name in _PRELOAD_NAMES:
        return {**value, "alwaysLoad": True}
    return value
```

В `build_mcp_json` применять helper во всех ветках, где формируется запись сервера:

```python
        if connection:
            _, value = _parse_connection(connection, sel.id)
            servers[name] = _preload_entry(sel.id, name, value)
            continue
        ...
        if sel.mode == "external":
            servers[name] = _preload_entry(sel.id, name,
                                           _external_entry(sel.endpoint or ""))
        elif spec.transport == "http":
            servers[name] = _preload_entry(
                sel.id, name, {"url": f"http://127.0.0.1:{spec.default_port}"})
        else:
            servers[name] = _preload_entry(
                sel.id, name, {"command": "docker",
                               "args": ["exec", "-i", sel.id]})
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_catalog.py app/tests/env/test_mcp_catalog_from_connection.py app/tests/env/test_content_deploy.py -q`
Expected: зелёные.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/mcp_catalog.py app/tests/env/test_mcp_catalog.py \
        app/tests/env/test_mcp_catalog_from_connection.py
git commit -m "feat(env): предзагружать схемы code_index и bsl_ls"
```

---

### Task 7: UTF-8 окружение, `modelOverrides` и устойчивость entrypoint'ов

**Files:**
- Modify: `template/.claude/settings.json`
- Modify: `template/.claude/settings.local.json.example`
- Modify: `benchmark/claude-local.bat.example`
- Modify: `benchmark/claude-local.sh.example`
- Modify: `template/.claude/skills/1c-batch/scripts/1c-batch.py`
- Modify: `template/.claude/tools/run-tests.py`
- Modify: `template/.claude/tools/load-config-optimized.py`
- Modify: `template/.claude/tools/task_status.py`
- Modify: `benchmark/README.md`
- Modify: `app/tests/env/test_content_deploy.py`

**Interfaces:**
- Produces: после `deploy_content` в `.claude/settings.json` есть `env.PYTHONUTF8=1`, `env.PYTHONIOENCODING=utf-8`; в примере локальных настроек — `modelOverrides`.
- Consumes: `content.deploy_content`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_content_deploy.py` добавить:

```python
def test_settings_sets_utf8_env(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    data = json.loads((tmp_path / ".claude" / "settings.json")
                      .read_text(encoding="utf-8"))
    assert data["env"]["PYTHONUTF8"] == "1"
    assert data["env"]["PYTHONIOENCODING"] == "utf-8"


def test_local_settings_example_has_model_overrides(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    text = (tmp_path / ".claude" / "settings.local.json.example").read_text(
        encoding="utf-8")
    assert "modelOverrides" in text
    assert "claude-sonnet-4-6" in text
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_content_deploy.py -q -k "utf8_env or model_overrides"`
Expected: FAIL.

- [ ] **Step 3: Добавить env в `settings.json`**

В `template/.claude/settings.json` добавить верхнеуровневый блок:

```json
  "env": {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8"
  },
```

- [ ] **Step 4: Обновить пример локальных настроек**

В `template/.claude/settings.local.json.example` в `env` добавить:

```json
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
```

и верхнеуровневый блок (рядом с `env`, не внутри него):

```json
  "modelOverrides": {
    "claude-sonnet-4-6": "<model-id>"
  },
```

- [ ] **Step 5: Обновить обёртки запуска**

`benchmark/claude-local.bat.example` — перед `claude`:

```bat
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
```

`benchmark/claude-local.sh.example` — перед `exec`:

```sh
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
```

- [ ] **Step 6: Переключить stdout/stderr entrypoint'ов на UTF-8**

В начало `1c-batch.py`, `run-tests.py`, `load-config-optimized.py`,
`task_status.py` (после импортов) добавить одинаковый блок:

```python
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
```

Убедиться, что `sys` импортирован в каждом файле.

- [ ] **Step 7: Дополнить README**

В `benchmark/README.md` в раздел «Настройки из Strata» добавить:

```markdown
Если Claude Code пишет в stderr `[claude-code:unrecognized_model]`, это
диагностика, а не ошибка. Погасить её можно в `settings.local.json`:

```json
"modelOverrides": {"claude-sonnet-4-6": "<фактический id модели>"}
```
```

- [ ] **Step 8: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_content_deploy.py app/tests/env/test_content_conditions.py -q
```
Expected: зелёные.

- [ ] **Step 9: Коммит**

```bash
git add template/.claude/settings.json template/.claude/settings.local.json.example \
        benchmark/claude-local.bat.example benchmark/claude-local.sh.example \
        template/.claude/skills/1c-batch/scripts/1c-batch.py \
        template/.claude/tools/run-tests.py \
        template/.claude/tools/load-config-optimized.py \
        template/.claude/tools/task_status.py benchmark/README.md \
        app/tests/env/test_content_deploy.py
git commit -m "fix(env): UTF-8 вывод на Windows и modelOverrides"
```

---

### Task 8: Чеклисты, правила и хуки под реальное поведение индекса

**Files:**
- Modify: `template/.claude/skills/mcp-usage/SKILL.md`
- Modify: `template/.claude/checklists/developer.md`
- Modify: `template/.claude/skills/query-analyze/SKILL.md`
- Modify: `template/.claude/hooks/route_to_checklists.py`
- Modify: `template/.claude/hooks/bsl_nudge.py`
- Modify: `template/.claude/hooks/code_index_guard_lib/redirect.py`
- Modify: `benchmark/bench_run.py` (`build_task_prompt`)
- Modify: `benchmark/stage_run.py` (`stage_prompt`)
- Modify: `app/tests/env/test_content_conditions.py`
- Modify: `app/tests/env/test_route_hook.py`
- Modify: `app/tests/env/test_bsl_nudge.py`
- Modify: `benchmark/tests/test_bench_e2e.py`

**Interfaces:**
- Produces: обновлённые тексты окружения и injected-context.
- Consumes: `deploy_content`, `route_to_checklists.build_output`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_content_conditions.py` добавить:

```python
def test_deploy_documents_index_fallback_and_path_format(tmp_path):
    content.deploy_content(LocalProvisioner(), cfg(tmp_path, []), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "Documents/Анкета.xml" in text
    assert "not in the index" in text
    assert "native Read" in text


def test_deploy_documents_validate_query_text_format(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "queryText" in text
    assert "without leading" in text
```

В `app/tests/env/test_route_hook.py` добавить проверку в существующем стиле
(модуль загружается через `_load()`, проект создаётся `_project()`):

```python
def test_first_action_is_mcp_usage(tmp_path):
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task#100001 ...", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "First action" in context
    assert "mcp-usage" in context
```

В `app/tests/env/test_bsl_nudge.py` добавить в существующем стиле:

```python
def test_bom_hint_present():
    mod = _load()
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": "/p/Module.bsl"}})
    assert "BOM" in out["hookSpecificOutput"]["additionalContext"]
```

В `benchmark/tests/test_bench_e2e.py::test_task_prompt_triggers_single_agent`
добавить `assert "mcp-usage" in prompt`.

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py app/tests/env/test_route_hook.py app/tests/env/test_bsl_nudge.py benchmark/tests/test_bench_e2e.py -q
```
Expected: FAIL — нет новых фраз.

- [ ] **Step 3: Обновить `mcp-usage/SKILL.md`**

- В §5 «Index boundary» добавить исключение:

```
   **Exception:** if `code_index` reports that a file/object is not in the
   index (created in this task) or the index is stale, read that exact path
   with native `Read`/`meta-info`. The guard allows it; do not build Python
   workarounds.
```

- Заменить блок «Index freshness» на:

```
- **Index freshness.** With a working file watcher the index updates in seconds
  (debounce 1.5 s + batch 2 s). On Windows bind mounts watcher events may be
  missing: if `health`/`stat_file` disagree or a new object is not found, treat
  the index as stale and use the native fallback above. The benchmark runner
  refreshes the index between tasks.
```

- В bullet `read_file` добавить:

```
  `path` is relative to the repository root (`src/cf`), e.g.
  `Documents/Анкета.xml` or `CommonModules/Х/Ext/Module.bsl`; do not repeat the
  metadata type (`Documents/Анкета/Documents/Анкета.xml` is wrong).
```

- В §0 или §1 добавить:

```
- **First exploration call** for `src/cf` is
  `list_files(repo="...", path_prefix="...")`; `ls`/`find`/`grep` are denied
  by the code-index guard.
```

- В golden rules добавить пункт:

```
7. One `get_object_structure`/`get_object_profile`/`list_files` per object per
   task - reuse the result; repeat only if the object changed after a return to
   `develop`.
```

- В разделе `validate_query` добавить:

```
**Text format:** `queryText` is the concatenated query text **without leading
`|`** and without outer quotes; the tool is not a 1C literal parser. A literal
with `|` prefixes will fail with a syntax error.
```

- [ ] **Step 4: Обновить `developer.md`**

- В шаг 3 после требования `sha256` добавить:

```
   The server strips a leading UTF-8 BOM itself; do not spend a turn checking
   the BOM manually.
```

- В раздел Environment (перед «Mandatory first step») добавить:

```
**First action:** invoke the `mcp-usage` skill before any tool call.
**First exploration call:** `mcp__code_index__list_files(repo=..., path_prefix=...)`,
not `ls`/`find`/`grep` - the guard denies them.
**One profile per object:** call `get_object_structure`/`get_object_profile`
once per object per task and reuse the result.
```

- В конец абзаца «Index boundary» добавить:

```
If `code_index` says a file/object is not in the index (created in this task)
or the index is stale, use native `Read`/`meta-info` for that exact path; the
guard allows it.
```

- В раздел про `validate_query` добавить:

```
Pass `queryText` as the concatenated text without leading `|` and without
outer quotes.
```

- [ ] **Step 5: Обновить `query-analyze/SKILL.md`**

В шаге 2 проверки `validate_query` добавить строку:

```
   `queryText` is the concatenated query text without leading `|` and without
   outer quotes; the tool is not a 1C literal parser.
```

- [ ] **Step 6: Обновить хуки**

`route_to_checklists.py` — в обе ветки `parts` первой строкой добавить:

```python
        "[ai1c] First action before any tool call: invoke Skill mcp-usage.",
```

`bsl_nudge.py` — в текст `additionalContext` добавить:

```
" BOM: no manual check - the server strips a leading UTF-8 BOM."
```

`redirect.py` — в `reason` для directory listing добавить конкретный вызов:

```python
    listing_hint = ""
    if _is_directory_listing(link):
        listing_hint = (f' First call: {tools.tool("list_files")}'
                        f'(repo="{alias}", pattern="*").')
    reason = (... + listing_hint)
```

- [ ] **Step 7: Обновить промпты раннеров**

`benchmark/bench_run.py::build_task_prompt` — в первую строку добавить:

```python
              f"Первое действие до вызова инструментов — Skill mcp-usage. "
```

`benchmark/stage_run.py::stage_prompt` — в `lines` после чеклиста добавить:

```python
        "Первое действие до вызова инструментов — Skill mcp-usage.",
```

- [ ] **Step 8: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py \
    app/tests/env/test_route_hook.py app/tests/env/test_bsl_nudge.py \
    app/tests/env/test_code_index_guard_bash.py \
    benchmark/tests/test_bench_e2e.py -q
```
Expected: зелёные.

- [ ] **Step 9: Коммит**

```bash
git add template/.claude/skills/mcp-usage/SKILL.md \
        template/.claude/checklists/developer.md \
        template/.claude/skills/query-analyze/SKILL.md \
        template/.claude/hooks/route_to_checklists.py \
        template/.claude/hooks/bsl_nudge.py \
        template/.claude/hooks/code_index_guard_lib/redirect.py \
        benchmark/bench_run.py benchmark/stage_run.py benchmark/tests/test_bench_e2e.py \
        app/tests/env/test_content_conditions.py app/tests/env/test_route_hook.py \
        app/tests/env/test_bsl_nudge.py
git commit -m "docs(env): индекс, read_file, validate_query и первый шаг mcp-usage"
```

---

## Финальная проверка (выполняет оркестратор, не сабагент)

- [ ] Полный прогон benchmark-тестов:
  `.venv/bin/python -m pytest benchmark/tests -q`
- [ ] Полный прогон env-тестов:
  `.venv/bin/python -m pytest app/tests/env -q`
- [ ] `git status --short` — чисто; `git log --oneline -10` — восемь локальных коммитов в `main`, push не выполнялся.
- [ ] Сверить спеку: каждый пункт «Критериев приёмки» покрыт таском.
