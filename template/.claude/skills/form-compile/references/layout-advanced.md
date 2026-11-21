# Advanced layout

Fine-tuning of element placement inside a parent beyond the basic geometry (`width`/`height`/`horizontalStretch`/`verticalStretch`/`visible`/`enabled` and group/page orientations - they are in the main instruction). All keys below are set directly on the element and are **optional** - without them the platform's default behavior applies.

## Alignment inside a parent

There is a distinction between **alignment of the element itself** in its allocated cell and **alignment of the element's content**.

| Key | Values | What it aligns |
|------|----------|-----------------|
| `groupHorizontalAlign` | `Left` / `Center` / `Right` | Horizontal position of the **element** in the parent group (when the element is narrower than the available space) |
| `groupVerticalAlign` | `Top` / `Center` / `Bottom` | Vertical position of the **element** in the parent group |
| `horizontalAlign` | `Left` / `Center` / `Right` | Alignment of the **content** (text/value) inside the element itself |
| `verticalAlign` | `Top` / `Center` / `Bottom` | Vertical alignment of the content inside the element |

`group*Align` answers the question "where to move a non-stretched element in its cell", `horizontalAlign`/`verticalAlign` - "how to place the text inside the element". These are different axes of adjustment, they are often combined.

```json
{ "button": "ОК", "groupHorizontalAlign": "Right" }
{ "input": "Сумма", "path": "Объект.Сумма", "horizontalAlign": "Right" }
{ "label": "Итого", "groupHorizontalAlign": "Center", "horizontalAlign": "Center" }
```

## Maximum size limit

By default a stretching element has an auto-computed width/height limit. To set a hard limit or remove the auto limit entirely:

| Key | Values | Purpose |
|------|----------|-----------|
| `maxWidth` | number | Hard maximum of the element width |
| `maxHeight` | number | Hard maximum of the element height |
| `autoMaxWidth` | `false` | Disable the auto width limit (the element stretches without an upper bound) |
| `autoMaxHeight` | `false` | Disable the auto height limit |

`autoMaxWidth: false` is needed, for example, for a wide multiline field or an input field stretched across the whole form, so that the platform does not "press" it against the auto limit. Specify only the deviation from the default; there is no need to write the usual value `true`.

```json
{ "input": "Комментарий", "path": "Объект.Комментарий", "multiLine": true,
  "horizontalStretch": true, "autoMaxWidth": false }
{ "input": "Поиск", "path": "СтрокаПоиска", "horizontalStretch": true, "maxWidth": 600 }
```

## Behavior on input and activation

| Key | Values | Purpose |
|------|----------|-----------|
| `skipOnInput` | `true` / `false` | Skip the element when traversing by Enter/Tab (focus does not pass through it). Specify explicitly, including `false` to return to the traversal a field that the platform would skip |
| `defaultItem` | `true` | The element gets focus by default when the form opens (a field/table for immediate input) |

```json
{ "input": "Идентификатор", "path": "Объект.Идентификатор", "skipOnInput": true }
{ "input": "Штрихкод", "path": "Штрихкод", "defaultItem": true }
```

`skipOnInput: true` - for service/computed fields that are visible but not edited by keyboard input in the general flow. `defaultItem: true` is set on one form element - the point from which the user starts working.

## Dragging

| Key | Values | Purpose |
|------|----------|-----------|
| `enableStartDrag` | `true` | Allow starting a drag from the element (a drag-n-drop source) |

For tables, row acceptance/movement is controlled by table keys (`enableDrag`, `changeRowOrder`) - see the main instruction; `enableStartDrag` is a general low-level flag "this element can be a drag source".

## Fixing a column in a table (`fixingInTable`)

A property of a column field inside a table: fix the column to an edge so that it does not go away on horizontal scrolling.

| Values |
|----------|
| `None` (default - not fixed) / `Left` / `Right` |

```json
{ "table": "Товары", "path": "Объект.Товары", "columns": [
    { "input": "Номенклатура", "path": "Объект.Товары.Номенклатура", "fixingInTable": "Left" },
    { "input": "Количество", "path": "Объект.Товары.Количество" },
    { "input": "Сумма", "path": "Объект.Товары.Сумма", "fixingInTable": "Right" } ] }
```

Fix key columns (the identifying one on the left, the total one on the right) so that they stay visible when scrolling a wide table.

## Column cells: header and footer

For a column field inside a table (and `columnGroup`) - placement in the header/footer and alignment of cell text. Apply only to elements inside table `columns`.

| Key | Values | Purpose |
|------|----------|-----------|
| `showInHeader` | `true` / `false` | Show the column in the table header |
| `showInFooter` | `true` / `false` | Show the column in the footer (needed for totals; the table's own footer is enabled by `footer: true`) |
| `headerHorizontalAlign` | `Left` / `Right` / `Center` / `Auto` | Alignment of the text in the column header |
| `footerHorizontalAlign` | `Left` / `Right` / `Center` | Alignment of the text in the column footer |
| `autoCellHeight` | `true` / `false` | Cell auto height (wrapping content to several lines) |

```json
{ "table": "Товары", "path": "Объект.Товары", "footer": true, "columns": [
    { "input": "Номенклатура", "path": "Объект.Товары.Номенклатура", "autoCellHeight": true },
    { "input": "Сумма", "path": "Объект.Товары.Сумма",
      "headerHorizontalAlign": "Right", "showInFooter": true, "footerHorizontalAlign": "Right" } ] }
```

## Adaptive importance (`displayImportance`)

| Values |
|----------|
| `VeryHigh` / `High` / `Usual` / `VeryLow` / `Low` |

The element priority during adaptive form re-layout on narrow/mobile screens: elements with lower importance collapse/hide first. Applies to any element.

```json
{ "input": "Комментарий", "path": "Объект.Комментарий", "displayImportance": "Low" }
```
