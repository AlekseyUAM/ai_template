# Исправление конвейера по итогам task##002 — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести красный смоук к автору тестов, сделать логи `run-tests.py` однозначными, запретить запросы с невалидными литералами и включить инвалидацию кэша `code_index`.

**Architecture:** Правки сосредоточены в трёх слоях: (1) шаблон промптов/скиллов `template/.claude` — контракт ролей и правила проверки; (2) инструмент `run-tests.py` — свежий результат, сводка, коды `4/5`; (3) генератор окружения `app/src/agentmon/env` — `[[cache_targets]]` в `daemon.toml`. Каждая задача оставляет независимо проверяемый результат и свой коммит.

**Tech Stack:** Python 3.14, pytest 9, Markdown-шаблоны Claude Code, TOML-конфиг `bsl-indexer` 0.44.3, bash.

## Global Constraints

- Рабочая ветка — `main`; коммиты **локальные, без push**.
- Каждая задача — один коммит; в `git add` включать только файлы этой задачи. В рабочем дереве есть посторонние незакоммиченные файлы `benchmark/tasks/task##002/TASK.md` и `template/.bsl-language-server.json` — их **не трогать и не коммитить**.
- Не править `test2` и не запускать benchmark.
- Не менять плейсхолдеры шаблона (`{{MODEL}}`, `{{EFFORT}}`, `{{MCP_1C_MD_TOOLS}}`, `{{CODE_INDEX_REPO}}`) и условные маркеры `<!-- @if 1c-md -->`.
- Тесты запускать из корня репозитория: `.venv/bin/python -m pytest ...`.
- Тексты промптов — на русском, в стиле окружающих файлов.
- Никаких изменений в `code-index-mcp` (Rust) — только конфигурация.

---

### Task 1: `run-tests.py` — удаление старого результата, сводка, коды `4/5`

**Files:**
- Modify: `template/.claude/tools/run-tests.py`
- Test: `app/tests/env/test_run_tests_cli.py`

**Interfaces:**
- Produces: константы `RC_TESTS_FAILED = 4`, `RC_NO_RESULT = 5`; функции `_result_log_path(project_root: Path, config_path: Path) -> Path | None`, `_reset_result_log(path: Path | None) -> None`, `_read_and_print_result(path: Path | None) -> int`.
- Produces: `run_tests(...)` возвращает `0` (все зелёные), `4` (есть падения/`Выполнено=false`), `5` (нет/невалиден `result.json`), плюс прежние `1/2/3/124`.

- [ ] **Step 1: Добавить падающие тесты**

В конец `app/tests/env/test_run_tests_cli.py` добавить `import json` в начало файла (после `import importlib.util`) и следующие тесты:

```python
def _config(tmp_path, result_path):
    cfg = tmp_path / "test.json"
    cfg.write_text(json.dumps({"ИмяМодуля": "M", "ИмяФайлаЛог": str(result_path)},
                              ensure_ascii=False), encoding="utf-8")
    return cfg


def _result(tests, done=True, error=None):
    return {"Выполнено": done, "ОписаниеОшибки": error, "РезультатТестов": tests}


def _patch_enterprise(monkeypatch, mod, result_path, result=None, rc=0):
    state = {"exists_at_start": None}

    def fake(project_root, c_value, timeout):
        state["exists_at_start"] = result_path.exists()
        if result is not None:
            result_path.write_text(json.dumps(result, ensure_ascii=False),
                                   encoding="utf-8")
        return rc

    monkeypatch.setattr(mod, "run_enterprise", fake)
    return state


def test_all_tests_passed_returns_rc0(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": True, "ОписаниеОшибки": None}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_OK


def test_failed_test_returns_rc4_and_prints_summary(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": False,
                                "ОписаниеОшибки": "boom"}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_TESTS_FAILED
    out = capsys.readouterr().out
    assert "ИТОГ: 0/1 пройдено" in out
    assert "✗ A" in out
    assert "boom" in out


def test_missing_result_returns_rc5(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path, None)
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_NO_RESULT
    assert "Файл результата не найден" in capsys.readouterr().out


def test_empty_test_list_returns_rc5(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path, _result([]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_NO_RESULT


def test_previous_result_removed_before_run(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    result_path.write_text("старый", encoding="utf-8")
    cfg = _config(tmp_path, result_path)
    state = _patch_enterprise(monkeypatch, mod, result_path,
                              _result([{"Имя": "A", "Результат": True,
                                        "ОписаниеОшибки": None}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_OK
    assert state["exists_at_start"] is False


def test_enterprise_failure_returned_as_is(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path, None, rc=1)
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == 1
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_run_tests_cli.py -v`
Expected: ошибки `AttributeError: module ... has no attribute 'RC_TESTS_FAILED'` (или аналогичные) — констант и функций ещё нет.

- [ ] **Step 3: Реализовать изменение**

В `template/.claude/tools/run-tests.py`:

1. В docstring после блока кодов добавить строки:

```text
    4    прогон состоялся, но есть проваленные тесты (result.json свежий)
    5    result.json не найден, невалиден или список тестов пуст
```

2. После констант `RC_TIMEOUT = 124` добавить:

```python
RC_TESTS_FAILED = 4
RC_NO_RESULT = 5

RESULT_DONE_KEY = "Выполнено"
RESULT_ERROR_KEY = "ОписаниеОшибки"
RESULT_TESTS_KEY = "РезультатТестов"
```

3. Перед функцией `run_tests(...)` добавить три функции:

