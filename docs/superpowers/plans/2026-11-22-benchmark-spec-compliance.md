# Benchmark spec-compliance fixes — 2026-11-22

## Global constraints

- Main repo: `/home/uam/projects/ai_template`, branch `main`. Commits are local, no push.
- Never `git add -A`: stage only the files named in the task. The working tree already
  contains the user's uncommitted edits to `benchmark/tasks/task#002/TASK.md`,
  `task#003/TASK.md`, `task#004/TASK.md` — preserve them.
- Exception: `ЮТ_ТестированиеСервер` source is edited in place at
  `/home/uam/projects/test2/src/cfe/ЮнитТесты/CommonModules/ЮТ_ТестированиеСервер/Ext/Module.bsl`.
  Do not modify any other file in `test2`, do not commit in `test2`, do not rebuild
  `app/web/assets/ЮнитТесты.cfe`.
- Do not add review-stage checks, new `DEVELOP.md` sections, or new `reviewer.md` checks.
- New wording in `.claude/**` and `benchmark/tasks/**/TASK.md` is affirmative: describe
  what to do, without "НЕ ДЕЛАЙ ТАК" rules.
- Each implementer writes a report to `<git-dir>/sdd/task-<N>-report.md`, runs the
  covering tests, and commits locally with a Conventional Commits message.

## Task 1: query-analyze — remove totals rule, add parameter-table rule

Files:
- `template/.claude/skills/query-analyze/scripts/rules.py`
- `template/.claude/skills/query-analyze/scripts/tests/test_rules.py`
- `template/.claude/skills/query-analyze/SKILL.md`
- `template/.claude/skills/bsl-coding-standards/SKILL.md`
- `template/.claude/skills/bsl-coding-standards/reference/query-totals.md`

Requirements:

1. Remove the rule `totals-field-not-aggregated` completely: the decorated function
   `check_totals_field_not_aggregated` and its tests. Keep the manual guidance about
   NULL in ИТОГИ:
   - `bsl-coding-standards/SKILL.md` keeps its `[critical]` manual item but no longer
     mentions the automatic rule;
   - `reference/query-totals.md` intro describes a manual check, section 4 stays;
   - `query-analyze/SKILL.md` removes the rule from the AST error-class list and adds
     a line to "What the analyzer does NOT check": non-aggregated fields in ИТОГИ are
     checked manually by `query-review`.
2. Add rule `param-table-in-from`, severity `error`, title explaining that a
   parameter table in `ИЗ` must first be placed into a temporary table.
   - Iterate `iter_query_models(ctx)`.
   - For each `model_dict`, inspect `model_dict.get("tables") or []`; a table whose
     `fullName` starts with `&` is a parameter table.
   - Flag when `model_dict.get("queryType") != "createTemp"`.
   - Message (affirmative): "Параметрическую таблицу помещай во временную
     (`ПОМЕСТИТЬ ВТ ИЗ &Параметр`) и выбирай из неё — на 8.3.27 выборка
     `ИЗ &Параметр` не компилируется."
   - Add it to the `query-analyze/SKILL.md` AST error-class list.
3. Tests in `test_rules.py`:
   - invalid: `ВЫБРАТЬ Т.Номенклатура КАК Номенклатура ИЗ &ТаблицаТоваров КАК Т`
     is flagged;
   - valid: `ВЫБРАТЬ Т.Номенклатура КАК Номенклатура ПОМЕСТИТЬ ВТ ИЗ
     &ТаблицаТоваров КАК Т` is not flagged;
   - the removed `totals-field-not-aggregated` tests are gone.
4. Run: `python -m pytest template/.claude/skills/query-analyze/scripts/tests -q`.
   Probe both queries through `analyze_query.py`.
5. Commit only the five listed files.

## Task 2: code-analyze — comment-in-body rule

Files:
- `template/.claude/skills/code-analyze/scripts/rules.py`
- `template/.claude/skills/code-analyze/scripts/tests/test_rules.py`
- `template/.claude/skills/code-analyze/SKILL.md`

Requirements:

1. Add rule `comment-in-body`, severity `warning` (the standard marks it `[important]`).
   - Use `ctx.model.methods`; for each method, a comment token with
     `method.header_line < token.line <= method.end_line` is in the body.
   - Do not flag comments before the method declaration (method description), comments
     in the module header, `// BSLLS:` directive comments, or `mark_changes` markers
     (lines containing `-->` or `<--`).
   - Also flag `|//` comment lines inside multi-line query string tokens. For each
     string token, split its value by lines; a line whose stripped content starts with
     `|//` is a finding. Report the source line.
   - Message (affirmative): "Комментарий в теле метода: перенеси пояснение в описание
     метода или в DEVELOP.md."
2. Tests:
   - comment inside procedure body is flagged;
   - description before the declaration is not flagged;
   - `// BSLLS:...` inside body is not flagged;
   - `mark_changes` marker is not flagged;
   - `|//` inside a query string is flagged;
   - module header comment is not flagged.
