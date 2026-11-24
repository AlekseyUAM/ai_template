---
name: run-unit-tests
description: Running 1C unit tests via run-enterprise with the /C ВыполнитьЗапускЮнитТестов parameter.
---

# Running unit tests

## Where the tests live (project framework)

Unit tests in the project are **common modules inside the `ЮнитТесты` extension**
(sources in `src/cfe/ЮнитТесты`), and NOT modules in the main configuration `src/cf`.
The extension runs the tests in the test database itself; its runner (`ЮТ_Тестирование*`)
is connected to the launch parameter `ВыполнитьЗапускЮнитТестов`.

- Add a new test module to `src/cfe/ЮнитТесты/CommonModules/` following the example of
  `ЮТ_ТестыПример`: the exported `Сценарии()` returns an array of test function names;
  each test function is exported and returns a `Структура` with `Результат` and
  `ОписаниеОшибки` (blank - `ЮТ_ТестированиеСервер.РезультатТеста()`). A bare `Булево`
  is an error: the runner writes `Тест вернул некорректный результат` and counts the test
  as failed.
- Do NOT invent a separate runner and do NOT put test modules in `src/cf` - this violates
  both the framework and the standard task constraint "we do not change extra objects".
- Load the test extension before the run:
  `python .claude/skills/1c-batch/scripts/1c-batch.py load-extension src/cfe/ЮнитТесты --name ЮнитТесты`.
- For the red smoke (tests stage), also refresh the main configuration in the IB - the
  changed modules or the whole `src/cf` via `1c-batch load-config`. The extension load
  alone does not remove an older implementation of the object under test; otherwise the
  red smoke can become falsely green and a real defect will not be caught.

Role details are in the `.claude/checklists/developer-tests.md` checklist (writes tests and
the launch config, runs the red smoke check and debug runs itself) and the
`single-agent-workflow` rule (the `testing` stage checks the smoke evidence, runs the
full set and issues the verdict in `TESTING.md`). This is the authoritative
source.

## How to run

A command like **"run the tests <config>"** is executed by the
`.claude/tools/run-tests.py` script:

```bash
python .claude/tools/run-tests.py configs/task#<id>/test.json
```

**`run-tests.py` is an exception to the "<=10 min" rule: the Bash tool timeout is
2 000 000 ms.** The script has three own budgets of 600 s each: extension check,
main configuration check and enterprise session (1800 s in total); the timeout of
2 000 000 ms leaves a margin so Bash does not kill the wrapper right at the 3x600 s boundary -
otherwise it will not print `rc 3` (environment/license or module check timeout), and
it becomes unclear whether this is the environment or a code defect. With a 600 000 ms timeout the wrapper dies even
earlier. Run the `run-tests.py` command itself - with side effects (loads, 1C processes) - in Bash, not under `Monitor`. In `claude -p` use Bash with a
timeout of 2 000 000 ms; `run_in_background` is forbidden. In an interactive session
`Monitor` serves only for waiting (do not run the script in it) - see
`single-agent-workflow`.

The config is **one per task**: `configs/task#<id>/test.json` (format sample -
`configs/test_example.json`):

```json
{
    "ИмяМодуля": "<ИмяТестМодуля из TESTS.md>",
    "ИмяФайлаЛог": "<абсолютный путь>/logs/task#<id>/result.json"
}
```

`ИмяМодуля` - the extension common module with `Сценарии()` (the name is fixed by `developer-tests`
in `TESTS.md`). `ИмяФайлаЛог` - an absolute path; create the `logs/task#<id>` directory in advance.
(`configs/test.json` is only the script default when no argument is given; for tasks use the
per-task config.)

For a debug run of a subset of scenarios pass `--test` - short scenario names
from `Сценарии()` separated by commas:

```bash
python .claude/tools/run-tests.py \
    configs/task#<id>/test.json --test СебестоимостьФИФО,ПроверкаСклада --timeout 90
```

The timeout for a debug run is set by the one who launches it - short (60-120 s) to quickly
localize a hang; a full run uses the normal timeout. If the filter finds nothing,
`result.json` contains `Выполнено=false` with the error text.

On the red smoke check the expected return code is `4` (the run happened, all tests are red;
there must be no green ones before implementation). `0` on the smoke check means the tests do not check
the new behavior.

The script starts the database (from `.1c-devbase.json`) in enterprise mode via
`1c-batch run-enterprise --wait -C "ВыполнитьЗапускЮнитТестов=<абсолютный путь к конфигу>"`.
A relative config path is converted to absolute; if the file is not found -
the run is not performed, if it is empty - a warning is printed. Cross-platform; requires
Python 3.6+ and a local copy of `1c-batch`.

### Preliminary compilation (mandatory)

