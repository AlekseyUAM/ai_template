# Доработки окружения (v2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Исправить/дополнить содержимое окружения и установщик по обратной связи: деградируемый Вход субагентов, убрать YaxUnit, хук-роутер к оркестратору, ветка git на старте задачи, git init src + установка внешних инструментов, вендоринг cc-1c-skills (кроме дублей 1c-batch) + 1c-batch.

**Tech Stack:** Python 3.10+ (stdlib), pytest. Контент — markdown/Python. Внешние скилы — Python-рантайм.

## Global Constraints

- Кросс-платформа; pathlib; тексты на русском; хуки/тулзы — самодостаточный Python (без agentmon).
- template/ — источник содержимого; деплой через `content.py` в `.claude/`.
- 5 предметных субагентов + orchestrator; артефакты `ANALYZE/ARCHITECT/TESTS/DEVELOP/TESTING/REVIEW/DOCS.md`; всегда доступен `TASK.md`.
- Исключаемые дубли 1c-batch при вендоринге: `db-create`, `db-update`, `db-run`, `db-dump-cf`, `db-load-cf`, `db-dump-xml`, `db-load-xml`, `db-dump-dt`, `db-load-dt`, `db-cfe-admin`, `epf-build`, `epf-dump`, `erf-build`, `erf-dump`.

---

# ФАЗА 1 — контент-фиксы, хук, тул ветки

## Task 1: Деградируемый `## Вход` + правка оркестрации

**Files:**
- Modify: `template/agents/{analyst,architect,developer,tester,reviewer}.md` (раздел `## Вход`)
- Modify: `template/skills/task-orchestration/SKILL.md`
- Test: `app/tests/env/test_agent_inputs.py`

**Interfaces:** Produces — каждый агент в `## Вход` явно допускает отсутствие артефактов предыдущих этапов и называет `TASK.md` как fallback.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_agent_inputs.py
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[3] / "template" / "agents"


def test_each_agent_input_is_degradable():
    # downstream-агенты должны допускать отсутствие предыдущих артефактов и падать на TASK.md
    for name in ("architect", "developer", "tester", "reviewer"):
        text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
        assert "TASK.md" in text, f"{name}: нет упоминания TASK.md как fallback"
```

- [ ] **Step 2: Run — fails** (TASK.md не упомянут в этих агентах).
Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_agent_inputs.py -q`

- [ ] **Step 3: Правка агентов.** В каждом из `architect.md`, `developer.md`, `tester.md`, `reviewer.md` заменить раздел `## Вход` на деградируемую формулировку. Пример для `developer.md`:

```markdown
## Вход
Используй имеющиеся артефакты задачи: `ANALYZE.md` (спецификация), `ARCHITECT.md`
(техдизайн), ранее написанные тесты. Если каких-то из них нет (включены не все
этапы) — опирайся на `TASK.md` (цель, план, ограничения) как первичный источник.
```
Аналогично для `architect.md` (входы: `ANALYZE.md` или `TASK.md`), `tester.md`
(входы: `ANALYZE.md`/`ARCHITECT.md`/код если есть, иначе `TASK.md`), `reviewer.md`
(входы: имеющиеся артефакты + изменения; иначе `TASK.md`). `analyst.md` уже опирается
на `TASK.md` — оставить, но явно упомянуть `TASK.md` по имени.

- [ ] **Step 4: Правка `task-orchestration/SKILL.md`.** В раздел про делегирование добавить:
```markdown
При делегировании передавай субагенту ТОЛЬКО реально существующие артефакты
предыдущих этапов плюс всегда `TASK.md`. Не требуй отсутствующих файлов, если
соответствующие этапы не были включены.
```

- [ ] **Step 5: Run — passes.** Прогон `test_agent_inputs.py` + `test_content_files.py`.

- [ ] **Step 6: Commit** `git commit -m "fix(agents): деградируемый Вход при частичном наборе этапов"`

---

## Task 2: Убрать YaxUnit

**Files:**
- Modify: `template/agents/tester.md`, `template/skills/sdd-tdd-workflow/SKILL.md`
- Test: `app/tests/env/test_no_yaxunit.py`

- [ ] **Step 1: Failing test**

```python
# app/tests/env/test_no_yaxunit.py
from pathlib import Path
TPL = Path(__file__).resolve().parents[3] / "template"


def test_no_yaxunit_hardcoded():
    for rel in ("agents/tester.md", "skills/sdd-tdd-workflow/SKILL.md"):
        text = (TPL / rel).read_text(encoding="utf-8").lower()
        assert "yaxunit" not in text and "яксюнит" not in text
```

