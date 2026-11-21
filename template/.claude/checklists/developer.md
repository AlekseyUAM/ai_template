> **Stage checklist.** This is not a separate agent: you perform every item yourself
> in the main thread.

# Developer

You are a 1C developer. You implement BSL code so tests pass, following the standards.

## When applied
Stage "development" (code): after the analyst, architect and test developer. Documentation for the ready solution is written by a separate agent (`technical-writer`) at the "documentation" stage.

## Input
Use the task's existing artifacts: `ANALYZE.md` (specification), `ARCHITECT.md` (technical design), previously written tests. If some of them are absent (not all stages enabled) - rely on `TASK.md` (goal, plan, constraints) as the primary source.

## Steps

**Stage priority.** Working code first: module -> `check-modules` -> infobase load
(`db-update start`, `load-config-optimized.py`, `db-update done`) -> run
`run-tests.py` and bring tests to green -> `DEVELOP.md`.
Static analysis (`bsl_ls`, `query-analyze`, `code-analyze`) and `validate_query` - after
the load, one call per changed module and static query text.

> **Accumulation registers.** If you create an accumulation register, before the IB load
> check the registrars: documents with `RegisterRecords` and the register's `<Registrars>`.
> Without matched registrars the load fails ("Ни один из документов не
> является регистратором").

1. I search for existing code before writing new (rule search-before-write).
2. I write minimal BSL code per the standards (skill bsl-coding-standards).
   **Posting logic** - I implement per `ARCHITECT.md`: it already accounts for
   balance control, locks, boundary and point in time, movement deletion
   (metadata from `code_index`). I open the references on these topics pointwise,
   for a specific unclear question:
   - [balance control](../skills/bsl-coding-standards/reference/balance-control-methodology.md);
   - [locks](../skills/bsl-coding-standards/reference/locks.md);
   - [boundary and point in time](../skills/bsl-coding-standards/reference/boundary-and-moment.md);
   - [movement deletion](../skills/bsl-coding-standards/reference/movements-deletion.md).
   **Queries** - I write per the `query-review` checklist (indexes; `ЕСТЬNULL` on a left
   join with balances; static text must open in the Configurator;
   the source query text exactly as written must pass `validate_query`;
   substitution via `СтрЗаменить` - only into valid places (`&ОсобыйПараметр`,
   `1 = 1`), stubs `!...!`/`%1`/`{0}` are forbidden; a query to a document's tabular section
   directly instead of unloading it into a value table) and reuse ready BSP functions
   instead of manual implementations (`bsp-reuse`). Skills are available via the Skill tool.
   If the query uses `ИТОГИ`, remember: non-aggregated fields on total rows
   are returned as `NULL`.
   **New metadata and `validate_query`.** If the query references objects that
   are not yet in the IB (they were added in this task), `validate_query` before the load will return
   "Таблица не найдена". This is a deferred check: I record it in `DEVELOP.md` and
   proceed to the load; after the load I check the query.
   **`validate_query` result.** The response contains the `valid` field - it is authoritative:
   `valid: true` - the text is accepted; `valid: false` - a defect of the query text,
   I fix the text and check again until `valid: true`. In `DEVELOP.md` I record
   the actual result as the line `validate_query: valid` (or `deferred` for
   new objects).
   **`validate_query` call failure.** If the response has no `valid` field (transport,
   HTTP, server), I make one retry; then I record the tool failure
   in `DEVELOP.md` and continue. A syntax error (`valid: false`) is a
   query defect, not a tool failure.
   **Final files - in place.** Create and edit `src/cf/**/*.bsl` and `src/cfe/**`
   via `Write`/`Edit` at real paths. `tmp/` - for generated JSON and
   intermediate data; write the final version of the module directly into the target file.
   **DCS and reports** - before editing the schema/report read in full
   [DCS specifics](../skills/bsl-coding-standards/reference/skd-specifics.md) and the references
   [accumulation registers](../skills/bsl-coding-standards/reference/accumulation-registers.md),
   [information registers](../skills/bsl-coding-standards/reference/information-registers.md).
   Implement per the TS and these rules; before submitting, perform the checks from `skd-specifics.md`
   (`skd-validate -ExpectedFields`, `skd-info -Mode variant`).
3. After edits I run static analysis (rule verify-with-syntax-checker);
   before the call I compute the file's sha256 (`sha256sum <файл>` or
   `shasum -a 256 <файл>`) and pass it to `check`. Without `sha256` the tool
   will reject the call. I do not retype the module manually;
   for changed modules I run `code-analyze`; for static query text
   from the source - one `validate_query` call (substitution of the sort direction
   via `СтрЗаменить` into a valid place does not require a separate validation; for
   queries to new objects `validate_query` is deferred until the IB load).
   At 0 `bsl_ls` findings I proceed to the load; I eliminate findings before handing over to
   review; I record the result in `DEVELOP.md`.
   **Main configuration compilation check (mandatory).** Before submitting
   the stage I run the main configuration modules with the batch configurator - not in
   the background, `timeout: 600000` (10 min):
   ```bash
   python .claude/skills/1c-batch/scripts/1c-batch.py check-modules --thin-client --server
   ```
   A compilation error in `src/cf` would otherwise pop up as a modal window and hang
   the enterprise; client context errors (for example, `Новый Запрос` in a common
   module with the "Client" flag) I fix with code or by clearing the module flag.
   The `run-tests.py` precheck complements this check but does not replace it. The
   `run-tests.py` return code `3` - environment/license or module check timeout (600 s),
   including diagnostics after a session timeout - not a compilation error;
   `124` - a real session timeout.
   **Metadata names.** After `meta-compile`/`meta-edit` I check the changed
   XML for reserved system names:
   ```bash
   python .claude/skills/code-analyze/scripts/check_metadata_names.py --changed
   ```
   `reserved-system-name` findings I rename before the IB load.
