# Special "document/sensor" fields

Fields for displaying special data: spreadsheet document, HTML, text, formatted document, progress indicator, slider. Each is bound to an attribute of its own platform type.

Structurally these are regular fields - they support the common field skeleton (`path`, `title`, `titleLocation`, `readOnly`/`enabled`/`visible` flags, `layout`, appearance, events). Below are only the `type` key (the element name is set by the key value) and the own scalars of each family. All scalars are optional.

| Type key | Attribute type |
|-----------|---------------|
| `spreadsheet` | `mxl:SpreadsheetDocument` (ТабличныйДокумент) |
| `html` | `string` |
| `textDoc` | `d5p1:TextDocument` (ТекстовыйДокумент) |
| `formattedDoc` | `fd:FormattedDocument` (ФорматированныйДокумент) |
| `progressBar` | number |
| `trackBar` | number |

## spreadsheet - spreadsheet document field

Viewing/editing a spreadsheet document (report, print form).

```json
{ "spreadsheet": "ТаблицаОтчета", "path": "ТаблицаОтчета",
  "titleLocation": "none", "readOnly": true,
  "output": "Disable", "protection": true }
```

| Key | Type | Purpose |
|------|-----|-----------|
| `output` | string | Output usage: `Enable` / `Disable` |
| `protection` | bool | Protection against changes |
| `edit` | bool | Allow editing |
| `showGrid` | bool | Show the grid |
| `showHeaders` | bool | Show row/column headers |
| `showGroups` | bool | Show groupings |
| `showRowAndColumnNames` | bool | Show row and column names |
| `showCellNames` | bool | Show cell names |
| `verticalScrollBar` / `horizontalScrollBar` | string | Scroll bar mode |
| `viewScalingMode` | string | View scaling mode |
| `selectionShowMode` | string | Selection display mode |
| `pointerType` | string | Pointer type |
| `enableDrag` / `enableStartDrag` | bool | Allow dragging / starting a drag |

## html - HTML document field

HTML viewing. The attribute is a string (contains HTML text or an address).

```json
{ "html": "Просмотр", "path": "СодержимоеHTML", "titleLocation": "none",
  "output": "Enable", "warningOnEditRepresentation": false }
```

| Key | Type | Purpose |
|------|-----|-----------|
| `output` | string | Output usage: `Enable` / `Disable` |
| `warningOnEditRepresentation` | bool | Warn when the presentation changes |

## textDoc - text document field

Viewing/editing a text document.

```json
{ "textDoc": "Текст", "path": "ТекстДокумента", "editMode": "Edit" }
```

| Key | Type | Purpose |
|------|-----|-----------|
| `editMode` | string | Edit mode (e.g. `Edit` / `View`) |

## formattedDoc - formatted document field

Viewing/editing a formatted document.

```json
{ "formattedDoc": "Описание", "path": "ФорматированноеОписание", "editMode": "Edit" }
```

| Key | Type | Purpose |
|------|-----|-----------|
| `editMode` | string | Edit mode (e.g. `Edit` / `View`) |

## progressBar - progress indicator field

Progress indicator. The attribute is numeric.

```json
{ "progressBar": "Прогресс", "path": "Прогресс",
  "minValue": 0, "maxValue": 100, "showPercent": true }
```

| Key | Type | Purpose |
|------|-----|-----------|
| `minValue` / `maxValue` | number | Minimum / maximum value |
| `showPercent` | bool | Show percentages |

## trackBar - slider field

Slider control. The attribute is numeric.

```json
{ "trackBar": "Масштаб", "path": "Масштаб",
  "minValue": 20, "maxValue": 400, "markingStep": 20 }
```

| Key | Type | Purpose |
|------|-----|-----------|
| `minValue` / `maxValue` | number | Minimum / maximum value |
| `step` | number | Change step |
| `largeStep` | number | Large step |
| `markingStep` | number | Marking step |
| `markingAppearance` | string | Marking appearance |
