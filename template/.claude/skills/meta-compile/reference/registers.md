# Registers: Information, Accumulation, Accounting, Calculation

**Dimensions and resources** are specified as attributes (shorthand `"Имя: Тип | флаги"` or object form, see
`attributes.md`). Dimension flags: `master`, `mainFilter`, `denyIncomplete`, `useInTotals` (accumulation register).

```json
"dimensions": ["Организация: CatalogRef.Организации | master, mainFilter"],
"resources": ["Сумма: Number(15,2)"]
```

## InformationRegister (Регистр сведений)

| Key | Default | Values |
|------|-----------|----------|
| `writeMode` | `Independent` | `Independent` / `RecorderSubordinate` |
| `periodicity` | `Nonperiodical` | `Nonperiodical` / `Second` / `Day` / `Month` / `Quarter` / `Year` / `RecorderPosition` |
| `mainFilterOnPeriod` | `false` | bool (main filter by period) |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `dimensions` / `resources` / `attributes` | `[]` | dimensions / resources / attributes |

```json
{ "type": "InformationRegister", "name": "КурсыВалют", "periodicity": "Day",
  "dimensions": ["Валюта: CatalogRef.Валюты | master, mainFilter, denyIncomplete"],
  "resources": ["Курс: Number(15,4)", "Кратность: Number(10,0)"] }
```

## AccumulationRegister (Регистр накопления)

| Key | Default | Values |
|------|-----------|----------|
| `registerType` | `Balance` | `Balance` (balances) / `Turnovers` (turnovers) |
| `enableTotalsSplitting` | `true` | bool (totals splitting) |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `dimensions` / `resources` / `attributes` | `[]` | dimensions / resources / attributes |

```json
{ "type": "AccumulationRegister", "name": "ОстаткиТоваров", "registerType": "Balance",
  "dimensions": ["Номенклатура: CatalogRef.Номенклатура", "Склад: CatalogRef.Склады"],
  "resources": ["Количество: Number(15,3)"] }
```

## AccountingRegister (Регистр бухгалтерии)

| Key | Default | Values |
|------|-----------|----------|
| `chartOfAccounts` | - | **required**: reference to the chart of accounts `ChartOfAccounts.X` |
| `correspondence` | `false` | bool (correspondence) |
| `periodAdjustmentLength` | `0` | adjustment period length |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `dimensions` / `resources` / `attributes` | `[]` | dimensions / resources / attributes |

```json
{ "type": "AccountingRegister", "name": "Хозрасчетный",
  "chartOfAccounts": "ChartOfAccounts.Хозрасчетный",
  "dimensions": ["Организация: CatalogRef.Организации"], "resources": ["Сумма: Number(15,2)"] }
```

## CalculationRegister (Регистр расчёта)

| Key | Default | Values |
|------|-----------|----------|
| `chartOfCalculationTypes` | - | **required**: reference to the chart of calculation types `ChartOfCalculationTypes.X` |
| `periodicity` | `Month` | periodicity |
| `actionPeriod` | `false` | bool (action period) |
| `basePeriod` | `false` | bool (base period) |
| `schedule` | empty | reference to the schedule information register |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `dimensions` / `resources` / `attributes` | `[]` | dimensions / resources / attributes |

```json
{ "type": "CalculationRegister", "name": "Начисления",
  "chartOfCalculationTypes": "ChartOfCalculationTypes.Начисления", "periodicity": "Month",
  "dimensions": ["Сотрудник: CatalogRef.Сотрудники"], "resources": ["Сумма: Number(15,2)"] }
```

> **AccountingRegister** requires a chart of accounts, **CalculationRegister** - a chart of calculation types (and both - a recorder document).
