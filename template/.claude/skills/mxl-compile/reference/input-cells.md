# Input field cells

A cell can show no text and instead accept a value from the user - this is how templates for
data entry are made. It is enough to set the value type:

```json
{ "col": 1, "valueType": "Number(15,3,nonneg)" }
{ "col": 2, "valueType": "String(10)" }
{ "col": 3, "valueType": "Boolean", "controlType": "checkbox" }
{ "col": 4, "valueType": "CatalogRef.Валюты" }
{ "col": 5, "valueType": "Boolean + String + Date + CatalogRef.Валюты" }
{ "col": 6, "valueType": "AnyRef" }
```

Type grammar:

| Entry | Meaning |
|---|---|
| `Boolean` | boolean |
| `String`, `String(10)`, `String(10,fixed)` | string; without length - unlimited, `fixed` - fixed length |
| `Number`, `Number(15,3)`, `Number(15,3,nonneg)` | number; without parameters - no digit limit, `nonneg` - non-negative |
| `Date`, `DateTime`, `Time` | date, date with time, time |
| `CatalogRef.Валюты`, `DocumentRef.Реализация`, `EnumRef.Статусы`, `DefinedType.Сумма` | reference type |
| `CatalogRef`, `DocumentRef`, `AnyRef` | the category as a whole: any reference of this kind |
| `A + B` | composite type; repeating the same primitive is not allowed |

Russian names are accepted on a par with English ones: `Число(15,3)`, `Строка(10)`,
`СправочникСсылка.Валюты`.

`text` and `template` are not allowed in such a cell - the platform does not show text where a
value is entered. `param` and `detail` are allowed: they describe filling and decryption, not content.

Empty type `"valueType": ""` - "the cell contains a value", but the type is not restricted.

The input field value is set with the `value` key. Its type is the JSON literal type: string, number,
`true`/`false`; the value is not cast to the cell's declared type. An empty string means
an empty value of the declared type. A date is written as the string `ГГГГ-ММ-ДДTчч:мм:сс` and is read
as a date for a cell declared as a date; for a reference and composite type the value is a string.

```json
{ "col": 1, "valueType": "Number(15,3)", "value": 12.5 }
{ "col": 2, "valueType": "String(10)", "value": "5" }
{ "col": 3, "valueType": "Boolean", "value": true }
{ "col": 4, "valueType": "DateTime", "value": "" }
```

`controlType` is rarely needed: the platform default is an input field, and it suits all types, including
`Boolean`. A checkbox is set explicitly.
