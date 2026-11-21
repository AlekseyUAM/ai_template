---
name: skd-compile
description: Compile a 1C data composition schema (DCS) from a compact JSON definition. Use when you need to create a DCS from scratch
argument-hint: "[-DefinitionFile <json> | -Value <json-string>] -OutputPath <Template.xml>"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /skd-compile - DCS generation from JSON DSL

Accepts a JSON data composition schema definition -> generates Template.xml (DataCompositionSchema).

## Parameters and command

| Parameter | Description |
|----------|----------|
| `DefinitionFile` | Path to the JSON file with the DCS definition (mutually exclusive with Value) |
| `Value` | JSON string with the DCS definition (mutually exclusive with DefinitionFile) |
| `OutputPath` | Path to the output Template.xml |

```bash
# Из файла
python "${CLAUDE_SKILL_DIR}/scripts/skd-compile.py" -DefinitionFile "<json>" -OutputPath "<Template.xml>"

# Из строки (без промежуточного файла)
python "${CLAUDE_SKILL_DIR}/scripts/skd-compile.py" -Value '<json-string>' -OutputPath "<Template.xml>"
```

## Before creating a report

Before creating a DCS report, read in full:
[DCS specifics](../bsl-coding-standards/reference/skd-specifics.md),
[accumulation registers](../bsl-coding-standards/reference/accumulation-registers.md),
[information registers](../bsl-coding-standards/reference/information-registers.md).

The field composition and selection strictly follow the specification; do not add a custom report form without a specification requirement.
After compilation, run `skd-validate -ExpectedFields "<колонки ТЗ>"` and `skd-info -Mode variant`.

## JSON DSL - quick reference

The reference is below. All examples compile as is.

### Root structure

```json
{
  "dataSets": [...],
  "calculatedFields": [...],
  "totalFields": [...],
  "parameters": [...],
  "templates": [...],
  "groupTemplates": [...],
  "dataSetLinks": [...],
  "settingsVariants": [...]
}
```

Defaults: `dataSources` -> auto `ИсточникДанных1/Local`; `settingsVariants` -> auto "Основной" with details.

### Data sets

Type by key: `query` -> DataSetQuery, `objectName` -> DataSetObject, `items` -> DataSetUnion.

```json
{ "name": "Продажи", "query": "ВЫБРАТЬ ...", "fields": [...] }
```

The query supports `@file` - a reference to an external .sql file instead of inline text: `"query": "@queries/sales.sql"`. The path is resolved relative to the JSON file, then CWD.

**DataSetObject** - an external data set (without a query source). Fields are described explicitly; data is passed as the second parameter `ПроцессорКомпоновкиДанных.Инициализировать(Макет, Новый Структура("<objectName>", ТЗ), ...)`.

```json
{ "name": "ЖурналОшибок", "objectName": "ЖурналОшибок", "fields": [
  { "field": "ТекстСообщения", "title": "Текст сообщения", "type": "string(150)" },
  { "field": "Расшифровка",   "title": "Описание",       "type": "CatalogRef.СтруктураПредприятия" }
]}
```

`name` - the set name in the schema, `objectName` - the key in the data transfer structure.

### Fields - shorthand and object form

```
"Наименование"                              — просто имя
"Количество: decimal(15,2)"                  — имя + тип
"Организация: CatalogRef.Организации @dimension"  — + роль
"Служебное: string #noFilter #noOrder"       — + ограничения
```

Object form - when a title or other properties are needed:
```json
{ "field": "ОстатокНаНачалоПериода", "title": "Остаток на начало периода" }
```
`dataPath` is taken from `field` automatically if not specified explicitly.

Multilingual title: `"title": { "ru": "...", "en": "..." }`. Applies wherever title/presentation is accepted (fields, calculatedFields, parameters, settingsVariants, availableValues, etc.). A string is equivalent to `{ "ru": "..." }`.

Types: `string`, `string(N)`, `decimal`, `decimal(D)`, `decimal(D,F)`, `boolean`, `date`, `dateTime`, `CatalogRef.X`, `DocumentRef.X`, `EnumRef.X`, `StandardPeriod`. Reference types are emitted with the inline namespace `d5p1:` (`http://v8.1c.ru/8.1/data/enterprise/current-config`). Building an EPF with reference types requires an infobase with the corresponding configuration.

`decimal` without parentheses = `10,2` (money by default), `decimal(N)` = `N,0` (integer); `,nonneg` at the end of the parentheses -> AllowedSign=Nonnegative.

Composite type (several value types) - an array in the object form: `"type": ["CatalogRef.A", "CatalogRef.B"]`. Qualifiers (`(N)`, `(D,F)`) apply to each element.

