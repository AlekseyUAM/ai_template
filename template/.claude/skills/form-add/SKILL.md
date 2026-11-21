---
name: form-add
description: Add an empty managed form to a 1C object. Use when you need to create a new form for an object
argument-hint: <ObjectPath> <FormName> [-Purpose <Purpose>] [-Synonym <Synonym>] [-SetDefault]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /form-add - Adding a form to a configuration object

Creates a managed form (metadata XML + Form.xml + Module.bsl) and registers it in the root XML of the configuration object (Document, Catalog, InformationRegister, etc.).

> **DCS reports.** A report with a main data composition schema does not need its own form:
> the platform builds an auto-form from the DCS. Do not call `form-add` for a report and do not assign
> `defaultForm` without an explicit requirement in the specification.

## Usage

```
/form-add <ObjectPath> <FormName> [-Purpose <Purpose>] [-Synonym <Synonym>] [-SetDefault]
```

| Parameter   | Required     | Default      | Description                                  |
|-------------|:------------:|--------------|----------------------------------------------|
| ObjectPath  | yes          | -            | Path to the object XML file (Documents/Док.xml) |
| FormName    | yes          | -            | Form name (ФормаДокумента)                    |
| Purpose     | no           | main form of the kind | Form purpose - see the table below: for a catalog this is the object form, for an information register - the record form, for a journal - the list form |
| Synonym     | no           | = FormName   | Form synonym                                 |
| -SetDefault | no           | auto         | Make it the main one. Without the flag, the first form of each purpose becomes the main one |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/form-add.py" -ObjectPath "<ObjectPath>" -FormName "<FormName>" [-Purpose "<Purpose>"] [-Synonym "<Synonym>"] [-SetDefault]
```

## Purpose - form purpose

| Purpose | Which form | Becomes the main one |
|---------|-------------|---------------------|
| Object | object form (item, document, data processor) | yes |
| List | list form | yes |
| Choice | choice form | yes |
| Folder | folder form | yes |
| FolderChoice | folder choice form | yes |
| Record | record form | yes |
| RecordSet | record set form | no - the platform has no such property |
| Save | settings save form | yes |
| Load | settings load form | yes |
| Custom | arbitrary form, not bound to the object | no |

### What is available for an object type

| Object type | Purposes |
|-------------|------------|
| Catalog, ChartOfCharacteristicTypes | Object, Folder, List, Choice, FolderChoice, Custom |
| Document, ChartOfAccounts, ChartOfCalculationTypes, ExchangePlan, BusinessProcess, Task | Object, List, Choice, Custom |
| DataProcessor, Report, ExternalDataProcessor, ExternalReport | Object, Custom |
| InformationRegister | Record, List, RecordSet, Custom |
| AccumulationRegister, AccountingRegister, CalculationRegister | List, RecordSet, Custom |
| DocumentJournal, FilterCriterion | List, Custom |
| Enum | List, Choice, Custom |
| SettingsStorage | Save, Load, Custom |
| Table (external data source table) | `tableDataType=ObjectData` - Object, List, Choice, Custom; `NonobjectData` - Record, List, Choice, Custom |

An invalid combination is rejected with the list of purposes available for that type. A constant has no
forms of its own - a common form (`CommonForm`) is used for it.

An external data source table is addressed by the table file:
`ExternalDataSources/<Источник>/Tables/<Таблица>.xml`. References in such a form are three-part;
without `-Purpose` the object form is taken, and for a table with a composite key - the record form.

## Examples

```
# Форма документа
/form-add Documents/АвансовыйОтчет.xml ФормаДокумента -Purpose Object

# Форма списка каталога
/form-add Catalogs/Контрагенты.xml ФормаСписка -Purpose List

# Форма записи регистра сведений
/form-add InformationRegisters/КурсыВалют.xml ФормаЗаписи -Purpose Record

# Форма выбора с синонимом
/form-add Catalogs/Номенклатура.xml ФормаВыбора -Purpose Choice -Synonym "Выбор номенклатуры"

# Установить как форму по умолчанию
/form-add Documents/Заказ.xml ФормаДокументаНовая -Purpose Object -SetDefault
```

## Workflow

1. `/form-add` - create the form skeleton
2. `/form-compile` or `/form-edit` - fill Form.xml with elements
3. `/form-validate` - check correctness
4. `/form-info` - analyze the result
