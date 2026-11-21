---
name: form-compile
description: Compile a 1C managed form from a JSON definition or from object metadata. Use when you need to create a form from scratch by an element description or generate a typical form
argument-hint: <JsonPath> <OutputPath> | -FromObject <OutputPath>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /form-compile - Form.xml generation

Two modes:
1. **JSON DSL** - from a form JSON definition
2. **From object** (`-FromObject`) - automatically from 1C object metadata by an ERP preset

> **When designing a form from scratch (5+ elements or vague requirements)** - call `/form-patterns` to load the reference. For simple forms (1-3 fields) - not needed.

## Parameters

| Parameter  | Required     | Description                     |
|------------|:------------:|---------------------------------|
| JsonPath   | mode 1       | Path to the form JSON definition |
| OutputPath | yes          | Path to the output Form.xml     |
| FromObject | mode 2       | Flag (no value) - generation by object metadata |

## Command

```bash
# Режим JSON DSL
python "${CLAUDE_SKILL_DIR}/scripts/form-compile.py" -JsonPath "<json>" -OutputPath "<Form.xml>"

# Режим from-object (объект и purpose выводятся из OutputPath; Document и Catalog)
python "${CLAUDE_SKILL_DIR}/scripts/form-compile.py" -FromObject -OutputPath "<.../TypePlural/ObjectName/Forms/FormName/Ext/Form.xml>"
```

## JSON DSL - reference

### Top-level structure

```json
{
  "title": "Заголовок формы",
  "properties": { "autoTitle": false, ... },
  "events": { "OnCreateAtServer": "ПриСозданииНаСервере" },
  "excludedCommands": ["Reread"],
  "elements": [ ... ],
  "attributes": [ ... ],
  "commands": [ ... ],
  "parameters": [ ... ]
}
```

- `title` - form title (multilingual). Can also be set in `properties`, but better at the top level
- `properties` - form properties: `autoTitle`, `windowOpeningMode`, `commandBarLocation`, `saveDataInSettings`, `width`, `height` and others
- `events` - form event handlers (key: 1C event name, value: procedure name)
- `excludedCommands` - excluded standard commands

### Elements (the key determines the type)

| DSL key      | XML element       | Key value                                         |
|--------------|-------------------|---------------------------------------------------|
| `"group"`    | UsualGroup        | orientation: `"vertical"` / `"horizontalIfPossible"` / `"alwaysHorizontal"` (behavior is a separate key `behavior`) |
| `"columnGroup"` | ColumnGroup    | `"horizontal"` / `"vertical"` / `"inCell"` - only inside table `columns` |
| `"input"`    | InputField        | element name                                      |
| `"check"`    | CheckBoxField     | name                                              |
| `"radio"`    | RadioButtonField  | name                                              |
| `"label"`    | LabelDecoration   | name (text is set via `title`)                    |
| `"labelField"` | LabelField      | name                                              |
| `"table"`    | Table             | name                                              |
| `"pages"`    | Pages             | name                                              |
| `"page"`     | Page              | name                                              |
| `"button"`   | Button            | name                                              |
| `"picture"`  | PictureDecoration | name                                              |
| `"picField"` | PictureField      | name                                              |
| `"calendar"` | CalendarField     | name                                              |
| `"cmdBar"`   | CommandBar        | name                                              |
| `"autoCmdBar"` | form AutoCommandBar | name - fills the main form command bar (id=-1), does not go into `<ChildItems>` |
| `"popup"`    | Popup             | name                                              |

### Common properties (all element types)

| Key | Description |
|------|----------|
| `name` | Override the name (by default = the type key value). Names are unique across all form collections (elements, attributes, commands, columns) |
| `title` | Element title |
| `tooltip` | Element tooltip (string or `{ru,en}`) |
| `visible: false` | Hide (synonym: `hidden: true`) |
| `enabled: false` | Make unavailable (synonym: `disabled: true`) |
| `readOnly: true` | Read-only |
| `events: {...}` | Event handlers: `{ "OnChange": "ИмяОбработчика" }`. Same format as form events. A `null` value -> the handler name is generated automatically |

### Valid event names (`events`)

The compiler warns about unknown events. Names are case-sensitive - use them exactly as specified.

