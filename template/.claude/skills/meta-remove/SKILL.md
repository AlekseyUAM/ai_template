---
name: meta-remove
description: Delete a metadata object from a 1C configuration. Use when you need to delete or remove an object from the configuration
argument-hint: <ConfigDir> -Object <Type.Name>
allowed-tools:
  - Bash
  - Read
  - Glob
  - AskUserQuestion
---

# /meta-remove - deleting a metadata object

Safely deletes an object from the configuration XML dump. Before deletion it checks references to the object in attributes, code and other metadata. If references are found - deletion is blocked.

## Usage

```
/meta-remove <ConfigDir> -Object <Type.Name>
```

## Parameters

| Parameter   | Required | Description                                        |
|------------|:------------:|-------------------------------------------------|
| ConfigDir  | yes          | Root dump directory (where Configuration.xml is) |
| Object     | yes          | Object type and name: `Catalog.Товары`, `Document.Заказ`, etc. An external data source table - in four parts: `ExternalDataSource.PG.Table.products` |
| DryRun     | no           | Only show what will be deleted, without changes |
| KeepFiles  | no           | Do not delete files, only deregister       |
| Force      | no           | Delete despite the found references; references to the object's forms are cleared |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-remove.py" -ConfigDir "<путь>" -Object "Catalog.Товары"
```

## Supported types

Catalog, Document, Enum, Constant, InformationRegister, AccumulationRegister, AccountingRegister, CalculationRegister, ChartOfAccounts, ChartOfCharacteristicTypes, ChartOfCalculationTypes, BusinessProcess, Task, ExchangePlan, DocumentJournal, Report, DataProcessor, CommonModule, ScheduledJob, EventSubscription, HTTPService, WebService, DefinedType, Role, Subsystem, CommonForm, CommonTemplate, CommonPicture, CommonAttribute, SessionParameter, FunctionalOption, FunctionalOptionsParameter, Sequence, FilterCriterion, SettingsStorage, XDTOPackage, WSReference, StyleItem, Language

## Examples

```bash
# Проверка ссылок + dry run
... -ConfigDir C:\WS\tasks\cfsrc\acc_8.3.24 -Object "Catalog.Устаревший" -DryRun

# Удалить объект без ссылок
... -ConfigDir C:\WS\tasks\cfsrc\acc_8.3.24 -Object "Catalog.Устаревший"

# Принудительно удалить несмотря на ссылки
... -ConfigDir C:\WS\tasks\cfsrc\acc_8.3.24 -Object "Catalog.Устаревший" -Force

# Только дерегистрировать (файлы оставить)
... -ConfigDir C:\WS\tasks\cfsrc\acc_8.3.24 -Object "Report.Старый" -KeepFiles

# Удалить общий модуль
... -ConfigDir src -Object "CommonModule.МойМодуль"
```

