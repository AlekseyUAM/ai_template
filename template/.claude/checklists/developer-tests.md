> **Stage checklist.** This is not a separate agent: work through every item yourself in
> the current thread. Stage names below (`analyze`, `plan`, `tests`, `develop`, `testing`,
> `review`, `docs`) refer to other stages of the same task, not to handoffs to other agents.

# Test developer

Role: 1C test developer. Write unit tests before implementation (TDD, Red phase): tests
must fail while the code is not yet written.

## When applied
Stage `tests` (before `develop`, Red): after `analyze` and `plan`, before `develop`.

Repeatedly - when the `tests` stage is returned in the loop: the test turned out **defective**
(in the testing verdict the culprit is the test) or red smoke found a defect before development. Then:
1. Determine the source of diagnostics by the reason for the return:
   - **return from smoke** (red smoke found a defect before development) - there is no verdict:
     the `testing` stage has not run yet, the `TESTING*.md` file does not exist.
     Source - `run-tests-smoke.log` and `result.json` of the last **full** run;
   - **return from `testing`** - the testing verdict and `result.json`;
   - **return from `review`** - the review verdict and `result.json`.

   Вердикт (only for returns from `testing`/`review`) read as follows: the current
   `TESTING.md`/`REVIEW.md`, if it exists; otherwise - the newest by number archive
   `TESTING.<n>.md`/`REVIEW.<n>.md` (on return the verdict is already archived by
   `task_status.py`); `<n>` - iteration of the **verdict stage** (`testing`/`review`), not of
   the returned `tests` stage. The current `TESTS.md` is the file without a suffix; the previous
   version is `TESTS.<n>.md`.
2. Fix the test module in `src/cfe/ЮнитТесты` without weakening the check to hide
   a real code bug; if needed, update `TESTS.md`. After the fix, perform
   a debug run with `--test` over the failed scenarios, then the full set (smoke) and
   update the "Smoke" section in `TESTS.md`. The full run after implementation belongs to
   the `testing` stage. Do not edit applied code - that is the `develop` stage.
3. On a return to the same stage, do not re-read the whole task: read the current
   `TESTS.md` (without suffix), the source of diagnostics per step 1 and edit only the
   test module. Do not rewrite `TESTS.md` entirely - add an iteration section.

## Input
Use the task's existing artifacts: `ANALYZE.md` (specification), `ARCHITECT.md` (technical design). If some of them are absent (not all stages enabled) - rely on `TASK.md` (goal, plan, constraints) as the primary source.

