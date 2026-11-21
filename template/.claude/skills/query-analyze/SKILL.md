---
name: query-analyze
description: Automatic analysis of 1C queries for violations of optimal query standards. Use to find problems/errors in query text before code review.
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /query-analyze - automatic analysis of 1C queries

Finds violations of the development standards for optimal queries (ITS).
Works in two steps: extracting query text from `.bsl`/DCS-XML and running the
registry of automatic checks.
<!-- @if 1c-md -->

## Priority check: `validate_query`

If MCP `1c-md` with the `validate_query` tool is available (full tool name -
`mcp__1c-md__validate_query`; with a renamed server -
`mcp__<имя>__validate_query`), each extracted query text is first checked by the platform:

1. Extract queries - as described below.
2. Call `validate_query` with `{"queryText": "<текст запроса>"}`.
   - `valid: true` - syntax accepted by the platform.
   - `valid: false` - parse `message` and fix the error.
   - `queryText` is the concatenated query text without leading `|` and without
     outer quotes; the tool is not a 1C literal parser.
3. Then run the local `analyze_query.py` - it checks style and optimization rules
   that `validate_query` does not do.
4. **Every query literal is validated exactly as written in the source**
   (the whole literal, each concatenation part). Substitution is allowed
   only in places where the source text remains a valid query: parameters like
   `&ОсобыйПараметр`, neutral substrings `1 = 1`, `2 = 2`; in code -
   `СтрЗаменить(ТекстЗапроса, "&ОсобыйПараметр", "<фрагмент>")`. Arbitrary
   placeholders (`!НАПРАВЛЕНИЕСОРТИРОВКИ!`, `%1`, `{0}`) are forbidden: text with them does not
   pass `validate_query` and does not open in the query designer. Checking the variant after
   substitution **does not replace** checking the source literal: an invalid literal is a
   `query-not-parseable` finding (warning), not a "placeholder".

**`validate_query` limitation:** it checks against metadata loaded into the
infobase. If metadata was edited in XML sources and not yet loaded into the DB, new
attributes, tabular sections or objects will cause false "not found" errors. Verify
such names against XML (the `meta-info`, `code_index` skills), do not rewrite a
correct query to fit a stale DB. After loading changes into the IB, repeat the check.

If `validate_query` is unavailable (MCP not connected or the extension build lacks the
tool) - work with the local analyzer as described below.
<!-- @endif -->

## Extracting queries

```bash
# Из .bsl-файла или каталога (рекурсивно)
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path src/cf/Catalogs/Товары/Ext/ManagerModule.bsl
# Из макетов СКД (XML)
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path src/cf/Reports -Xml
```

Prints blocks `# <путь>:<строка>` with query text, separated by `--- 8< ---`.

`extract_queries.py` strips leading `//` lines before checking and prints a
warning to stderr (exit code `2`) if the module contains
`Запрос.Текст`/`Новый Запрос` but 0 queries were extracted. This means that
`query-analyze` did not check the query: the absence of findings in such a run is not
"clean". The `-NoFail` flag disables code `2`.

## Query analysis

```bash
# Текст запроса из файла
python "${CLAUDE_SKILL_DIR}/scripts/analyze_query.py" query.txt
# Или из stdin
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path Module.bsl | python "${CLAUDE_SKILL_DIR}/scripts/analyze_query.py" -
```

`analyze_query.py` understands both formats: plain query text is analyzed as a whole,
and the output of `extract_queries.py` (headers `# <путь>:<строка>` and the separator
`--- 8< ---`) is split into separate queries - each is checked independently, the block
header is printed before its findings. This matters for the pipeline above: without
splitting, the concatenated text of several queries does not parse and yields a false
`query-not-parseable`.

Findings are printed as `severity | код | строка N | сообщение`, where the code is a
meaningful rule slug (e.g. `select-star`, `vt-filter-in-where`, `like-leading-wildcard`),
not `std*`. The `-Detailed` flag also shows passed checks. Exit code is non-zero on
`error`-level findings.