**Form** (`events`): `OnCreateAtServer`, `OnOpen`, `BeforeClose`, `OnClose`, `NotificationProcessing`, `ChoiceProcessing`, `OnReadAtServer`, `BeforeWriteAtServer`, `OnWriteAtServer`, `AfterWriteAtServer`, `BeforeWrite`, `AfterWrite`, `FillCheckProcessingAtServer`, `BeforeLoadDataFromSettingsAtServer`, `OnLoadDataFromSettingsAtServer`, `ExternalEvent`, `Opening`

**input / picField**: `OnChange`, `StartChoice`, `ChoiceProcessing`, `AutoComplete`, `TextEditEnd`, `Clearing`, `Creating`, `EditTextChange`

**check / radio**: `OnChange`

**table**: `OnStartEdit`, `OnEditEnd`, `OnChange`, `Selection`, `ValueChoice`, `BeforeAddRow`, `BeforeDeleteRow`, `AfterDeleteRow`, `BeforeRowChange`, `BeforeEditEnd`, `OnActivateRow`, `OnActivateCell`, `Drag`, `DragStart`, `DragCheck`, `DragEnd`

**label / picture**: `Click`, `URLProcessing`

**labelField**: `OnChange`, `StartChoice`, `ChoiceProcessing`, `Click`, `URLProcessing`, `Clearing`

**button**: `Click`

**pages**: `OnCurrentPageChange`

### Input field (input)

| Key | Description | Example |
|------|----------|--------|
| `path` | DataPath - binding to data | `"Объект.Организация"` |
| `titleLocation` | Title placement | `"none"`, `"left"`, `"right"`, `"top"`, `"bottom"`, `"auto"` |
| `multiLine: true` | Multiline field | text field, comment |
| `passwordMode: true` | Password mode (asterisks) | password input field |
| `choiceButton: true` | Choice button ("...") | reference field |
| `clearButton: true` | Clear button ("X") | |
| `spinButton: true` | Spin button | numeric fields |
| `dropListButton: true` | Drop-down list button | |
| `markIncomplete: true` | Mark incomplete | required fields |
| `skipOnInput: true` | Skip on Tab traversal | |
| `inputHint` | Hint in an empty field | `"Введите наименование..."` |
| `width` / `height` | Size | numbers |
| `autoMaxWidth: false` | Remove the auto width limit (the field will stretch) | |
| `maxWidth` / `maxHeight` | Hard size limit | numbers; usually together with `autoMaxWidth: false` |
| `horizontalStretch: true` | Stretch horizontally | |

### Checkbox (check)

| Key | Description |
|------|----------|
| `path` | DataPath |
| `titleLocation` | Title placement |

### Radio switch field (radio)

Radio buttons or a tumbler to choose one value from a list.

| Key | Description | Example |
|------|----------|--------|
| `path` | DataPath - binding to an attribute | `"СпособКурса"` |
| `radioButtonType` | Switch kind | `"Auto"` (default), `"RadioButtons"`, `"Tumbler"` |
| `columnsCount` | Number of layout columns | `1`, `2`, ... |
| `titleLocation` | Title placement | by default `"none"` |
| `choiceList` | List of options: array `{value, presentation}` | see below |

`choiceList[*]`:

| Key | Description |
|------|----------|
| `value` | Option value. String/number/boolean; for an enum - `"Enum.ИмяТипа.EnumValue.ИмяЗначения"` |
| `presentation` | Text next to the switch. A string (Russian) or an object `{ru, en, ...}` for multilingual support |

```json
{
  "radio": "СпособКурса",
  "path": "Объект.СпособУстановкиКурса",
  "radioButtonType": "Auto",
  "choiceList": [
    { "value": "Enum.СпособыКурса.EnumValue.Авто",   "presentation": { "ru": "Автоматически", "en": "Automatic" } },
    { "value": "Enum.СпособыКурса.EnumValue.Ручной", "presentation": "вручную" }
  ]
}
```

### Label decoration (label)

| Key | Description |
|------|----------|
| `title` | Label text (required) |
| `hyperlink: true` | Make it a link |
| `width` / `height` | Size |

### Group (group)

The key value sets the **orientation**: `"vertical"`, `"horizontalIfPossible"`, `"alwaysHorizontal"`.