Roles (shorthand or object):

- `@` flags: `@dimension`, `@account`, `@balance`, `@period`, `@required`, `@autoOrder`, `@ignoreNullValues`
- KV: `balanceGroupName`, `balanceType` (`OpeningBalance`/`ClosingBalance`), `parentDimension`, `accountTypeExpression`, `expression`, `orderType` (`Asc`/`Desc`), `periodNumber`, `periodType`

```
"Сумма: decimal(15,2) @balance balanceGroupName=Сумма balanceType=OpeningBalance"
```

Restrictions: `#noField`, `#noFilter`, `#noGroup`, `#noOrder`.

In the object form: `"useRestriction": { "field": true, "condition": true, "group": true, "order": true }` or `"restrict": ["noField", "noFilter"]`.

Additional object form keys:
- `"presentationExpression": "<выражение>"` - what to show instead of the field value. The original value remains "under the hood" for navigation/decryption.
- `"appearance": { "<параметр>": "<значение>" }` - column formatting by default (applied in all settings variants). Keys are platform parameters (`ГоризонтальноеПоложение`, `МинимальнаяШирина`, `Формат`, `Текст`, etc.).
- `"orderExpression": { "expression": "<выражение>", "orderType": "Asc"/"Desc", "autoOrder": true/false }` - sorting the field by an expression (for example `ЕстьNULL(Поле.Порядок, 10000)`).

```json
{ "field": "Сумма", "title": "Сумма продажи", "type": "decimal(15,2)",
  "appearance": { "ГоризонтальноеПоложение": "Right", "МинимальнаяШирина": "80" } }
```

### Calculated fields (calculatedFields)

Shorthand: `"Имя [Заголовок]: тип = Выражение #noField #noFilter #noGroup #noOrder"` - all parts except the name are optional.

```json
"calculatedFields": [
  "Маржа = Цена - Закупка",
  "Наценка [Наценка, %]: decimal(10,2) = Маржа / Закупка * 100",
  "Служебное: string = \"\" #noField #noFilter #noGroup #noOrder"
]
```

Object form - when `appearance` is needed:
```json
{ "name": "Маржа", "title": "Маржа", "expression": "Цена - Закупка", "type": "decimal(15,2)", "useRestriction": "#noField #noFilter" }
```

### Totals (shorthand)

```json
"totalFields": ["Количество: Сумма", "Стоимость: Сумма(Кол * Цена)"]
```

### Parameters (shorthand + @autoDates)

```json
"parameters": [
  "Период [Отчетный период]: StandardPeriod = LastMonth @autoDates"
]
```

Shorthand: `"Имя [Заголовок]: тип = значение @флаги"`. `[Заголовок]` is optional - adds `<title>` (LocalStringType).

Shorthand flags:
- `@autoDates` - adds to a StandardPeriod parameter a pair of dates `НачалоПериода`/`КонецПериода` computed from it. Use them in the query text as `&НачалоПериода`/`&КонецПериода`; the user selects only the period itself. By default the parameter itself gets `use=Always` and `denyIncompleteValues=true` (so the derived dates are always filled); in the object form you can override this explicitly.
- `@valueList` - `<valueListAllowed>true</valueListAllowed>` - allows passing a value list (for a list value below it is implied automatically)
- `@hidden` - hidden parameter: `availableAsField=false` + excluded from `"dataParameters": "auto"`

Object form: `title`, `hidden: true`, `valueListAllowed: true`, `availableAsField: false`, `denyIncompleteValues: true`, `use: "Always"`.

List value: several default values separated by commas in `значение` (for a comma inside a value - quotes `'...'`). In the object form - an array in `value`.

```json
"parameters": [
  "Виды: ChartOfCharacteristicTypesRef.ВидыСубконтоХозрасчетные = ПланВидовХарактеристик.ВидыСубконтоХозрасчетные.Контрагенты, ПланВидовХарактеристик.ВидыСубконтоХозрасчетные.Договоры"
]
```

If there is no default value - omit `=` in the shorthand or specify `"value": null` in the object form.

List of allowed values (availableValues):

```json
{
  "name": "ПорядокОкругления",
  "type": "EnumRef.Округления",
  "value": "Перечисление.Округления.Окр1_00",
  "use": "Always",
  "denyIncompleteValues": true,
  "availableValues": [
    {"value": "Перечисление.Округления.Окр1_00", "presentation": "руб. коп"},
    {"value": "Перечисление.Округления.Окр1", "presentation": "руб."},
    {"value": "Перечисление.Округления.Окр1000", "presentation": "тыс. руб"}
  ]
}
```