```python
def _result_log_path(project_root: Path, config_path: Path) -> Path | None:
    """Путь к result.json из конфига тестов (поле ИмяФайлаЛог)."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        print(f"⚠️  Не удалось прочитать конфиг для определения ИмяФайлаЛог: {err}")
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("ИмяФайлаЛог")
    if not isinstance(name, str) or not name.strip():
        return None
    path = Path(name)
    return path if path.is_absolute() else (project_root / path).resolve()


def _reset_result_log(path: Path | None) -> None:
    """Удалить прошлый результат: после прогона файл может быть только свежим."""
    if path is None:
        print("⚠️  В конфиге не задан ИмяФайлаЛог — результат после прогона не прочитать.")
        return
    try:
        path.unlink()
        print(f"🧹 Удалён прошлый результат: {path}")
    except FileNotFoundError:
        pass
    except OSError as err:
        print(f"⚠️  Не удалось удалить прошлый результат {path}: {err}")
    print(f"📄 Результат будет записан в: {path}")


def _read_and_print_result(path: Path | None) -> int:
    """Прочитать result.json, напечатать сводку и вернуть 0/4/5."""
    if path is None:
        print("❌ В конфиге тестов не задан ИмяФайлаЛог — результат некуда прочитать.")
        return RC_NO_RESULT
    if not path.exists():
        print(f"❌ Файл результата не найден: {path}")
        print("   Прогон не дошёл до записи результата — проверьте лог сеанса выше.")
        return RC_NO_RESULT
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        print(f"❌ Не удалось прочитать результат {path}: {err}")
        return RC_NO_RESULT

    tests = data.get(RESULT_TESTS_KEY) if isinstance(data, dict) else None
    if not isinstance(tests, list) or not tests:
        print(f"❌ В результате нет тестов: {path}")
        return RC_NO_RESULT

    done = data.get(RESULT_DONE_KEY)
    error = data.get(RESULT_ERROR_KEY)
    passed = sum(
        1 for test in tests
        if isinstance(test, dict) and test.get("Результат") is True
    )
    failed = len(tests) - passed

    print()
    print(f"📊 Результат прогона: {path}")
    print(f"   Выполнено: {done}")
    print(f"   ОписаниеОшибки: {error}")
    print()
    for test in tests:
        if not isinstance(test, dict):
            continue
        is_ok = test.get("Результат") is True
        print(f"   {'✓' if is_ok else '✗'} {test.get('Имя', '<без имени>')}")
        if not is_ok and test.get("ОписаниеОшибки"):
            print(f"      {test['ОписаниеОшибки']}")
    print()
    print(f"ИТОГ: {passed}/{len(tests)} пройдено")

    all_passed = done is True and error is None and failed == 0
    return RC_OK if all_passed else RC_TESTS_FAILED
```

4. В `run_tests(...)` после проверки `effective_config` и перед `print("🧪 Запуск юнит-тестов 1С")` добавить:

```python
    result_path = _result_log_path(project_root, effective_config)
    _reset_result_log(result_path)
```

5. Заменить финальный блок `run_enterprise` в `run_tests(...)`:

```python
    c_value = f"{LAUNCH_PARAM}={effective_config}"
    rc = run_enterprise(project_root, c_value, timeout)

    if rc == RC_TIMEOUT:
        return diagnose_timeout(project_root)
    if rc != RC_OK:
        return rc
    return _read_and_print_result(result_path)
```

6. В `run_enterprise(...)` удалить строки:

```python
        print("✅ Прогон тестов завершён (сеанс 1С закрыт).")
        print("   Результаты смотри там, куда их пишет обработчик тестов в конфигурации.")
```

и оставить только `print("✅ Прогон тестов завершён (сеанс 1С закрыт).")`:

```python
    if returncode == 0:
        print("✅ Прогон тестов завершён (сеанс 1С закрыт).")
    else:
        print("❌ Ошибка запуска предприятия")
    return returncode
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest app/tests/env/test_run_tests_cli.py -v`
Expected: все тесты PASS.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/tools/run-tests.py app/tests/env/test_run_tests_cli.py
git commit -m "feat(run-tests): сводка результата и коды 4/5"
```

---

### Task 2: `developer-tests.md` — смоук и `--test` выполняет автор тестов

**Files:**
- Modify: `template/.claude/agents/developer-tests.md`

**Interfaces:**
- Consumes: коды `run-tests.py` из Task 1 (`EXIT=4` — ожидаемый красный смоук).
- Produces: секция `TESTS.md` «Смоук» с полями, которые проверяет Task 3.

- [ ] **Step 1: Переписать блок «Повторно» (строки 17–30)**

Заменить:

```markdown
Повторно — когда оркестратор вернул этап `tests` в цикле: тест оказался **дефектным**
(в `TESTING.md` виновник — тест) или красный смоук нашёл дефект до разработки. Тогда:
1. Определи источник диагностики: при возврате со смоука — лог
   `logs/task#<id>/run-tests-smoke.log`; при возврате из `testing` — `TESTING.md` и
   `result.json`; при возврате из `review` — `REVIEW.md` и `result.json` последнего
   прогона `testing`. Текущий `TESTS.md` — файл без суффикса; предыдущая версия —
   `TESTS.<n>.md`.
2. Почини тест-модуль в `src/cfe/ЮнитТесты`, не ослабляя проверку ради сокрытия
   реального бага кода; при необходимости обнови `TESTS.md`. Сам прогон не запускай —
   его повторит оркестратор (смоук или `testing`). Прикладной код не правь — это зона
   разработчика.
3. Если тебя продолжили через SendMessage — не перечитывай всю задачу заново:
   прочитай текущие `TESTS.md` (без суффикса), источник диагностики по шагу 1 и правь
   только тест-модуль.
```

на:

```markdown
Повторно — когда оркестратор вернул этап `tests` в цикле: тест оказался **дефектным**
(в `TESTING.md` виновник — тест) или красный смоук нашёл дефект до разработки. Тогда:
1. Определи источник диагностики: `TESTING.md`/`REVIEW.md` и `result.json` последнего
   прогона. Текущий `TESTS.md` — файл без суффикса; предыдущая версия — `TESTS.<n>.md`.
2. Почини тест-модуль в `src/cfe/ЮнитТесты`, не ослабляя проверку ради сокрытия
   реального бага кода; при необходимости обнови `TESTS.md`. После правки выполни
   отладочный прогон `--test` по упавшим сценариям, затем полный набор (смоук) и
   обнови секцию «Смоук» в `TESTS.md`. Полный прогон этапа `testing` делает
   оркестратор. Прикладной код не правь — это зона разработчика.