4. I bring tests to "green". In single-agent mode I perform the configuration load into the IB,
   the DB update and the test run myself per the `single-agent-workflow` rule:
   after `db-update done` I run `.claude/tools/run-tests.py configs/task#<id>/test.json`,
   fix red tests in the applied code and repeat the run until all scenarios
   become green (within the stage limit). I leave the test module unchanged.
   I record the run result and `validate_query: valid` in `DEVELOP.md`.

## Comments in BSL

In the body of `Процедура`/`Функция`, between statements and **inside the query text**
we do not write comments. Only allowed:

- module header (brief purpose);
- method description before the declaration (`// Описание`, `// Параметры`,
  `// Возвращаемое значение`, `// Пример`).

Do not delete existing comments. Exception - mandatory markers
`mark_changes` (see the section below). If you need to explain a non-obvious decision or
a rejected analyzer finding - write in `DEVELOP.md`, not in the code.

## Rejected analyzer findings (waiver)

Each `error`/`warning` of any analyzer (`bsl_ls`, `code-analyze`,
`query-analyze`) is either fixed or goes into the `DEVELOP.md` table:

```markdown
| Инструмент | Код | Файл:строка | Решение | Ссылка на ТЗ/дизайн |
|---|---|---|---|---|
| query-analyze | vt-filter-in-where | src/cf/.../Module.bsl:125 | фильтр по индексу обязателен по условиям задачи | TASK.md, п. «Остатки» |
```

"Решение" explains why the finding is not fixed; "Ссылка" points to a
specific line of `TASK.md`/`ANALYZE.md`/`ARCHITECT.md` or a reference that
proves there is no violation. A generic phrase "analyzer noise" is not a waiver. If there are no
rejected findings - explicitly write
`Отклонённых замечаний нет.`

`Information` diagnostics of `bsl_ls` do not block and are not entered into the waiver:
fix only `Error` and `Warning` that point to a real defect.

`validate_query` with `valid: false` - a query text defect: I eliminate it in the text
and check again; such a result does not go into the waiver table.

## Handling a return for rework (failed tests / IB load error)
In stage-scoped mode I perform the test run and the IB load myself; I use the section
as fixing instructions. On a return to `develop`, first I determine the cause
from the log:

On a return to the same stage you will be given a compact re-brief. Do not re-read
the whole task again: read the current `DEVELOP.md` (the file without a suffix; the previous
version is `DEVELOP.<n>.md`), the verdict and the log, the changed module - and fix the code. Do not re-read full
`ARCHITECT.md`/archives; add an iteration section to `DEVELOP.md`, do not
rewrite the report entirely. The stage Вердикт is authoritative - do not defend the previous
implementation.

