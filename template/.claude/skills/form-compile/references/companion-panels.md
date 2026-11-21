# Companion panels and extended element tooltip

Any form element can carry its own content in three companion properties: the extended tooltip (`extendedTooltip`), the command bar (`commandBar`) and the context menu (`contextMenu`). All three are set by keys directly on the element object.

```jsonc
{ "table": "Список", "path": "Список",
  "commandBar": { "children": [ … ] },
  "contextMenu": { "children": [ … ] },
  "extendedTooltip": "Двойной клик открывает карточку" }
```

## Extended tooltip (`extendedTooltip`)

A tooltip label next to the element. Two notation forms.

**Text form** - just the tooltip text:

```jsonc
"extendedTooltip": "Укажите ИНН контрагента"
"extendedTooltip": { "ru": "Сумма с НДС", "en": "Amount incl. VAT" }
"extendedTooltip": { "text": "Всего <b>с НДС</b>", "formatted": true }
```

- a string - Russian text;
- `{ "ru": …, "en": … }` - multilingual (like `title`);
- `{ "text": …, "formatted": true }` - formatted text (1C inline markup: `<b>…</>`, `<i>`, `<u>`, `<color web:Red>…</>`, `<bgColor …>`, `<font …>`, `<fontSize …>`, `<link URL>…</>`, `<img …>`; the closing tag is `</>`). `formatted` is needed only when the text contains such markup.

**Own-content form** - an object with layout/appearance/flags, when the tooltip needs sizes, color, a hyperlink, etc.:

```jsonc
"extendedTooltip": {
  "text": "Перейти к инструкции",
  "hyperlink": true,
  "textColor": "web:Blue",
  "events": { "URLProcessing": "ПодсказкаОбработкаНавигационнойСсылки" }
}
```

Own-content object keys (all optional):

| Key | Type | Purpose |
|------|-----|-----------|
| `text` | string/ML | Tooltip text (with `formatted` - formatted) |
| `formatted` | bool | Interpret inline markup in `text` |
| `tooltip` | string/ML | Tooltip of the extended tooltip itself (rare; != the element's regular `tooltip`) |
| `hyperlink` | bool | Make the tooltip a hyperlink |
| `visible` / `enabled` | bool | Visibility / availability of the tooltip |
| `width` / `height` | number | Sizes |
| `maxWidth` / `autoMaxWidth` | number / bool | Maximum width / auto maximum |
| `titleHeight` | number | Title height |
| `horizontalStretch` | bool | Horizontal stretch |
| `verticalAlign` | string | Vertical alignment |
| `textColor` / `font` | string/object | Text color / font (see `references/appearance.md`) |
| `events` | object | Tooltip event handlers, e.g. `{ "URLProcessing": "Имя" }` for a hyperlink tooltip |

## Command bar (`commandBar`)

The element's own command bar (usually of a table or group).

**The value** is an array or an object:

```jsonc
"commandBar": [ { "button": "Создать", "command": "СоздатьЭлемент" } ]

"commandBar": {
  "autofill": false,
  "horizontalAlign": "Right",
  "children": [
    { "button": "Создать", "command": "СоздатьЭлемент" },
    { "buttonGroup": "Печать", "children": [ … ] }
  ]
}
```

- the array `[ … ]` - a short notation for `{ "children": [ … ] }`;
- an object - `children` plus optional `autofill` and `horizontalAlign`.

| Key | Type | Purpose |
|------|-----|-----------|
| `children` | array | Panel content - the regular button grammar (see the main instruction) |
| `autofill` | bool | `false` - suppress panel autofill with standard commands. Optional (by default the panel is autofilled) |
| `horizontalAlign` | string | Horizontal alignment of the content: `Left` / `Center` / `Right`. Optional |

`children` - buttons: `button` (with `command` / `commandName` / `stdCommand`), `buttonGroup`, `popup` - as in the main button instruction.

> For a dynamic list table the panel is suppressed by default (to avoid duplicating the form command bar). To keep an autofilled panel on the table itself, set `commandBar: { "autofill": true }`.

## Context menu (`contextMenu`)

The element's own context menu. The grammar is the same as for `commandBar`, but without `horizontalAlign`.

```jsonc
"contextMenu": [ { "button": "Карта маршрута", "commandName": "CommonCommand.КартаМаршрута" } ]

"contextMenu": {
  "autofill": false,
  "children": [
    { "button": "Скопировать ссылку", "command": "СкопироватьСсылку" }
  ]
}
```

| Key | Type | Purpose |
|------|-----|-----------|
| `children` | array | Menu items - the regular button grammar |
| `autofill` | bool | `false` - suppress menu autofill. Optional |

## Example: a table with its own menu and info banner

```jsonc
{ "table": "Заказы", "path": "Объект.Заказы",
  "extendedTooltip": {
    "text": "Строки с просрочкой выделены <color web:FireBrick>красным</>",
    "formatted": true
  },
  "commandBar": {
    "autofill": false,
    "horizontalAlign": "Right",
    "children": [
      { "button": "Добавить", "command": "ДобавитьЗаказ" },
      { "button": "Удалить", "command": "УдалитьЗаказ" }
    ]
  },
  "contextMenu": {
    "children": [
      { "button": "Открыть документ", "command": "ОткрытьЗаказ" },
      { "buttonGroup": "Экспорт", "children": [
        { "button": "В Excel", "command": "ВыгрузитьВExcel" } ] }
    ]
  } }
```