3. Если тебя продолжили через SendMessage — не перечитывай всю задачу заново:
   прочитай текущие `TESTS.md` (без суффикса), источник диагностики по шагу 1 и правь
   только тест-модуль.
```

- [ ] **Step 2: Переписать пункт 5 «Порядок действий» (строки 91–106)**

Заменить абзац, начинающийся с `5. Тесты должны быть «красными» по построению:`,
целиком (до `6. Запиши **конфиг запуска тестов**`) на:

```markdown
5. Тесты должны быть «красными» по построению: проверяемого поведения ещё нет, поэтому
   каждый тест обязан реально что-то утверждать и падать до реализации. Если тест
   пройдёт на пустом коде — он ничего не проверяет, переделай его. Сам красный смоук
   выполняешь ты (раздел «Запуск тестов (Red) — выполняешь сам»): загружаешь расширение,
   запускаешь полный набор и добиваешься корректного красного результата. Полный прогон
   на этапе `testing` после реализации ведёт оркестратор.
   Критерии смоука: нет ошибок компиляции тест-модуля и setup-исключений; ни один тест
   не зелёный до реализации; красные падают по утверждению (expected/actual) или по
   ожидаемому отсутствию ещё не написанной функциональности; проверяемый вызов не
   обёрнут в `Попытка` (исключение должно доходить до раннера, кроме сценария с
   ожидаемым отказом). Тест, который проверяет ожидаемое значение (например,
   `СтоимостьРасход = 300`), на пустом коде красный: 0/`NULL` не равно 300; зелёным до
   реализации может быть только тест, сравнивающий состояние до/после («не
   изменилось»), — его нужно усилить.
```

- [ ] **Step 3: Переписать пункт 7 и добавить секцию смоука**

Заменить пункт 7:

```markdown
7. Зафиксируй в `TESTS.md`: имя тест-модуля (значение `ИмяМодуля`), путь к конфигу
   запуска `configs/task#<id>/test.json` и то, что прогон ожидается «красным».
   Оркестратор возьмёт эти данные для красного смоука после этапа `tests` и полного
   прогона на этапе `testing`.
```

на:

````markdown
7. Зафиксируй в `TESTS.md`: имя тест-модуля (значение `ИмяМодуля`), путь к конфигу
   запуска `configs/task#<id>/test.json`, общее число сценариев полного набора и
   секцию «Смоук» с доказательствами (см. раздел «Запуск тестов (Red) — выполняешь
   сам»). Оркестратор проверит эти данные перед закрытием этапа `tests`.

## Запуск тестов (Red) — выполняешь сам

Смоук и отладочные прогоны — твоя работа. Оркестратор проверяет доказательства и
запускает полный прогон этапа `testing` после реализации.

### Полный набор (смоук)

После записи `TESTS.md` и `configs/task#<id>/test.json` выполни в одном вызове Bash
(таймаут не меньше 300 000 мс):

```bash
python .claude/skills/1c-batch/scripts/1c-batch.py load-extension \
    src/cfe/ЮнитТесты --name ЮнитТесты \
    > logs/task#<id>/load-extension-tests.log 2>&1
python .claude/tools/run-tests.py configs/task#<id>/test.json --timeout 120 \
    > logs/task#<id>/run-tests-smoke.log 2>&1
rc=$?; echo "EXIT=$rc" >> logs/task#<id>/run-tests-smoke.log
tail -80 logs/task#<id>/run-tests-smoke.log
```

На смоуке ожидаемый код — `EXIT=4` (прогон состоялся, все тесты красные). `EXIT=2`
(ошибка компиляции), `EXIT=5` (нет результата) и `1/3/124` — дефекты, чини до `4`.

### Отладочный прогон одного сценария

```bash
python .claude/tools/run-tests.py configs/task#<id>/test.json \
    --test <ИмяСценария> --timeout 90 \
    > logs/task#<id>/run-tests-debug.log 2>&1
rc=$?; echo "EXIT=$rc" >> logs/task#<id>/run-tests-debug.log
tail -80 logs/task#<id>/run-tests-debug.log
```

`--test` перезаписывает `result.json` подмножеством. Итоговое доказательство смоука —
только **последний полный** прогон в `run-tests-smoke.log`; после отладки запусти
полный набор заново последним.

### Критерии смоука

- компиляция расширения без ошибок, setup-исключений нет;
- ни один тест не зелёный до реализации;
- красные падают по утверждению (expected/actual) или по ожидаемому отсутствию
  функциональности;
- проверяемый вызов не обёрнут в `Попытка` (кроме сценария ожидаемого отказа);
- тест, сравнивающий состояние до/после («не изменилось»), до реализации зелёный быть
  не может — усилить.

Лимит — 2–3 цикла «правка → смоук». Параллельно с полным прогоном оркестратора
(`testing`) тесты не запускай.

### Секция «Смоук» в `TESTS.md`

Запиши: дату/время, пути `load-extension-tests.log` и `run-tests-smoke.log`, `EXIT`,
`Выполнено`, `ОписаниеОшибки`, общее число сценариев полного набора, подтверждение что
все `Результат=false` и красные падают по утверждению.
````

- [ ] **Step 4: Убрать упоминание `ЗаписиЖР` и добавить правило про запросы**

1. В пункте 3 «Порядок действий» заменить фрагмент:

```markdown
   значений при разборе падений (они видны в журнале регистрации ИБ). **Учти:** в
   `result.json` попадают только `Имя`, `Результат`, `ОписаниеОшибки`; поля `ЗаписиЖР`
   там нет. Поэтому **не перехватывай исключение только ради записи в ЖР**: раннер сам
   ловит исключение сценария и сохраняет его текст в `ОписаниеОшибки` — это и есть
   основной канал диагностики.
```

на:

```markdown
   значений при разборе падений (они видны в журнале регистрации ИБ). **Учти:** в
   `result.json` попадают только `Имя`, `Результат`, `ОписаниеОшибки`; отладочных
   записей журнала регистрации в нём нет. Поэтому **не перехватывай исключение только
   ради записи в ЖР**: раннер сам ловит исключение сценария и сохраняет его текст в
   `ОписаниеОшибки` — это и есть основной канал диагностики.
```

