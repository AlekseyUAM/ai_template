# Layout: areas by coordinates and column sets

Read when an area is not described by a range of consecutive rows or when parts of the document need different column widths.

## Named areas by coordinates (`namedAreas[]`)

For areas that are not described by a range of consecutive rows: a band of columns, a rectangle, a cell, and also ones overlapping with others.

| Field | Required | Description |
|------|:-----:|----------|
| `name` | yes | Area name |
| `rows` | \* | Rows: a number or range `"N-M"`, 1-based |
| `cols` | \* | Columns: a number or range `"N-M"`, 1-based |
| `columnSet` | no | Column set of the area. Without the key it is derived from the covered rows, `""` - no binding |

\* At least one of the axes is required.

**The area type is not specified** - it follows from which axes are set, as in `ТабличныйДокумент.Область()`: rows only -> a band of rows, columns only -> a band of columns, both axes -> a rectangle, single values on both axes -> one cell.

```json
"namedAreas": [
  { "name": "ОбластьПечатиПоВысоте", "rows": "1-48" },
  { "name": "ОбластьПечатиПоШирине", "cols": "1-35" },
  { "name": "HZY", "rows": 9, "cols": "16-17" }
]
```

The range has the same grammar as `columnWidths`, but **only** a number or `"N-M"`: a comma-separated list is forbidden, the area is continuous. The name is required, and at least one axis must be set; violating any of these rules -> a non-zero exit code and a message to stderr.

## Column sets (`columnSets`)

A group of rows can have its own column widths - in 1C this is "individual column width".
Document-level `columns` and `columnWidths` describe the default set; additional ones
are declared in `columnSets`, and an area refers to the needed one with the `columnSet` key - just as
a cell refers to `styles` via `style`.

```json
{
  "columns": 52,
  "columnWidths": { "1": 8 },
  "columnSets": {
    "таблица": { "columns": 52, "columnWidths": { "1": 7, "2-52": 24 } }
  },
  "areas": [
    { "name": "Шапка", "rows": [["Отчёт о продажах"]] },
    { "name": "ТабличнаяЧасть", "columnSet": "таблица",
      "rows": [["№", "Номенклатура"]] }
  ]
}
```

A set is described by the same pair of fields as the document one: `columns` - the number of columns
(it is usually different for sets), `columnWidths` - the widths. The dictionary key is the set name;
in templates produced by decompilation it is an identifier from the source file, when describing
from scratch - any string.

All rows of an area get the area's set, so one area cannot mix
sets. Column positions (`col`, `span`) are checked against the width of the area's OWN set,
not the document one.

A reference to an undeclared set -> a non-zero exit code and a message to stderr.

## Column style (`columnStyles`)

A column carries the same formatting as a cell and a row. Keys use the same range grammar
as `columnWidths`; the value is a style name.

```json
"columnWidths": { "1": 30, "2-3": 15 },
"columnStyles": { "1": "по-центру", "4": "скрытая" }
```

The same key works inside `columnSets`. Width and style are independent: a column can have
only a width, only a style, or both.