In a settings variant `"dataParameters": "auto"` outputs all non-hidden parameters with `userSettingID`. Default values are inherited and remain active; parameters without a default value are disabled (the user will enable them in settings).

### Filters - shorthand

```json
"filter": [
  "Организация = _ @off @user",
  "Дата >= 2024-01-01T00:00:00",
  "Статус filled"
]
```

Format: `"Поле оператор значение @флаги"`. The value `_` = empty (placeholder). Flags: `@off` (use=false), `@user` (userSettingID=auto), `@quickAccess`, `@normal`, `@inaccessible`.

Available in the object form: `viewMode`, `userSettingID`, `userSettingPresentation`.

Filter groups (Or/And/Not):
```json
{ "group": "Or", "items": [
  { "group": "And", "items": [
    { "field": "Статус", "op": "=", "value": "Активен" },
    { "field": "Сумма", "op": ">", "value": 1000 }
  ]},
  { "field": "Количество", "op": "filled" }
]}
```

### Data parameters - shorthand

```json
"dataParameters": [
  "Период = LastMonth @user",
  "Организация @off @user"
]
```

Format: `"Имя [= значение] @флаги"`. For StandardPeriod variants (LastMonth, ThisYear, etc.) are recognized automatically.

### Structure - string shorthand

```json
"structure": "Организация > details"
"structure": "Организация > Номенклатура > details"
```

`>` separates grouping levels. `details` (or `детали`) = detail records. `selection` and `order` default to `["Auto"]` at each level.

Object form - for complex cases (named groupings, selection/filter at grouping level, tables, charts):

```json
"structure": [
  {
    "name": "ПоОрганизациям",
    "groupFields": ["Организация"],
    "selection": ["Организация", "Сумма", "Auto"],
    "children": [{ "groupFields": [] }]
  }
]
```

`type` defaults to `"group"` (can be omitted). `groupFields` is an alias for `groupBy`. Supports `name`, `selection`, `order`, `filter`, `outputParameters`, recursive `children`.

### Settings variants

```json
"settingsVariants": [{
  "name": "Основной",
  "title": "Продажи по организациям",
  "settings": {
    "selection": ["Номенклатура", "Количество", "Auto"],
    "filter": ["Организация = _ @off @user"],
    "order": ["Количество desc", "Auto"],
    "conditionalAppearance": [
      {
        "filter": ["Просрочено = true"],
        "appearance": { "ЦветТекста": "style:ПросроченныеДанныеЦвет" },
        "presentation": "Выделять просроченные",
        "viewMode": "Normal",
        "userSettingID": "auto"
      }
    ],
    "outputParameters": { "Заголовок": "Мой отчёт" },
    "dataParameters": ["Период = LastMonth @user"],
    "structure": "Организация > details"
  }
}]
```

### Conditional appearance (conditionalAppearance)

```json
"conditionalAppearance": [
  {
    "selection": ["Поле1"],
    "filter": ["Поле1 notFilled"],
    "appearance": { "Текст": "Не указано", "ЦветТекста": "style:XXX" },
    "presentation": "Описание",
    "viewMode": "Normal",
    "userSettingID": "auto"
  }
]
```

Appearance value types: `style:XXX`/`web:XXX`/`win:XXX` -> Color, `true`/`false` -> Boolean, the `Формат`/`Текст`/`Заголовок` parameter -> LocalStringType, anything else -> String.

Filter value types: `Перечисление.*`/`Справочник.*`/`ПланСчетов.*`/`Документ.*` -> DesignTimeValue (auto-detected).

OrGroup in a filter: `{"group": "Or", "items": ["условие1", "условие2"]}`.

Folder in selection: `{"folder": "Поступление", "items": ["ПолеА", "ПолеБ"]}` -> SelectedItemFolder with lwsTitle and placement=Auto.

### Totals bound to groupings

```json
"totalFields": [
  { "dataPath": "Кол", "expression": "Сумма(Кол)", "group": ["Группа1", "Группа1 Иерархия", "ОбщийИтог"] }
]
```

### Output templates - compact DSL

Instead of raw XML (`template`) - a tabular description via `rows` + a named style `style`:

```json
"templates": [
  {
    "name": "Макет1",
    "style": "header",
    "widths": [36, 33, 16, 17],
    "minHeight": 24.75,
    "rows": [
      ["Виды кассы", "Валюта", "Остаток на начало\nпериода", "Остаток на\nконец периода"],
      ["|", "|", "|", "|"],
      ["К1", "К2", "К3", "К4"]
    ]
  },
  {
    "name": "Макет2",
    "style": "data",
    "widths": [36, 33, 16, 17],
    "rows": [["{ВидКассы}", "{Валюта}", "{Остаток}", "{ОстатокКонец}"]],
    "parameters": [
      { "name": "ВидКассы", "expression": "Представление(Счет)" },
      { "name": "Остаток", "expression": "ОстатокНаНачалоПериода" }
    ]
  }
]
```