- [ ] **Step 2: Run — fails.**
- [ ] **Step 3:** В `tester.md` и `sdd-tdd-workflow/SKILL.md` заменить «юнит-тесты (YaxUnit)» → «юнит-тесты средствами, принятыми в проекте»; убрать строку про «серверная логика → YaxUnit», заменив на «выбор тест-раннера — на усмотрение проекта/задачи».
- [ ] **Step 4: Run — passes.**
- [ ] **Step 5: Commit** `git commit -m "fix(content): убрать хардкод YaxUnit"`

---

## Task 3: Хук route_to_orchestrator.py

**Files:**
- Create: `template/hooks/route_to_orchestrator.py`
- Modify: `app/src/agentmon/env/content.py` (`_render_settings` — зарегистрировать UserPromptSubmit хук)
- Test: `app/tests/env/test_route_hook.py`, и правка `test_content_deploy.py::test_settings_registers_hook` при необходимости

**Interfaces:** Produces — `build_output(event: dict) -> dict`: если `event["prompt"]` содержит `tasks/task#` → `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}` с упоминанием `task-orchestration`; иначе `{}`. `main()` читает stdin.

- [ ] **Step 1: Failing test**

```python
# app/tests/env/test_route_hook.py
import importlib.util
from pathlib import Path
HOOK = Path(__file__).resolve().parents[3] / "template" / "hooks" / "route_to_orchestrator.py"


def _load():
    spec = importlib.util.spec_from_file_location("r2o", HOOK)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def test_task_prompt_routes_to_orchestrator():
    m = _load()
    out = m.build_output({"prompt": "Выполни задачу tasks/task#100001 ..."})
    assert "task-orchestration" in out["hookSpecificOutput"]["additionalContext"]


def test_other_prompt_silent():
    m = _load()
    assert m.build_output({"prompt": "просто вопрос"}) == {}
```

- [ ] **Step 2: Run — fails.**
- [ ] **Step 3: Создать хук**

