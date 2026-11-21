# Printing: headers/footers and page parameters

Read when a template is prepared for printing: repeating captions at the top and bottom, orientation, margins, scale.

## Headers and footers

The top and bottom headers/footers each have three slots - `left`, `center`, `right` - and common settings:

```json
"header": {
  "font": "мелкий",
  "verticalAlignment": "Bottom",
  "startPage": 2,
  "left": "Слева\nвторая строка",
  "center": "Стр. [&НомерСтраницы] из [&СтраницВсего]",
  "right": { "ru": "Справа", "en": "Right" }
},
"footer": {
  "show": false,
  "center": { "formatted": "<b>Итог</> <colorstyle -16>красным</>" }
}
```

| Field | Default | Description |
|------|-----------|----------|
| `left`, `center`, `right` | - | Slot text: a string, a "language -> text" object or `{ "formatted": … }` |
| `font` | - | Font name from `fonts` - for the whole header/footer |
| `verticalAlignment` | - | Vertical text position: `Top`, `Center`, `Bottom` |
| `show` | `true` | Whether to output the header/footer |
| `startPage` | `1` | Page from which the header/footer is printed |

The text can be multiline (`\n`) and contain fields `[&НомерСтраницы]`, `[&СтраницВсего]`,
`[&Дата]`, `[&Время]` - the platform substitutes them when printing. `{ "formatted": … }` is a formatted
string: the markup lives right in the text (`<b>жирный</>`, `<fontsize 12>`, `<colorstyle -16>`).

## Print parameters

A flat object; the key name matches the property name in the export:

```json
"printSettings": {
  "pageOrientation": "Landscape",
  "topMargin": 500, "leftMargin": 500, "bottomMargin": 500, "rightMargin": 500,
  "headerSize": 1000, "footerSize": 1000,
  "fitToPage": true, "firstPageNumber": 7
}
```

Allowed keys: `pageOrientation`, `scale`, `collate`, `copies`, `perPage`, `topMargin`,
`leftMargin`, `bottomMargin`, `rightMargin`, `headerSize`, `footerSize`, `fitToPage`,
`blackAndWhite`, `printerName`, `paper`, `paperSource`, `pageWidth`, `pageHeight`, `duplexType`,
`pagePlacementAlternation`, `firstPageNumber`. An unknown key is an error. Order in the object does not
matter: the compiler writes properties in the same order as the platform.

## What the DSL does not have

The print area and area repetition when printing (header on every page) are not described:
these settings are set in Configurator and are lost when rebuilding someone else's template. If a task
requires exactly them - edit the template in Configurator, not via the DSL.
