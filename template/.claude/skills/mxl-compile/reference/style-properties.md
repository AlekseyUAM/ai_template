# Style properties: full list

Read when the needed property is not among the common ones described in SKILL.md: indents, protection, pattern, mask, edit format, print behavior.

The key name matches the property name in the export - there are no exceptions.

Value type:

- **number** - integer;
- **yes/no** - `true` / `false`;
- **enum** - one of the listed values, case-insensitive;
- **color** - `#RRGGBB`, `style:Имя`, `web:Имя`, `win:Имя`;
- **line** - `"Solid"` or `{ style, width }`;
- **text** - a string (expanded into the template languages).

## Text and alignment

| Key | Type | Value |
|------|-----|----------|
| `font` | name | Reference to a name from `fonts` |
| `horizontalAlignment` | enum | `Left`, `Center`, `Right`, `Justify`, `Auto` |
| `verticalAlignment` | enum | `Top`, `Center`, `Bottom` |
| `textPlacement` | enum | `Wrap`, `Cut`, `Block`, `Auto` |
| `textOrientation` | number | Rotation in tenths of a degree: `900` = 90° |
| `textColor` | color | Text color |
| `indent` | number | Text indent |
| `autoIndent` | number | Automatic indent |
| `format` | text | Data format: `"ЧЦ=15; ЧДЦ=2"` |
| `editFormat` | text | Edit format |
| `mask` | text | Input mask |
| `markNegatives` | yes/no | Highlight negatives |

## Background and border

| Key | Type | Value |
|------|-----|----------|
| `backColor` | color | Background color |
| `pattern` | enum | `WithoutPattern`, `Solid`, `Pattern1`…`Pattern17` (in Configurator "Pattern 1" ... "Pattern 17") |
| `patternColor` | color | Pattern color |
| `border` | line | All four sides |
| `leftBorder`, `topBorder`, `rightBorder`, `bottomBorder` | line | Separate side |
| `borderColor` | color | Border color |

## Behavior

| Key | Type | Value |
|------|-----|----------|
| `hidden` | yes/no | Hide |
| `protection` | yes/no | Edit protection |
| `print` | yes/no | Print |
| `hyperLink` | yes/no | Hyperlink |
| `detailsUse` | enum | Decryption use: `Cell`, `Row`, `WithoutProcessing` |
| `autoMarkIncomplete` | yes/no | Auto-mark incomplete |
| `bySelectedColumns` | yes/no | By selected columns |
| `columnSizeChange` | enum | `Normal`, `QuickChange` |
| `autoWidthCalculation` | yes/no | Automatic width calculation |
| `widthWeightFactor` | number | Width weight factor |

## Picture in a cell

The keys below set the picture inside a cell; the picture palette itself and drawings on top of the grid are
in `reference/drawings.md`.

| Key | Type | Value |
|------|-----|----------|
| `picIndex` | number | Picture number |
| `pictureSizeMode` | enum | `AutoSize`, `Proportionally`, `RealSize` |
| `picHorizontalAlignment` | enum | `Auto`, `Center`, `Left`, `Right` |
| `picVerticalAlignment` | enum | `Top`, `Center`, `Bottom` |
| `textPosition` | enum | Text position relative to the picture: `Auto`, `Top`, `Right`, `Bottom` |

## What a style does not have

- `width` - a column property, set via `columnWidths`;
- `height` - a row property, set with the `height` key on the row;
- `fillType` - derived from which key sets the cell content
  (`text` / `param` / `template`);
- `containsValue`, `valueType`, `controlType` - properties of a specific cell, not of the shared
  formatting: set with the cell keys `valueType` and `controlType`;
- the drawing line and its sides - drawing properties: set with its `line` and `sides` keys
  (`reference/drawings.md`); a cell has no such property at all.
