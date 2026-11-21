# Predefined items

Add predefined items (Catalog, ChartOfCharacteristicTypes). Existing items and their
identifiers are preserved, new ones get a fresh id.

Inline - a string `(Код) Имя [Наименование]` (batch via `;;`; `[Наименование]` is optional - otherwise it is auto from the name):
```bash
-Operation add-predefined -Value "(001) Основной ;; (002) Резервный [Резервный склад]"
```

JSON - strings and/or objects (for groups with nested items):
```json
{ "add": { "predefined": [
  "(001) Основной",
  { "name": "Группа", "isFolder": true, "childItems": ["(002) Вложенный"] }
] } }
```

Object keys: `name`, `code`, `description`, `isFolder`, `childItems` (tree). The code type (string/numeric)
is taken from the object automatically.
