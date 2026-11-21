# Dynamic list

An attribute with `type: "DynamicList"` (usually `main: true`) is the base of a list form. The `settings` object describes the data source and list settings. The minimum is to specify the source:

```json
{ "name": "Список", "type": "DynamicList", "main": true,
  "settings": { "mainTable": "Catalog.Контрагенты" } }
```

A table element (`table`) is bound to the list, referencing the attribute via `path` - see the main instruction.

## Data source

Two mutually exclusive modes:

**Table-oriented** - the main metadata table:

```json
"settings": { "mainTable": "Catalog.Контрагенты" }
```

**Query-based** - an arbitrary query:

```json
"settings": {
  "query": "ВЫБРАТЬ Т.Ссылка, Т.Наименование, Т.Сумма ИЗ Документ.Заказ КАК Т ГДЕ Т.Сумма > &Порог",
  "mainTable": "Document.Заказ"
}
```

| Key | Type | Purpose |
|------|-----|-----------|
| `mainTable` | string | Main table (`Catalog.X` / `Document.X` / …). Can be used together with `query` |
| `query` | string | Query text. Supports `@file.sql` (path to a query file next to the JSON) |
| `keyType` | string | Query list without `mainTable`: set key type - `FieldValue` / `RowKey` / `RowNumber` |
| `keyFields` | array | Set key fields (for `keyType` without `mainTable`) |

Query parameters (`&Имя`) are set in `parameters` (below).

`"dynamicDataRead": false` disables dynamic reading (the list is read by a regular query, without background refresh) - needed for heavy/aggregate queries.

## Query parameters (`parameters`)

Values for the query text's `&параметров`. Shorthand `"Имя [Заголовок]: тип = Значение"` (everything except the name is optional) or an object:

```json
"settings": {
  "query": "… ГДЕ Т.Артикул = &Артикул И Т.Цена ПОДОБНО &Маска",
  "parameters": [
    "Артикул",
    "Маска: string = %",
    { "name": "ВидЦен", "valueListAllowed": true },
    { "name": "Период", "type": "dateTime" }
  ]
}
```

Object keys: `name`, `title`, `type` (type grammar - see the main instruction), `value`, `valueListAllowed` (allow a value list), `availableValues` (`[{ value, presentation }]`), `expression`, `use`.

## Parameter values in settings (`dataParameters`)

Preset parameter values at the list settings level. Shorthand `"Имя = Значение"` or an object `{ parameter, value?, use?, viewMode? }`:

```json
"dataParameters": [ "Организация = _", "ВидЦен" ]
```

## Set fields (`fields`)

Usually fields are derived from the source automatically - `fields` is needed **only to override** the properties of an individual field:

```json
"fields": [
  { "field": "Сумма", "title": "Сумма, руб", "appearance": { "Формат": "ЧДЦ=2" } },
  { "field": "Остаток", "valueType": "number(15,2)" }
]
```

Field keys: `field`, `dataPath`, `title`, `valueType`, `appearance` (as in conditional appearance), `presentationExpression`, `inputParameters` (link by choice parameters), `typeLink` (`{ field, linkItem }` - type link, e.g. subconto).

## Calculated fields (`calculatedFields`)

Fields computed by an expression. Shorthand `"Имя [Заголовок]: тип = Выражение"`:

```json
"calculatedFields": [
  "Метка = Code + \" \" + Description",
  "Маржа [Маржа, руб]: number(15,2) = Цена - Закупка"
]
```

Object form - for `presentationExpression` / `orderExpression`:

```json
{ "dataPath": "Сорт", "expression": "Code", "title": "Сорт",
  "valueType": "string(10)", "presentationExpression": "Code" }
```

## Filter (`filter`)

Shorthand `"Поле оператор значение @флаги"` or an object:

```json
"filter": [
  "Организация = _ @off @user",
  "Сумма > 1000",
  { "field": "Дата", "op": ">=", "value": "2024-01-01T00:00:00" },
  { "group": "Or", "items": [ "Статус = 1", "Статус = 2" ] }
]
```

- **Operators:** `=` `<>` `>` `>=` `<` `<=`, `in` / `notIn`, `inHierarchy`, `contains` / `notContains`, `beginsWith` / `notBeginsWith`, `like` / `notLike` (`%` pattern), `filled` / `notFilled`.
- **Flags:** `@off` (disabled), `@user` (in custom settings), `@quickAccess`; `_` = empty value.
- **Group:** `{ group: "And"|"Or"|"Not", items: [...] }`.
- **Date value:** ISO date `"2024-01-01T00:00:00"` - a fixed date. A named relative period - by a string with a type: `{ "value": "BeginningOfThisWeek", "valueType": "v8:StandardBeginningDate" }` (options `BeginningOfThisDay`/`BeginningOfThisWeek`/`BeginningOfThisMonth`/`BeginningOfThisYear`/…).

## Sorting (`order`)

The string `"Поле"` (ascending) / `"Поле desc"`, or an object `{ field, direction? }`. `"Auto"` - auto sorting:

```json
"order": [ "Дата desc", "Наименование", "Auto" ]
```

## Row grouping (`grouping`)

A linear chain of levels (outer -> inner). Shortcut `>` or an array:

```json
"grouping": "Контрагент > Договор"
"grouping": [ "Контрагент", { "field": "Дата", "groupType": "Hierarchy" } ]
```

Level object keys: `field`, `groupType` (`Items` / `Hierarchy`).

## Conditional appearance (`conditionalAppearance`)

```json
"conditionalAppearance": [
  { "filter": [ "Просрочено = true" ], "appearance": { "ЦветТекста": "web:Red" } }
]
```

`filter` - the same grammar as above. `appearance` - a "platform parameter: value" dictionary (`ЦветТекста`, `ЦветФона`, `Шрифт`, `Текст`, `Формат`, …). The value of `Текст`/`Заголовок`/`Формат`: a bare string - a non-localized literal; `{ru,en}` - a localizable string; `{ field: "путь" }` - a field reference. More about appearance - `references/appearance.md`.
