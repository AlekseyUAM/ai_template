---
name: role-edit
description: Point edits of an existing 1C role. Use when you need to add, remove or deny rights, set up RLS restrictions and templates, change role properties without losing other rights and UUIDs
argument-hint: <RolePath> -Operation <op> -Value "<val>" | -DefinitionFile <json> [-NoValidate]
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /role-edit - point edits of a 1C role

Changes rights of an existing role in place: UUID, other rights, RLS and templates are preserved.
To create a new role - `/role-compile`.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `RolePath` | Role directory, `Roles/Имя.xml` or `Roles/Имя/Ext/Rights.xml` |
| `Operation` | One operation from the table below |
| `Value` | Operation value; several values - separated by `;;` |
| `DefinitionFile` | JSON array of operations (alternative to `Operation`) - this is how several different operations are set |
| `NoValidate` | Do not run `role-validate` after the edit |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/role-edit.py" -RolePath "<роль>" -Operation <op> -Value "<значение>"
```

Operations are applied in the order listed.

## Operations

| Operation | `Value` format | Description |
|----------|----------------|----------|
| `add-rights` | `Тип.Имя: Право1, Право2` or `Тип.Имя: @пресет` | Add rights, keep existing ones |
| `set-rights` | same | Replace the object's right set entirely |
| `remove-rights` | `Тип.Имя: Право1, Право2` - remove rights<br>`Тип.Имя` - delete the object entirely | Remove rights |
| `deny-rights` | `Тип.Имя: Право1, Право2` | Close an attribute or tabular section that would otherwise inherit the object's rights |
| `set-rls` | `Тип.Имя.Право: условие`<br>`Тип.Имя.Право[Поле1, Поле2]: условие` | Data access restriction |
| `remove-rls` | `Тип.Имя.Право` - remove all<br>`Тип.Имя.Право[Поле1]` - remove one row | Remove the restriction, keep the right |
| `add-template` | `Имя(Параметры): условие` | Add a restriction template |
| `set-template` | same | Replace the template, or add it if absent |
| `remove-template` | `Имя(Параметры)` or `Имя` | Delete the template |
| `modify-property` | `setForNewObjects=true`<br>`setForAttributesByDefault=false`<br>`independentRightsOfChildObjects=true` | Global role flags |
| `set-synonym` | text | Role synonym |
| `set-comment` | text | Role comment |

## Quick examples

```bash
# Добавить права нового регистра, ничего не потеряв
... -RolePath "src/Roles/Менеджер" -Operation add-rights -Value "InformationRegister.Цены: Read, Update"

# Пресет и несколько объектов в одном вызове
... -RolePath "src/Roles/Менеджер" -Operation add-rights -Value "Catalog.Товары: @view ;; Document.Заказ: @edit"

# Снять права; объект без разрешающих прав удаляется целиком
... -RolePath "src/Roles/Менеджер" -Operation remove-rights -Value "Document.Заказ: Delete"

# Закрыть реквизит от роли
... -RolePath "src/Roles/Менеджер" -Operation deny-rights -Value "Catalog.Товары.Attribute.Цена: View"
```

Several different operations - as a list in a file:

```json
[
  { "operation": "add-rights", "value": "Catalog.Товары: @view" },
  { "operation": "set-rls", "value": "Catalog.Товары.Read: #ПоОрганизации(\"\")" }
]
```

```bash
... -RolePath "src/Roles/Менеджер" -DefinitionFile "операции.json"
```

## Rights

Object and right names are the same as in `/role-compile`: `Catalog`, `Read`, presets `@view` and
`@edit`, nested paths (`Catalog.Контрагенты.Attribute.ИНН: View, Edit`), service short notation
(`HTTPService.ЭДО: Use` expands over all methods of URL templates).

`remove-rights` and `deny-rights` affect more than listed: rights that depend on the removed one
also go (remove `Read` - `Update`, `View`, `Edit` go). Cascaded removals are listed in the output.

An error in a value is a refusal before writing; the file is not changed. Full type-to-rights tables and nesting
kinds are in the `/role-compile` reference.

## RLS

Right restrictions are a list of rows, like the "Data access restrictions" table of the editor.
A row without a field list applies to all other fields; a row with a list applies only to them.
Typical technique: close the data entirely but leave reference presentation fields open, otherwise
references to the object become "object not found":

```bash
... -Operation set-rls -Value "Catalog.Товары.Read: ГДЕ ЛОЖЬ"
... -Operation set-rls -Value "Catalog.Товары.Read[Ссылка, Код, Наименование]: "
```

A row with the same field set is replaced; with a different one it is added. The right must already be granted:
the platform ignores a restriction without the right, so the skill refuses.

Template reference - `#ИмяШаблона("")`; `&` in conditions is escaped automatically.

## Value from a file

Instead of text you can specify `@путь` - the RLS condition, template body, synonym and comment are taken from
the file. A relative path is looked up next to `DefinitionFile`, then in the current directory. The separator
`;;` inside a file remains plain text.

```bash
... -Operation set-rls -Value "Catalog.Товары.Read: @условие.txt"
... -Operation add-template -Value "ПоОрганизации(Мод): @условие.txt"
... -Operation set-comment -Value "@комментарий.txt"
```

## Verification

```
/role-info <RightsPath>      — сводка прав после правки
/role-validate <RightsPath>  — проверка корректности (запускается автоматически)
```
