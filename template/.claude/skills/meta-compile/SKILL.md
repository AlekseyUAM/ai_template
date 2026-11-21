---
name: meta-compile
description: Create a 1C metadata object. Use when you need to create or add a catalog, document, register, enum, constant, common module, data processor, report, etc.
argument-hint: <JsonPath> <OutputDir>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /meta-compile - generating metadata objects from JSON

Accepts an object JSON definition -> generates XML + modules in the configuration dump structure and
registers the object in `Configuration.xml`.

`ConfigDumpInfo.xml` is intentionally not touched: it is a service file of object versions managed by
the platform (for incremental dump).

## Workflow

1. Compose JSON using the syntax below -> write it to a temporary file.
2. Run the script.
3. Modify the created object - `/meta-edit`; validate - `/meta-validate`.

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-compile.py" -JsonPath "<json>" -OutputDir "<ConfigDir>"
```

| Parameter | Description |
|----------|----------|
| `JsonPath` | Path to the JSON file |
| `OutputDir` | Root of the configuration dump (where `Configuration.xml`, `Catalogs/`, `Documents/`, ... are) |

## JSON format

**Single object** `{ ... }` or an **array** of objects `[{ ... }, { ... }]` (batch - several objects per run).

```json
{ "type": "Catalog", "name": "Номенклатура", "...свойства типа...": "..." }
```

`type` and `name` are required. The rest depends on the type (see the index below). By default `synonym` is derived from
`name` (CamelCase -> words separated by spaces); it can be set explicitly as a string or multilingual: `"synonym": { "ru": "…", "en": "…" }`.

## Attributes (shorthand)

The `attributes`, `dimensions`, `resources` arrays and columns in `tabularSections` are specified as strings:

```
"Имя"                          → String(10)
"Имя: Тип"                     → с типом
"Имя: Тип | req, index"        → с флагами
```

**Types:** `String(100)`, `String(10, fixed)` (fixed length), `Number(15,2)`, `Boolean`, `Date`, `DateTime`,
`Time`, reference `CatalogRef.Xxx` / `DocumentRef.Xxx` / `EnumRef.Xxx` / `DefinedType.Xxx`, etc.
Composite type - via `+`: `"Значение: String + Number(15,2) + CatalogRef.Контрагенты"`.

**Flags** (after `|`, comma-separated):

| Flag | Meaning | Where |
|------|----------|-----|
| `req` | required filling | attributes, dimensions, resources |
| `index` | index | attributes, dimensions |
| `indexAdditional` | index with additional ordering | attributes |
| `multiline` | multiline field | attributes |
| `nonneg` | non-negative (Number) | attributes, resources |
| `master` | leading dimension | dimensions (registers) |
| `mainFilter` | main filter | dimensions (registers) |
| `denyIncomplete` | deny incomplete | dimensions |
| `useInTotals` | use in totals | dimensions (accumulation register) |

If an attribute needs properties beyond shorthand (fill value, choice parameters, format, tooltip, ...),
use the **object form**, see `reference/attributes.md`.

## Tabular sections

```json
"tabularSections": { "Товары": ["Номенклатура: CatalogRef.Номенклатура", "Количество: Number(15,3)"] }
```

The key is the tabular section name, the value is a column array (shorthand) OR an object with tabular section properties (see `reference/attributes.md`).

## Index: properties by type

Each type has its own reference file with properties, defaults and allowed values:

| Type(s) | File |
|--------|------|
| Catalog (Справочник) | `reference/catalog.md` |
| Document, DocumentJournal, Sequence, DocumentNumerator | `reference/document.md` |
| InformationRegister, AccumulationRegister, AccountingRegister, CalculationRegister | `reference/registers.md` |
| ChartOfAccounts, ChartOfCharacteristicTypes, ChartOfCalculationTypes | `reference/charts.md` |
| ExchangePlan | `reference/exchangeplan.md` |
| BusinessProcess, Task | `reference/process.md` |
| Report, DataProcessor | `reference/report-dataprocessor.md` |
| CommonModule, ScheduledJob, EventSubscription | `reference/code.md` |
| HTTPService, WebService | `reference/web.md` |
| Enum, Constant, DefinedType | `reference/simple.md` |
| ExternalDataSource (external data source) | `reference/external-data-source.md` |
| FunctionalOption, FilterCriterion, SettingsStorage, CommonForm, CommonPicture, CommonTemplate, service ones | `reference/other-types.md` |

Cross-type details:
- **`reference/attributes.md`** - object form of an attribute and tabular section column (fill value, choice
  parameters, format, tooltip, bounds, ...) + properties of the tabular section itself.
- **`reference/blocks.md`** - object blocks: presentations, commands (+ characteristics/standard attributes).

This instruction and the reference files are the complete documentation. Do not look for XML examples in configuration dumps.

## Examples

Catalog with attributes:
```json
{ "type": "Catalog", "name": "Организации", "descriptionLength": 100,
  "attributes": ["ИНН: String(12)", "КПП: String(9)", "Директор: CatalogRef.ФизическиеЛица"] }
```

Document with movements and a tabular section:
```json
{ "type": "Document", "name": "ПриходнаяНакладная",
  "registerRecords": ["AccumulationRegister.ОстаткиТоваров"],
  "attributes": ["Организация: CatalogRef.Организации", "Контрагент: CatalogRef.Контрагенты"],
  "tabularSections": { "Товары": ["Номенклатура: CatalogRef.Номенклатура", "Количество: Number(15,3)", "Цена: Number(15,2)"] } }
```

Information register:
```json
{ "type": "InformationRegister", "name": "КурсыВалют", "periodicity": "Day",
  "dimensions": ["Валюта: CatalogRef.Валюты | master, mainFilter, denyIncomplete"],
  "resources": ["Курс: Number(15,4)", "Кратность: Number(10,0)"] }
```

Batch:
```json
[ { "type": "Enum", "name": "Статусы", "values": ["Новый", "Закрыт"] },
  { "type": "Catalog", "name": "Валюты" },
  { "type": "Constant", "name": "ОсновнаяВалюта", "valueType": "CatalogRef.Валюты" } ]
```
