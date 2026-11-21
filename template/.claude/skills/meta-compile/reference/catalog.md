# Catalog (Справочник)

```json
{ "type": "Catalog", "name": "Организации", "descriptionLength": 100,
  "attributes": ["ИНН: String(12)", "КПП: String(9)"] }
```

## Properties

| Key | Default | Values |
|------|-----------|----------|
| `comment` | empty | string |
| `hierarchical` | `false` | bool |
| `hierarchyType` | `HierarchyFoldersAndItems` | `HierarchyFoldersAndItems` / `HierarchyOfItems` |
| `limitLevelCount` | `false` | bool (limit the number of levels) |
| `levelCount` | `2` | number of levels (with `limitLevelCount`) |
| `foldersOnTop` | `true` | bool (folders on top) |
| `owners` | `[]` | array of owners: `["Catalog.Контрагенты"]` |
| `subordinationUse` | `ToItems` | `ToItems` / `ToFolders` / `ToFoldersAndItems` (whom it is subordinate to) |
| `codeLength` | `9` | code length (0 - no code) |
| `codeType` | `String` | `String` / `Number` |
| `codeAllowedLength` | `Variable` | `Variable` / `Fixed` |
| `codeSeries` | `WholeCatalog` | `WholeCatalog` / `WithinSubordination` / `WithinOwnerSubordination` |
| `autonumbering` | `true` | bool (autonumbering) |
| `checkUnique` | `false` | bool (code uniqueness check) |
| `descriptionLength` | `25` | description length |
| `defaultPresentation` | `AsDescription` | `AsDescription` / `AsCode` |
| `quickChoice` | `true` | bool (quick choice) |
| `choiceMode` | `BothWays` | `BothWays` / `QuickChoice` / `FromForm` |
| `editType` | `InDialog` | `InDialog` / `InList` / `BothWays` |
| `createOnInput` | `Use` | `Auto` / `Use` / `DontUse` |
| `choiceHistoryOnInput` | `Auto` | `Auto` / `DontUse` |
| `fullTextSearch` | `Use` | `Use` / `DontUse` |
| `fullTextSearchOnInputByString` | `DontUse` | `Use` / `DontUse` |
| `searchStringModeOnInputByString` | `Begin` | `Begin` / `AnyPart` |
| `predefinedDataUpdate` | `Auto` | `Auto` / `DontAutoUpdate` / `AutoUpdate` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `useStandardCommands` | `true` | bool |
| `includeHelpInContents` | `false` | bool |
| `attributes` | `[]` | attributes (shorthand / object form) |
| `tabularSections` | `{}` | tabular sections |

**Forms.** A form reference is `Тип.Объект.Form.ИмяФормы` (e.g. `Catalog.Организации.Form.ФормаЭлемента`).
Main form slots: `defaultObjectForm`, `defaultFolderForm`, `defaultListForm`, `defaultChoiceForm`,
`defaultFolderChoiceForm`; auxiliary ones - the same names with the `auxiliary` prefix (`auxiliaryObjectForm`, …).

## `predefined` - predefined items

An array of predefined items -> `Ext/Predefined.xml`. An item is a string (flat case) or an object (hierarchy).

**String:** `"(Код) Имя [Наименование]"` - `Имя` is required; `(Код)` and `[Наименование]` are optional.
Without `[...]` the description is derived from the name; `[]` - empty; `[текст]` - the given one.

```json
"predefined": [
  "Основной",
  "(1) ДокументОПриемке [Документ о приемке]",
  { "name": "Группа1", "isFolder": true, "description": "Прочие",
    "childItems": ["Факс", "(7) Скайп"] }
]
```

**Object:** `name` (required), `code`, `description` (name), `isFolder` (folder flag),
`childItems` (nested, recursively). The code type is per the `codeType` property.

## Additional

- Attribute and tabular section properties - `attributes.md`.
- Presentations (`objectPresentation`, `listPresentation`, …), object commands, characteristics
  ("Additional attributes and information"), standard attribute customization, `inputByString` / `dataLockFields` /
  `basedOn` - `blocks.md`.
