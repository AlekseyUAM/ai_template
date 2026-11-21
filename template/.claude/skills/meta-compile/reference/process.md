# BusinessProcess, Task (Бизнес-процессы и Задачи)

Reference types. Inherit the Catalog layer (numbering, forms, `standardAttributes`, `characteristics`, `basedOn`,
presentations - see `catalog.md` / `attributes.md` / `blocks.md`). A business process is always linked to a task.

## BusinessProcess (Бизнес-процесс)

| Key | Default | Values |
|------|-----------|----------|
| `task` | empty | reference to the task `Task.X` (required for a working BP) |
| `numberType` | `String` | `String` / `Number` |
| `numberLength` | `11` | number length |
| `checkUnique` | `true` | bool |
| `autonumbering` | `true` | bool |
| `createOnInput` | `DontUse` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

Created with a route map (`Ext/Flowchart.xml`) and an object module.

```json
{ "type": "BusinessProcess", "name": "Согласование", "task": "Task.ЗадачаИсполнителя",
  "attributes": ["Документ: DocumentRef.ЗаявкаНаРасход"] }
```

## Task (Задача)

| Key | Default | Values |
|------|-----------|----------|
| `numberType` | `String` | `String` / `Number` |
| `numberLength` | `14` | number length |
| `checkUnique` | `true` | bool |
| `autonumbering` | `true` | bool |
| `descriptionLength` | `150` | description length |
| `defaultPresentation` | `AsDescription` | `AsDescription` / `AsNumber` |
| `addressing` | empty | reference to the addressing information register `InformationRegister.X` |
| `mainAddressingAttribute` | empty | main addressing attribute (addressing attribute name) |
| `currentPerformer` | empty | current performer attribute |
| `createOnInput` | `DontUse` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `addressingAttributes` | `[]` | addressing attributes (see below) |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

**Addressing attribute** - shorthand `"Имя: Тип"` or an object `{ name, type, addressingDimension }`
(`addressingDimension` - the addressing register dimension).

```json
{ "type": "Task", "name": "ЗадачаИсполнителя",
  "addressingAttributes": ["Исполнитель: CatalogRef.Пользователи", "Роль: CatalogRef.Роли"] }
```