Before starting the enterprise, the script compiles modules with the batch configurator in two
steps:

1. extension modules with tests -
   `1c-batch check-modules --thin-client --server --extension ЮнитТесты`;
2. modules of the **main configuration** -
   `1c-batch check-modules --thin-client --server` (without `--extension`).

Why: a compilation error in the enterprise is shown in a **modal window**, which makes the
session hang forever, while the executor waits synchronously - the task stalls without a
timeout. An error in the main configuration (`src/cf`, a module loaded at the development
stage) behaved the same way: it was caught only by diagnostics after a 600-second
enterprise hang. Now the main configuration precheck catches it in advance.
The Configurator writes errors to the log and exits with a code, without modal windows. On a
compilation error at any step the enterprise **is not started** - the script returns
`2` and prints the error text.

The module check itself is limited to **600 s** per process: a hung check (an environment that does not
respond) is killed by process tree, the script prints "проверка модулей
не уложилась в 600 c — проблема среды, не компиляции" and returns `3`. This is not a
compilation error - no need to fix the code, check the environment.

Parameters: `--extension ИМЯ` (extension with tests, default `ЮнитТесты`),
`--no-check` (skip both checks - debug only),
`--no-check-main` (skip only the main configuration check; the extension
is checked), `--no-cache` (do not use the module check success cache).

A successful module check is cached by the hash of the sources (`src/cf` or
`src/cfe/<extension>`) in `logs/.check-modules-cache/`; with unchanged files
the repeated check is not run (message `♻️ ... кэш`). This is safe:
the cache is invalidated by any change of `.bsl`/`.xml` in the checked directory. For the
main configuration smoke check use `--no-check-main`: it does not change at the
`tests` stage, while the extension is always checked.

The same `logs/.check-modules-cache/cf.json` is written by
`.claude/tools/check-modules.py` after the infobase load. The sources are already
loaded at that point, so `run-tests.py` reuses the result and does not compile the
main configuration a second time. Do not run `check-modules.py` before the load:
`/CheckModules` would check the previous configuration state.

### Session timeout

The enterprise is started with a timeout of `--timeout СЕК` (default `600`). After it expires
the script kills **only its own** process tree (the session itself and its `1cv8`); foreign 1C sessions
(other databases, the user's configurator) are not touched. Return on timeout - `124`.

On a timeout the script **additionally checks the main configuration modules**
(`check-modules` without `--extension`): the session could hang on a modal window of a module
compilation error loaded into the database at the development stage and not part of the extension
with tests. If such an error is found, `2` is returned (not `124`), the error text
is printed to the log. If the check itself did not fit into 600 s - `3` is returned
(environment problem, not code). If there are no errors - `124` remains, the timeout cause is different.

Diagnostics is also a module check, and its environment errors are not passed off as a session
timeout: if it did not start due to the environment/license or did not fit into 600 s,
the script returns `3` ("environment/license problem, not code"), not `124`. Code `124`
remains only for a real session timeout, when there is no compilation error and diagnostics
found no environment cause.

### Return codes

| Code | Meaning |
|-----|----------|
| `0` | all tests passed, result is fresh |
| `1` | launch error (no config, no 1c-batch wrapper) |
| `2` | compilation error of extension or main configuration modules (the enterprise was not started; after a timeout - an error was found in the main configuration) |
| `3` | environment/license or module check timeout (600 s) - not a compilation error; also during diagnostics after a session timeout: environment/license or timeout of the diagnostic check itself |
| `4` | the run happened, but there are failed tests / `Выполнено=false` / `ОписаниеОшибки≠null` |
| `5` | `result.json` not found, invalid or the test list is empty |
| `124` | enterprise session timeout without a compilation error and without an environment problem in diagnostics |

## Result

`Сообщить(...)` in batch mode does NOT go to stdout - the results are written by the
runner itself to the `ИмяФайлаЛог` file (JSON). The old file is deleted before the run, so
after the run any existing `result.json` is fresh. `run-tests.py` prints a
summary (`Выполнено`, `ОписаниеОшибки`, `✓/✗` per test, `ИТОГ: N/M пройдено`) and
returns `0/4/5` (see the code table). A test passed **only if**:
`Результат = true` **and** its `ОписаниеОшибки` is empty. A non-empty error with
`Результат = true` is a failure: the scenario reported an error but did not reset the
result. The whole run passed only if `Выполнено = true`, the top-level
`ОписаниеОшибки` is empty, and every test passed. On failure the script also prints
the first lines of `ЖурналРегистрацииВсеОшибки`; the full text is in `result.json`.

After reading the result the script saves a copy `result.<n>.json` next to
`result.json` (the next free number) - the run history is not lost on
`--test` and repeated smoke checks. The `result.json` itself remains the latest and is read
as usual.
