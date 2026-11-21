# Attributes, dimensions, resources, columns

Operations on "flat" child elements of an object: attribute (`attribute`), dimension (`dimension`),
resource (`resource`), journal column (`column`). The syntax is the same for all.

## General rules

**Batch mode** - several elements via `;;`:
```
-Value "Комментарий: Строка(200) ;; Сумма: Число(15,2) | index"
```

**Shorthand format**: `ИмяРеквизита: Тип | флаги`

Flags: `req` - required filling; `index` - index; `master` - leading dimension (dimensions
only); `mainFilter` - main filter (dimensions only).

**Positional insert**: `>> after ИмяЭлемента` or `<< before ИмяЭлемента`:
```bash
-Operation add-attribute -Value "Склад: CatalogRef.Склады >> after Организация"
```

## Composite types

Separator `+`:
```bash
-Operation add-attribute -Value "Значение: Строка + Число(15,2) + Дата + CatalogRef.Контрагенты"
-Operation add-attribute -Value "Значение: Строка + Число(15,2) | req"
```

In JSON DSL - an array in `type`:
```json
{ "name": "Значение", "type": ["Строка", "Число(15,2)", "Дата", "CatalogRef.Контрагенты"] }
```

## add-attribute / add-dimension / add-resource / add-column

```bash
-Operation add-attribute -Value "Комментарий: Строка(200)"
-Operation add-attribute -Value "Сумма: Число(15,2) | req, index"
-Operation add-attribute -Value "Ном: CatalogRef.Номенклатура | req ;; Кол: Число(15,3)"
-Operation add-dimension -Value "Организация: CatalogRef.Организации | master, mainFilter"
-Operation add-resource -Value "Сумма: Число(15,2)"
-Operation add-column -Value "Тип: EnumRef.ТипыДокументов"
```

## remove-*

Element name (or several via `;;`):
```bash
-Operation remove-attribute -Value "СтарыйРеквизит ;; ЕщёОдин"
-Operation remove-enumValue -Value "НеиспользуемоеЗначение"
```

## modify-attribute / modify-dimension / modify-resource / modify-enumValue / modify-column

Format: `ИмяЭлемента: ключ=значение, ключ=значение`

**Special operations** (lowercase keys): `name` (rename), `type` (type change), `synonym`.

**Properties** are set by the 1C property name (PascalCase, as in the Configurator): `Indexing`, `FillChecking`,
`Use`, `FullTextSearch`, `DataHistory`, `PasswordMode`, `MultiLine`, `Mask`, `CreateOnInput`, `QuickChoice`, etc.
A property can be set even if it is not yet set on the attribute.

```bash
-Operation modify-attribute -Value "СтароеИмя: name=НовоеИмя, type=Строка(500)"
-Operation modify-attribute -Value "Комментарий: Indexing=Index, FullTextSearch=Use"
-Operation modify-enumValue -Value "СтароеЗначение: name=НовоеЗначение"
```

## Structural attribute properties

Set properties with a complex value via JSON DSL (`{ "modify": { "attributes": { "Имя": { ... } } } }`):

| Key | Value | Example (JSON) |
|------|----------|---------------|
| `Format` / `EditFormat` / `ToolTip` | string (multilingual) | `"Format": "ДФ=dd.MM.yyyy"` |
| `ChoiceForm` | choice form path | `"ChoiceForm": "Catalog.Товары.Form.ФормаВыбора"` |
| `MinValue` / `MaxValue` | number or string | `"MinValue": 0, "MaxValue": 100` |
| `FillValue` | fill value | `"FillValue": "EmptyRef"` · `true` · `10` · `{"nil": true}` |
| `LinkByType` | `{dataPath, linkItem?}` | `"LinkByType": {"dataPath": "Вид", "linkItem": 0}` |
| `ChoiceParameterLinks` | `[{name, dataPath, valueChange?}]` | `["Отбор.Организация=Организация"]` |
| `ChoiceParameters` | `[{name, type?, value?}]` | `[{"name": "Отбор.ЭтоГруппа", "value": false}]` |

- `FillValue`: `"EmptyRef"` - an empty reference by attribute type; `{"emptyRef": true}` / `{"nil": true}` - explicit markers.
- `ChoiceParameters` value - bool/number/string/reference path or array; specify `type` (e.g.
  `EnumRef.СтавкиНДС`) to set values by short names (`"Оптовая"` instead of the full path).
- In data paths (`LinkByType`/`ChoiceParameterLinks`) you can write a short attribute name instead of the full path.
