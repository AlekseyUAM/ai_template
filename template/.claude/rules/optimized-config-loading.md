---
name: optimized-config-loading
description: Partial infobase load of only changed configuration files; process log in logs/, synchronous run with timeout.
---

# Configuration load (partial)

The `.claude/tools/load-config-optimized.py` script loads into the IB **only the changed
configuration files** (`1c-batch load-config src/cf --list-file …`). Partial
load is the only mode: it correctly handles all four operations -
adding and removing an attribute, adding and removing an object - with the same
result as a full reload, but faster (the full `--full` mode was removed as
unnecessary). Cross-platform; requires Python 3.6+, git and a local copy of
`1c-batch` (wrapper `.claude/skills/1c-batch/scripts/1c-batch.py`).

The script takes changed files from `git diff` against `HEAD` over `src/cf` (plus
new untracked files) and builds the list for `-listFile`: the root file of each
changed object, the changed subfile itself (forms/templates/modules) and - for non-XML
or `Ext` files - all files of the object's `Ext` directory. The root alone is not enough:
with it the platform does not load the content of child objects, and for a **new** object
without the listed form/template files it fails with "Неизвестный объект метаданных".
If there are no changed files, the load is skipped.

## Incremental load (`--state`)

The orchestrator passes `--state logs/task#<id>/load-state.json` - a manifest of "what has
already been loaded successfully" (`путь → sha256`). Only files changed since the last
successful load are loaded from the diff. Unchanged metadata and `Configuration.xml`
do not get into the list - otherwise every task iteration after adding an object
would turn into a full reload (having `Configuration.xml` in `-listFile`
forces the platform to load the configuration in full).

- state is written only on success - return code `0` or "nothing to load"; on a
  load error **and on platform warnings without `--allow-warnings`**
  (code `2`, see below) the state is not changed, and the next run will take the same files;
- the hash snapshot is taken before the load starts: edits "during the load" go
  into the next run;
- no state file, broken JSON or a foreign version - the whole diff vs `HEAD`
  is loaded (a warning in the log);
- without `--state` - the previous behavior (whole diff vs `HEAD`);
- deleted parts of objects (modules, `Ext/`) are not deleted by a partial load - as
  before; previously loaded but vanished files are simply forgotten from the state.

## Transient infobase lock

A shared database (for example, `t_ssl2`) may be locked by a background job or
a foreign session: the platform responds "Ошибка исключительной блокировки
информационной базы". The script recognizes this marker and **retries the load itself**
after 30 and 60 seconds (up to three attempts), without requiring source edits. If the lock
remains after the retries - it is the environment, not a code defect: report the problem,
do not return the task to `develop`.

## Platform warnings: ignored properties

With incorrect sources (for example, information register dimension properties
copied into an accumulation register) the platform **silently ignores** part of the
metadata and finishes the load with code `0`. The script captures stdout+stderr of
`1c-batch load-config` (UTF-8, `errors="replace"`), prints them to the log and
parses the output with the `platform_warnings(text)` function -> `PlatformWarnings`
(`count`, `groups`, `other`). These markers are recognized:

- `Неверное свойство объекта метаданных` - grouped by
  `(вид объекта, свойство)` from "Свойство X не входит в состав объекта
  метаданных <Вид>";
- `facet` - only the word `facet` in platform phrasing
  (`facet фиксации …`, `facet перечисления …`, `facet движений …`);
  paths like `FacetGroups.xml` are not counted as a warning;
- `Исключение XDTO`;
- `Неверное значение перечисления`.

A line recognized as a property marker is not counted again in "other".
The script prints two summaries with separate counters: `⚠️ Платформа
проигнорировала N свойств (загрузка применена):` broken down by groups
(`- Dimension FillValue: 5` etc.) and, if there are other markers,
`⚠️ Прочие предупреждения платформы (M):` broken down by markers.

| Situation | Code | Success line | state |
|---|---|---|---|
| Warnings, **without** `--allow-warnings` | `2` | **no** | **not saved** |
| Warnings, with `--allow-warnings` | `0` | `✅ … (с предупреждениями, --allow-warnings)` | saved |
| Clean load | `0` | `✅ Оптимизированная загрузка завершена` | saved |
| Child process returned a non-zero code | child code | no | not saved |

Code `2` means "load applied, but the sources are incorrect": the platform
has already applied everything else, however the listed properties are lost. For the
executor this is a **stage error** (like a non-zero code), not success:
`db-update done` and `develop done` are not called, the task returns to
`develop` for fixing. **The success criterion is the absence of warnings.**
`--allow-warnings` is a deliberate choice only when the loss of these properties is
known and acceptable (for example, the property intentionally makes no sense in an object
of this kind).

## Who runs it and when

The load is run by the **executor** (in single-agent mode - you yourself) at the `develop` stage, only
if the `update_db` flag is on in `task.json` (see the `single-agent-workflow` rule).
Everything runs in the main thread.

## Synchronous run and process log

The executor starts the load **synchronously** (ordinary Bash without
`run_in_background`, tool `timeout` up to 600000 ms) with all output
redirected to the log. While the command runs, no tokens are spent; after it returns
the executor reads the log and the return code.

A background task is not acceptable here: in non-interactive mode `claude -p` (AgentMon,
benchmark) the turn ends (`end_turn`) and the harness kills the background process - the load
breaks off without a result.

```bash
# <id> — идентификатор задачи; каталог logs/task#<id> создать заранее
python .claude/tools/load-config-optimized.py --state logs/task#<id>/load-state.json > logs/task#<id>/load-config.log 2>&1
```

- **Where the log is:** `logs/task#<id>/load-config.log` (stdout+stderr of the script).
- **How to analyze:** after the command returns check the return code and
  the log content:
  - return code `0` and the line `✅ Оптимизированная загрузка завершена` - success
    (with `--allow-warnings` - suffix `(с предупреждениями, --allow-warnings)`);
  - the line `✅ Нет изменённых файлов конфигурации — загрузка не требуется` - there was
    nothing to load (also success).
    **Only after success** the executor closes the load and the stage:
    `task_status.py ... db-update done`, then `... develop done --files ...`.
  - return code `2` and the summary `⚠️ Платформа проигнорировала N свойств` or
    `⚠️ Прочие предупреждения платформы` without a success
    line - the sources are incorrect, the load was applied only partially: **error**,
    the task returns to `develop` (fix the properties or deliberately retry
    with `--allow-warnings`).
  - the line `❌ Ошибка при загрузке конфигурации` or any other non-zero return code -
    error.
    Loading into a "dirty" database is not allowed, so `db-update done` and `develop done`
    **are not called**: the executor **returns the task to the `develop` stage** (as when
    tests fail - the `cyclic-review-workflow` cycle): the developer reads this log and
    fixes the sources/metadata. With `update_db`, `task_status.py` will refuse to close
    `develop` without a completed load. The limit is 10 iterations; when it is exhausted
    `develop` is marked `failed`.