| Key | Description |
|------|----------|
| `behavior` | Group behavior: `"collapsible"` (collapsible) / `"popup"` (popup). Omit = regular |
| `showTitle: true` | Show the group title |
| `united: false` | The left edge of input fields is aligned only within this group (by default `true` - end-to-end alignment by the longest title, including with neighboring groups) |
| `collapsed: true` | For `behavior: "collapsible"` / `"popup"` - the group is created collapsed |
| `controlRepresentation` | Collapse control representation (`behavior: "collapsible"`): `"TitleHyperlink"` (title hyperlink, default) / `"Picture"` (picture) |
| `representation` | `"none"`, `"normal"`, `"weak"`, `"strong"` |
| `children: [...]` | Nested elements |

### Table (table)

**Important**: a table requires a linked form attribute of type `ValueTable` with columns (see the "Links" section).

| Key | Description |
|------|----------|
| `path` | DataPath (binding to the table attribute) |
| `columns: [...]` | Columns - an array of elements (usually `input`) |
| `changeRowSet: true` | Allow adding/deleting rows |
| `changeRowOrder: true` | Allow moving rows |
| `height` | Height in table rows |
| `header: false` | Hide the header |
| `footer: true` | Show the footer |
| `commandBarLocation` | `"None"`, `"Top"`, `"Bottom"`, `"Auto"` |
| `searchStringLocation` | `"None"`, `"Top"`, `"Bottom"`, `"CommandBar"`, `"PullFromTop"`, `"Auto"` |
| `choiceMode: true` | Choice mode (for choice forms) |
| `initialTreeView` | `"ExpandTopLevel"` and others (hierarchical lists) |
| `enableDrag: true` | Allow dragging |
| `enableStartDrag: true` | Allow starting a drag |
| `rowPictureDataPath` | Path to the row picture (e.g. `"Список.DefaultPicture"`) |
| `tableAutofill: false` | Control Autofill of the internal AutoCommandBar |

Columns can be grouped via `columnGroup` (see below).

### Column group (columnGroup)

Used only inside table `columns`. The key value sets the orientation: `"horizontal"`, `"vertical"`, `"inCell"` (merges columns into one header cell). Nesting `columnGroup` inside `columnGroup` is allowed.

| Key | Description |
|------|----------|
| `name` | Element name (recommended to set explicitly) |
| `title` | Group title |
| `showTitle: false` | Hide the title |
| `showInHeader: true/false` | Whether to show the group in the table header |
| `width` | Width |
| `horizontalStretch: false` | Stretching |
| `children: [...]` | Columns inside the group (`input`, `labelField`, `picField`, nested `columnGroup` ...) |

```json
{ "table": "Список", "path": "Список", "columns": [
    { "columnGroup": "horizontal", "name": "ГруппаДата", "title": "Срок", "children": [
        { "input": "СрокИсполнения", "path": "Список.СрокИсполнения" },
        { "labelField": "Просрочено", "path": "Список.Просрочено" }
    ]},
    { "columnGroup": "inCell", "name": "ГруппаИсполнитель", "showInHeader": true, "children": [
        { "input": "Исполнитель", "path": "Список.Исполнитель" }
    ]},
    { "input": "Комментарий", "path": "Список.Комментарий" }
]}
```

### Picture field (picField)

A PictureField bound to a boolean/number draws an icon only when `valuesPicture` is set:

| Key | Description |
|------|----------|
| `valuesPicture` | Value picture ref: `"StdPicture.Favorites"`, `"CommonPicture.X"` |
| `loadTransparent: true` | Hide the "no value" frame |

### Pages (pages + page)

| Key (pages) | Description |
|------|----------|
| `pagesRepresentation` | `"None"`, `"TabsOnTop"`, `"TabsOnBottom"` and others |
| `children: [...]` | Array of `page` |

| Key (page) | Description |
|------|----------|
| `title` | Tab title |
| `group` | Orientation inside the page |
| `children: [...]` | Page content |

### Button (button)