2. После пункта 6 (`Не ослабляй проверки...`) добавить пункт 7:

```markdown
7. **Запросы в тест-модуле проверяй `query-analyze`.** Каждый написанный/изменённый
   текст запроса (включая запросы хелперов) прогони навыком `query-analyze` и
   `validate_query` по литералу ровно в том виде, как он записан в исходнике. Заглушки
   `!...!`, `%1`, `{0}` в тексте запроса запрещены; подстановка — только в валидные
   места (`&ОсобыйПараметр`, `1 = 1`). Результат зафиксируй в отчёте `TESTS.md`.
```

- [ ] **Step 5: Обновить «Выход»**

Заменить:

```markdown
Файл `TESTS.md` в каталоге задачи: созданные тесты, имя тест-модуля, путь к конфигу
запуска `configs/task#<id>/test.json` и список изменённых файлов. Сам конфиг запуска
(`configs/task#<id>/test.json`) тоже создаёшь ты.
```

на:

```markdown
Файл `TESTS.md` в каталоге задачи: созданные тесты, имя тест-модуля, путь к конфигу
запуска `configs/task#<id>/test.json`, список изменённых файлов, общее число сценариев
и секция «Смоук» с доказательствами (пути логов, `EXIT`, все ли тесты красные по
утверждению). Сам конфиг запуска (`configs/task#<id>/test.json`) тоже создаёшь ты.
```

- [ ] **Step 6: Проверить, что старые формулировки удалены**

Run: `grep -R "сам прогон.*не запускай\|оркестратор пришлёт лог" template/.claude/agents/developer-tests.md`
Expected: пусто.

Run: `grep -n "Запуск тестов (Red) — выполняешь сам\|Секция «Смоук»\|run-tests-smoke.log" template/.claude/agents/developer-tests.md`
Expected: строки с новыми заголовками и путями есть.

- [ ] **Step 7: Коммит**

```bash
git add template/.claude/agents/developer-tests.md
git commit -m "docs(agents): developer-tests сам выполняет красный смоук"
```

---

### Task 3: Оркестрация — проверка доказательств смоука и чистый пре-флайт

**Files:**
- Modify: `template/.claude/skills/task-orchestration/SKILL.md`
- Modify: `template/.claude/rules/cyclic-review-workflow.md`
- Modify: `template/.claude/rules/run-unit-tests.md`

**Interfaces:**
- Consumes: секция «Смоук» в `TESTS.md` (Task 2); коды `4/5` (Task 1).
- Produces: контракт «смоук у автора тестов, оркестратор проверяет доказательства».

- [ ] **Step 1: Заменить раздел «Долгие фоновые операции»**

Заменить первый абзац (строки 85–93) на:

```markdown
## Долгие фоновые операции без расхода токенов
Загрузка конфигурации в ИБ и полный прогон тестов на этапе `testing` — долгие операции.
Их ведёт **оркестратор** (главный цикл), а не субагент: субагент не умеет «проснуться»
по завершении фонового процесса и просто жёг бы токены в ожидании. Смоук и отладочные
прогоны выполняет `developer-tests` синхронно в своём ходе — это не фоновые операции
оркестратора; параллельно с этапом `testing` тесты не запускаются. Правило для
оркестратора:
- запускай операцию **в фоне** с перенаправлением всего вывода в лог-файл в каталоге
  `logs/task#<id>/`;
- **не опрашивай** процесс в цикле — харнесс сам разбудит оркестратора по завершении
  процесса;
- проснувшись, прочитай лог/результат из `logs/task#<id>/` и прими решение.
```

- [ ] **Step 2: Заменить раздел о красном смоуке**

Заменить весь раздел от `## Красный смоук после этапа `tests` (ведёт оркестратор)` до
строки перед `## Загрузка в базу после этапа `develop` (флаг `update_db`)` на:

````markdown
## Красный смоук после этапа `tests` (выполняет developer-tests; оркестратор проверяет)
Смоук — часть завершения этапа `tests`, до `develop`. Он ловит ошибки компиляции
тест-модуля, ошибки setup и зелёные тесты до реализации. Загрузку расширения и прогон
выполняет автор тестов (`developer-tests`) — у него есть Bash и `run-tests.py --test`
для локальной итерации. Оркестратор проверяет доказательства.

1. После того как автор тестов записал `TESTS.md` (с секцией «Смоук») и
   `configs/task#<id>/test.json`, **не закрывай этап `tests`** — он остаётся `running`.
2. Проверь доказательства смоука:
   - `TESTS.md` содержит секцию «Смоук» с общим числом сценариев;
   - `logs/task#<id>/run-tests-smoke.log` и `result.json` (`ИмяФайлаЛог` из конфига)
     существуют, и их mtime позже mtime тест-модуля `src/cfe/ЮнитТесты`;
   - в логе `EXIT=4` (прогон состоялся, тесты красные — на смоуке это норма), нет
     `EXIT=2`; в `result.json` `Выполнено = true`, `ОписаниеОшибки = null`, число
     тестов равно числу сценариев из секции «Смоук», у каждого теста `Результат = false`.
3. Если доказательства отсутствуют/противоречивы — один контрольный прогон в фоне
   (см. «Долгие фоновые операции»):
   ```bash
   python .claude/skills/1c-batch/scripts/1c-batch.py load-extension src/cfe/ЮнитТесты --name ЮнитТесты > logs/task#<id>/load-extension-tests.log 2>&1
   ( python .claude/tools/run-tests.py configs/task#<id>/test.json --timeout 120 > logs/task#<id>/run-tests-smoke.log 2>&1; echo "EXIT=$?" >> logs/task#<id>/run-tests-smoke.log )
   ```
   Не подтвердился — вернуть `tests` в `pending` с логом.
