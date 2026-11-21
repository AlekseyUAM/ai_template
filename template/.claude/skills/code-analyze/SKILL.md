---
name: code-analyze
description: Automatic analysis of 1C BSL code for violations of development standards. Use to find problems/errors/potential issues in modules before code review. Complements bsl_ls diagnostics - checks what it lacks.
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /code-analyze - automatic analysis of 1C BSL code

Finds violations of 1C development standards **that are not in BSL Language
Server (bsl_ls)**. Works on a structural module model (methods, loops,
declarations) built by a lightweight Python parser - no external dependencies.

This is the first review step. Requirements that a script cannot check (metadata,
task semantics, configuration context) are moved to the manual checklist of the
`bsl-coding-standards` skill.

## Module analysis

```bash
# Один .bsl-файл
python "${CLAUDE_SKILL_DIR}/scripts/analyze_code.py" src/cf/Catalogs/Товары/Ext/ManagerModule.bsl
# Каталог (рекурсивно по *.bsl)
python "${CLAUDE_SKILL_DIR}/scripts/analyze_code.py" src/cf/CommonModules
# Из stdin
cat Module.bsl | python "${CLAUDE_SKILL_DIR}/scripts/analyze_code.py" -
```

Findings are printed as `severity | код | строка | сообщение`. The `-Detailed` flag
also shows passed rules. Exit code is not 0 when there are `error`-level findings
(suppressed by the `-NoFail` flag). When analyzing a directory, blocks are separated by
`--- 8< ---`.

## Rule registry

Rules are declared in `scripts/rules.py` via the decorator `@rule(code, severity,
title)`; each returns a list of `Finding`. Codes are meaningful slugs (not `std*`).

| Code | Severity | What it catches |
|---|---|---|
| `string-concat-in-loop` | warning | Accumulator concatenation `Х = Х + …` in a loop body, except numeric accumulators (`Сумма`, `Стоимость`, `Количество`, etc.) |
| `tv-find-multiple-columns` | warning | `ТаблицаЗначений.Найти(.., "Кол1, Кол2")` - index on a single field |
| `var-name-starts-with-underscore` | warning | Variable/parameter name starts with `_` |
| `var-name-single-char` | info | Single-character variable/parameter name, except loop counters |
| `raise-in-cancel-event` | info | `ВызватьИсключение` in a handler with the `Отказ` parameter |
| `error-description-without-stack` | info | Call to `ОписаниеОшибки()` instead of `ПодробноеПредставлениеОшибки()` |
| `type-check-via-metadata-name` | warning | Type check via `Метаданные().Имя = "…"` instead of `ТипЗнч() = Тип()` |
| `column-copy-loop` | info | Copying value table rows by iterating `.Колонки` instead of `ЗаполнитьЗначенияСвойств` |
| `char-code-literal` | info | `Символ(10)` instead of the system set `Символы.*` |
| `attachable-handler-prefix` | info | Handler from `УстановитьДействие` without the `Подключаемый_` prefix |
| `record-manager-in-loop` | info | `СоздатьМенеджерЗаписи()` in a loop instead of `НаборЗаписей` |
| `new-applied-object-via-constructor` | warning | `Новый("ДокументОбъект.…")` instead of the manager method |
| `explicit-write-in-posting` | warning | Explicit `.Записать()` in `ОбработкаПроведения` |
| `system-enum-value` | error | Nonexistent value of a system enum/value set: `<Тип>.<Значение>` |
| `reserved-system-name` | error | Variable/parameter/procedure/function/loop label name matches a system enum or value set |
| `record-set-in-loop` | info | `СоздатьНаборЗаписей()` in a loop instead of writing as one set |
| `sequence-boundary-in-posting` | info | `УстановитьГраницу` of a sequence in a posting handler |
| `query-execute-in-loop` | warning | `Запрос.Выполнить()`/`.ВыполнитьПакет()` in a loop body |
| `query-new-in-loop` | warning | `Новый Запрос` in a loop body |
| `query-execute-in-loop-via-call` | warning | call in a loop to a local module method that executes a query (depth 1) |
| `query-new-in-loop-via-call` | warning | call in a loop to a local module method that creates `Новый Запрос` (depth 1) |
| `user-message-via-constructor` | info | `Новый СообщениеПользователю` instead of `ОбщегоНазначения.СообщитьПользователю` |
| `use-before-assignment` | warning | Variable is initialized only in an `Если` branch without `Иначе` and is used after the block - `Неопределено` is possible |

## System enums and value sets

The `system-enum-value` and `reserved-system-name` rules use
`scripts/system_enums.json` - a snapshot of platform help (664 enums,
2914 values; 8 sets, 517 values; ru/en). **Do not read this file** - it is read
by the script. To update data, see `scripts/tools/README.md`.

Metadata names are checked against the XML dump (for task changes - `--changed`):

```bash
python .claude/skills/code-analyze/scripts/check_metadata_names.py --changed
```

Exit code 1 means findings exist; the line format is compatible with `analyze_code.py`.

## Severity scale and verdict

Single scale (as in `bsl_ls` / LSP static analysis): `error` = **critical**, `warning` =
**important**, `info` = **minor**. Verdict rule: **any `error` or `warning` finding
(critical|important) blocks acceptance** - see the `reviewer` checklist. `info`
(minor) does not block. Script exit code is non-zero only on `error`; `warning`
blocks at the reviewer verdict level, not at the exit code level.

## Analysis boundaries

The parser provides module structure (methods, block nesting, Перем declarations,
parameters), but **not a full expression AST**. Checks that require data-flow analysis
or knowledge of metadata/configuration are not performed automatically - they are in
the `bsl-coding-standards` checklist. The analyzer does not duplicate bsl_ls:
overlapping requirements are covered by bsl_ls diagnostics (run `mcp__bsl_ls__check`
separately).

The `use-before-assignment` rule is conservative: it catches only a single conditional
assignment - parameters, `Перем` declarations, loop variables, repeated assignments
and `Иначе`/`ИначеЕсли` branches exclude a finding.

## Dependencies

Python 3.6+ only. Node/bundles not needed.

## Tests

```bash
cd "${CLAUDE_SKILL_DIR}/scripts" && python -m pytest tests/ -q
```
Each rule is covered by tests for a correct and an incorrect example from the
standard.
