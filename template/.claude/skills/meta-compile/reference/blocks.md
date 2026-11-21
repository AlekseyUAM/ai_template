# Object blocks

Cross-type object-level blocks (applicable to reference types - Catalog, Document, ChartOf*, ExchangePlan,
BusinessProcess, Task, etc.).

## Presentations

Object presentation texts in the UI (ML - string or `{ru,en}`, empty by default):

| Key | Meaning |
|------|-------|
| `objectPresentation` | object presentation |
| `extendedObjectPresentation` | extended object presentation |
| `listPresentation` | list presentation |
| `extendedListPresentation` | extended list presentation |
| `explanation` | explanation |

The set of available keys depends on the type (list-only objects without an object form have no `objectPresentation`, etc.).

```json
"listPresentation": "Организации", "objectPresentation": { "ru": "Организация", "en": "Company" }
```

## Commands

Object commands. The key is the command name, the value is a properties object (map `имя → объект` or array `[{name, …}]`).
For each command a module stub with the `ОбработкаКоманды` handler is created.

| Key | Default | Values |
|------|-----------|----------|
| `synonym` | from name | ML |
| `tooltip` | empty | ML |
| `comment` | empty | string |
| `group` | **required** | placement group (see below) |
| `commandParameterType` | empty | parameter type (e.g. `CatalogRef.Номенклатура`) - **only for form groups** |
| `parameterUseMode` | `Single` | `Single` / `Multiple` |
| `modifiesData` | `false` | bool |
| `representation` | `Auto` | representation kind |
| `picture` | empty | picture reference (`StdPicture.Print`, `CommonPicture.Загрузка`) |
| `shortcut` | empty | key combination |

```json
"commands": {
  "ПечатьЭтикеток": { "synonym": "Печать этикеток", "group": "FormCommandBarImportant",
                      "commandParameterType": "CatalogRef.Номенклатура", "picture": "StdPicture.Print" }
}
```

**The group (`group`) is required** - every command is placed in a command interface group:

- **Section command interface** (navigation panel / actions panel; `commandParameterType` is **not available**):
  `NavigationPanelImportant` / `NavigationPanelOrdinary` / `NavigationPanelSeeAlso`,
  `ActionsPanelCreate` / `ActionsPanelReports` / `ActionsPanelTools`.
- **Form command interface** (`commandParameterType` is allowed): `FormCommandBarImportant` /
  `FormCommandBarCreateBasedOn`, `FormNavigationPanelImportant` / `FormNavigationPanelGoTo` / `FormNavigationPanelSeeAlso`.
- **Custom group:** `CommandGroup.<Имя>` (parameter is allowed).

A section group together with `commandParameterType` -> error.

## `inputByString` / `dataLockFields` / `basedOn`

Object-level field/object lists. Fields are by object attribute name (regular or standard).

- **`inputByString`** - quick input by string fields. By default they are derived from Code/Description - the key is not needed;
  set it for a different set/order, or `[]` to disable.
  ```json
  "inputByString": ["Код", "Наименование", "Контрагент"]
  ```
- **`dataLockFields`** - managed data lock fields (empty by default).
  ```json
  "dataLockFields": ["Организация", "Контрагент"]
  ```
- **`basedOn`** - "based on" input: a list of references to metadata objects (empty by default).
  ```json
  "basedOn": ["Catalog.Контрагенты", "Document.ЗаказПоставщику"]
  ```

## `standardAttributes` - standard attribute customization

Standard object attributes (Description, Code, Owner, ...) are overridden by the
`standardAttributes` block - an object `{ ИмяРеквизита: { переопределения } }`. Names are as in 1C: `Description`, `Code`,
`Owner`, `Parent`, `DeletionMark`, `Ref`, etc. (for Document - `Date`, `Number`, `Posted`).

Overridable fields are as for a regular attribute (`synonym`, `tooltip`, `fillChecking`, `fillValue`,
`choiceParameters`, `comment`, `mask`, `choiceForm`; the full set is in `attributes.md`).

```json
"standardAttributes": {
  "Description": { "synonym": "Наименование контрагента" },
  "Code": { "fillChecking": "ShowError" }
}
```

## `characteristics` - "Additional attributes and information"

Binding of a chart of characteristic types. An array; each element links a **type source** (where
characteristics are defined) and a **value source** (where values are stored).

```json
"characteristics": [{
  "types":  { "from": "Catalog.НаборыДопРеквизитов.ДополнительныеРеквизиты",
              "key": "Свойство", "filterField": "Ссылка", "filterValue": "Справочник_Организации" },
  "values": { "from": "Catalog.Организации.TabularSection.ДополнительныеРеквизиты",
              "object": "Ссылка", "type": "Свойство", "value": "Значение" }
}]
```

- `from` - source table; `key`/`filterField`/`object`/`type`/`value` - source fields (by attribute name).
- `filterValue` - type filter value: the name of a predefined set (string) or a path to an item.