```python
# template/hooks/route_to_orchestrator.py
#!/usr/bin/env python3
"""UserPromptSubmit-хук: задачи вида tasks/task# маршрутизируются оркестратору."""
import json
import sys


def build_output(event: dict) -> dict:
    prompt = event.get("prompt") or ""
    if "tasks/task#" in prompt:
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "[ai1c] Это выполнение задачи. Действуй как оркестратор: следуй "
                "навыку task-orchestration, веди этапы из task.json и делегируй "
                "субагентам (analyst/architect/developer/tester/reviewer)."),
        }}
    return {}


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    out = build_output(event)
    if out:
        json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4:** В `content.py` `_render_settings` добавить регистрацию UserPromptSubmit:
```python
        "UserPromptSubmit": [{
            "hooks": [{"type": "command",
                       "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/route_to_orchestrator.py"'}],
        }],
```
(в том же объекте `hooks`, рядом с `PostToolUse`). Это НЕ ломает `test_settings_registers_hook` (он проверяет PostToolUse → bsl_nudge).

- [ ] **Step 5: Run — passes** (`test_route_hook.py` + `test_content_deploy.py` + полный набор).
- [ ] **Step 6: Commit** `git commit -m "feat(hooks): маршрутизация задачи к оркестратору (UserPromptSubmit)"`

---

## Task 4: Тул task_branch.py + ветка на старте задачи

**Files:**
- Create: `template/tools/task_branch.py`
- Modify: `template/skills/task-orchestration/SKILL.md`, `template/rules/task-lifecycle.md`
- Test: `app/tests/env/test_task_branch.py`

**Interfaces:** Produces — `main(argv)`: `task_branch.py <src_dir> <task_id>` → `git -C <src_dir> checkout -b task/<task_id>` (если ветка есть → `checkout`). Самодостаточный (subprocess git).

- [ ] **Step 1: Failing test**

```python
# app/tests/env/test_task_branch.py
import importlib.util, subprocess
from pathlib import Path
TOOL = Path(__file__).resolve().parents[3] / "template" / "tools" / "task_branch.py"


def _load():
    spec = importlib.util.spec_from_file_location("task_branch", TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True,
                   capture_output=True, text=True)


def test_creates_and_reswitches(tmp_path):
    m = _load()
    src = tmp_path / "src"; src.mkdir()
    _git(src, "init", "-q")
    _git(src, "config", "user.email", "t@t"); _git(src, "config", "user.name", "t")
    (src / "f.txt").write_text("x"); _git(src, "add", "."); _git(src, "commit", "-qm", "init")
    m.main([str(src), "100001"])
    cur = subprocess.run(["git", "-C", str(src), "branch", "--show-current"],
                         capture_output=True, text=True).stdout.strip()
    assert cur == "task/100001"
    m.main([str(src), "100001"])   # повторно — не падает, остаёмся на ветке
    cur2 = subprocess.run(["git", "-C", str(src), "branch", "--show-current"],
                          capture_output=True, text=True).stdout.strip()
    assert cur2 == "task/100001"
```

- [ ] **Step 2: Run — fails.**
- [ ] **Step 3: Создать тул**

```python
# template/tools/task_branch.py
#!/usr/bin/env python3
"""Создать/переключиться на ветку задачи в репозитории src. Самодостаточный."""
import subprocess
import sys


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        raise SystemExit("использование: task_branch.py <src_dir> <task_id>")
    src_dir, task_id = argv[0], argv[1]
    branch = f"task/{task_id}"
    exists = subprocess.run(
        ["git", "-C", src_dir, "rev-parse", "--verify", branch],
        capture_output=True, text=True).returncode == 0
    action = ["checkout", branch] if exists else ["checkout", "-b", branch]
    r = subprocess.run(["git", "-C", src_dir, *action], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stderr.strip() or "git checkout не удался")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4:** В `task-orchestration/SKILL.md` добавить раздел «Ветка задачи»: перед первым изменяющим этапом выполнить `python3 .claude/tools/task_branch.py src <task_id>`; все изменения — в ветке `task/<id>`. В `task-lifecycle.md` добавить пункт про ветку.
- [ ] **Step 5: Run — passes** (`test_task_branch.py` + полный набор).
- [ ] **Step 6: Commit** `git commit -m "feat(tasks): ветка git на старте задачи (task_branch.py)"`

---

# ФАЗА 2 — установщик и вендоринг (детализируется перед исполнением)

## Task 5: Установщик — git init src + .1c-devbase.json
- Шаг `git-init` в `installer.py`: `git init` в `<project>/src` (идемпотентно) + `.gitignore` (logs/, *.log).
- Генерация `<project>/.1c-devbase.json` из `ai1c.config.json` (platform_path, connection, cf_dir=src/cf, cfe_dir=src/cfe).
- Порядок: layout → config → content → mcp → git-init → [dump-cf] → [dump-cfe] → [tools-install] → register.
- Тесты: шаг git-init создаёт `.git` в src; `.1c-devbase.json` сгенерирован.

## Task 6: Установщик — tools-install (pip)
- Шаг `tools-install` (инъектируемый `run`): `pip install` 1c-batch CLI (`.claude/skills/1c-batch/scripts`) + `lxml Pillow psutil`.
- Галка в мастере «установить инструменты» (по умолч. вкл.).
- Тесты: с моком `run` вызывается нужные команды; ошибка pip → error-событие.

## Task 7: Вендоринг cc-1c-skills (python-рантайм, без дублей) + 1c-batch
- Через `deps/cc-1c-skills/scripts/switch.py ... --runtime python` в tmp → скопировать в `template/skills/`, исключив список дублей (Global Constraints).
- Скопировать `deps/1c-batch-py/src/1c-batch` → `template/skills/1c-batch/`.
- Node-хуки cc-1c-skills не переносим.
- Тесты: наличие `meta-info`/`form-edit`/`web-test`/`1c-batch`; отсутствие `db-dump-cf`/`epf-build`; SKILL.md ссылается на python, не powershell.

## Task 8: Обновить валидацию контента + интеграция
- `test_content_files.py`: допустить расширенный набор скилов (проверять наличие обязательных, не равенство множества).
- Интеграция: `deploy_content` разворачивает новые хук/тул/скилы; полный набор зелёный.

---

## Self-Review (Фаза 1)
- п.1 → Task 1; п.2 → Task 2; п.3 → Task 3; п.6 → Task 4. (п.4,5 — Фаза 2.)
- Хук/тул — самодостаточный Python, деплоятся существующим `content.py` (копирует hooks/ и tools/).
- Регистрация UserPromptSubmit не ломает существующий тест PostToolUse.
- Фаза 2 детализируется (код) непосредственно перед исполнением.
