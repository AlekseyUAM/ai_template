---
name: skd-info
description: Analyze the structure of a 1C data composition schema (DCS) - data sets, fields, parameters, variants. Use to understand a report - data source (query), available fields, parameters
argument-hint: <TemplatePath> [-Mode overview|query|fields|links|calculated|resources|params|variant|templates|trace|full] [-Name <dataset|variant|field|group>] [-Raw]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /skd-info - Data composition schema analysis

Reads Template.xml of a data composition schema (DCS) and outputs a compact summary. Replaces the need to read thousands of lines of XML.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `TemplatePath` | Path to Template.xml or the template directory (auto-resolved to `Ext/Template.xml`) |
| `Mode` | Analysis mode (default `overview`) |
| `Name` | Name of the data set (query), field (fields/calculated/resources/trace), variant (variant) or grouping/field (templates) |
| `Batch` | Query batch number, 0 = all (query only) |
| `Raw` | (query only) the raw query text in full, without headings/table of contents/batch separators. For dumping to `.sql` and returning via `skd-edit set-query @file` |
| `Limit` / `Offset` | Pagination (150 lines by default; `-Raw` is not truncated) |
| `OutFile` | Write the result to a file (UTF-8 BOM) |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/skd-info.py" -TemplatePath "<путь>"
```

With a mode specified:
```bash
... -Mode query -Name НоменклатураСЦенами
... -Mode query -Name ДанныеТ13 -Batch 3
... -Mode query -Name ДанныеТ13 -Raw -OutFile query.sql
... -Mode fields -Name КадастроваяСтоимость
... -Mode calculated -Name КоэффициентКи
... -Mode resources -Name СуммаНалога
... -Mode trace -Name "Коэффициент Ки"
... -Mode variant -Name 1
... -Mode templates
... -Mode templates -Name ВидНалоговойБазы
```

## Modes

| Mode | Without `-Name` | With `-Name` |
|-------|-------------|-----------|
| `overview` | Navigation map of the schema + Next hints | - |
| `query` | - | Set query text (with a batch table of contents); `-Raw` - a clean dump for editing |
| `fields` | Map: field names by data set | Field detail: data set, type, role, format |
| `links` | All data set links | - |
| `calculated` | Map: calculated field names | Expression + title + restrictions |
| `resources` | Map: resource names (`*` = group formulas) | Aggregation formulas by grouping |
| `params` | Parameter table: type, value, visibility | - |
| `variant` | List of variants | Grouping structure + filters + output |
| `templates` | Map of template bindings (field/group) | Template content: rows, cells, expressions |
| `trace` | - | Full chain: data set -> calculation -> resource |
| `full` | Full summary: overview + query + fields + resources + params + variant | - |

Pattern: without `-Name` - a map/index, with `-Name` - details of a specific element. The `full` mode combines 6 key modes in one call.

## Typical workflow

1. `overview` - understand the structure, see hints
2. `trace -Name <поле>` - find out how a report column is calculated (from the title to the query in one call)
3. `query -Name <набор>` - view the SQL query text
4. `variant -Name <N>` - view the variant groupings and filters

Query rework (round-trip): `query -Name <набор> -Raw -OutFile q.sql` ->
edit `q.sql` -> `/skd-edit <tpl> -Operation set-query -Value "@q.sql"`. The
`-Raw` flag returns the query in full without decorations, so dump <-> return
are exact (including multi-batch queries with temporary tables).

## Compliance check against the specification

Before submitting the report, compare the output with the specification columns:

1. `variant -Name <вариант>` - the variant selection and groupings. Every selection field must
   be a specification column; an extra/missing one is a defect. If a calculated field is selected with
   a title equal to the name of another column - this is a field substitution (see `trace`).
2. `query -Name <набор>` - the query text: there must be no `СГРУППИРОВАТЬ ПО` over
   a virtual table of an accumulation register (the VT already aggregates) and no fields beyond the specification.
3. `fields` / `calculated` / `resources` - exact field names and titles.
4. For automatic comparison - `skd-validate <tpl> -ExpectedFields "<колонки ТЗ>"`.

## Verification

```
/skd-info <path>                            — overview (точка входа)
/skd-info <path> -Mode trace -Name <field>  — трассировка поля
```