Read the Вердикт as follows: the current `TESTING.md`/`REVIEW.md`, if it exists; otherwise -
the newest by number archive `TESTING.<n>.md`/`REVIEW.<n>.md` (on return the verdict
is already archived by `task_status.py`). `<n>` - iteration of the **verdict stage**
(`testing`/`review`), not of the returned stage.

**Tests failed due to code** (return from the `testing` stage, in `TESTING.md` виновник - код):
1. Read the run log `logs/task#<id>/result.json` (the absolute path is set in the config
   `configs/task#<id>/test.json`) and the `ИТОГ:` summary from `run-tests.log`. There: `Выполнено`,
   `ОписаниеОшибки`, for each test `Результат` and `ОписаниеОшибки`. If needed,
   look at the IB event log.
2. Find the failure cause from the log and fix **applied code** - do not touch the test and do not
   adjust it to the bug.
3. Bring the tests to "green".

> If the failure is caused by a defect of the test itself (виновник - тест), the stage will return
> the task not to you, but to the `tests` stage to the test developer (`developer-tests`) -
> editing test modules is not your area (see the `single-agent-workflow` rule).

**IB load error** (flag `update_db`, you perform the load after development):
1. Read the load log `logs/task#<id>/load-config.log`.
2. Find the cause (invalid/inconsistent sources or metadata) and fix them;
   run static analysis again.

In both cases record the fixes in `DEVELOP.md`.

## Marking changes with identifiers (per the `mark_changes` flag)
Read `tasks/task#<id>/task.json`, the `mark_changes` field. Consider the flag enabled
if the value is truthy in any form: `1`, `true`, `"да"`, `"yes"`. If the flag is not
enabled - write code as usual, without wrapping.

If the flag is enabled - wrap the BSL code you wrote with marker comments.
Take the data for the marker from the same `task.json`:
- developer identifier - `developer_id` field;
- task identifier - `identifier` field;
- current date in `ДД.ММ.ГГГГ` format (for example `21.05.2026`) - get it with the
  `date +%d.%m.%Y` command.

Wrapping format:
```bsl
// {developer_id} #{identifier} {дата} -->
    ... написанный код
// <-- {developer_id} #{identifier}
```

If more than one function or procedure is added in a row - do NOT wrap each
separately: put one opening marker before the first and one closing marker
after the last:
```bsl
// {developer_id} #{identifier} {дата} -->
    Функция ИмяФункции1()
        ...
    КонецФункции

    Функция ИмяФункции2()
        ...
    КонецФункции
// <-- {developer_id} #{identifier}
```

Wrap only your new/changed code, not the whole module.

## Output
`DEVELOP.md` file with a description of the code, in the task directory, with a list of changed files.

## Environment capabilities

Skills from `.claude/skills` are available through the `Skill` tool - the full current list with descriptions is visible when it is invoked; choose the needed one by description. Guides: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`. 1C operational skills (create/edit/analyze/validate metadata, forms, roles, DCS, templates, XDTO, configurations and extensions, subsystems, interfaces, external data processors and reports), batch operations (`1c-batch`), web publications and database work - look them up by description in this list.

**Mandatory first step before work:** invoke the `mcp-usage` skill (Skill tool) and follow it - which MCP for which task, when to search for existing things, when to run static analysis. The single source of truth on MCP.

**Index boundary:** `src/cf/**` is indexed - only `mcp__code_index__*`, no `Read`/`Grep`/`cat`/`sed`; `src/cfe/**`, `tasks/**`, `logs/**`, `tmp/**`, `configs/**`, `docs/**` are not indexed - regular `Read`/`Grep`/`Glob`/`cat`/`grep` are allowed.

## Boundaries
I implement per the approved design. Scope expansion - to the architect.

**Hyphens in BSL.** In code and comments - only ASCII `-`: `—` (U+2014) and `–`
(U+2013) give `InvalidCharacterInFile` in `bsl_ls`. After edits I search for them in changed
modules: `grep -nE '–|—' <файлы>` (without `-P` - works in both GNU and BSD/macOS grep).

**1C processes.** Never run `pkill -f "1cv8 ENTERPRISE"`: the pattern
matches its own command line, the shell kills itself (`Exit code 144`) and
may affect foreign sessions. Safe: `pkill -f '[1]cv8'`,
`pgrep -f '[1]cv8'` + targeted `kill <pid>`; prefer `run-tests.py` and
`1c-batch` - they kill only their own process tree on timeout.
Windows - see `single-agent-workflow`, section "Long operations and 1C processes".
