# Cell notes

A tooltip that the platform shows on hover. Set with the `note` key -
a string, a "language -> text" object or the full form:

```json
{ "col": 1, "text": "Итого", "note": "Сумма без НДС" }
{ "col": 2, "note": { "ru": "на дату документа", "en": "as of the document date" } }
{ "col": 3, "note": { "text": "не более 20%", "style": "жёлтая-подсказка" } }
{ "col": 4, "note": { "text": "…", "autoSize": false,
                      "box": { "top": 58, "left": -175, "bottom": 362, "right": 478 } } }
```

The object is interpreted by its keys - just like cell text in the short row form: if a note
key is present (`text`, `style`, `box`, `autoSize`) -> this is a note description, otherwise the keys
are treated as language identifiers.

| Field | Default | Description |
|------|-----------|----------|
| `text` | - | Tooltip text: a string or a "language -> text" object |
| `style` | tooltip style | Style name from `styles`; without it - the formatting that Configurator provides |
| `autoSize` | `true` | Whether to fit the window size to the text |
| `box` | - | Window offsets: `top`, `left` - position, `bottom`, `right` - size. Without the key the window is placed in the standard way |

Cell coordinates are not set in a note. `autoSize` and `box` are independent: with automatic
size fitting the window position is still stored.
