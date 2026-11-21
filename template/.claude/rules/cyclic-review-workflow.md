---
name: cyclic-review-workflow
description: Cyclic workflow develop -> [testing] -> review for iterative code improvement based on review findings.
---

# Cyclic workflow: develop -> [testing] -> review -> develop

For tasks that need iterative code improvement based on test results and reviewer findings.

## Enabling the cyclic workflow

The cyclic workflow is **enabled automatically** if these stages are on:
- `testing: true` AND/OR `review: true`, OR the `update_db: true` flag is on

In this case:
- If `update_db` is on and the infobase load fails -> cycle: develop -> develop
- If `testing` is on and not passed -> cycle: develop -> testing -> develop
- If `testing` is on and passed -> cycle: develop -> testing -> review -> develop
- If `testing` is off but `review` is on -> cycle: develop -> review -> develop
- If review returns `tests`, then after fixing the tests the test author runs the red
  smoke check themselves and records the evidence in `TESTS.md`; the executor checks it before moving
  `tests` to `done` - regardless of whether `testing` is on.

## Execution logic

### 0. Infobase load after `develop` (if `update_db` is on)
```
develop остаётся running, пока загрузка не завершится успехом: task_status.py
не даст поставить develop done без db-update done (загрузка — часть этапа).
После develop исполнитель грузит конфигурацию в ИБ (см. правила
single-agent-workflow и optimized-config-loading); лог — logs/task#<id>/load-config.log:
├─ Ошибка загрузки (в «грязную» базу грузить нельзя; db-update done и develop done
│  не вызывать):
│  ├─ Если iteration этапа develop ≥ 10: отметить develop как failed, остановиться
│  ├─ Иначе: архивировать DEVELOP.md → DEVELOP.<n>.md, где <n> — текущее значение
│  │  iteration в task.json на момент архивирования (до следующего running)
│  ├─ Перезагрузить develop в pending: task_status.py ... develop pending
│  │  (разработчик читает load-config.log и чинит исходники/метаданные)
│  │  iteration инкрементируется автоматически при следующем переводе в running
└─ Успех:
   ├─ task_status.py ... db-update done
   ├─ task_status.py ... develop done --files <изменённые>
   └─ Перейти к следующему включённому этапу (testing/review/docs)
```

### 1. Stage `testing` (if enabled)
```
После завершения testing ищем в TESTING.md строку-ячейку вердикта ровно
«| Вердикт | ✓ ПРОЙДЕНО |» (не голый глиф ✓/✗):
├─ Если строки «| Вердикт | ✓ ПРОЙДЕНО |» НЕТ (тесты не пройдены —
│  строка «| Вердикт | ✗ НЕ ПРОЙДЕНО |»):
│  ├─ Определить возвращаемый этап по виновнику (строка «| Виновник | … |»):
│  │  ├─ «| Виновник | код |»  → возвращаемый этап: develop
│  │  └─ «| Виновник | тест |» → возвращаемый этап: tests
│  ├─ Если iteration возвращаемого этапа ≥ 10: отметить этот этап как failed, остановиться
│  ├─ Архивировать артефакты возвращаемого этапа:
│  │  ├─ виновник код  → DEVELOP.md → DEVELOP.<n>.md, где <n> — текущее iteration
│  │  │  этапа develop в task.json на момент архивирования (до следующего running)
│  │  └─ виновник тест → TESTS.md → TESTS.<n>.md, где <n> — текущее iteration
│  │     этапа tests в task.json на момент архивирования (до следующего running)
│  │     (TESTING.md архивирует сам task_status.py — см. ниже, вручную не дублируй:
│  │     файл станет TESTING.<n>.md, где <n> — iteration этапа testing)
│  └─ Вернуть этап в pending: task_status.py ... <этап> pending
│     (iteration инкрементируется автоматически при следующем переводе в running;
│      develop не трогаем при виновнике тест — код не менялся)
└─ Если строка «| Вердикт | ✓ ПРОЙДЕНО |» есть (все тесты пройдены):
   └─ Перейти к review
```

### 2. Stage `review` (if enabled)
```
После завершения review ищем в REVIEW.md строку-ячейку вердикта ровно
«| Вердикт | ✓ ПРИНЯТО |» (не голый глиф ✓/✗ — он встречается в чек-листе):
├─ Если строки «| Вердикт | ✓ ПРИНЯТО |» НЕТ (вердикт «на доработку» —
│  строка «| Вердикт | ✗ НА ДОРАБОТКУ |»):
│  ├─ Определить возвращаемые этапы по принадлежности находок:
│  │  ├─ код (src/cf, src/cfe кроме тест-модуля) → develop
│  │  ├─ тесты (src/cfe/ЮнитТесты, TESTS.md, TESTING.md) → tests
│  │  ├─ и код, и тесты → develop и tests
│  │  └─ принадлежность неоднозначна → develop и tests
│  ├─ Если iteration любого возвращаемого этапа ≥ 10: пометить его failed, остановиться
│  ├─ Архивировать артефакты возвращаемых этапов: DEVELOP.md/TESTS.md — по
│  │  принадлежности, где <n> — текущее значение iteration этого этапа в task.json
│  │  на момент архивирования (REVIEW.md архивирует сам task_status.py — см. ниже)
│  └─ Вернуть этапы в pending: task_status.py ... <этап> pending
│     (iteration инкрементируется автоматически при следующем переводе в running;
│      порядок выполнения возвращённых этапов: tests (после правки — красный смоук
│      до tests done) → develop → testing (если включён) → review)
└─ Если строка «| Вердикт | ✓ ПРИНЯТО |» есть (одобрено):
   └─ Перейти к следующему включённому этапу (обычно `docs`)
```