## Steps
Unit tests are arranged as **common modules inside the `ЮнитТесты` extension** - it also
runs the tests in the test infobase (installed into it separately, downloaded with the "Download
test extension" button in the project card). The sample is the common module `ЮТ_ТестыПример`,
already part of `ЮнитТесты`. Do not create a separate extension for tests - add new modules
to `ЮнитТесты`.

Extension sources are in `src/cfe/ЮнитТесты` (if they are not yet in the project, unpack
`ЮнитТесты.cfe` there with the `1c-batch` skill). Make all edits in these sources.

**Scope - only tests from the TS.** Create only those tests that are directly specified in the TS
(test description - `TASK.md`). Never invent or add your own tests: neither
additional checks "just in case" nor scenarios for adjacent cases.

**Small steps - mandatory.** Do not write the whole test module in one piece:
1. First the skeleton: `Сценарии()` and common helpers - no more than 120 lines per one `Write`.
2. Then one scenario at a time: one test function per step, `Write`/`Edit` no more than
   150 lines.
3. After each scenario - check only the changed file (`bsl_ls`/`check`);
   full `check-modules` - once at the end.
4. The next scenario - only after successful check of the previous one.
5. Do not rewrite the module entirely and do not re-read it after each edit: edit
   pointwise (`Edit`), `Read` - only the needed range.
6. If a scenario does not fit into 150 lines - move the common part into helpers or a separate
   module, do not generate everything at once.

**Ready helpers.** Use the existing functions of `ЮТ_ТестированиеСервер`, do not duplicate
them in the test module:

- movements: `ДвиженияПоРегистратору`, `НоваяТаблицаДвижений`,
  `ПроверитьНаборДвижений`, `ПроверитьОтсутствиеДвижения`;
- registers and data: `ДобавитьЗаписьРегистраСведений`, `СоздатьДокумент`,
  `СоздатьЭлементСправочника`, `СоздатьЭлементПВХ`, `ДанныеНовогоЭлемента`;
- comparison and run: `ТаблицыЗначенийРавны`, `РезультатТеста`, `ЗаписьЖР`,
  `Тестирование`, `ВыполнениеТеста`, `УдалитьТестовыеЭлементы`.

Helpers take metadata names as parameters (catalog, document, register, attribute) and
do not reference task#001 objects, so they work for any task's metadata.
`ДобавитьЗаписьРегистраСведений` accepts only a `Структура`: it checks the fields whose
metadata fill checking is `ВыдаватьОшибку` and requires `Период` for a periodic register.

**`bsl_ls` diagnostics.** `Information` diagnostics do not block the stage; fix
only `Error` and `Warning` that point to a real defect.

1. Add to the `ЮнитТесты` extension a new common module of test scenarios following the sample
   `ЮТ_ТестыПример`. Name - meaningful (for example, `ЮТ_<Задача>`). Create the module
   metadata with the `meta-compile` skill (CommonModule in the extension); do not edit
   `Configuration.xml`/`ConfigDumpInfo.xml` manually.
2. In the common module declare an export function `Сценарии()` - it returns `Массив`
   of names of export test functions of this module:
   ```bsl
   Функция Сценарии() Экспорт
       Результат = Новый Массив;
       Результат.Добавить("СложениеЧисел");
       Возврат Результат;
   КонецФункции
   ```
3. Each test function - export and **returns `Структура`** - the test result with
   fields `Результат` (`Булево`: `Истина` - passed, `Ложь` - failed) and
   `ОписаниеОшибки` (`Строка`: explanation on failure). The blank is created by
   `ЮТ_ТестированиеСервер.РезультатТеста()`:
   ```bsl
   Функция МойСценарий() Экспорт
       РезультатТеста = ЮТ_ТестированиеСервер.РезультатТеста();
       <подготовка данных и вызов проверяемого кода>
       РезультатТеста.Результат = <проверка>;
       Если Не РезультатТеста.Результат Тогда
           РезультатТеста.ОписаниеОшибки = "Ожидали ..., получили ...";
       КонецЕсли;
       Возврат РезультатТеста;
   КонецФункции
   ```
   The body - regular 1C code: prepare data, perform the action under test, write
   the comparison result into `Результат`. `РезультатТеста()` returns a successful blank:
   assign `Результат` from the check. On an early exit because of an error, set
   `Результат = Ложь` and `ОписаниеОшибки` in that branch; the runner counts a non-empty
   error with `Результат = true` as a failure. Returning a "bare" `Булево` is an error: the runner
   will write `Тест вернул некорректный результат` and count the test as failed.

   In the sample `ЮТ_ТестыПример` there is an example of logging debug information via
   the event log - call `ЮТ_ТестированиеСервер.ЗаписьЖР(Комментарий)` (the second
   parameter `Уровень` defaults to `"Информация"`). Use this for intermediate
   values when analyzing failures. **The event log for the run also goes into `result.json`:**
   - `ЖурналРегистрации` - event log records filtered by the event name `ЮнитТесты` (that is,
     all `ЗаписьЖР` calls from tests and the runner);
   - `ЖурналРегистрацииВсеОшибки` - all event log records of the `Ошибка` level for the run, **without**
     filtering by event name (including foreign errors, not only "ЮнитТесты").

   Each array element is a structure with fields `Дата`, `Уровень`,
   `ПредставлениеСобытия`, `Комментарий`, `ПредставлениеМетаданных`,
   `ПредставлениеДанных`. The `run-tests.py` summary does not print these arrays - when analyzing,
   open `result.json` yourself. The main diagnostic channel is still
   `ОписаниеОшибки`: **do not catch the exception just to write to the event log** - the runner
   itself catches the scenario exception and saves its text into `ОписаниеОшибки`.
4. **Do not delete data you did not create.** The test infobase is not empty and can be
   very large; foreign data, especially register records, must not be deleted. Clean
   only your own test artifacts and by specific references, not with queries like
   "delete everything from the register/catalog". The test must be self-contained and
   reproducible, not depend on scenario order or balances from previous runs.
   - All created reference items (catalogs, charts of characteristic types (PVH), documents) must be
     registered in the information register `ТестовыеЭлементы` - the runner later deletes them
     by this registration. Use the helpers `ЮТ_ТестированиеСервер.СоздатьЭлементСправочника`,
     `СоздатьЭлементПВХ`, `СоздатьДокумент` - they register the item themselves.
     The sample is the test `ПроведениеАнкеты` in `ЮТ_ТестыПример`.
   - Before **each** test (not once before the run) the runner calls
     `УдалитьТестовыеЭлементы()` and deletes everything registered in the information register
     `ТестовыеЭлементы`. Documents are unposted before deletion (posting cancellation),
     so register movements are deleted together with them - there is no need to clean movements
     separately.
   - Cleanup is shared for the whole infobase, therefore **parallel test execution on one infobase
     is impossible**: runs will delete each other's data. Within one run scenarios
     execute sequentially, but the data of each test is deleted before the next one
     starts - do not count on what was created in one test surviving to another.
5. Tests must be "red" by construction: the behavior under test does not exist yet, so
   every test must really assert something and fail before implementation. If a test
   passes on empty code - it checks nothing, redo it. You perform the red smoke
   yourself (section "Running tests (Red) - you do it yourself"): load the extension,
   run the full set and achieve a correct red result. The full run
   after implementation is performed at the `testing` stage.
   Smoke criteria: no test module compilation errors and no setup exceptions; no test
   is green before implementation; red ones fail on an assertion (expected/actual) or on
   the expected absence of not-yet-written functionality; the call under test is not
   wrapped in `Попытка` (the exception must reach the runner, except for the scenario with
   expected refusal). A test that checks an expected value (for example,
   `СтоимостьРасход = 300`), on empty code is red: 0/`NULL` is not equal to 300; green before
   implementation can only be a test comparing state before/after ("did not
   change") - it must be strengthened.
6. Write the **test run config** `configs/task#<id>/test.json` (one per task;
   format sample - `configs/test_example.json`) - use it to run the tests:
   ```json
   {
       "ИмяМодуля": "<ИмяТестМодуля>",
       "ИмяФайлаЛог": "<корень проекта>/logs/task#<id>/result.json"
   }
   ```
   - `ИмяМодуля` - the name of the test module you added with the `Сценарии()` function.
   - `ИмяФайлаЛог` - an **absolute** path where the test runner will write the result;
     use `logs/task#<id>/result.json`.
7. Record in `TESTS.md`: test module name (the `ИмяМодуля` value), path to the run config
   `configs/task#<id>/test.json`, total number of scenarios of the full set and
   the "Smoke" section with evidence (see section "Running tests (Red) - you do it
   yourself"). The `testing` stage relies on this data; make sure it is complete before
   `tests done`.

## Retry after timeout (test module already exists)

If the stage is launched again after a timeout and the task's test module already exists in
`src/cfe/ЮнитТесты`:
1. Do not create a new module and do not rewrite the existing one entirely.
2. Check it pointwise (`bsl_ls`/`check`); add only missing scenarios
   from the TS, edit existing ones minimally.
3. Immediately write `TESTS.md` and `configs/task#<id>/test.json` if they do not exist yet
   (the artifact must exist even on a repeated timeout).
4. Perform the smoke and mark the `tests done` stage.
5. Do not call `meta-info`, `meta-compile`, `validate_query` again if
   the module metadata is already created and added to `Configuration.xml`.

## Running tests (Red) - you do it yourself

Smoke and debug runs are performed at this stage. The `testing` stage checks the
evidence and runs the full set after implementation.

### Full set (smoke)

After writing `TESTS.md` and `configs/task#<id>/test.json`, execute in one Bash call
(timeout not less than 300000 ms):

```bash
SMOKE_LOG="logs/task#<id>/run-tests-smoke-$(date +%Y%m%d-%H%M%S).log"
python .claude/skills/1c-batch/scripts/1c-batch.py load-extension \
    src/cfe/ЮнитТесты --name ЮнитТесты \
    > logs/task#<id>/load-extension-tests.log 2>&1
load_rc=$?; echo "LOAD_EXIT=$load_rc" >> logs/task#<id>/load-extension-tests.log
if [ "$load_rc" -eq 0 ]; then
    python .claude/tools/run-tests.py configs/task#<id>/test.json --timeout 300 \
        --no-check-main > "$SMOKE_LOG" 2>&1
    rc=$?; echo "EXIT=$rc" >> "$SMOKE_LOG"
else
    echo "EXIT=load-failed" > "$SMOKE_LOG"
fi
cp "$SMOKE_LOG" logs/task#<id>/run-tests-smoke.log
tail -80 logs/task#<id>/load-extension-tests.log "$SMOKE_LOG"
```

`--no-check-main` saves a minute per cycle: the main configuration does not change
at the `tests` stage, its successful check is cached by the source hash (not rerun).
Each smoke is written to a separate timestamp log; `run-tests-smoke.log`
remains the last one - it is checked by the `testing` stage.

`LOAD_EXIT=0` is mandatory: with `LOAD_EXIT≠0` or `EXIT=load-failed` the test run
did not start - the extension load failed, this is a defect; do not count the run as
smoke evidence (a run against the previous version of the test extension would give
a plausible `EXIT=4`).

Before the smoke, refresh the main configuration in the IB: pointwise for the changed
modules or the whole `src/cf` via `1c-batch load-config`. The extension load alone does
not remove an older implementation of the object under test; otherwise the red smoke
can become falsely green and a real defect will not be caught.

On smoke the expected code is `EXIT=4` (the run took place, all tests are red). `EXIT=2`
(compilation error), `EXIT=5` (no result) and `1/3/124` are defects, fix until `4`.

### Debug run of one scenario

```bash
python .claude/tools/run-tests.py configs/task#<id>/test.json \
    --test <ИмяСценария> --timeout 90 --no-check-main \
    > logs/task#<id>/run-tests-debug.log 2>&1
rc=$?; echo "EXIT=$rc" >> logs/task#<id>/run-tests-debug.log
tail -80 logs/task#<id>/run-tests-debug.log
```

`--test` overwrites `result.json` with a subset. The final smoke evidence is
only the **last full** run in `run-tests-smoke.log`; after debugging run
the full set again last.

### Smoke criteria

- extension compiles without errors, no setup exceptions (check
  `ЖурналРегистрацииВсеОшибки` in `result.json` - there must be no run errors there);
- no test is green before implementation;
- red ones return `Результат = Ложь` on an assertion, and `ОписаниеОшибки` records
  the expectation/actual (or an exception of the expected absence of functionality);
- the call under test is not wrapped in `Попытка` (except the expected-refusal scenario);
- a test comparing state before/after ("did not change") cannot be green before
  implementation - strengthen it;
- **on an empty implementation, absence of movements is a normal red result.**
  An `ОписаниеОшибки` message like "no movements", "expected 300, got -" is an
  assertion on the expected value, not a setup error. Do not try to get movements
  before implementation: do not create extension roles, do not edit `Rights.xml`/`ConfigDumpInfo.xml`,
  do not change `src/cf` and do not look for the "right way to post". If all tests are red
  on expected values, the smoke is accepted.

**The whole `tests` stage - no more than 30 minutes.** If the limit expires, stop and return a
report: what was done, what result, what hypotheses remain.

Limit - 2-3 "edit -> smoke" cycles. After the third cycle **stop** and return a
stage report: what was done, what result, what hypotheses remain. Further
diagnostic cycles without user instruction are forbidden.

**Diagnostics boundaries.** The test module and its diagnostic probes - only in
`src/cfe/ЮнитТесты`. It is forbidden to modify `src/cf` (including temporary probes and
`Rights.xml`): there is a separate `develop` stage for that. If it seems that a fix
to the main configuration is needed, stop and describe the problem in the report.

### "Smoke" section in `TESTS.md`

Record: date/time, paths `logs/task#<id>/load-extension-tests.log` and
`logs/task#<id>/run-tests-smoke.log`, `LOAD_EXIT`, `EXIT`,
`Выполнено`, `ОписаниеОшибки`, total number of scenarios of the full set, confirmation that
all `Результат=false` and red ones fail on an assertion.

## Typical test module errors (mandatory rules)

1. **First read the sample `ЮТ_ТестыПример`** (structure: `Сценарии()` + export
   test functions) and write following it. **Do not create your own skeletons/wrappers around
   scenarios** (for example, `ВыполнитьСценарий`): the runner
   (`ЮТ_ТестированиеСервер.Тестирование`) already wraps each scenario in `Попытка` and
   writes the exception text into `ОписаниеОшибки`. A wrapper hides the failure cause from
   `result.json` and makes diagnostics expensive.
2. **`Попытка` - only for expected refusal** (the scenario checks that posting/writing
   is rejected); in all other cases the exception must reach the runner.
3. **Do not declare procedures/functions with platform names** (for example,
   `ПодробноеОписаниеОшибки`): a local function shadows the global one, and a call inside its body
   becomes recursion (stack overflow, session hang). For the error text use
   `ОписаниеОшибки()` or `ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())`.
4. **Check signatures** before use: `1c_platform` (rule `mcp-usage`);
5. **Clarify metadata names via `code_index`, do not guess**: full names of
   catalogs, documents, registers, attributes and their types check against the configuration
   code index. A guessed name does not exist in the infobase - the test fails at runtime.
6. Do not weaken checks and expected values for a "green" run and do not adjust
   the check to the actual implementation: if the expectation follows from the TS or the platform
   model (for example, for a balance register - `ВидДвижения` and `Обороты.РесурсРасход`),
   and the code gives something else, record the discrepancy, do not rewrite the check. If in doubt
   about the API, check against the configuration code.
7. **Check queries in the test module with `query-analyze`.** Every written/changed
   query text (including helper queries) run with the `query-analyze` skill and
   `validate_query` on the literal exactly as it is written in the source. Stubs
   `!...!`, `%1`, `{0}` in the query text are forbidden; substitution - only into valid
   places (`&ОсобыйПараметр`, `1 = 1`). Record the result in the `TESTS.md` report.
8. **Failure of `validate_query` call.** If the tool ends with a transport/server
   error (for example, `Тип не определен ...`), do not repeat it
   endlessly: at most one retry, then consider the query valid,
   record the failure in `TESTS.md` and continue.
9. **`bsl_ls` and dates.** `bsl_ls` does not parse date literals `#...#` (ParseError);
   use `Дата(Год, Месяц, День)` or `Дата(Год, Месяц, День, Час, Мин, Сек)`.
   Do not waste time on a diagnostic probe of this limitation.
10. **Arrays.** `Массив` has no `Соединить` method; use
    `СтрСоединить(Массив, Разделитель)`.

## Output
`TESTS.md` file in the task directory: created tests, test module name, path to the run
config `configs/task#<id>/test.json`, list of changed files, total number of scenarios
and the "Smoke" section with evidence (log paths, `LOAD_EXIT`/`EXIT`, whether all tests are
red on the
assertion). You also create the run config itself (`configs/task#<id>/test.json`).

## Environment capabilities

Skills from `.claude/skills` are available through the `Skill` tool - the full current list with descriptions is visible when it is invoked; choose the needed one by description. Guides: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`. 1C operational skills (create/edit/analyze/validate metadata, forms, roles, DCS, templates, XDTO, configurations and extensions, subsystems, interfaces, external data processors and reports), batch operations (`1c-batch`), web publications and database work - look them up by description in this list.

**Mandatory first step before work:** invoke the `mcp-usage` skill (Skill tool) and follow it - which MCP for which task, when to search for existing things, when to run static analysis. The single source of truth on MCP.

**Index boundary:** `src/cf/**` is indexed - only `mcp__code_index__*`, no `Read`/`Grep`/`cat`/`sed`; `src/cfe/**`, `tasks/**`, `logs/**`, `tmp/**`, `configs/**`, `docs/**` are not indexed - regular `Read`/`Grep`/`Glob`/`cat`/`grep` are allowed.

## Boundaries
Test writing only (Red): do not write implementation code - that is the `develop` stage.

**1C processes.** Never run `pkill -f "1cv8 ENTERPRISE"`: the pattern
matches its own command line, the shell kills itself (`Exit code 144`) and
may affect foreign sessions. Safe: `pkill -f '[1]cv8'`,
`pgrep -f '[1]cv8'` + targeted `kill <pid>`; prefer `run-tests.py` and
`1c-batch` - they kill only their own process tree on timeout. More details -
`single-agent-workflow`, section "Long operations and 1C processes".
