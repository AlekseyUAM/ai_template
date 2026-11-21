# Choice parameters and type link

Input field (`input`) properties that control value choice: what limits the choice list and what the value type will be. Parameter names are 1C strings as is (`"Отбор.Х"`).

```json
{ "input": "Контрагент", "path": "Объект.Контрагент",
  "choiceParameters": [
    { "name": "Отбор.Активный", "value": true },
    { "name": "Отбор.ВидПродукции", "value": ["Enum.Виды.Агрохимикат", "Enum.Виды.Пестицид"] }
  ],
  "choiceParameterLinks": [
    { "name": "Отбор.Организация", "dataPath": "Объект.Организация" },
    { "name": "Отбор.Тип", "dataPath": "Объект.Тип", "valueChange": "DontChange" }
  ],
  "typeLink": { "dataPath": "Объект.ЗначениеДата", "linkItem": 0 }
}
```

## Choice parameters (`choiceParameters`)

Fixed values of choice parameters that filter the value list independently of form data. An array of objects `{ name, value }`:

- `name` - parameter name (`"Отбор.Активный"`).
- `value` - value. Allowed: bool, number, string, ISO date (`"2020-01-01T00:00:00"`), reference path (`Enum.X.Y`, `Catalog.X`). An **array** of values sets a fixed array.

Short form - `"name=value"` strings; a value with commas becomes an array, `true`/`false` -> bool, a number -> number, the rest -> string/reference:

```json
"choiceParameters": [
  "Отбор.Активный=true",
  "Отбор.ВидПродукции=Enum.Виды.Агрохимикат, Enum.Виды.Пестицид"
]
```

## Choice parameter links (`choiceParameterLinks`)

Choice parameters whose value is taken from **another form field** (rather than fixed). The typical case is filtering the list of contracts by the selected counterparty. An array of objects `{ name, dataPath, valueChange? }`:

- `name` - choice parameter name.
- `dataPath` - path to the form field whose value is substituted into the parameter.
- `valueChange` - what to do with the already selected value when the source changes: `Clear` (clear; optional - default behavior) / `DontChange` (do not change).

```json
{ "input": "Договор", "path": "Объект.Договор",
  "choiceParameterLinks": [
    { "name": "Отбор.Владелец", "dataPath": "Объект.Контрагент" }
  ]
}
```

Short form - `"name=dataPath"` strings, an optional tail `:Clear` / `:DontChange`:

```json
"choiceParameterLinks": [ "Отбор.Организация=Объект.Организация", "Отбор.Тип=Объект.Тип:DontChange" ]
```

## Type link (`typeLink`)

The field value type is determined by another form field (e.g. the "Value" field of a subconto, whose type is set by the selected subconto kind). Object `{ dataPath, linkItem }`:

- `dataPath` - path to the field that sets the type.
- `linkItem` - link item index (optional, default `0`).

```json
"typeLink": { "dataPath": "Объект.ВидСубконто", "linkItem": 0 }
```

Short form - the string `"dataPath"` or `"dataPath#linkItem"`:

```json
"typeLink": "Объект.ВидСубконто"
"typeLink": "Объект.ВидСубконто#1"
```