| Key | Description |
|------|----------|
| `command` | Form command name -> `Form.Command.Имя` |
| `stdCommand` | Standard command: `"Close"` -> `Form.StandardCommand.Close`; with a dot: `"Товары.Add"` -> `Form.Item.Товары.StandardCommand.Add` |
| `defaultButton: true` | Default button |
| `type` | `"usual"`, `"hyperlink"`. Default `"usual"`. The concrete XML kind (UsualButton/Hyperlink/CommandBarButton/CommandBarHyperlink) is substituted automatically by context |
| `picture` | Button picture |
| `representation` | `"Auto"`, `"Text"`, `"Picture"`, `"PictureAndText"` |
| `locationInCommandBar` | `"Auto"`, `"InCommandBar"`, `"InAdditionalSubmenu"` |

### Command bar (cmdBar)

An additional custom command bar, placed as a regular element in the form layout.

| Key | Description |
|------|----------|
| `autofill: true` | Autofill with standard commands |
| `children: [...]` | Bar buttons |

### Main form auto command bar (autoCmdBar)

Fills the form's built-in AutoCommandBar (id=-1) with custom buttons. Specify only if you need to add your own buttons to the main bar or explicitly control autofill.

| Key | Description |
|------|----------|
| `autofill: true/false` | Autofill with standard commands |
| `horizontalAlign` | `"Left"` / `"Center"` / `"Right"` |
| `children: [...]` | Buttons/popup |

```json
{ "autoCmdBar": "ФормаКоманднаяПанель", "autofill": true, "children": [
   { "button": "ИзменитьВыделенные", "command": "ИзменитьВыделенные",
     "locationInCommandBar": "InAdditionalSubmenu" }
]}
```

Place the form's main action buttons and submenus here, not in a separate group on the form. Use a separate button in the layout only if it is logically bound to a specific field or group.

### Drop-down menu (popup)

| Key | Description |
|------|----------|
| `title` | Submenu title |
| `children: [...]` | Submenu buttons |

Used inside `cmdBar` to group buttons into a submenu:
```json
{ "cmdBar": "Панель", "children": [
  { "popup": "Добавить", "title": "Добавить", "children": [
    { "button": "ДобавитьСтроку", "stdCommand": "Товары.Add" },
    { "button": "ДобавитьИзДокумента", "command": "ДобавитьИзДокумента", "title": "Из документа" }
  ]}
]}
```

### Attributes (attributes)

```json
{ "name": "Объект", "type": "DataProcessorObject.Загрузка", "main": true }
{ "name": "Список", "type": "DynamicList", "main": true, "settings": {
    "mainTable": "Catalog.Номенклатура", "dynamicDataRead": true
}}
{ "name": "Итого", "type": "decimal(15,2)" }
{ "name": "Таблица", "type": "ValueTable", "columns": [
    { "name": "Номенклатура", "type": "CatalogRef.Номенклатура" },
    { "name": "Количество", "type": "decimal(10,3)" }
]}
```

- `savedData: true` - saved data
- `main: true` - the main form attribute (for example, the main `*Object.*`, `DynamicList`, `*RecordSet.*`)

### Commands (commands)

```json
{ "name": "Загрузить", "action": "ЗагрузитьОбработка", "shortcut": "Ctrl+Enter" }
```

- `title` - title (if it differs from name)
- `picture` - command picture

### Type system

**Primitive:**

| DSL                    | XML                                    |
|------------------------|----------------------------------------|
| `"string"` / `"string(100)"` | `xs:string` + StringQualifiers  |
| `"decimal(15,2)"`     | `xs:decimal` + NumberQualifiers        |
| `"decimal(10,0,nonneg)"` | with AllowedSign=Nonnegative        |
| `"boolean"`            | `xs:boolean`                          |
| `"date"` / `"dateTime"` / `"time"` | `xs:dateTime` + DateFractions |

**Reference and object types (`cfg:Prefix.Name`):**

| DSL | Description |
|-----|----------|
| `"CatalogRef.XXX"` / `"CatalogObject.XXX"` | Catalog |
| `"DocumentRef.XXX"` / `"DocumentObject.XXX"` | Document |
| `"EnumRef.XXX"` | Enum |
| `"DataProcessorObject.XXX"` / `"ReportObject.XXX"` | Data processor / Report |
| `"InformationRegisterRecordSet.XXX"` | Information register record set |
| `"AccumulationRegisterRecordSet.XXX"` | Accumulation register record set |
| `"DynamicList"` | Dynamic list |