4. Критерии корректного красного (те же, что у автора тестов): нет ошибок
   компиляции/setup; ни один тест не зелёный; красные падают по утверждению или по
   ожидаемому отсутствию функциональности; проверяемый вызов не обёрнут в `Попытка`.
5. Смоук подтверждён — `task_status.py ... tests done --files <изменённые>`, дальше
   `develop`.

Особые случаи:
- ошибка компиляции в `ЮнитТесты` — дефект теста: верни `tests` в `pending`, автор
  чинит и повторяет смоук сам;
- ошибка компиляции в `src/cf` — дефект baseline, тест-модуль не виноват: зафиксируй
  лог, закрой `tests` и передай лог разработчику на `develop`; после `develop` смоук
  повторится в рамках `testing`;
- зелёный тест до реализации — дефект теста: верни `tests` в `pending`.

> Возврат `tests` из `review` также завершается красным смоуком автором тестов до
> `tests done`, независимо от того, включён ли `testing`.
````

- [ ] **Step 3: Уточнить исключение для `tests` в общем разделе**

В разделе «Для каждого этапа» строку:

```markdown
   **Исключение — `tests`:** этап закрывается `done` только после прохождения красного
   смоука (см. «Красный смоук после этапа `tests`»).
```

заменить на:

```markdown
   **Исключение — `tests`:** этап закрывается `done` только после подтверждения
   доказательств красного смоука (см. «Красный смоук после этапа `tests`»).
```

- [ ] **Step 4: Заменить шаг 1 пре-флайта перед загрузкой в ИБ**

Заменить:

```markdown
1. Разработчик закончил; убедись, что артефакт `DEVELOP.md` на месте, метаданные
   валидны, статический анализ чист. Этап `develop` — по-прежнему `running`.
```

на:

```markdown
1. Разработчик закончил. Проверь только:
   - `DEVELOP.md` существует;
   - перечисленные в нём изменённые файлы совпадают с `git status --short`.
   Не перечитывай код, не перезапускай `bsl_ls`/`code-analyze`/`meta-validate` и не
   изучай дифф: это зона `developer` и `reviewer`. Расхождение списка файлов — возврат
   на `develop`. Этап `develop` — по-прежнему `running`.
```

- [ ] **Step 5: Обновить коды и диагностику этапа `testing`**

В шаге 4 после блока про `124` добавить:

```markdown
   - **`4` — тесты выполнены, но есть проваленные** (сводка `run-tests.py` и
     `result.json` актуальны). Читай `result.json` по шагу 5.
   - **`5` — файла результата нет/он невалиден**: прогон не дошёл до записи. Не
     перезапускай вслепую; проверь лог и `ИмяФайлаЛог` в конфиге.
```

Заменить шаг 5:

```markdown
5. Проснувшись, прочитай `logs/task#<id>/result.json`. Тесты пройдены, **только если**:
   `Выполнено` = `true`, `ОписаниеОшибки` = `null`, и у **каждого** теста
   `Результат` = `true`. Разбор падений — по полям теста и `ЗаписиЖР` (отладочные записи
   журнала регистрации из тестов).
```

на:

```markdown
5. Проснувшись, прочитай `logs/task#<id>/result.json` и сводку `ИТОГ:` из
   `run-tests.log`. Тесты пройдены, **только если**: `Выполнено` = `true`,
   `ОписаниеОшибки` = `null`, и у **каждого** теста `Результат` = `true`. Причину
   падения ищи в `ОписаниеОшибки` теста; при необходимости — в журнале регистрации ИБ.
```

В шаге 8 фразу:

```markdown
     После правки теста сначала повтори красный смоук (см. «Красный смоук после этапа
     `tests`»), затем `testing`.
```

заменить на:

```markdown
     После правки теста автор тестов сам повторяет красный смоук и обновляет
     `TESTS.md`; оркестратор проверяет доказательства, затем `testing`.
```

- [ ] **Step 6: Дополнить re-brief SendMessage**

В разделе «Продолжение субагента (SendMessage)», в цитате re-brief после строки
`> что прочитал, что изменил, какие проверки выполнил.` добавить:

```markdown
   > Если этап `tests` — после правки выполни красный смоук сам (`run-tests.py`,
   > полный набор), обнови секцию «Смоук» в `TESTS.md` и приложи пути логов.
```

(вставка идёт внутри той же цитаты перед закрывающим абзацем).

- [ ] **Step 7: Обновить правило `cyclic-review-workflow`**

Заменить строки 20–21:

```markdown
- Если review вернул `tests`, после правки тестов обязателен красный смоук до перевода
  `tests` в `done` — независимо от того, включён ли `testing`.
```

на:

```markdown
- Если review вернул `tests`, после правки тестов автор тестов сам выполняет красный
  смоук и фиксирует доказательства в `TESTS.md`; оркестратор проверяет их до перевода
  `tests` в `done` — независимо от того, включён ли `testing`.