**Line numbering.** `строка N` in a finding is counted from the start of the **query
text** (from 1), not from the line in the source `.bsl`/XML. The absolute position in the
file is given by the block header `# <путь>:<строка>` from `extract_queries.py`: add N to
it to get the place in the source.

## Severity scale and verdict

Single scale (as in `bsl_ls` / LSP): `error` = **critical**, `warning` =
**important**, `info` = **minor**. **Any `error`|`warning` finding
(critical|important) blocks acceptance** - see the `reviewer` agent; `info` does not block.

If structural (AST) checks were skipped due to missing `node`/bundle (see
"Dependencies") - this is **not** "checks passed". The reviewer treats analyzer
unavailability as a **critical** finding (a control layer did not run) -> "rework"
until the environment is fixed.

## Dependencies

Structural (AST) checks require:
- `node` in PATH;
- the vendored bundle `scripts/vendor/sdbl_parse.js` (rebuild: `scripts/vendor/build-parser.sh`).

Without them, **only text rules** work (keyword-lowercase, query-one-line); all
structural checks are **SKIPPED** (not considered passed). The tool
prints a warning to stderr in this case.

This differs from the case when the parser **ran and reported a syntax
error** (query text does not parse). Then this is not a skipped layer but a
`query-not-parseable` finding (severity `warning` -> important, blocks acceptance): the query
will not open in the query designer and, as a rule, is incorrect.

## Error classes caught by the AST model

Structural checks use full query parsing by the SDBL parser
(`vendor/sdbl_parse.js`), not regexes. Besides violations of optimal query
standards, common errors are caught that make a query fail to compile or silently
produce a wrong result (typical code-generation mistakes):

- `alias-collides-with-field` (**important**) - a source alias matches the name of a
  field in another table (`… КАК Номенклатура` with a field `Номенклатура` present).
  The platform reports "Ambiguous field". Compares source aliases with the `path`
  of fields/conditions/join keys and their owning table.
- `order-after-totals` (**critical**) - `УПОРЯДОЧИТЬ ПО` comes after `ИТОГИ`
  (section order violated). The platform reports a syntax error. **The parser is
  lenient about this order** (parses without error, silently dropping `УПОРЯДОЧИТЬ`),
  so the check is textual, not via `query-not-parseable`.
- `totals-field-not-aggregated` (**critical**) - in a query with `ИТОГИ`, a field is
  neither in the grouping nor in an aggregate -> on total rows it returns `NULL` (a common
  cause of the runtime error "Преобразование значения к типу Булево…").
- `vt-too-many-params` (**critical**) - more parameters are passed in a virtual table
  call than its signature allows. `РегистрНакопления.*.Остатки` -
  2 parameters `(Период, Условие)`, `*.Обороты` - 4, `*.ОстаткиИОбороты` - 5;
  `РегистрСведений.*.СрезПоследних`/`СрезПервых` - 2; for an accounting register -
  up to 4/8/8/7/5 (composition depends on subconto and correspondence). The platform will not compile such a
  query. A typical code-generation error is passing a dimension filter
  as a separate argument after an empty "Условие":
  `Остатки(&Дата, , Организация = &Организация)`; correct is
  `Остатки(&Дата, Организация = &Организация)`. Fewer parameters are
  allowed: omitted ones get default values.

## What the analyzer does NOT check

Automatic checks work only on query text. Compliance with DB indexes,
task semantics and metadata composition is checked manually - see the
`query-review` skill. In particular, the existence of fields and the correctness of
virtual table resource suffixes (`СуммаОборот`, `СтоимостьРасход`, `…Остаток`)
depend on the register metadata composition (kind, correspondence, subconto) and are
checked in `query-review` via `code_index` (`get_object_structure`).
The exact allowed number of parameters for an accounting register VT (depends on the presence of
subconto and correspondence) is not checked - `vt-too-many-params` catches only
guaranteed extra parameters (above the maximum).