Also allowed: `ChartOfAccountsRef/Object`, `ChartOfCharacteristicTypesRef/Object`, `ChartOfCalculationTypesRef/Object`, `ExchangePlanRef/Object`, `BusinessProcessRef/Object`, `TaskRef/Object`, `AccountingRegisterRecordSet`, `InformationRegisterRecordManager`, `ConstantsSet`.

**Platform types:**

| DSL | XML |
|-----|-----|
| `"ValueTable"` | `v8:ValueTable` |
| `"ValueTree"` | `v8:ValueTree` |
| `"ValueList"` | `v8:ValueListType` |
| `"TypeDescription"` | `v8:TypeDescription` |
| `"UUID"` | `v8:UUID` |
| `"FormattedString"` | `v8ui:FormattedString` |
| `"Picture"` / `"Color"` / `"Font"` | `v8ui:*` |
| `"DataCompositionSettings"` | `dcsset:DataCompositionSettings` |
| `"Type1 \| Type2"` | composite type (several `<v8:Type>`) |

**Invalid types (XDTO error on load):**

> `FormDataStructure`, `FormDataCollection`, `FormDataTree` - runtime types of 1C, they do not exist in the XML schema. Use `CatalogObject.XXX`, `DocumentObject.XXX`, `DataProcessorObject.XXX`, `ValueTable`, `ValueTree` instead.

## Links: element + attribute

A table and some fields require a linked attribute. An element references an attribute via `path`.

**Table** - a `table` element + a `ValueTable` attribute:
```json
{
  "elements": [
    { "table": "Товары", "path": "Объект.Товары", "columns": [
      { "input": "Номенклатура", "path": "Объект.Товары.Номенклатура" }
    ]}
  ],
  "attributes": [
    { "name": "Объект", "type": "DataProcessorObject.Загрузка", "main": true,
      "columns": [
        { "name": "Товары", "type": "ValueTable", "columns": [
          { "name": "Номенклатура", "type": "CatalogRef.Номенклатура" }
        ]}
      ]
    }
  ]
}
```

Or, if the table is bound to a form attribute (not to Объект):
```json
{
  "elements": [
    { "table": "ТаблицаДанных", "path": "ТаблицаДанных", "columns": [
      { "input": "Наименование", "path": "ТаблицаДанных.Наименование" }
    ]}
  ],
  "attributes": [
    { "name": "ТаблицаДанных", "type": "ValueTable", "columns": [
      { "name": "Наименование", "type": "string(150)" }
    ]}
  ]
}
```

## Patterns

### File load dialog

```json
{
  "title": "Загрузка из файла",
  "properties": { "autoTitle": false },
  "events": { "OnCreateAtServer": "ПриСозданииНаСервере" },
  "elements": [
    { "group": "horizontal", "name": "ГруппаФайл", "children": [
      { "input": "ИмяФайла", "path": "ИмяФайла", "title": "Файл", "inputHint": "Выберите файл...", "choiceButton": true, "events": { "StartChoice": "ИмяФайлаНачалоВыбора" } },
      { "check": "ПерваяСтрокаЗаголовок", "path": "ПерваяСтрокаЗаголовок" }
    ]},
    { "input": "Результат", "path": "Результат", "multiLine": true, "height": 8, "readOnly": true, "title": "Лог" },
    { "autoCmdBar": "ФормаКоманднаяПанель", "children": [
      { "button": "Загрузить", "command": "Загрузить", "defaultButton": true },
      { "button": "Закрыть",   "stdCommand": "Close" }
    ]}
  ],
  "attributes": [
    { "name": "Объект", "type": "ExternalDataProcessorObject.ЗагрузкаИзФайла", "main": true },
    { "name": "ИмяФайла", "type": "string" },
    { "name": "ПерваяСтрокаЗаголовок", "type": "boolean" },
    { "name": "Результат", "type": "string" }
  ],
  "commands": [
    { "name": "Загрузить", "action": "ЗагрузитьОбработка", "shortcut": "Ctrl+Enter" }
  ]
}
```

### Wizard with steps

