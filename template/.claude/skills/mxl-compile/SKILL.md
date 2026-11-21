---
name: mxl-compile
description: Compile a spreadsheet document (MXL) from a JSON definition. Use when you need to create a print form template
argument-hint: <JsonPath> <OutputPath>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /mxl-compile - Template compiler from DSL

Accepts a compact JSON template definition (areas, parameters, styles) -> generates Template.xml of a 1C spreadsheet document: palettes, indexes, merges, namespace.

## Usage

```
/mxl-compile <JsonPath> <OutputPath>
```

## Parameters

| Parameter  | Required     | Description                        |
|------------|:------------:|------------------------------------|
| JsonPath   | yes          | Path to the JSON template definition |
| OutputPath | yes          | Path for generating Template.xml   |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/mxl-compile.py" -JsonPath "<путь>.json" -OutputPath "<путь>/Template.xml"
```

## Workflow

1. Write the JSON definition (Write tool) -> file `.json`
2. Call `/mxl-compile` to generate Template.xml
3. Call `/mxl-validate` to validate correctness
4. Call `/mxl-info` to verify the structure

**If the template is created from an image** (screenshot, scan of a print form) - first call `/img-grid` to overlay a grid, use it to determine column boundaries and proportions, then use `"Nx"` widths + `"page"` for automatic size calculation.

## What to read per task

Below is everything needed for a typical template. The rest lives one file per task; read
only your own:

| Task | Keys | File |
|---|---|---|
| Style property outside the common ones: indent, protection, pattern, mask, print behavior | - | `reference/style-properties.md` |
| Area not described by a row range; own column widths for part of the document | `namedAreas`, `columnSets`, `columnSet` | `reference/layout.md` |
| Headers/footers, orientation, margins, scale | `header`, `footer`, `printSettings` | `reference/print.md` |
| Picture, shape or text label on top of the grid; picture in a cell | `pictures`, `drawings`, `pictureParameter` | `reference/drawings.md` |
| Cells for user data input | `valueType`, `controlType`, `value` | `reference/input-cells.md` |
| Collapsible row or column groups | `rowGroups`, `columnGroups` | `reference/groups.md` |
| Tooltip on a cell | `note` | `reference/notes.md` |

## Example

```json
{
  "columns": 5,
  "columnWidths": { "1": 5, "2": 40, "3-5": 12 },
  "fonts": { "жирный": { "face": "Arial", "size": 10, "bold": true } },
  "styles": {
    "шапка":  { "font": "жирный", "horizontalAlignment": "Center", "textPlacement": "Wrap", "border": "Solid" },
    "клетка": { "border": "Solid" },
    "число":  { "border": "Solid", "horizontalAlignment": "Right", "format": "ЧЦ=15; ЧДЦ=2" },
    "итог":   { "font": "жирный", "horizontalAlignment": "Right", "topBorder": "Solid" }
  },
  "areas": [
    { "name": "Заголовок", "rows": [
      { "height": 20, "cells": [{ "col": 1, "span": 5, "style": "шапка", "param": "ЗаголовокОтчёта" }] },
      {}
    ]},
    { "name": "ШапкаТаблицы", "rows": [
      { "rowStyle": "шапка", "cells": ["№", "Номенклатура", "Количество", "Цена", "Сумма"] }
    ]},
    { "name": "Строка", "rows": [
      { "rowStyle": "клетка", "cells": [
        { "col": 1, "param": "НомерСтроки" },
        { "col": 2, "param": "Товар", "detail": "Номенклатура" },
        { "col": 3, "style": "число", "param": "Количество" },
        { "col": 4, "style": "число", "param": "Цена" },
        { "col": 5, "style": "число", "param": "Сумма" }
      ]}
    ]},
    { "name": "Итого", "rows": [
      { "rowStyle": "итог", "cells": [null, null, null, "Итого:", "{Всего}"] }
    ]}
  ]
}
```

The table header and total are written positionally - the position comes from the order, `col` is not needed;
the table row is written with cells that have `col` because they have different styles and decryption.

## DSL structure

```
{ columns, page, defaultWidth, columnWidths, columnStyles, textLanguages,
  fonts:  { имя: { face, size, bold, italic, underline, strikeout } | { ref } },
  styles: { имя: { font, horizontalAlignment, verticalAlignment, textPlacement,
                   border, leftBorder, topBorder, rightBorder, bottomBorder,
                   borderColor, backColor, textColor, format } },
  areas: [{ name, columnSet, rows: [
    { height, hidden, rowStyle, empty, cells: [
      { col, span, rowspan, style, param, detail, text, template, note,
        valueType, controlType, value, pictureParameter } ] } ] }],
  namedAreas, columnSets, rowGroups, columnGroups, header, footer, printSettings,
  pictures, drawings
}
```

Top level: `columns` is required, the rest as needed.

| Key | Description |
|---|---|
| `columns` | Number of layout columns by default |
| `page` | Page format: `"A4-landscape"` (780), `"A4-portrait"` (540) or a number. Computes `defaultWidth` itself from the sum of `"Nx"` proportions |
| `defaultWidth` | Default column width (10) |
| `columnWidths` | Widths: 1-based keys (`"1"`, `"3-14"`, `"5,7,9"`), value - a number or `"2x"` (fraction of `defaultWidth`) |
| `columnStyles` | Style for a whole column: same range keys, value - style name |
| `textLanguages` | Languages into which text given as a string is expanded (default `["ru"]`) |
| `areas` | Areas - ranges of consecutive rows, in document order |

## Areas, rows, cells

**Area** (`areas[]`) - a range of consecutive rows: `name` (optional; with a name the area
is available as `Макет.ПолучитьОбласть("Имя")`) and `rows`. An area without a name is just a piece of the grid.

**Row** (`rows[]`): `height`, `hidden`, `rowStyle`, `cells`. An empty row is `{}`,
and `{ "empty": 3 }` replaces three in a row. `height` and `hidden` are properties of the row itself; a cell
has none of them.

**Cell** (`cells[]`):

| Key | Description |
|---|---|
| `col` | Column position, 1-based |
| `span` / `rowspan` | Merge right / down |
| `style` | Style name; overrides `rowStyle` for this cell |
| `param` | Fill parameter - `Область.Параметры.Имя = …` |
| `text` | Static text: a string or a "language -> text" object |
| `template` | Text with `[Параметр]` inserts |
| `detail` | Decryption parameter; can be set without `param` |

Content is set by exactly one of `param` / `text` / `template`; a cell without them is
empty (needed, for example, for a border). The empty string `"text": ""` is also text, not
the absence of text.

### Short form: positional cell list

Position comes from the order, `col` is not needed:

| Element | Meaning |
|---|---|
| `"текст"` | Static text |
| `{ "ru": "…", "en": "…" }` | The same text in several languages |
| `"{Имя}"` | Fill parameter |
| `">"` | Continuation of the cell on the left - increases its `span` |
| `"|"` | Continuation of the cell above - increases its `rowspan` |
| `null` | Skip column |
| `{ … }` | Regular cell without `col` - when `style`, `detail`, `template` are needed |

```json
"rows": [
  ["Вид", "Остаток", ">", "Итог"],
  ["|",   "начало",  "конец", "|"],
  ["{Вид}", "{Нач}", "{Кон}", "{Итог}"]
]
```

Here "Вид" and "Итог" are merged vertically, "Остаток" - horizontally across two columns.

The positional list is a way to write CELLS, not a row. If the row has no properties of its own, it
is the row (as in the example above). If `height`, `hidden` or `rowStyle` are needed, the same
list is placed in `cells`:

```json
{ "rowStyle": "итог", "cells": [null, null, null, "Итого:", "{Всего}"] }
```

### `rowStyle` - row formatting

The style applies to the WHOLE row width: columns without explicit cells get it too - this is how
solid borders in a tabular section come out. It also becomes the formatting of the row itself. Cells with `rowspan`
from previous rows are skipped.

## Formatting

A cell, row and column refer to the same named style: a cell with the `style` key,
a row with `rowStyle`, a column via `columnStyles`.

**Font** (`fonts.<имя>`): `face` (Arial), `size` (10), `bold`, `italic`, `underline`,
`strikeout`. Or a reference instead of a description: `{ "ref": "style:TextFont" }`,
`{ "ref": "sys:DefaultGUIFont" }`. The `"default"` font is used when the style does not specify its own.

**Common style keys** - the key name matches the property name in the export, enum values
are case-insensitive:

| Key | Value |
|---|---|
| `font` | Name from `fonts` |
| `horizontalAlignment` | `Left`, `Center`, `Right`, `Justify`, `Auto` |
| `verticalAlignment` | `Top`, `Center`, `Bottom` |
| `textPlacement` | Long text: `Wrap` (wrap), `Cut` (cut), `Block`, `Auto` |
| `border` | Border on all sides |
| `leftBorder`, `topBorder`, `rightBorder`, `bottomBorder` | Separate side |
| `borderColor` | Border color |
| `backColor`, `textColor` | Background and text color |
| `format` | 1C data format: `"ЧЦ=15; ЧДЦ=2"`, `"ДФ=dd.MM.yyyy"` |

**Border**: `"Solid"` (width 1) or `{ "style": "Solid", "width": 2 }`. Line styles: `None`,
`Solid`, `Dotted`, `Dashed`, `DashDotted`, `DashDottedDotted`, `ThinDashed`, `LargeDashed`,
`ThickDashed`, `Double`. Sides can always be set separately: the compiler will collapse the four matching ones itself.

**Color** - platform notation: `#RRGGBB`, `style:ИмяСтиля` (configuration style item),
`web:Имя`, `win:Имя`. A nonexistent name will be rejected by the platform on load.

```json
"styles": {
  "шапка":  { "font": "жирный", "horizontalAlignment": "Center", "backColor": "#EBEBEB" },
  "рамка":  { "border": { "style": "Solid", "width": 2 } },
  "снизу":  { "bottomBorder": "Dotted" }
}
```
