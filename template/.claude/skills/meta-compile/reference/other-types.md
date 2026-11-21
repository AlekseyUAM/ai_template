# Other types

Rare/service objects. Each has a minimal set of properties.

## FunctionalOption (Функциональная опция)

| Key | Default | Values |
|------|-----------|----------|
| `location` | empty | where the value is stored: `Constant.X` / `InformationRegister.X.Resource.Y` / `<Тип>.X.Attribute.Y` |
| `content` | `[]` | attributes/dimensions/resources depending on the option (full object paths) |
| `privilegedGetMode` | `true` | bool |
| `comment` | empty | string |

```json
{ "type": "FunctionalOption", "name": "ВестиУчетПоСкладам", "location": "Constant.ВестиУчетПоСкладам",
  "content": ["Document.РеализацияТоваров.TabularSection.Товары.Attribute.Склад"] }
```

## FilterCriterion (Критерий отбора)

| Key | Default | Values |
|------|-----------|----------|
| `valueType` | - | filter value type (composite via `+`) |
| `content` | `[]` | attributes the filter is based on (object paths) |
| `useStandardCommands` | `true` | bool |
| `defaultForm` / `auxiliaryForm` | empty | forms |
| `comment` | empty | string |

```json
{ "type": "FilterCriterion", "name": "ДокументыПоКонтрагенту", "valueType": "CatalogRef.Контрагенты",
  "content": ["Document.Реализация.Attribute.Контрагент"] }
```

## SettingsStorage (Хранилище настроек)

| Key | Default | Values |
|------|-----------|----------|
| `defaultSaveForm` / `defaultLoadForm` | empty | save / load forms |
| `auxiliarySaveForm` / `auxiliaryLoadForm` | empty | auxiliary forms |
| `comment` | empty | string |

## CommonForm (Общая форма)

Creates metadata + a form stub. The form content is filled by `/form-compile` or `/form-edit`.

| Key | Default | Values |
|------|-----------|----------|
| `formType` | `Managed` | form type |
| `usePurposes` | `[PlatformApplication, MobilePlatformApplication]` | purposes (array) |
| `useStandardCommands` | `false` | bool |
| `includeHelpInContents` | `false` | bool |
| `comment` | empty | string |

```json
{ "type": "CommonForm", "name": "НастройкиОбмена", "usePurposes": ["PlatformApplication"] }
```

## CommonPicture / CommonTemplate (Общие картинки и макеты)

Metadata + registration only; the content (`Ext/Picture*`, `Ext/Template.*`) is imported separately
(for a spreadsheet template - `/mxl-compile`).

- **CommonPicture** - `availabilityForChoice` / `availabilityForAppearance` (bool, `false` by default).
- **CommonTemplate** - `templateType` (`SpreadsheetDocument` by default / `TextDocument` / `HTMLDocument` /
  `BinaryData` / `AddIn` / `DataCompositionSchema` / `DataCompositionAppearanceTemplate` / `GraphicalSchema`).

```json
{ "type": "CommonTemplate", "name": "ПечатьЗаказа", "templateType": "SpreadsheetDocument" }
```

## Service types

- **SessionParameter** (session parameter) - `valueType` (value type, composite via `+`).
- **FunctionalOptionsParameter** (functional option parameter) - `use` (array of dimensions/attributes).
- **WSReference** (WS reference) - `locationURL` (WSDL URL).
- **CommandGroup** (command group) - `category` (default `NavigationPanel`) - where the group is placed:
  `NavigationPanel` / `ActionsPanel` (section command interface) or `FormCommandBar` / `FormNavigationPanel`
  (form command interface); `representation` (`Auto`), `tooltip` (ML), `picture`. Object commands reference a
  group via `group: "CommandGroup.<Имя>"` (see `blocks.md`).
- **CommonCommand** (common command) - `group`, `representation`, `tooltip`, `picture`, `shortcut`,
  `commandParameterType`, `parameterUseMode` (`Single`/`Multiple`), `modifiesData`, `includeHelpInContents`.
  Creates `Ext/CommandModule.bsl`.
- **CommonAttribute** (common attribute) - `valueType` (`String(0)` by default) + attribute properties
  (`attributes.md`) + `content` (objects the attribute is included in) + data separation properties
  (`dataSeparation`, `separatedDataUse`, `usersSeparation`, … - `DontUse`/`Independently` by default).

```json
{ "type": "CommonAttribute", "name": "Организация", "valueType": "CatalogRef.Организации",
  "autoUse": "Use", "content": ["Document.РеализацияТоваров", "Document.ПоступлениеТоваров"] }
```