```json
{
  "title": "Мастер настройки",
  "properties": { "autoTitle": false },
  "elements": [
    { "pages": "СтраницыМастера", "pagesRepresentation": "None", "children": [
      { "page": "Шаг1", "title": "Параметры", "children": [
        { "input": "Параметр1", "path": "Параметр1" }
      ]},
      { "page": "Шаг2", "title": "Результат", "children": [
        { "input": "Итог", "path": "Итог", "readOnly": true }
      ]}
    ]},
    { "group": "horizontal", "name": "Навигация", "children": [
      { "button": "Назад", "command": "Назад", "title": "< Назад" },
      { "button": "Далее", "command": "Далее", "title": "Далее >" }
    ]}
  ],
  "attributes": [
    { "name": "Объект", "type": "ExternalDataProcessorObject.Мастер", "main": true },
    { "name": "Параметр1", "type": "string" },
    { "name": "Итог", "type": "string" }
  ],
  "commands": [
    { "name": "Назад", "action": "НазадОбработка" },
    { "name": "Далее", "action": "ДалееОбработка" }
  ]
}
```

### List with a filter and a table

```json
{
  "title": "Просмотр данных",
  "elements": [
    { "group": "horizontal", "name": "Фильтр", "children": [
      { "input": "Период", "path": "Период", "events": { "OnChange": "ПериодПриИзменении" } },
      { "input": "Организация", "path": "Организация", "events": { "OnChange": "ОрганизацияПриИзменении" } }
    ]},
    { "table": "Данные", "path": "Данные", "changeRowSet": true, "columns": [
      { "input": "Дата", "path": "Данные.Дата" },
      { "input": "Сумма", "path": "Данные.Сумма" },
      { "input": "Комментарий", "path": "Данные.Комментарий" }
    ]}
  ],
  "attributes": [
    { "name": "Объект", "type": "ExternalDataProcessorObject.Просмотр", "main": true },
    { "name": "Период", "type": "date" },
    { "name": "Организация", "type": "string" },
    { "name": "Данные", "type": "ValueTable", "columns": [
      { "name": "Дата", "type": "date" },
      { "name": "Сумма", "type": "decimal(15,2)" },
      { "name": "Комментарий", "type": "string(200)" }
    ]}
  ]
}
```

## Advanced constructs (when needed)

The above is enough for most forms. For a specific task, load a file from `references/`:

- `dynamic-list.md` - list form: source, filter, sorting, groupings, query parameters
- `appearance.md` - conditional and static element appearance (colors/fonts/borders)
- `choice-params.md` - choice parameters and links for input fields
- `command-interface.md` - form command interface
- `roles-access.md` - custom visibility and role-based access
- `companion-panels.md` - content of the extended tooltip and context menu
- `special-fields.md` - document/sensor fields (HTML, text, indicator, slider)
- `charts.md` - charts and scheduler
- `report-form.md` - report form properties
- `type-system-advanced.md` - sets and composite types
- `table-advanced.md` - advanced table properties
- `layout-advanced.md` - fine layout and geometry

## Auto-generation

- **Companion elements**: ContextMenu, ExtendedTooltip, etc. are created automatically
- **Namespace**: all 17 namespace declarations
- **ID**: sequential numbering, AutoCommandBar = id="-1"
- **Unknown keys**: a warning is printed about unrecognized keys

## Workflow

1. **Skeleton**: `/form-add` creates the form metadata (`ФормаСписка.xml`), `Module.bsl` and registers the form with the object.
2. **Compilation**: `/form-compile` fills `Form.xml` with elements.
3. **Check**: `/form-validate`, `/form-info`.

## Verification

```
/form-validate <OutputPath>    — проверка корректности XML
/form-info <OutputPath>        — визуальная сводка структуры
```

## Specifics for external data processors (EPF)

- **Main attribute type**: `ExternalDataProcessorObject.ИмяОбработки` (not `DataProcessorObject`)
- **DataPath**: use form attributes (`ИмяРеквизита`), not `Объект.ИмяРеквизита` - external data processors have no object attributes in the metadata
- **Reference types**: `CatalogRef.XXX`, `DocumentRef.XXX` are allowed in XML, but building an EPF requires an infobase with the target configuration (see the `1c-batch` skill, `build-epf` command)
