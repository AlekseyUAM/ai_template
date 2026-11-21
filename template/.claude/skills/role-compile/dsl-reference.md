# Role DSL - full reference

Detailed reference for the JSON DSL of `/role-compile`. A compact description is in [SKILL.md](SKILL.md).

## Which objects can be written in `objects`

Rights in a role are held by exactly 27 types. A type outside this list is a compilation error: the role is not
created, files are not written.

| Type | Rights |
|-----|-------|
| `Configuration` | Administration, DataAdministration, UpdateDataBaseConfiguration, ConfigurationExtensionsAdministration, ActiveUsers, EventLog, ExclusiveMode, ThinClient, ThickClient, WebClient, MobileClient, ExternalConnection, Automation, Output, SaveUserData, TechnicalSpecialistMode, InteractiveOpenExtDataProcessors, InteractiveOpenExtReports, AnalyticsSystemClient, CollaborationSystemInfoBaseRegistration, MainWindowModeNormal, MainWindowModeWorkplace, MainWindowModeEmbeddedWorkplace, MainWindowModeFullscreenWorkplace, MainWindowModeKiosk |
| `Catalog`, `ChartOfCharacteristicTypes` | Read, Insert, Update, Delete, View, Edit, InputByString, Interactive* (Insert, SetDeletionMark, ClearDeletionMark, Delete, DeleteMarked), *PredefinedData, *DataHistory* |
| `Document` | same + Posting, UndoPosting, InteractivePosting, InteractivePostingRegular, InteractiveUndoPosting, InteractiveChangeOfPosted |
| `ChartOfAccounts`, `ChartOfCalculationTypes`, `ExchangePlan` | Read, Insert, Update, Delete, View, Edit, InputByString, Interactive*, *DataHistory* |
| `BusinessProcess` | Read, Insert, Update, Delete, View, Edit, InputByString, Start, InteractiveInsert, InteractiveSetDeletionMark, InteractiveClearDeletionMark, InteractiveDelete, InteractiveDeleteMarked, InteractiveActivate, InteractiveStart, *DataHistory* |
| `Task` | same, but Execute, InteractiveExecute instead of Start/InteractiveStart |
| `InformationRegister` | Read, Update, View, Edit, TotalsControl, *DataHistory* |
| `AccumulationRegister`, `AccountingRegister` | Read, Update, View, Edit, TotalsControl |
| `CalculationRegister` | Read, Update, View, Edit |
| `Constant` | Read, Update, View, Edit, *DataHistory* |
| `DocumentJournal` | Read, View |
| `Sequence` | Read, Update |
| `DataProcessor`, `Report` | Use, View |
| `WebService`, `HTTPService`, `IntegrationService` | - rights only on nested objects, see below |
| `CommonForm`, `CommonCommand`, `Subsystem`, `FilterCriterion` | View |
| `CommonAttribute` | View, Edit |
| `SessionParameter` | Get, Set |
| `ExternalDataSource` | Use, Administration, StandardAuthenticationChange, SessionStandardAuthenticationChange, SessionOSAuthenticationChange |

Full right lists for each type are in the skill code (`scripts/role-compile.py`,
known rights table); the skill checks every right name and rejects a nonexistent one.

### Nested objects

A path longer than two segments sets rights on a part of an object. The nesting kind is the
second-to-last segment; it determines the right set.

| Kind | Rights |
|-----|-------|
| `Attribute`, `StandardAttribute`, `TabularSection`, `StandardTabularSection`, `Dimension`, `Resource`, `AccountingFlag`, `ExtDimensionAccountingFlag`, `AddressingAttribute` | View, Edit |
| `Command`, nested `Subsystem` | View |
| `Operation` (web service), `Method` (HTTP service, under `URLTemplate`), `IntegrationServiceChannel` | Use |
| `Recalculation` (calculation register) | Read, Update |

The kinds `Operation`, `Method`, `IntegrationServiceChannel`, `Recalculation` and the external
source kinds are allowed only under their own parent type. Document journal graphs
(`DocumentJournal.Ж.Column.Г`) have no rights of their own.

Examples: `Catalog.Контрагенты.Attribute.ИНН: View, Edit`,
`Document.Реализация.TabularSection.Товары.Attribute.Цена: View`,
`WebService.Обмен.Operation.Загрузить: Use`,
`HTTPService.API.URLTemplate.Файлы.Method.Получить: Use`.

The segment after `Method.` is the **name of the Method object in the metadata tree**, not an HTTP verb:
both `Method.GET`, `Method.Установить`, and `Method.СоздатьПодключение` occur.

For the short notation `HTTPService.API: Use` see section "Services" in `SKILL.md`.

### Nested objects of an external data source

The kinds `Table`, `Cube`, `Function`, `Field`, `DimensionTable` occur **only** under
`ExternalDataSource`.

| Path | Rights |
|------|-------|
| `ExternalDataSource.И.Table.Т` | Read, Insert, Update, Delete, View, Edit, InputByString, InteractiveInsert, InteractiveDelete |
| `ExternalDataSource.И.Table.Т.Field.П` | View, Edit |
| `ExternalDataSource.И.Cube.К` | Read, View |
| `ExternalDataSource.И.Cube.К.Dimension.И`, `…Resource.Р` | View |
| `ExternalDataSource.И.Cube.К.DimensionTable.Т` | Read, View |
| `ExternalDataSource.И.Cube.К.DimensionTable.Т.Field.П` | View, Edit |
| `ExternalDataSource.И.Function.Ф` | Use, View |
| `…Table.Т.Command.К`, `…Cube.К.Command.К`, `…DimensionTable.Т.Command.К` | View |

