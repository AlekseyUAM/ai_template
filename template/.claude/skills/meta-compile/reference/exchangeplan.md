# ExchangePlan (План обмена)

Close to a catalog (without hierarchy/owners), plus the composition of exchange objects. Inherits the Catalog layer:
`codeLength`, `codeAllowedLength`, `descriptionLength`, `defaultPresentation`, `editType`, `quickChoice`,
`choiceMode`, forms, `standardAttributes`, `characteristics`, `inputByString`, `basedOn`, presentations -
see `catalog.md` / `attributes.md` / `blocks.md`.

| Key | Default | Values |
|------|-----------|----------|
| `comment` | empty | string |
| `distributedInfoBase` | `false` | bool (distributed infobase - DIB) |
| `includeConfigurationExtensions` | `false` | bool (include configuration extensions) |
| `descriptionLength` | `150` | description length |
| `createOnInput` | `DontUse` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `dataHistory` | `DontUse` | `Use` / `DontUse` |
| `useStandardCommands` | `true` | bool |
| `content` | `[]` | exchange content (see below) |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

## `content` - exchange plan content

A list of exchange participant objects; each has an auto-registration of changes flag (off by default).
An item is a reference to a metadata object (string) or an object with the flag:

```json
"content": [
  "Catalog.Организации",                                    // авторегистрация выключена
  "InformationRegister.Курсы: autoRecord",                  // авторегистрация включена (токен)
  { "metadata": "Document.РеализацияТоваров", "autoRecord": true }
]
```

- A string `"Тип.Имя"` - auto-registration off; the `: autoRecord` suffix - on.
- Object: `metadata` (reference), `autoRecord` (bool or `Allow`/`Deny`).

```json
{ "type": "ExchangePlan", "name": "ОбменССайтом", "distributedInfoBase": false,
  "content": ["Catalog.Номенклатура: autoRecord", "Catalog.Контрагенты: autoRecord"],
  "attributes": ["АдресСервера: String(200)"] }
```
