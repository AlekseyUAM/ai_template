# Object form of an attribute and tabular section

When an attribute (in `attributes` / `dimensions` / `resources` / tabular section columns) needs properties beyond
shorthand - an object is specified instead of a string:

```json
{ "name": "Цена", "type": "Number(15,2)", "tooltip": "Цена за единицу", "fillValue": 0 }
```

`name` and `type` are required (the type can also be set separately: `"type": "Number", "length": 15, "precision": 2`).
The other keys are below, all with a default value (do not set them if the default is fine).

## Attribute properties

| Key | Default | Values |
|------|-----------|----------|
| `synonym` | from name | ML (string or `{ru,en}`) |
| `tooltip` | empty | ML |
| `comment` | empty | string |
| `fillChecking` | `DontCheck` | `DontCheck` / `ShowError` (same as the `req` flag) |
| `fullTextSearch` | `Use` | `Use` / `DontUse` |
| `fillFromFillingValue` | `false` | bool |
| `fillValue` | by type (see below) | fill value |
| `createOnInput` | `Auto` | `Auto` / `Use` / `DontUse` |
| `quickChoice` | `Auto` | `Auto` / `Use` / `DontUse` |
| `choiceHistoryOnInput` | `Auto` | `Auto` / `DontUse` |
| `dataHistory` | `Use` | `Use` / `DontUse` |
| `use` | `ForItem` | `ForItem` / `ForFolder` / `ForFolderAndItem` (attribute of a hierarchical catalog) |
| `passwordMode` | `false` | bool |
| `multiLine` | `false` | bool (same as the `multiline` flag) |
| `extendedEdit` | `false` | bool (extended editing - multiline input) |
| `mask` | empty | input mask string |
| `format` / `editFormat` | empty | 1C format string (ML) |
| `markNegatives` | `false` | bool (highlight negatives, for Number) |
| `minValue` / `maxValue` | not set | range bound (see below) |
| `choiceParameterLinks` | empty | choice parameter links (see below) |
| `choiceParameters` | empty | choice parameters (see below) |
| `choiceForm` | empty | reference to the choice form `Тип.Объект.Form.ИмяФормы` |
| `choiceFoldersAndItems` | `Items` | `Items` / `Folders` / `FoldersAndItems` (what to choose in a hierarchical catalog) |

Indexing is set by the `index` / `indexAdditional` flag in shorthand, or in the object - as in the string form,
via `"type": "… | index"`.

### `fillValue` - fill value

The compiler substitutes the empty value for the type itself - the key is **not set**:

| Attribute type | Empty value |
|---------------|-----------------|
| String | empty string |
| Number | `0` |
| Boolean, Date, reference, composite | not set (nil) |

The `fillValue` key is set for a **specific** value - it is interpreted by the attribute type:

- **Boolean** - `true` / `false`.
- **Number** - a number (`21`, `1.5`).
- **String** - a string.
- **Date** - ISO string `"2020-01-01T00:00:00"`.
- **Reference** - a path: `"Catalog.Валюты.EmptyRef"` (empty reference), `"Enum.Периодичность.EnumValue.Месяц"`
  (enum value), `"Catalog.СтраныМира.Россия"` (predefined item).
- **`null`** - explicitly "value not set" (nil), when you need to override a non-empty type default.
- **`{ "emptyRef": true }`** - empty reference for an attribute of type `DefinedType.X` (when the type is not derived from the path).

> An empty reference (`EmptyRef`) and `null` are different: the platform stores them separately.

### `minValue` / `maxValue` - range bounds

A number -> numeric bound; a string -> string bound (e.g. year `"2000"`). Without the key - the bound is not set.

### `choiceParameterLinks` - choice parameter links

Link the choice parameter of this attribute to another attribute of the object. An array of strings or objects:

```json
"choiceParameterLinks": ["Отбор.Организация=Организация", "Отбор.Договор=Договор:DontChange"]
"choiceParameterLinks": [{ "name": "Отбор.Организация", "dataPath": "Организация", "valueChange": "Clear" }]
```

- `dataPath` - an attribute of **the same object**: the name of a regular attribute (`"Организация"`) or a standard
  one (`"Владелец"`, `"Ссылка"`).
- `valueChange` - `Clear` (default) / `DontChange`.

### `choiceParameters` - choice parameters

Fix a choice parameter with a value. An array of strings or objects:

```json
"choiceParameters": ["Отбор.ЭтоГруппа=false"]
"choiceParameters": [{ "name": "Отбор.Владелец", "value": "Catalog.Организации.EmptyRef" }]
```

- `value` - bool / number / string / reference path (carries the type) OR an array (list of fixed values).
- For a set of bare value names, add `type` (the filter field type) so that they become references:
  `{ "name": "Отбор.Тип", "type": "EnumRef.ТипыВЕТИС", "value": ["EmptyRef", "ТТН"] }`.

### Rare keys

`linkByType` - type link (the type of the Characteristic attribute is taken from another attribute):
`{ "dataPath": "Свойство", "linkItem": 0 }` or a path string. Used for characteristic attributes.

---

## Tabular section - object form

The value in `tabularSections` is a column array OR an object with the properties of the tabular section itself:

```json
"tabularSections": {
  "Товары": {
    "synonym": { "ru": "Товары", "en": "Goods" },
    "tooltip": "Строки заказа",
    "fillChecking": "ShowError",
    "attributes": ["Номенклатура: CatalogRef.Номенклатура", "Количество: Number(15,3)"]
  }
}
```

| Key | Default | Values |
|------|-----------|----------|
| `synonym` | from name | ML |
| `tooltip` | empty | ML |
| `comment` | empty | string |
| `fillChecking` | `DontCheck` | `DontCheck` / `ShowError` (tabular section fill requirement) |
| `use` | `ForItem` | `ForItem` / `ForFolder` / `ForFolderAndItem` (only Catalog / ChartOfCharacteristicTypes) |
| `attributes` | `[]` | columns (shorthand or attribute object form) |
| `lineNumber` | - | customization of the standard LineNumber attribute (see below) |
| `lineNumberLength` | depends on compatibility mode | `5`...`9` - line number width: `5` -> up to 99 999 lines, `9` -> up to 999 999 999. Requires format 2.20 (platform 8.3.27) |

### `lineNumber` - standard LineNumber attribute

Every tabular section has the standard LineNumber attribute. By default all its properties are typical. The `lineNumber`
key in the tabular section object form overrides them:

```json
"Строки": { "lineNumber": { "synonym": "Номер п/п", "fullTextSearch": "DontUse" }, "attributes": [...] }
```

Overridable: `synonym`, `comment`, `fullTextSearch` (`Use`/`DontUse`), `tooltip`, `format`, `editFormat`,
`choiceHistoryOnInput` (`Auto`/`DontUse`).