### Object types without rights in roles

Rights cannot be assigned to `Enum`, `CommonModule`, `DefinedType`, `CommonPicture`,
`CommonTemplate`, `Language`, `FunctionalOption`, `FunctionalOptionsParameter`,
`EventSubscription`, `ScheduledJob`, `StyleItem`, `Style`, `SettingsStorage`,
`XDTOPackage`, `WSReference`, `DocumentNumerator` - these types are not in the role editor tree.

An attempt is a compilation error. Rights on enums are especially dangerous: a configuration with such
a block does not load into the infobase, and Configurator hangs without messages.

## Object entry format

The `objects` array accepts strings (shorthand) and objects (full form).

```json
{
  "name": "Document.Реализация",
  "preset": "view",
  "rights": { "Delete": false },
  "rls": { "Read": "#ДляОбъекта(\"\")" }
}
```

- `preset` - basic right set (`"view"`, `"edit"`)
- `rights` - overrides: dict `{"Right": true/false}` or array `["Right1", "Right2"]`
- `rls` - RLS restrictions: `{"ИмяПрава": "текст условия"}`

Russian type and right names are also accepted (`Справочник.Контрагенты: Чтение`); the canonical
form is English.

## Presets - detailed tables

Presets are marked with `@` in string format. In object form the key is `preset` without `@`.

### `@view` - view

| Object type | Rights |
|-------------|-------|
| Catalog, ExchangePlan, Document, ChartOfAccounts, ChartOfCharacteristicTypes, ChartOfCalculationTypes, BusinessProcess, Task | Read, View, InputByString |
| InformationRegister, AccumulationRegister, AccountingRegister, CalculationRegister, Constant, DocumentJournal | Read, View |
| Sequence | Read |
| CommonForm, CommonCommand, Subsystem, FilterCriterion, CommonAttribute | View |
| DataProcessor, Report | Use, View |
| SessionParameter | Get |
| Configuration | ThinClient, WebClient, Output, SaveUserData, MainWindowModeNormal |

### `@edit` - full editing

| Object type | Rights |
|-------------|-------|
| Catalog, ExchangePlan, ChartOfAccounts, ChartOfCharacteristicTypes, ChartOfCalculationTypes | Read, Insert, Update, Delete, View, Edit, InputByString, InteractiveInsert, InteractiveSetDeletionMark, InteractiveClearDeletionMark |
| Document | Read, Insert, Update, Delete, View, Edit, InputByString, Posting, UndoPosting, InteractiveInsert, InteractiveSetDeletionMark, InteractiveClearDeletionMark, InteractivePosting, InteractivePostingRegular, InteractiveUndoPosting, InteractiveChangeOfPosted |
| BusinessProcess | Read, Insert, Update, Delete, View, Edit, InputByString, Start, InteractiveInsert, InteractiveSetDeletionMark, InteractiveClearDeletionMark, InteractiveActivate, InteractiveStart |
| Task | Read, Insert, Update, Delete, View, Edit, InputByString, Execute, InteractiveInsert, InteractiveSetDeletionMark, InteractiveClearDeletionMark, InteractiveActivate, InteractiveExecute |
| InformationRegister, AccumulationRegister, AccountingRegister, Constant | Read, Update, View, Edit |
| DocumentJournal | Read, View |
| Sequence | Read, Update |
| SessionParameter | Get, Set |
| CommonAttribute | View, Edit |

For services (WebService, HTTPService, IntegrationService) and external data sources
presets are not defined - set rights explicitly: `"WebService.Обмен.Operation.Загрузить: Use"`.

## Restriction templates (RLS templates)

```json
"templates": [
  {
    "name": "ДляОбъекта(Модификатор)",
    "condition": "// текст шаблона\nГДЕ 1=1\n&Модификатор"
  }
]
```

- `&` in a condition is escaped automatically as `&amp;` in XML
- Reference to a template in `rls`: `"#ИмяШаблона(\"параметры\")"` - starts with `#`
- Template parameters can be passed empty: `#ДляОбъекта("")`

## Examples

### Role with RLS

```json
{
  "name": "ЧтениеДокументовПоОрганизации",
  "synonym": "Чтение документов (ограничение по организации)",
  "objects": [
    "Catalog.Организации: @view",
    {
      "name": "Document.РеализацияТоваровУслуг",
      "preset": "view",
      "rls": {
        "Read": "#ДляОбъекта(\"\")"
      }
    }
  ],
  "templates": [
    {
      "name": "ДляОбъекта(Модификатор)",
      "condition": "ГДЕ Организация = &ТекущаяОрганизация"
    }
  ]
}
```

### Role with rights overridden from a preset

```json
{
  "name": "ОграниченноеРедактирование",
  "synonym": "Редактирование без удаления",
  "objects": [
    {
      "name": "Catalog.Контрагенты",
      "preset": "edit",
      "rights": { "Delete": false }
    }
  ]
}
```

### Role with rights on parts of an object

```json
{
  "name": "МенеджерБезЦен",
  "synonym": "Менеджер без доступа к ценам",
  "objects": [
    "Catalog.Номенклатура: @view",
    { "name": "Catalog.Номенклатура.Attribute.Цена", "rights": { "View": false, "Edit": false } }
  ]
}
```