```

- [ ] **Step 8: Обновить правило `run-unit-tests`**

1. В абзаце «Детали ролей…» заменить:

```markdown
Детали ролей — в `.claude/agents/developer-tests.md` (пишет тесты и конфиг запуска,
фаза Red) и навыке `task-orchestration` (оркестратор запускает прогон и выносит вердикт
в `TESTING.md` на этапе `testing`). Это авторитетный источник.
```

на:

```markdown
Детали ролей — в `.claude/agents/developer-tests.md` (пишет тесты и конфиг запуска,
сам выполняет красный смоук и отладочные прогоны) и навыке `task-orchestration`
(оркестратор проверяет доказательства смоука, запускает полный прогон этапа `testing`
и выносит вердикт в `TESTING.md`). Это авторитетный источник.
```

2. После блока про `--test` добавить:

```markdown
На красном смоуке ожидаемый код возврата — `4` (прогон состоялся, все тесты красные;
зелёных до реализации быть не должно). `0` на смоуке означает, что тесты не проверяют
новое поведение.
```

3. Таблицу кодов заменить на:

```markdown
| Код | Значение |
|-----|----------|
| `0` | все тесты пройдены, результат свежий |
| `1` | ошибка запуска (нет конфига, нет wrapper 1c-batch) |
| `2` | ошибка компиляции модулей (предприятие не запускалось; после таймаута — ошибка найдена в основной конфигурации) |
| `3` | ошибка среды/лицензии при проверке модулей |
| `4` | прогон состоялся, но есть проваленные тесты / `Выполнено=false` / `ОписаниеОшибки≠null` |
| `5` | `result.json` не найден, невалиден или список тестов пуст |
| `124` | таймаут сеанса предприятия (ошибок компиляции основной конфигурации нет) |
```

4. В разделе «Результат» заменить:

```markdown
`Сообщить(...)` в пакетном режиме в stdout НЕ попадает — результаты пишет сам
раннер в файл `ИмяФайлаЛог` (JSON). Читай его. Тесты пройдены, **только если**:
`Выполнено = true`, `ОписаниеОшибки = null`, и у **каждого** теста `Результат = true`.
```

на:

```markdown
`Сообщить(...)` в пакетном режиме в stdout НЕ попадает — результаты пишет сам
раннер в файл `ИмяФайлаЛог` (JSON). Старый файл перед прогоном удаляется, поэтому
после прогона любой существующий `result.json` — свежий. `run-tests.py` печатает
сводку (`Выполнено`, `ОписаниеОшибки`, `✓/✗` по тестам, `ИТОГ: N/M пройдено`) и
возвращает `0/4/5` (см. таблицу кодов). Тесты пройдены, **только если**:
`Выполнено = true`, `ОписаниеОшибки = null`, и у **каждого** теста `Результат = true`.
```

- [ ] **Step 9: Проверки и коммит**

Run: `grep -R "ЗаписиЖР" template/.claude`
Expected: пусто.

Run: `grep -n "смоук выполняет\|выполняет developer-tests\|EXIT=4" template/.claude/skills/task-orchestration/SKILL.md`
Expected: строки нового раздела есть.

Run: `.venv/bin/python -m pytest app/tests/env/test_content_files.py -q`
Expected: PASS (структура файлов не сломана).

```bash
git add template/.claude/skills/task-orchestration/SKILL.md template/.claude/rules/cyclic-review-workflow.md template/.claude/rules/run-unit-tests.md
git commit -m "docs(orchestration): смоук у developer-tests, чистый пре-флайт, коды 4/5"
```

---

### Task 4: Валидация запросов — «литерал как записан»

**Files:**
- Modify: `template/.claude/skills/query-analyze/SKILL.md`
- Modify: `template/.claude/skills/query-review/SKILL.md`
- Modify: `template/.claude/agents/developer.md`
- Modify: `template/.claude/agents/reviewer.md`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: единое правило для всех агентов; обязательный `query-analyze` в developer/developer-tests/reviewer.

- [ ] **Step 1: Дополнить `query-analyze`**

В разделе «Приоритетная проверка: `validate_query`» после пункта 3 и перед абзацем
`**Ограничение `validate_query`:**` вставить пункт 4:

```markdown
4. Валидируется **каждый литерал запроса ровно в том виде, как он записан в
   исходнике** (литерал целиком, каждая часть конкатенации). Подстановка допустима
   только в места, где исходный текст остаётся валидным запросом: параметры вида
   `&ОсобыйПараметр`, нейтральные подстроки `1 = 1`, `2 = 2`; в коде —
   `СтрЗаменить(ТекстЗапроса, "&ОсобыйПараметр", "<фрагмент>")`. Произвольные
   заглушки (`!НАПРАВЛЕНИЕСОРТИРОВКИ!`, `%1`, `{0}`) запрещены: текст с ними не
   проходит `validate_query` и не открывается конструктором. Проверка варианта после
   подстановки **не заменяет** проверку исходного литерала: невалидный литерал — это
   находка `query-not-parseable` (warning), а не «placeholder».
```

- [ ] **Step 2: Переписать пункт `query-review` о программной сборке**

Заменить пункт (строки 182–185):

```markdown
- [важная] Программная сборка запроса — собирать текст запроса из частей конкатенацией или подставлять/менять куски через `СтрЗаменить` разрешается, только если доступен `validate_query` (MCP `1c-md`) и выполнено одно из условий:
  - при конкатенации — **каждая часть** является самостоятельным текстом запроса и проходит `validate_query`;
  - при `СтрЗаменить` — осевой (исходный) текст запроса проходит `validate_query`, а заменяются только параметры вида `&ОсобыйПараметр` или подстроки-заглушки (`"1 = 1"`, `"2 = 2"` и т.п.).
  Если `validate_query` недоступен или хотя бы одна часть / осевой текст не проходят проверку — это находка **важная** (блокирует приёмку).
```

на:

```markdown
- [важная] Программная сборка запроса — собирать текст запроса из частей конкатенацией или подставлять/менять куски через `СтрЗаменить` разрешается, только если доступен `validate_query` (MCP `1c-md`) и выполнено всё перечисленное:
  - **исходный текст запроса (ровно как записан в исходнике, литерал целиком) проходит `validate_query`** — до подстановки;
  - заменяются только места, где исходный текст остаётся валидным запросом: параметры вида `&ОсобыйПараметр` или нейтральные подстроки (`"1 = 1"`, `"2 = 2"` и т.п.); в коде — `СтрЗаменить(ТекстЗапроса, "&ОсобыйПараметр", "<фрагмент>")`;
  - при конкатенации **каждая часть** является самостоятельным текстом запроса и проходит `validate_query`.
  Произвольные заглушки (`!НАПРАВЛЕНИЕСОРТИРОВКИ!`, `%1`, `{0}`) запрещены: текст с ними не проходит `validate_query` и не открывается конструктором. Если направление/режим нельзя выразить параметром — используй два статических текста. Проверка варианта после подстановки не заменяет проверку исходного литерала. Если `validate_query` недоступен или хотя бы одна часть / исходный литерал не проходят проверку — это находка **важная** (блокирует приёмку).
