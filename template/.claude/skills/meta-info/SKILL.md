---
name: meta-info
description: Analyze the structure of a 1C metadata object from an XML dump - attributes, tabular sections, forms, movements, types. Use to study object structure (instead of reading XML files directly) and as a preparatory step when writing queries and code that works with objects
argument-hint: <ObjectPath> [-Mode overview|brief|full] [-Name <element>]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /meta-info - 1C metadata object structure

Reads metadata object XML from a 1C configuration dump and outputs a compact structure description.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `ObjectPath` | Path to the object XML file or directory (auto-resolve `<name>/<name>.xml`) |
| `Mode` | Mode: `overview` (default), `brief`, `full` |
| `Name` | Drill-down by element name (attribute, tabular section, enum value, URL template, operation) |
| `Limit` / `Offset` | Pagination (150 lines by default) |
| `OutFile` | Write the result to a file (UTF-8 BOM) |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-info.py" -ObjectPath "<путь>"
```

## Three modes

| Mode | What it shows |
|---|---|
| `overview` *(default)* | Header + key properties + structure without details |
| `brief` | Everything in one or two lines: field names, counters |
| `full` | Everything expanded: tabular section columns, subscription source list, movements, forms |

`-Name` - drill-down: expand a specific object element (tabular section, attribute, standard attribute,
URL template, web service operation). A composite type in the summary is collapsed into a counter - the full
type list is given by drill-down: `-Name ТипЗначения` for a chart of characteristic types, `-Name Владелец` for a subordinate catalog.

## Supported types (23)

**Reference:** Catalog, Document, Enum, Business process, Task, Exchange plan, Chart of accounts, Chart of characteristic types, Chart of calculation types
**Registers:** Information register, Accumulation register, Accounting register, Calculation register
**Service:** Report, Data processor, HTTP service, Web service, Common module, Scheduled job, Event subscription
**Other:** Constant, Document journal, Defined type

## Examples

```bash
# Справочник — overview
... -ObjectPath Catalogs/Валюты/Валюты.xml

# Документ — полная сводка с колонками ТЧ, движениями, формами
... -ObjectPath Documents/АвансовыйОтчет/АвансовыйОтчет.xml -Mode full

# Регистр сведений — краткая сводка
... -ObjectPath InformationRegisters/КурсыВалют/КурсыВалют.xml -Mode brief

# Drill-down в ТЧ документа
... -ObjectPath Documents/АвансовыйОтчет/АвансовыйОтчет.xml -Name Товары

# Drill-down в реквизит
... -ObjectPath Catalogs/Валюты/Валюты.xml -Name ОсновнаяВалюта

# Общий модуль — флаги контекста и повторное использование
... -ObjectPath CommonModules/ОбщегоНазначения/ОбщегоНазначения.xml

# HTTP-сервис — шаблоны URL и методы
... -ObjectPath HTTPServices/ExternalAPI/ExternalAPI.xml

# HTTP-сервис — drill-down в шаблон URL
... -ObjectPath HTTPServices/ExternalAPI/ExternalAPI.xml -Name АктуальныеЗадачи

# Веб-сервис — операции с параметрами
... -ObjectPath WebServices/EnterpriseDataUpload_1_0_1_1/EnterpriseDataUpload_1_0_1_1.xml

# Веб-сервис — drill-down в операцию
... -ObjectPath WebServices/EnterpriseDataUpload_1_0_1_1/EnterpriseDataUpload_1_0_1_1.xml -Name TestConnection

# Подписка на событие — full раскрывает список источников
... -ObjectPath EventSubscriptions/ПолныйРегистрацияУдаления/ПолныйРегистрацияУдаления.xml -Mode full

# Регламентное задание
... -ObjectPath ScheduledJobs/АвтоматическоеЗакрытиеМесяца/АвтоматическоеЗакрытиеМесяца.xml

# Определяемый тип
... -ObjectPath DefinedTypes/GLN/GLN.xml
```