3. Add the rule to the registry table in `code-analyze/SKILL.md`.
4. Run: `python -m pytest template/.claude/skills/code-analyze/scripts/tests -q`.
5. Commit only the three listed files.

## Task 3: bsl_ls — sha newline tolerance, transient retry, metric

Files:
- `app/docker/mcp/bsl_check_server.py`
- `app/tests/env/test_bsl_check_server.py`
- `template/.claude/hooks/bsl_nudge.py`
- `docs/mcp/bsl-ls.md`
- `benchmark/bench_metrics.py`
- `benchmark/tests/test_bench_metrics.py`

Requirements:

1. `bsl_check_server.py`:
   - Accept an expected SHA-256 that matches the sent text with no trailing newline,
     with one trailing `\n`, or with the trailing `\n` removed. Keep BOM variants.
     Apply the same tolerance in `prepare_input` and `run_check`.
   - On a missing report whose stderr contains `org.springframework.beans.factory.BeanCreationException`
     (or `BeanCreationException`), retry the Java run once. Do not retry syntax/analysis
     errors.
   - Keep the response `sha256` normalized as today.
2. Tests:
   - file text ends with `\n`, code sent without it, expected hash of the file is accepted;
   - code sent with an extra trailing `\n`, expected hash without it is accepted;
   - mismatched hash still rejected;
   - fake run returning `BeanCreationException` once then a valid report produces `ok=True`
     and exactly two Java invocations.
3. `bsl_nudge.py` and `docs/mcp/bsl-ls.md`: positive instruction to send `code` +
   `sha256`; `file_path` only for mounted paths. Do not add project mounting.
4. `bench_metrics.py`: count MCP tool results with `ok:false` as `mcp_errors` in
   addition to `is_error`; add a test with an MCP result containing `ok:false`.
5. Run: `python -m pytest app/tests/env/test_bsl_check_server.py benchmark/tests/test_bench_metrics.py -q`.
6. Commit only the six listed files. The Docker image is rebuilt by the user.

## Task 4: environment instructions

Files:
- `template/.claude/checklists/developer.md`
- `template/.claude/checklists/query-review/SKILL.md` (actual path:
  `template/.claude/skills/query-review/SKILL.md`)
- `template/.claude/checklists/developer-tests.md`
- `template/.claude/skills/bsl-coding-standards/reference/information-registers.md`
- `benchmark/bench_run.py`

Requirements:

1. `template/.claude/skills/query-review/SKILL.md`: add a positive item:
   "При проведении документ уже записан: запрос к `Документ.<Имя>.<ТЧ>` с отбором
   `Ссылка = &Ссылка` возвращает сохранённые строки." Place it in a sensible section
   (general requirements or a new short section).