> **The cycle executor is you.** There is no separate tool for the cycle:
> archiving `DEVELOP.md`/`TESTS.md` and returning the stage to `pending` is done by the
> executor itself with ordinary file operations (see the rule
> `single-agent-workflow`). **Verdict archiving and the iteration counter are handled by
> `task_status.py` automatically:** it increments the stage's `iteration` field in
> `task.json` when the stage moves to `running` and archives `TESTING.md`/`REVIEW.md`
> when `develop`/`tests` returns to `pending` (see "Archiving artifacts").

## Managing stage iterations

The iteration number is stored in the `iteration` field of each stage in `task.json`.
`task_status.py` increments it automatically on each new `running` of the stage
(and on `restart`) if the stage run history already exists; the first run is `iteration = 1`:

```bash
# Пример: посмотреть текущую итерацию этапа develop
grep -A 20 '"name": "develop"' tasks/task#001/task.json | grep '"iteration"'

# Поле iteration содержит номер итерации этапа (1 = первый запуск)
# Максимум: 10 итераций
```

`done` is only set from `running`. Re-running a stage without returning it to
rework is the `restart` command: it closes the open run, increments
`iteration` and starts a new one. `restart` does not archive `TESTING.md`/`REVIEW.md` -
to return for rework use `pending`, then `running`. `pending`
is used only to return for rework (and archives verdicts). A repeated
run from `failed` (or from `pending`) via `running` also increments
`iteration` if the stage run history already exists.

`task_status.py` **forbids `restart` for `review` if the current `REVIEW.md`
contains the verdict "✗ НА ДОРАБОТКУ"/"НЕ ПРОЙДЕНО"**: this is a return for rework, it
must be done via `pending` (with verdict archiving), then `running`, and not
start a new round on top of the old verdict.

## Archiving artifacts during cycles

Before a new iteration the artifacts are renamed to preserve history:

```bash
# <n> — текущее значение поля iteration этапа в task.json НА МОМЕНТ архивирования
# (до следующего перевода в running, который инкрементирует iteration).
# Пример: iteration = 1 в момент архивирования → файл получает суффикс .1.md:
# DEVELOP.md → DEVELOP.1.md  (виновник код → возврат на develop)
# TESTS.md   → TESTS.1.md    (виновник тест → возврат на tests)
# TESTING.md → TESTING.1.md  (при возврате на develop/tests; <n> — iteration testing)
# REVIEW.md  → REVIEW.1.md   (при возврате из review на доработку)
#
# Новые артефакты создаются с исходным именем: DEVELOP.md, TESTS.md, TESTING.md, REVIEW.md
```

**Automatically by `task_status.py`** when `develop` or `tests` moves to `pending`:

- if `testing.status == "done"` and `TESTING.md` exists -> rename to
  `TESTING.<iteration testing>.md`;
- if `review.status == "done"` and `REVIEW.md` exists -> rename to
  `REVIEW.<iteration review>.md`.

Archiving happens before the status change. If the target file already exists, the command
fails and the status is not changed - sort out the files manually and retry.
If the source file does not exist (or the verdict stage is not `done`, for example on a return due to
a load failure) - nothing happens. Do **not** rename `TESTING.md`/`REVIEW.md` manually
- you will get a conflict with auto-archiving. `DEVELOP.md`/`TESTS.md`
are archived by the executor itself, as before.

Every move of a stage to `running` and every `restart` command adds a
`{"iteration", "started_at", "finished_at"}` record to
`stage["runs"]` - run history for metrics. `finished_at` is set on `done`/`failed`, and also
when the open run is closed by the `pending` command, a new `running` or
`restart`. The `iteration` field increases on a new `running` or `restart`
if run history already exists (otherwise it starts at 1). Auto-archiving of
`TESTING.md`/`REVIEW.md` does not change the `runs[]` field or `iteration`.

## Re-review and disputed findings

- On `review` iteration > 1 the reviewer checks the **delta**: changed files and
  changed queries/procedures in full, previously issued findings - closed/disputed;
  unchanged modules are not audited again. The full checklist is not repeated for unchanged
  files (see `reviewer.md`, "Step 1a. Re-review (iteration > 1)").
- A critical/important finding must contain a verbatim quote and `файл:строка`.
  The review stage checks the quote; without it the finding is downgraded to minor.
- A disputed finding is checked by **one targeted check**, not a new full
  review round; `restart` is not used to bypass a "for rework" verdict -
  only `pending` with verdict archiving (see `single-agent-workflow`).

## Stopping the cycle

The cycle stops on:
- ✅ **Reviewer approval** (the line "| Вердикт | ✓ ПРИНЯТО |" in REVIEW.md)
- ❌ **Reaching the iteration limit** (iteration >= 10 in task.json) -> the stage is marked `failed`
- ❌ **Explicit stop** by the command `python .claude/tools/task_status.py <task_dir> <stage> failed`

## Notes

- The iteration counter starts at 1 in the stage's `iteration` field in `task.json`
- `task_status.py` increments `iteration` when the stage moves to `running`
- The maximum of 10 iterations prevents infinite loops
- On every return to develop, DEVELOP.md is updated with the iteration number;
  on a return to tests - TESTS.md; TESTING.md/REVIEW.md verdicts are archived by
  `task_status.py` automatically
- The history of all versions is preserved via archive files (DEVELOP.1.md, DEVELOP.2.md, etc.)
- The developer sees the iteration number in the artifacts
- The `testing` stage verdict (issued by the executor) and the reviewer checklist produce findings on every iteration