Cell syntax: `"текст"` - static, `"{Имя}"` - parameter, `"|"` - merge with the cell above, `">"` - merge with the cell on the left, `null` - empty.

Two-level header with horizontal merging:
```json
"rows": [
  ["Вид актива", "Остаток начало", "Поступление", ">", ">", ">", "Выбытие", ">", ">", "Остаток конец"],
  ["|",          "|",              "из произв.",   "из п/ф", "со сч.40", "прочее", "Реализ.", "отгруж.", "прочее", "|"],
  ["К1",         "К2",             "К3",           "К4",     "К5",       "К6",     "К7",      "К8",      "К9",     "К10"]
]
```

Built-in styles: `header` (background, center, wrap), `data` (group background), `subheader` (no background, center), `total` (no background). All - Arial 10, Solid 1px borders, colors via platform styles.

Custom styles: a `skd-styles.json` file next to the JSON definition, in the current directory, or in `presets/skills/skd/skd-styles.json` (searched upward from OutputPath). The first file found wins. All allowed keys and the color format are in `examples/skd-styles.json`.

Raw XML (`"template": "<...>"`) remains as a fallback. Detection: if `rows` is present - DSL, otherwise - raw.

### Decryption (drilldown) in template parameters

The `drilldown` key in a template parameter automatically generates `DetailsAreaTemplateParameter` and a `Расшифровка` binding in cell appearance:

```json
"parameters": [
  { "name": "Сырье", "expression": "ПоступлениеСырья", "drilldown": "ПоступлениеСырья" }
]
```

Generates: `ExpressionAreaTemplateParameter` (regular) + `DetailsAreaTemplateParameter` with the name `Расшифровка_ПоступлениеСырья`, `fieldExpression` by the field `ИмяРесурса`, `mainAction=DrillDown`. Cells `{Сырье}` automatically get the appearance `Расшифровка = Расшифровка_ПоступлениеСырья`.

### Template bindings to groupings

```json
"groupTemplates": [
  { "groupName": "ДанныеОтчета", "templateType": "GroupHeader", "template": "Макет1" },
  { "groupField": "Счет", "templateType": "Header", "template": "Макет2" },
  { "groupField": "Счет", "templateType": "OverallHeader", "template": "Макет3" }
]
```

`groupField` - binding to a grouping field, `groupName` - to a named grouping in the variant structure.

`templateType`: `Header` (data rows) -> `<groupTemplate>`, `OverallHeader` (totals) -> `<groupTemplate>`, `GroupHeader` (header) -> `<groupHeaderTemplate>`.

## Examples

### Minimal

```json
{
  "dataSets": [{
    "query": "ВЫБРАТЬ Номенклатура.Наименование КАК Наименование ИЗ Справочник.Номенклатура КАК Номенклатура",
    "fields": ["Наименование"]
  }]
}
```

### With a query from an external file (@file)

```json
{
  "dataSets": [{
    "query": "@queries/sales.sql",
    "fields": ["Номенклатура: СправочникСсылка.Номенклатура @dimension", "Количество: число(15,3)", "Сумма: число(15,2)"]
  }]
}
```

### With resources, parameters and @autoDates

```json
{
  "dataSets": [{
    "query": "ВЫБРАТЬ Продажи.Организация, Продажи.Номенклатура, Продажи.КоличествоОборот КАК Количество, Продажи.СуммаОборот КАК Сумма ИЗ РегистрНакопления.Продажи.Обороты(&НачалоПериода, &КонецПериода) КАК Продажи",
    "fields": [
      "Организация: СправочникСсылка.Организации @dimension",
      "Номенклатура: СправочникСсылка.Номенклатура @dimension",
      "Количество: число(15,3)",
      "Сумма: число(15,2)"
    ]
  }],
  "totalFields": ["Количество: Сумма", "Сумма: Сумма"],
  "parameters": ["Период: СтандартныйПериод = LastMonth @autoDates"],
  "settingsVariants": [{
    "name": "Основной",
    "settings": {
      "selection": ["Организация", "Номенклатура", "Количество", "Сумма"],
      "filter": ["Организация = _ @off @user"],
      "dataParameters": "auto",
      "structure": "Организация > details"
    }
  }]
}
```

## Verification

```
/skd-validate <OutputPath>                  — валидация структуры XML
/skd-info <OutputPath>                      — визуальная сводка
/skd-info <OutputPath> -Mode variant -Name 1 — проверка варианта настроек
```
