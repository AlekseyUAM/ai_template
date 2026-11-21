# JSON DSL - definition mode

For complex and combined operations use a JSON file instead of inline mode.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/meta-edit.py -DefinitionFile "<json>" -ObjectPath "<path>"
```

## add - add elements

```json
{
  "add": {
    "attributes": [
      { "name": "Комментарий", "type": "Строка(200)" },
      { "name": "Сумма", "type": "Число(15,2)", "indexing": "Index" }
    ],
    "tabularSections": [{
      "name": "Товары",
      "attrs": [
        { "name": "Номенклатура", "type": "CatalogRef.Номенклатура" },
        { "name": "Количество", "type": "Число(15,3)" }
      ]
    }],
    "commands": ["Пересчитать"]
  }
}
```

Attributes can be specified as shorthand strings: `"Сумма: Число(15,2) | req, index"`.

## remove - remove elements

```json
{
  "remove": {
    "attributes": ["СтарыйРеквизит"],
    "tabularSections": ["УстаревшаяТЧ"]
  }
}
```

## modify - modify existing

```json
{
  "modify": {
    "properties": {
      "CodeLength": 11,
      "Hierarchical": true,
      "Owners": ["Catalog.Контрагенты", "Catalog.Организации"],
      "RegisterRecords": ["AccumulationRegister.Продажи"],
      "InputByString": ["StandardAttribute.Description"]
    },
    "attributes": {
      "Комментарий": { "type": "Строка(500)" },
      "СтароеИмя": { "name": "НовоеИмя" }
    }
  }
}
```

## modify - attributes inside a tabular section

```json
{
  "modify": {
    "tabularSections": {
      "Товары": {
        "add": ["СтавкаНДС: EnumRef.СтавкиНДС", "Скидка: Число(15,2)"],
        "remove": ["УстаревшийРекв"],
        "modify": {
          "СтароеИмя": { "name": "НовоеИмя", "type": "Строка(500)" }
        }
      }
    }
  }
}
```

## Combining

All three operations (`add`, `remove`, `modify`) can be specified in one JSON file:

```json
{
  "add": { "tabularSections": [{ "name": "НоваяТЧ", "attrs": ["Имя: Строка(100)"] }] },
  "modify": {
    "tabularSections": {
      "СуществующаяТЧ": {
        "add": ["НовыйРекв: Число(15,2)"],
        "remove": ["СтарыйРекв"]
      }
    }
  }
}
```

## Positional insert

```json
{ "name": "Склад", "type": "CatalogRef.Склады", "after": "Организация" }
```

## Key synonyms (case-insensitive)

**Operations:** `add`/`добавить`, `remove`/`удалить`, `modify`/`изменить`

| Canonical | Synonyms |
|-------------|----------|
| attributes | реквизиты, attrs |
| tabularSections | табличныеЧасти, тч, ts |
| dimensions | измерения, dims |
| resources | ресурсы, res |
| enumValues | значения, values |
| columns | графы, колонки |
| forms | формы |
| templates | макеты |
| commands | команды |
| properties | свойства |

`meta-edit` does not add or remove forms and templates: besides the entry in `ChildObjects` they have their own files.
Form - the `form-add` / `form-remove` skills, template - `template-add` / `template-remove`. A command has no file - `meta-edit` adds it itself.

## Composite types

For fields with several allowed types - an array in `type`:

```json
{ "name": "Значение", "type": ["Строка", "Число(15,2)", "Дата", "CatalogRef.Контрагенты"] }
```

In inline format - via `+`:
```
"Значение: Строка + Число(15,2) + Дата + CatalogRef.Контрагенты"
```

## Type synonyms

`Строка(200)`, `Число(15,2)`, `Булево`, `Дата`, `ДатаВремя`, `ХранилищеЗначения`, `СправочникСсылка.XXX`, `ДокументСсылка.XXX`, `ПеречислениеСсылка.XXX`, `ОпределяемыйТип.XXX`.

## Supported object types

| Object type | Allowed add types |
|-------------|-------------------|
| Catalog, Document, ExchangePlan, ChartOf*, BP, Task, Report, DP | attributes, tabularSections, commands |
| Enum | enumValues, commands |
| *Register (4 types) | dimensions, resources, attributes, commands |
| DocumentJournal | columns, commands |
| ExternalDataSource | tables, functions |
| Table (external data source table) | fields, commands |

There is nothing to add for a `Constant`: its only child is a form, and the form is added by the `form-add` skill.
