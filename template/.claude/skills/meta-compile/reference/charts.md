# Charts: ChartOfCharacteristicTypes, ChartOfAccounts, ChartOfCalculationTypes

All three are reference types (they inherit the Catalog layer: codes, `standardAttributes`, `characteristics`, `inputByString`,
forms, presentations - see `catalog.md` / `attributes.md` / `blocks.md`) with predefined items and their own
special properties.

## ChartOfCharacteristicTypes (План видов характеристик)

Stores characteristic (kind) definitions. Hierarchical (folders + items).

| Key | Default | Values |
|------|-----------|----------|
| `valueType` | any primitive | characteristic value type (composite - string `"A + B"` or `valueTypes` array) |
| `characteristicExtValues` | empty | reference to the additional values catalog |
| `hierarchical` | `false` | bool |
| `foldersOnTop` | `true` | bool |
| `codeLength` | `9` | code length |
| `descriptionLength` | `100` | description length |
| `checkUnique` | `true` | bool |
| `autonumbering` | `true` | bool |
| `codeSeries` | `WholeCharacteristicKind` | code series |
| `createOnInput` | `DontUse` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `predefined` | `[]` | predefined kinds (carry the value type - see below) |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

**Predefined kinds** carry a **value type per item** - as a short string after `:`
(`"(Код) Имя [Наименование]: Тип"`, composite via `+`) or as an object form with the `type` key:

```json
"predefined": [
  "(000001) Цвет: CatalogRef.Цвета",
  "(000002) Размер [Размер одежды]: String(50) + Number(3,0)",
  { "name": "Группа", "isFolder": true, "type": "" }
]
```

## ChartOfAccounts (План счетов)

| Key | Default | Values |
|------|-----------|----------|
| `extDimensionTypes` | empty | reference to the chart of characteristic types of subconto kinds `ChartOfCharacteristicTypes.X` |
| `maxExtDimensionCount` | `0` (no chart of characteristic types) / `3` (with it) | max number of subconto |
| `codeMask` | empty | account code mask (e.g. `"@@@.@@"`) |
| `codeLength` | `9` | code length |
| `descriptionLength` | `25` | description length |
| `checkUnique` | `true` | bool |
| `codeSeries` | `WholeChartOfAccounts` | code series |
| `defaultPresentation` | `AsCode` | `AsCode` / `AsDescription` |
| `autoOrderByCode` | `true` | bool |
| `orderLength` | `9` | ordering string length |
| `createOnInput` | `DontUse` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `accountingFlags` | `[]` | accounting flags (as attributes, default type Boolean; array of names/attributes) |
| `extDimensionAccountingFlags` | `[]` | subconto accounting flags (as attributes) |
| `predefined` | `[]` | predefined accounts (see below) |

**Predefined account** (object form):

| Field | Default | Values |
|------|-----------|----------|
| `name` | - | name (required) |
| `code` | empty | account code |
| `description` | from name | name |
| `accountType` | `ActivePassive` | `Active` / `Passive` / `ActivePassive` |
| `offBalance` | `false` | bool (off-balance) |
| `order` | - | sort string |
| `flags` | `[]` | enabled accounting flags (TRUE only) |
| `subconto` | `[]` | subconto kinds (see below) |
| `childItems` | `[]` | subordinate accounts |

`subconto` - a string `"Вид | Признак1, Признак2"` (after `|` - enabled subconto accounting flags; the `Turnover` token means
"turnovers only") or an object `{ type, turnover, flags }`. `Вид` - the name of a predefined kind from the chart of
characteristic types `extDimensionTypes`.

```json
"predefined": [
  { "name": "ОсновныеСредства", "code": "01", "accountType": "Active", "order": " 01",
    "flags": ["Количественный"], "subconto": ["Номенклатура | Суммовой, Валютный"],
    "childItems": [ { "name": "ОСВОрганизации", "code": "01.01", "accountType": "Active", "order": " 01.01" } ] }
]
```

## ChartOfCalculationTypes (План видов расчёта)

| Key | Default | Values |
|------|-----------|----------|
| `codeLength` | `5` | code length |
| `descriptionLength` | `100` | description length |
| `codeAllowedLength` | `Variable` | `Variable` / `Fixed` |
| `dependenceOnCalculationTypes` | `DontUse` | `DontUse` / `OnActionPeriod` / `OnRegistrationPeriod` |
| `baseCalculationTypes` | `[]` | base calculation types (list of references `ChartOfCalculationTypes.X`) |
| `actionPeriodUse` | `false` | bool (use action period) |
| `createOnInput` | `DontUse` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `predefined` | `[]` | predefined calculation types (see below) |

**Predefined calculation type** - flat: a string `"(Код) Имя [Наименование]"` or an object
`{ name, code, description, actionPeriodIsBase }` (`actionPeriodIsBase` - bool, `false` by default).

```json
"predefined": [ "(00001) Оклад [Оклад по дням]", { "name": "Премия", "code": "00002", "actionPeriodIsBase": true } ]
```

> **ChartOfAccounts** references a chart of characteristic types via `extDimensionTypes`. An accounting/calculation
> register requires the corresponding chart (see `registers.md`).
