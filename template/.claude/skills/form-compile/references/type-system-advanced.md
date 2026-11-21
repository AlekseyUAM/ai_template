# Advanced type constructs

Primitives (`string(n)`, `number(p,s)`, `boolean`, `date`/`dateTime`, …) and single references (`CatalogRef.Контрагенты`, `DocumentRef.Заказ`, `EnumRef.X`, …) are described in the main instruction. Here are types that cannot be expressed by a single name: composite types, type sets and platform reference sets.

Any of these constructs is written in the `type` field of an attribute, a parameter attribute or a field.

## Composite types

Several types on one attribute - the parts are listed with the separator `" | "` (`+` is also allowed). The attribute will be able to accept a value of any of the listed types:

```json
{ "name": "Плательщик",
  "type": "CatalogRef.Организации | CatalogRef.ИндивидуальныеПредприниматели" }
```

Types from different categories can be mixed - references, primitives, type sets:

```json
{ "name": "Источник",
  "type": "CatalogRef.Контрагенты | DocumentRef.Заказ | string(150)" }
```

Each part is a self-contained token from this file or from the main instruction. The order of parts is arbitrary.

## Type sets (TypeSet)

A "type set" is substituted instead of a concrete type - it is one token, not an enumeration. It is also applicable inside a composite type as one of the parts.

| `type` token | Meaning |
|------|-------|
| `"DefinedType.ИмяТипа"` | defined type of the configuration |
| `"Characteristic.ИмяПлана"` | value type of a characteristic (by the chart of characteristic types) |
| `"AnyRef"` | any reference |
| `"AnyIBRef"` | any infobase reference |

Defined type - the attribute accepts what is set in the configuration's defined type (for example `DefinedType.ДенежнаяСумма`):

```json
{ "name": "Сумма", "type": "DefinedType.ДенежнаяСумма" }
```

Characteristic - the value type is taken from the chart of characteristic types:

```json
{ "name": "Значение", "type": "Characteristic.ДополнительныеРеквизиты" }
```

## Platform reference sets

A "bare" reference token **without `.Имя`** means "any reference of this object category":

| `type` token | Meaning |
|------|-------|
| `"CatalogRef"` | any catalog reference |
| `"DocumentRef"` | any document reference |
| `"EnumRef"` | any enum reference |
| `"ExchangePlanRef"` | any exchange plan reference |
| `"TaskRef"` | any task reference |
| `"BusinessProcessRef"` | any business process reference |
| `"ChartOfCharacteristicTypesRef"` | any chart of characteristic types reference |
| `"ChartOfAccountsRef"` | any chart of accounts reference |
| `"ChartOfCalculationTypesRef"` | any chart of calculation types reference |

The difference from a single reference is only the presence of `.Имя`:

- `"CatalogRef.Валюты"` - a concrete catalog "Валюты";
- `"CatalogRef"` - any catalog.

```json
{ "name": "ЛюбойСправочник", "type": "CatalogRef" }
```

These sets also combine in a composite type:

```json
{ "name": "Объект", "type": "CatalogRef | DocumentRef" }
```