```

- [ ] **Step 3: Обновить `developer.md`**

1. Заменить абзац «**Запросы**» (строки 28–33) на:

```markdown
   **Запросы** — пишу по чеклисту `query-review` (индексы; `ЕСТЬNULL` при левом
   соединении с остатками; статический текст обязан открываться конструктором;
   исходный текст запроса ровно как записан обязан проходить `validate_query`;
   подстановка через `СтрЗаменить` — только в валидные места (`&ОсобыйПараметр`,
   `1 = 1`), заглушки `!...!`/`%1`/`{0}` запрещены; запрос к табличной части документа
   напрямую вместо выгрузки её в таблицу значений) и переиспользую готовые функции
   БСП вместо ручных реализаций (`bsp-reuse`). Навыки доступны через инструмент Skill.
```

2. Заменить пункт 3 (строки 40–42) на:

```markdown
3. После правок прогоняю статический анализ (правило verify-with-syntax-checker);
   по изменённым модулям прогоняю `code-analyze`, а по **каждому** написанному или
   изменённому тексту запроса — навык `query-analyze` и `validate_query` по литералу
   ровно в том виде, как он записан в исходнике. Находки устраняю до передачи на ревью;
   результат проверки фиксирую в `DEVELOP.md`.
```

3. Заменить пункт 1 «Упали тесты по вине кода» (строки 58–61) на:

```markdown
1. Прочитай лог прогона `logs/task#<id>/result.json` (абсолютный путь задан в конфиге
   `configs/task#<id>/test.json`) и сводку `ИТОГ:` из `run-tests.log`. Там: `Выполнено`,
   `ОписаниеОшибки`, по каждому тесту `Результат` и `ОписаниеОшибки`. При необходимости
   смотри журнал регистрации ИБ.
```

- [ ] **Step 4: Обновить `reviewer.md`**

1. В таблицу «Рационализация | Реальность» после строки про `ЛЕВОЕ соединение с
   ЕСТЬNULL` добавить:

```markdown
| «Текст с заглушкой не разбирается, а после подстановки валиден» | Это находка `query-not-parseable` (важная): проверяется литерал ровно как записан. Замена произвольной заглушки на ключевое слово не делает исходный запрос валидным. |
```

2. Заменить пункт 4 (строки 110–111) на:

```markdown
4. **Автоматические проверки запросов `query-analyze`** — навык `query-analyze` по
   изменённым текстам запросов. Для каждого литерала запроса **сам, независимо**
   проверяю `validate_query` ровно в том виде, как он записан в исходнике (включая
   заглушки и каждую часть конкатенации). Вариант после подстановки не заменяет эту
   проверку; невалидный литерал — находка, даже если подставленный вариант валиден.
```

3. Заменить пункт 6 (строки 114–115) на:

```markdown
6. **Ручной чеклист запросов `query-review`** — ручная проверка запросов (индексы
   БД, метаданные, семантика задачи), включая правило «литерал как записан».
```

- [ ] **Step 5: Проверки и коммит**

Run: `grep -n "литерал как записан" template/.claude/skills/query-review/SKILL.md template/.claude/agents/reviewer.md template/.claude/agents/developer.md`
Expected: совпадения в трёх файлах.

Run: `grep -n "!НАПРАВЛЕНИЕСОРТИРОВКИ!" template/.claude/skills/query-analyze/SKILL.md template/.claude/skills/query-review/SKILL.md`
Expected: антипример есть в обоих навыках.

Run: `grep -R "ЗаписиЖР" template/.claude/agents/developer.md`
Expected: пусто.

Run: `.venv/bin/python -m pytest app/tests/env/test_content_files.py -q`
Expected: PASS.

```bash
git add template/.claude/skills/query-analyze/SKILL.md template/.claude/skills/query-review/SKILL.md template/.claude/agents/developer.md template/.claude/agents/reviewer.md
git commit -m "docs(query): validate_query по литералу как записан"
```

---

### Task 5: `code_index` — `[[cache_targets]]` и признаки протухания

**Files:**
- Modify: `app/src/agentmon/env/mcp_docker_recipes.py`
- Modify: `app/src/agentmon/env/code_index_local.py`
- Modify: `template/.claude/skills/mcp-usage/SKILL.md`
- Test: `app/tests/env/test_mcp_docker_recipes.py`
- Test: `app/tests/env/test_code_index_local.py`

**Interfaces:**
- Produces: `_daemon_toml(alias: str, path: str, cache_target_url: str | None = None) -> str` — при заданном URL добавляет секцию `[[cache_targets]] url = "<url>"`.
- Produces: `daemon.toml` из docker/local деплоя содержит URL serve.

- [ ] **Step 1: Добавить/обновить тесты**

В `app/tests/env/test_mcp_docker_recipes.py`:

1. В тесте `test_code_index_requires_catalog_dir` (в нём вызывается
   `R.launch_params("code-index", port=8004, ...)` и читается `daemon`), после
   проверки `alias` добавить:

```python
    assert "[[cache_targets]]" in text
    assert 'url = "http://127.0.0.1:8004"' in text
```

2. Заменить тест `test_daemon_toml_interpolates_alias_and_path` и добавить новый:

```python
def test_daemon_toml_interpolates_alias_and_path():
    text = R._daemon_toml("мой-алиас", "/custom/code/path")
    assert 'alias = "мой-алиас"' in text
    assert 'path = "/custom/code/path"' in text
    # дефолтный /repos/src не должен появляться, если его не передали
    assert "/repos/src" not in text
    # без URL инвалидация не настраивается
    assert "[[cache_targets]]" not in text


def test_daemon_toml_has_cache_target_when_url_given():
    text = R._daemon_toml("мой-алиас", "/custom/code/path",
                          "http://127.0.0.1:8004")
    assert "[[cache_targets]]" in text
    assert 'url = "http://127.0.0.1:8004"' in text
