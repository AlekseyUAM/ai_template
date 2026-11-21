---
name: role-compile
description: Create a 1C role from a rights description. Use when you need to create a new role with a set of rights on objects
argument-hint: <JsonPath> <OutputDir>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /role-compile - generate a 1C role from JSON DSL

Takes a JSON role definition → generates `Roles/Имя.xml` (metadata) and `Roles/Имя/Ext/Rights.xml` (rights). UUID is automatic.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `JsonPath` | Path to the JSON role definition |
| `OutputDir` | Root of the configuration dump (where `Configuration.xml`, `Roles/` etc. are) |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/role-compile.py" -JsonPath "<json>" -OutputDir "<ConfigDir>"
```

Creates `{OutputDir}/Roles/Имя.xml` and `{OutputDir}/Roles/Имя/Ext/Rights.xml`. Registers `<Role>` in `Configuration.xml`.

## JSON DSL

### Structure

```json
{ "name": "ИмяРоли", "synonym": "Отображаемое имя", "objects": [...], "templates": [...] }
```

Optional: `comment` (""), `setForNewObjects` (false), `setForAttributesByDefault` (true), `independentRightsOfChildObjects` (false).

### Shorthand strings and object form

```json
"objects": [
  "Catalog.Номенклатура: @view",
  "Document.Реализация: @edit",
  "DataProcessor.Загрузка: @view",
  "InformationRegister.Цены: Read, Update",
  { "name": "Document.Продажа", "preset": "view", "rls": {"Read": "#Шаблон(\"\")"} },
  { "name": "Catalog.Номенклатура.Attribute.Цена", "rights": {"View": false} }
]
```

- Shorthand: `"Тип.Имя: @пресет"` or `"Тип.Имя: Право1, Право2"`
- Object form: `preset` + `rights` (per-right values) + `rls` (restrictions)

### Presets

| Preset | Action |
|--------|----------|
| `@view` | View - Read, View (+InputByString for catalogs/documents; Use+View for data processors/reports) |
| `@edit` | Full editing - CRUD + Interactive* + Posting (documents) |

`@` is required in shorthand. In object form - `"preset": "view"` without `@`.


### Services

Rights live on a **nested object** of the service - a URL template method, operation, channel; they are never on the service as a whole. A whole service is a short notation; the skill expands it from metadata in `OutputDir`:

```json
"objects": ["HTTPService.ЭДО: Use"]
```
→ `HTTPService.ЭДО.URLTemplate.ЕстьНовыеДокументы.Method.POST: Use`, and so on for every method of every template.

Some routes are full path only: `"HTTPService.ЭДО.URLTemplate.ЕстьНовыеДокументы.Method.POST: Use"`.


### RLS templates

```json
"templates": [{"name": "ДляОбъекта(Мод)", "condition": "ГДЕ Организация = &ТекОрг"}]
```

Reference in `rls`: `"#ДляОбъекта(\"\")"`. The `&` character is escaped automatically in XML.

Keep a long condition in a file - the value contains `@путь`. A relative path is looked up next to
the JSON role definition, then in the current directory:

```json
"objects": [{"name": "Document.Продажа", "preset": "view", "rls": {"Read": "@условие.txt"}}],
"templates": [{"name": "ДляОбъекта(Мод)", "condition": "@шаблон.txt"}]
```

## Examples

### Simple role

```json
{
  "name": "ЧтениеНоменклатуры", "synonym": "Чтение номенклатуры",
  "objects": ["Catalog.Номенклатура: @view", "Catalog.Контрагенты: @view", "DataProcessor.Загрузка: @view"]
}
```

### Role with RLS

```json
{
  "name": "ЧтениеДокументовПоОрганизации",
  "synonym": "Чтение документов (ограничение по организации)",
  "objects": [
    "Catalog.Организации: @view",
    {"name": "Document.РеализацияТоваровУслуг", "preset": "view", "rls": {"Read": "#ДляОбъекта(\"\")"}}
  ],
  "templates": [{"name": "ДляОбъекта(Модификатор)", "condition": "ГДЕ Организация = &ТекущаяОрганизация"}]
}
```

## What can be written in `objects`

Rights do not exist for `Enum`, `CommonModule`, `DefinedType`, `CommonPicture`, `CommonTemplate`, `Language`, `FunctionalOption`, `EventSubscription`, `ScheduledJob`, `StyleItem`, `SettingsStorage` and similar - they are not in the role editor tree. An error in the definition is a refusal before writing: files are not created, `Configuration.xml` is not changed.

Rights on parts of an object are set by dotted path: `Catalog.Контрагенты.Attribute.ИНН: View, Edit`, `WebService.Обмен.Operation.Загрузить: Use`, `HTTPService.ЭДО.URLTemplate.ЕстьНовыеДокументы.Method.POST: Use`.

Attributes, tabular sections, dimensions and resources inherit the rights of their object - they are given
a deny to close what is inherited:

```json
{"name": "Catalog.Товары.Attribute.Цена", "rights": {"View": false}}
```

An extension role included in the main roles (`DefaultRoles`) cannot grant rights on borrowed objects - the platform forbids it. Put such rights in a separate role outside the main ones.

Full type-to-rights tables, nesting kinds (including external data sources), the list of types without rights, preset tables and additional examples are in `dsl-reference.md`.

## Verification

```
/role-validate <RightsPath>  — проверка корректности XML, прав, RLS
/role-info <RightsPath>      — визуальная сводка структуры
```
