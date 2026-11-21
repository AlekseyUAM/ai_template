# Drawings and pictures

A drawing is an object on top of the cell grid: a picture, a shape or a text label. Its position is set by two
anchors: a cell plus an offset in points from its top-left corner.

```json
"pictures": {
  "знак":  { "ref": "v8ui:Стоп48" },
  "логотип": { "data": "iVBORw0KGgo...", "transparent": { "x": 24, "y": 29 } }
},
"drawings": [
  { "type": "Picture", "picture": "логотип", "name": "Логотип",
    "begin": { "row": 1, "col": 1 },
    "end":   { "row": 3, "col": 2, "dy": 34, "dx": 115 },
    "pictureSize": "Proportionally", "detail": "ПараметрРасшифровки" },
  { "type": "Rectangle", "style": "заливка",
    "line": { "style": "Dashed", "width": 2 },
    "sides": { "left": true, "top": true, "right": false, "bottom": false },
    "begin": { "row": 5, "col": 1 }, "end": { "row": 6, "col": 3 } },
  { "type": "Text", "text": { "ru": "Подпись", "en": "Signature" },
    "begin": { "row": 8, "col": 1 }, "end": { "row": 8, "col": 3, "dy": 12 } }
]
```

| Field | Required | Default | Description |
|------|:-----:|-----------|----------|
| `type` | no | `Picture` | `Picture`, `Rectangle`, `Ellipse`, `Line`, `Text`, `Chart`, `GanttChart` |
| `begin` / `end` | yes | - | Anchors: `row`, `col` (1-based) and offsets `dy`, `dx` in points |
| `picture` | no | - | Name of an entry from `pictures` |
| `pictureSize` | no | `Stretch` | How the picture fills the rectangle: `Stretch`, `AutoSize`, `Proportionally`, `RealSize` |
| `text` | no | - | Label: a string or a "language -> text" object |
| `name` | no | - | Drawing name used to refer to it from code |
| `detail` | no | - | Decryption parameter |
| `style` | no | - | Named style: fill, font, label alignment |
| `line` | no | - | Drawing line (also its border) - like `border` on a cell |
| `sides` | no | - | Which border sides are visible: `left`, `top`, `right`, `bottom` |
| `id` | no | sequential number | Drawing identifier |
| `zOrder` | no | sequential number | Overlap order: the bigger, the higher |

The order in the `drawings` list is the document order; `zOrder` sets who overlaps whom.

An entry in `pictures` is either a reference (`ref`) or the data itself in base64 (`data`). A reference
sets both a predefined platform picture and a common configuration picture - they are written
the same way, with the `v8ui:` prefix. An empty entry `{}` means the picture is not set; this occurs in templates.
Transparency is set with the `transparent` key in one of two forms: `false` - no transparent
background; `{ "x": …, "y": … }` - the color of the pixel at these coordinates inside
the picture is considered transparent (with the "transparent background" checkbox Configurator takes its bottom-right pixel).

Several drawings can use one `pictures` entry - the data is not duplicated in the template.

## Picture in a cell

A picture can be not only on top of the grid but also inside a cell - then it is set by the style, and the
picture itself is taken from the same `pictures` palette:

```json
{
  "columns": 2,
  "pictures": { "стоп": { "ref": "v8ui:Стоп48" } },
  "styles": { "значок": { "picIndex": 1, "picHorizontalAlignment": "Center",
                          "picVerticalAlignment": "Center", "textPosition": "Bottom" } },
  "areas": [{ "rows": [
    [{ "style": "значок", "text": "удалить", "pictureParameter": "Удалить" }]
  ]}]
}
```

- `picIndex` - entry number in `pictures`, 1-based in declaration order;
- `picHorizontalAlignment`, `picVerticalAlignment`, `pictureSizeMode`, `textPosition` - how
  the picture is placed in the cell and where the text is relative to it (values are in `style-properties.md`);
- `pictureParameter` - a key of the CELL itself, not of the style: the parameter name used to insert the picture
  from code, just as `param` inserts text. It coexists with cell text.