```

В `app/tests/env/test_code_index_local.py` после проверки `path` добавить:

```python
    assert "[[cache_targets]]" in daemon
    assert 'url = "http://127.0.0.1:8005"' in daemon
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_code_index_local.py -q`
Expected: FAIL — `[[cache_targets]]` отсутствует / `_daemon_toml` не принимает третий аргумент.

- [ ] **Step 3: Реализовать генератор**

В `app/src/agentmon/env/mcp_docker_recipes.py` заменить `_daemon_toml` на:

```python
def _daemon_toml(alias: str, path: str, cache_target_url: str | None = None) -> str:
    """Текст daemon.toml для code-index: alias репозитория = имя проекта,
    path — каталог кодовой базы (в контейнере `/repos/src`, локально — реальный
    путь на хосте). alias и `repo="..."` в подсказках агенту совпадают.
    cache_target_url — URL serve, которому демон шлёт инвалидацию кэша."""
    cache = ""
    if cache_target_url:
        cache = f'\n[[cache_targets]]\nurl = "{cache_target_url}"\n'
    return f"""# Сгенерировано автоматически при развёртывании code-index.
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"
{cache}
[[paths]]
path = "{path}"
alias = "{alias}"
language = "bsl"
"""
```

В `launch_params(...)` заменить вызов записи `daemon.toml`:

```python
        (sp / "daemon.toml").write_text(
            _daemon_toml(project_name, "/repos/src",
                         f"http://127.0.0.1:{port}"),
            encoding="utf-8")
```

В `app/src/agentmon/env/code_index_local.py` заменить вызов:

```python
    toml_path.write_text(
        _daemon_toml(project_name, catalog_dir, f"http://127.0.0.1:{port}"),
        encoding="utf-8")
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_code_index_local.py -q`
Expected: PASS.

- [ ] **Step 5: Дополнить `mcp-usage`**

В `template/.claude/skills/mcp-usage/SKILL.md`, раздел `### 0. Обязательная преамбула`,
после пункта про `health` добавить:

```markdown
- **Свежесть индекса.** После сохранения файла индекс обновляется за ~2–5 с
  (debounce 1.5 с + batch 2 с). Пока идёт переиндексация, инструмент может вернуть
  `{"status": "indexing"}` — повтори через пару секунд.
```

В разделе `### 2. Точное имя известно → навигация и тела`, после пункта про
`read_file`/`stat_file`, добавить:

```markdown
- **Признак протухшего `read_file`.** Если содержимое не сходится по `file_size`/
  `lines_total` со `stat_file` или выглядит как прошлая версия — это устаревший кэш
  `serve`. Не делай вывод «модуль пуст»: возьми `get_file_summary`/`get_function`
  (структурированные данные индекса) и повтори `read_file` через несколько секунд.
  Если расхождение держится больше минуты — сообщи об ошибке окружения (кэш `serve`
  не инвалидируется).
```

- [ ] **Step 6: Проверки и коммит**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_code_index_local.py app/tests/env/test_content_files.py -q`
Expected: PASS.

Run: `grep -n "cache_targets" app/src/agentmon/env/mcp_docker_recipes.py app/src/agentmon/env/code_index_local.py app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_code_index_local.py`
Expected: совпадения в генераторе, локальном деплое и обоих тестах.

```bash
git add app/src/agentmon/env/mcp_docker_recipes.py app/src/agentmon/env/code_index_local.py template/.claude/skills/mcp-usage/SKILL.md app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_code_index_local.py
git commit -m "fix(code-index): cache_targets для инвалидации кэша serve"
```

---

### Task 6: Финальная проверка

**Files:**
- No new files (only verification; fix regressions if any).

- [ ] **Step 1: Прогнать целевые тесты**

Run: `.venv/bin/python -m pytest app/tests/env/test_run_tests_cli.py app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_code_index_local.py app/tests/env/test_content_files.py app/tests/env/test_agent_capabilities.py app/tests/env/test_artifact_names.py -q`
Expected: PASS.

- [ ] **Step 2: Прогнать полный набор**

Run: `.venv/bin/python -m pytest app/tests -q`
Expected: PASS (если есть известные падения, зафиксировать и не выдавать за успех).

- [ ] **Step 3: Проверить отсутствие старых формулировок**

Run:

```bash
grep -R "ЗаписиЖР" template/.claude || echo "OK: ЗаписиЖР отсутствует"
grep -R "сам прогон.*не запускай" template/.claude || echo "OK: запрет снят"
grep -R "Результаты смотри там, куда их пишет" template/.claude || echo "OK: старая подсказка удалена"
```

Expected: три строки `OK: ...`.

- [ ] **Step 4: Проверить согласованность контракта**

Run: `grep -n "EXIT=4" template/.claude/agents/developer-tests.md template/.claude/skills/task-orchestration/SKILL.md`
Expected: `EXIT=4` есть в обоих файлах.

Run: `grep -n "RC_TESTS_FAILED\|RC_NO_RESULT" template/.claude/tools/run-tests.py`
Expected: константы определены.

- [ ] **Step 5: Финальный коммит (если появились правки)**

Если предыдущие шаги не потребовали правок — коммит не нужен. Если потребовались:

```bash
git add <изменённые файлы>
git commit -m "test: финальная проверка конвейера task##002"
```

- [ ] **Step 6: Отчёт**

Записать в ответ: список коммитов (`git log --oneline -8`), результат полного
`pytest`, результаты grep-проверок. Отдельно указать, что `benchmark/tasks/task##002/TASK.md`
и `template/.bsl-language-server.json` не трогались.

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки:**
  - A (смоук у developer-tests) → Task 2, Task 3.
  - B (`run-tests.py` сводка/коды) → Task 1, Task 3.
  - C (валидация запросов, обязательный `query-analyze`) → Task 4, плюс пункт 7 в
    Task 2 для `developer-tests`.
  - D (`cache_targets`, mcp-usage) → Task 5.
  - E (проверка) → Task 6.
- **Плейсхолдеры:** нет шагов вида «добавить обработку ошибок» без кода — все правки
  содержат готовый текст/код.
- **Согласованность:** коды `4/5` определены в Task 1 и используются в Task 3;
  секция «Смоук» описана в Task 2 и проверяется в Task 3; `_daemon_toml` с третьим
  аргументом определён и вызывается в Task 5.
