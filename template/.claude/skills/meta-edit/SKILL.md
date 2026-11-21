---
name: meta-edit
description: Point edit of a 1C metadata object. Use when you need to add, remove or change attributes, tabular sections, dimensions, resources or properties of an existing configuration object
argument-hint: <ObjectPath> -Operation <op> -Value "<val>" | -DefinitionFile <json> [-NoValidate]
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /meta-edit - point editing of 1C metadata

Atomic operations for modifying existing metadata object XML.

## Command

### Inline mode (simple operations)

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-edit.py" -ObjectPath "<path>" -Operation <op> -Value "<val>"
```

### JSON mode (complex/combined)

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-edit.py" -DefinitionFile "<json>" -ObjectPath "<path>"
```

| Parameter | Description |
|----------|----------|
| ObjectPath | Object XML file or directory (required, auto-resolved `<dirName>.xml`) |
| Operation | Inline operation (alternative to DefinitionFile) |
| Value | Value for the inline operation |
| DefinitionFile | JSON file with operations (alternative to Operation) |
| NoValidate | Do not run validation after the edit |

## Common operations

Batch via `;;` in all operations.

| Operation | Value format | Example |
|----------|-------------|--------|
| `add-attribute` | `Имя: Тип \| флаги` | `"Сумма: Число(15,2) \| req, index"` |
| `add-dimension` | `Имя: Тип \| флаги` | `"Организация: CatalogRef.Организации \| master"` |
| `add-resource` | `Имя: Тип` | `"Сумма: Число(15,2)"` |
| `add-column` | `Имя: Тип` | `"Тип: EnumRef.ТипыДокументов"` |
| `add-ts` | `ТЧ: Рекв1: Тип1, Рекв2: Тип2` | `"Товары: Ном: CatalogRef.Ном, Кол: Число(15,3)"` |
| `add-ts-attribute` | `ТЧ.Имя: Тип` | `"Товары.Скидка: Число(15,2)"` |
| `remove-*` | `Имя` | `"СтарыйРеквизит ;; ЕщёОдин"` |
| `remove-ts-attribute` | `ТЧ.Имя` | `"Товары.УстаревшийРекв"` |
| `modify-attribute` | `Имя: ключ=значение` | `"СтароеИмя: name=НовоеИмя, type=Строка(500)"` |
| `modify-ts-attribute` | `ТЧ.Имя: ключ=значение` | `"Товары.Рекв: name=НовоеИмя"` |
| `modify-ts` | `ТЧ: ключ=значение` | `"Товары: synonym=Товарный состав"` |
| `modify-property` | `Ключ=Значение` | `"CodeLength=11 ;; DescriptionLength=150"` |

Positional insert: `"Склад: CatalogRef.Склады >> after Организация"`.

Composite type - via `+`: `"Значение: Строка + Число(15,2) + Дата"`.

## Quick examples

```bash
# Добавить реквизиты
-Operation add-attribute -Value "Комментарий: Строка(200) ;; Сумма: Число(15,2) | index"

# Добавить ТЧ с реквизитами
-Operation add-ts -Value "Товары: Ном: CatalogRef.Ном | req, Кол: Число(15,3), Цена: Число(15,2)"

# Удалить реквизит
-Operation remove-attribute -Value "УстаревшийРеквизит"

# Переименовать + сменить тип
-Operation modify-attribute -Value "СтароеИмя: name=НовоеИмя, type=Строка(500)"

# Изменить свойства объекта
-Operation modify-property -Value "CodeLength=11 ;; DescriptionLength=150"

# Владельцы справочника
-Operation set-owners -Value "Catalog.Контрагенты ;; Catalog.Организации"
```

## Index: what you edit -> file

| What you need | File |
|-----------|------|
| Attribute, dimension, resource, column: flags, composite types, structural properties (`Format`, `ChoiceParameters`, `FillValue`, …) | `reference/attributes.md` |
| Tabular section and its attributes | `reference/tabular-sections.md` |
| The object's own properties, list properties (owners, movements, based on, input by string) | `reference/properties.md` |
| Predefined items | `reference/predefined.md` |
| Enum values, commands | `reference/other-children.md` |
| External data source: fields, tables, functions | `reference/external-data-source.md` |
| Combined operations in one JSON, key and type synonyms, which children are allowed for an object type | `reference/json-dsl.md` |

A form is added and removed by the `form-add` / `form-remove` skill, a template by the `template-add` /
`template-remove` skill: besides the entry in `ChildObjects` they have their own files, and `meta-edit` does not touch them.

## Verification

```
/meta-validate <ObjectPath>    — валидация после редактирования
/meta-info <ObjectPath>        — визуальная сводка
```