2. `template/.claude/checklists/developer.md`:
   - Replace the ambiguous phrase at lines 42-43 ("a query to a document's tabular
     section directly instead of unloading it into a value table") with the positive
     direct-query rule from item 1.
   - In step 3 add: for each changed module with a query run
     `extract_queries.py -Path <file> | analyze_query.py -` and record the result as a
     line in `DEVELOP.md`.
   - Rewrite the "Comments in BSL" section affirmatively: place comments in the module
     header and method description before the declaration; put implementation notes in
     `DEVELOP.md`.
3. `template/.claude/checklists/developer-tests.md`: replace the stale "Ready helpers"
   list with the functions that actually exist in `ЮТ_ТестированиеСервер` plus the new
   helpers from Task 6: `НоваяТаблицаДвижений`, `ПроверитьНаборДвижений`,
   `ПроверитьОтсутствиеДвижения`, `ЗаписатьЗаписьРегистраСведений`. Remove
   `СоздатьТестовуюОрганизацию`, `СоздатьТестовуюНоменклатуру`,
   `УстановитьМетодСписанияСебестоимости`, `УдалитьМетодСписанияСебестоимости`,
   `НоваяТаблицаСтрокНакладной`, `ДобавитьСтрокуНакладной`, `СоздатьНакладную`,
   `Проверить`, `ПроверитьНаборДвижений` (old), `ПроверитьОтсутствиеДвижения` (old)
   unless they exist. State that helpers take metadata names as parameters and do not
   reference task#001 objects.
4. `template/.claude/skills/bsl-coding-standards/reference/information-registers.md`:
   add a positive subsection: the manager call `СрезПоследних(Период, Отбор)` returns
   `ТаблицаЗначений`; take the row with `[0]`/`Выбрать()` and read resources by name.
5. `benchmark/bench_run.py` `build_task_prompt`: add one sentence — "План TASK.md —
   контракт: каждый пункт реализуй как написано и отрази в DEVELOP.md."
6. Run: `python -m pytest app/tests/env/test_template_docs.py -q`.
7. Commit only the five listed files.

## Task 5: benchmark task definitions

Files:
- `benchmark/tasks/task#002/TASK.md`
- `benchmark/tasks/task#002/task.json`
- `benchmark/tasks/task#003/TASK.md`
- `benchmark/tasks/task#003/task.json`
- `benchmark/tasks/task#004/TASK.md`
- `benchmark/tasks/task#004/task.json`
- `benchmark/README.md`

Requirements:

1. `task#002`:
   - `TASK.md`: max duration 10 -> 20; constraints affirmative:
     "Область изменений: общий модуль РегламентированныйУчетПовтИсп."
   - `task.json`: sync `constraints`, `tests` (text of the TASK.md "Тесты" section,
     without the heading), `max_minutes` = 20; enable `tests`, `develop`, `testing`;
     disable `analyze`, `plan`, `review`, `docs` (statuses `skipped` for disabled,
     `pending` for enabled).
2. `task#003`:
   - `TASK.md`: constraints affirmative:
     "Область изменений: документ ПриходнаяНакладная."
   - `task.json`: sync `constraints`, `tests`, `max_minutes` = 30; enable `tests`,
     `develop`, `testing`; disable the rest (`review` off).
3. `task#004`:
   - `TASK.md`: constraints affirmative:
     "Область изменений: документ РасходнаяНакладная и связанные объекты подсистемы
     ОперативныйУчет."
   - `task.json`: sync `goal`, `constraints`, `tests` from TASK.md. Stages and
     `max_minutes` unchanged.
4. `benchmark/README.md`: update the stage composition text in both places
   (around lines 30-34 and 209-213): #002/#003 — `tests`, `develop`, `testing`;
   #004 — `plan`, `tests`, `develop`, `testing`, `review`; the rest — `develop`.
5. Validate every changed JSON with `python -m json.tool`.
6. Commit only the seven listed files. Include the user's existing TASK.md test edits
   in the commit.

## Task 6: ЮТ_ТестированиеСервер helpers (test2, no commit)

File:
- `/home/uam/projects/test2/src/cfe/ЮнитТесты/CommonModules/ЮТ_ТестированиеСервер/Ext/Module.bsl`

Requirements:

1. Add exported generic helpers without references to task#001 metadata
   (`Организации`, `Номенклатура`, `ПриходнаяНакладная`, `УчетнаяПолитика` must not
   appear in the helper code):
   - `НоваяТаблицаДвижений(ИмяРегистра)` — `ТаблицаЗначений` with the register's
     standard movement columns and all dimensions/resources/attributes. Use
     `Метаданные.РегистрыНакопления[ИмяРегистра]`; metadata fields get their
     `Реквизит.Тип`; standard columns may be untyped to avoid invalid
     `ОписаниеТипов` constructors. Include `Период`, `Регистратор`, `НомерСтроки`,
     `Активность`, `ВидДвижения`.
   - `ПроверитьНаборДвижений(ИмяРегистра, Регистратор, Ожидаемые,
     КолонкиИсключения = "")` — fetch actual movements with the existing
     `ДвиженияПоРегистратору`, compare with `ТаблицыЗначенийРавны`, return a test
     result structure with `Результат` and `ОписаниеОшибки`; on mismatch describe
     expected/actual counts.
   - `ПроверитьОтсутствиеДвижения(ИмяРегистра, Регистратор)` — same result structure;
     `Результат = Истина` when there are no movements.
   - `ЗаписатьЗаписьРегистраСведений(ИмяРегистра, Данные)` — create a record manager,
     `ЗаполнитьЗначенияСвойств(Запись, Данные)`, write; return the written record or
     `Неопределено` on error with a log entry.
2. Follow the module's existing comment/format style. Export new functions. Put them in
   the public area.
3. Do NOT modify any other test2 file, do NOT commit in test2, do NOT rebuild
   `app/web/assets/ЮнитТесты.cfe`.
4. Verification: check the module text with the skill's `bsl_ls` if available; if not,
   at least run a syntax-oriented `check-modules` on the extension if the environment
   allows. Do not run the full benchmark. Write the report with the diff path
   `git -C /home/uam/projects/test2 diff -- src/cfe/ЮнитТесты/CommonModules/ЮТ_ТестированиеСервер/Ext/Module.bsl`.

## Task 7: final verification

1. Run the full relevant suites:
   - `python -m pytest template/.claude/skills/query-analyze/scripts/tests -q`
   - `python -m pytest template/.claude/skills/code-analyze/scripts/tests -q`
   - `python -m pytest app/tests/env/test_bsl_check_server.py benchmark/tests/test_bench_metrics.py app/tests/env/test_template_docs.py -q`
   - `python -m pytest benchmark/tests -q`
2. Validate task JSON and `git status`; ensure no unintended files are staged.
3. Dispatch the final whole-branch reviewer on the most capable model with the review
   package from the base commit.
4. Fix Critical/Important findings with one fix subagent; re-review.
5. Leave commits local on `main`; do not push.
