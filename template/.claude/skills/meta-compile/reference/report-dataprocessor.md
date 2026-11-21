# Report, DataProcessor (Отчёты и Обработки)

Almost identical in composition: attributes, tabular sections, forms, templates, commands. The object module is `Ext/ObjectModule.bsl`.
Attributes and tabular sections - `attributes.md`; commands - `blocks.md`.

References to forms/schemas/storages are written **as is** (the form name may literally be "Форма").

## Report (Отчёт)

> **Report form.** Do not create your own `ФормаОтчета` and do not assign `defaultForm`,
> unless the specification requires it: the platform builds the report form automatically from the DCS. A custom
> form is an extra object and a risk of malfunction; add it only on an explicit
> requirement and validate it separately.

| Key | Default | Values |
|------|-----------|----------|
| `comment` | empty | string |
| `useStandardCommands` | `true` | bool (availability via the standard command interface) |
| `mainDataCompositionSchema` | empty | main DCS template (`Report.X.Template.ОсновнаяСхемаКомпоновкиДанных`) |
| `defaultForm` / `auxiliaryForm` | empty | main / auxiliary form |
| `defaultSettingsForm` / `auxiliarySettingsForm` / `defaultVariantForm` | empty | settings / variant forms |
| `variantsStorage` / `settingsStorage` | empty | variant / settings storages (`SettingsStorage.X`) |
| `extendedPresentation` / `explanation` | empty | presentation / explanation (ML) |
| `includeHelpInContents` | `false` | bool |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

```json
{ "type": "Report", "name": "АнализПродаж", "useStandardCommands": false,
  "mainDataCompositionSchema": "Report.АнализПродаж.Template.ОсновнаяСхемаКомпоновкиДанных",
  "attributes": ["Период: StandardPeriod"] }
```

## DataProcessor (Обработка)

| Key | Default | Values |
|------|-----------|----------|
| `comment` | empty | string |
| `useStandardCommands` | `true` | bool |
| `defaultForm` / `auxiliaryForm` | empty | main / auxiliary form |
| `extendedPresentation` / `explanation` | empty | presentation / explanation (ML) |
| `includeHelpInContents` | `false` | bool |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

```json
{ "type": "DataProcessor", "name": "ЗагрузкаТаблиц", "useStandardCommands": false,
  "attributes": [{ "name": "Таблица", "type": "ValueTree" }, { "name": "Произвольные", "type": "" }] }
```

> Attributes of reports/data processors allow platform collection types: `ValueTable`, `ValueTree`, `ValueList`,
> `StandardPeriod`, `SpreadsheetDocument`, etc., as well as `"type": ""` - an attribute without a type.
