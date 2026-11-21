# Enum, Constant, DefinedType

## Enum (Перечисление)

| Key | Default | Values |
|------|-----------|----------|
| `values` | `[]` | enum values (array of names or objects) |

A value is a string `"ИмяЗначения"` or an object `{ name, synonym }`.

```json
{ "type": "Enum", "name": "Статусы", "values": ["Новый", "ВРаботе", "Закрыт"] }
```

## Constant (Константа)

| Key | Default | Values |
|------|-----------|----------|
| `valueType` | `String` | value type (type shorthand) |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |

`valueType` accepts shorthand: `"String(100)"`, `"Number(15,2)"`, `"Boolean"`, `"CatalogRef.Валюты"`,
composite via `+`.

```json
{ "type": "Constant", "name": "ОсновнаяВалюта", "valueType": "CatalogRef.Валюты" }
```

## DefinedType (Определяемый тип)

| Key | Default | Values |
|------|-----------|----------|
| `valueTypes` | `[]` | type composition (array of shorthand types) |
| `valueType` | - | same as one string (`"A + B"`) or a single-type string |

```json
{ "type": "DefinedType", "name": "ДенежныеСредства",
  "valueTypes": ["CatalogRef.БанковскиеСчета", "CatalogRef.Кассы"] }
{ "type": "DefinedType", "name": "ФлагАктивности", "valueType": "Boolean" }
```
