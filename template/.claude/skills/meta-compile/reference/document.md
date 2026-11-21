# Document, DocumentJournal, Sequence, DocumentNumerator

## Document (Документ)

```json
{ "type": "Document", "name": "ПриходнаяНакладная",
  "registerRecords": ["AccumulationRegister.ОстаткиТоваров"],
  "attributes": ["Организация: CatalogRef.Организации"],
  "tabularSections": { "Товары": ["Номенклатура: CatalogRef.Номенклатура", "Количество: Number(15,3)"] } }
```

| Key | Default | Values |
|------|-----------|----------|
| `comment` | empty | string |
| `numerator` | empty | reference to the numerator `DocumentNumerator.X` |
| `numberType` | `String` | `String` / `Number` |
| `numberLength` | `11` | number length |
| `numberAllowedLength` | `Variable` | `Variable` / `Fixed` |
| `numberPeriodicity` | `Year` | `Nonperiodical` / `Day` / `Month` / `Quarter` / `Year` |
| `checkUnique` | `true` | bool |
| `autonumbering` | `true` | bool |
| `posting` | `Allow` | `Allow` / `Deny` (posting) |
| `realTimePosting` | `Deny` | `Allow` / `Deny` (real-time posting) |
| `registerRecordsDeletion` | `AutoDelete` | `AutoDelete` / `AutoDeleteOnUnpost` / `AutoDeleteOff` |
| `registerRecordsWritingOnPost` | `WriteSelected` | `WriteModified` / `WriteSelected` |
| `sequenceFilling` | `AutoFill` | sequence filling |
| `postInPrivilegedMode` | `true` | bool |
| `unpostInPrivilegedMode` | `true` | bool |
| `createOnInput` | `Use` | `Auto` / `Use` / `DontUse` |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `fullTextSearch` | `Use` | `Use` / `DontUse` |
| `dataHistory` | `DontUse` | `Use` / `DontUse` |
| `registerRecords` | `[]` | movements: list of references `["AccumulationRegister.ОстаткиТоваров", "InformationRegister.Цены"]` |
| `useStandardCommands` | `true` | bool |
| `includeHelpInContents` | `false` | bool |
| `attributes` / `tabularSections` | `[]` / `{}` | attributes / tabular sections |

Forms: `defaultObjectForm`, `defaultListForm`, `defaultChoiceForm`, `auxiliary*` (see `catalog.md`).
Attributes and tabular sections - `attributes.md`. Presentations, commands, characteristics, `basedOn`, `standardAttributes`,
`inputByString`, `dataLockFields` - `blocks.md`.

## DocumentJournal (Document journal)

| Key | Default | Values |
|------|-----------|----------|
| `registeredDocuments` | `[]` | journal documents: `["Document.Встреча", "Document.Звонок"]` |
| `columns` | `[]` | journal columns (see below) |

A column is a string `"Имя"` or an object `{ name, synonym, indexing, references }`, where `indexing` is `Index`/`DontIndex`,
`references` are paths to document attributes displayed in the column.

```json
{ "type": "DocumentJournal", "name": "Взаимодействия",
  "registeredDocuments": ["Document.Встреча", "Document.Звонок"],
  "columns": [{ "name": "Организация", "indexing": "Index",
                "references": ["Document.Встреча.Attribute.Организация"] }] }
```

## Sequence (Document sequence)

| Key | Default | Values |
|------|-----------|----------|
| `moveBoundaryOnPosting` | `DontMove` | boundary movement on posting |
| `documents` | `[]` | sequence documents (list of references) |
| `registerRecords` | `[]` | movements (list of references) |
| `dataLockControlMode` | `Managed` | `Automatic` / `Managed` |
| `dimensions` | `[]` | dimensions `{name, type, documentMap[], registerRecordsMap[]}` |

`documentMap` / `registerRecordsMap` - paths to document attributes / movements corresponding to the dimension.

## DocumentNumerator (Document numerator)

| Key | Default | Values |
|------|-----------|----------|
| `numberType` | `String` | `String` / `Number` |
| `numberLength` | `11` | number length |
| `numberAllowedLength` | `Variable` | `Variable` / `Fixed` |
| `numberPeriodicity` | `Year` | `Nonperiodical` / `Day` / … / `Year` |
| `checkUnique` | `true` | bool |
