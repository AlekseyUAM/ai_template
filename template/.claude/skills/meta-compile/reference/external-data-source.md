# ExternalDataSource (External data source)

The source is described by **one whole JSON**: the source itself, its tables with fields, and functions.
The result is `ExternalDataSources/<Имя>.xml` plus one file per table in `<Имя>/Tables/`.

You do not need to set the connection string, user, password or DBMS type: they are not in the configuration,
they are configured in "Enterprise" mode and stored in the database.

```json
{
  "type": "ExternalDataSource",
  "name": "PG",
  "tables": {
    "prices": ["product_id: Number(10,0)", "period: Date", "price: Number(15,2)"],
    "products": {
      "nameInDataSource": "eds.public.products",
      "tableDataType": "ObjectData",
      "keyFields": ["id"],
      "presentationField": "name",
      "fields": [
        "id: Number(10,0)",
        "name: String(150)",
        "article: String(50) | nullable",
        "parent_id: ExternalDataSourceTableRef.PG.products | nullable"
      ]
    }
  },
  "functions": {
    "total": { "expression": "public.f_total(&1, &2)", "returns": "Number(15,2)" }
  }
}
```

## Source properties

| Key | Default | Values |
|------|-----------|----------|
| `dataLockControlMode` | `Automatic` | `Automatic` / `Managed` / `AutomaticAndManaged` |
| `tables` | `{}` | tables (see below) |
| `functions` | `{}` | functions (see below) |

With `AutomaticAndManaged` each table decides its lock mode itself; with a specific value the same-named
table property is ignored by the platform.

## Tables

The key is the table name in the configuration. The value is a **field array** or an **object** with properties
and a `fields` key (the same duality as for a catalog's `tabularSections`).

| Key | Default | Values |
|------|-----------|----------|
| `nameInDataSource` | = table name | physical table name; for a relational DBMS usually `<база>.<схема>.<таблица>` |
| `tableType` | `Table` | `Table` - a table or view; `Expression` - a table function |
| `readOnly` | `false` | write prohibition; set `true` for views and `Expression` tables - they cannot be written to |
| `expressionInDataSource` | empty | expression for `Expression`, e.g. `public.f_by_parent(&1)`; the database name is not specified |
| `tableDataType` | `NonobjectData` | `ObjectData` (a record is identified by one field) / `NonobjectData` |
| `keyFields` | `[]` | key field names; without them the table is assembled, but the record form and record set are unavailable |
| `presentationField` | empty | presentation field name (only `ObjectData`) |
| `parentField` | empty | parent field name; its type must be a reference to this same table |
| `inputByString` | `[]` | input by string field names; if the key is absent -> `presentationField` is taken |
| `dataVersionField` | empty | data version field name |
| `dataLockFields` | `[]` | lock field names |
| `transactionsIsolationLevel` | `Auto` | `Auto` / `ReadUncommitted` / `ReadCommitted` / `RepeatableRead` / `Serializable` |
| `dataLockControlMode` | `Automatic` | `Automatic` / `Managed` / `AutomaticAndManaged` |
| `basedOn` | `[]` | based on input, references like `Catalog.Контрагенты` |
| `useStandardCommands` | `true` | bool |
| `quickChoice` | `false` | bool |
| `editType` | `InDialog` | `InDialog` / `InList` |
| `fields` | `[]` | fields (see below); synonym - `columns` |

Field references (`keyFields`, `presentationField`, `parentField`, `dataVersionField`,
`inputByString`, `dataLockFields`) are specified by **short field names** of the same table.

Other properties - presentations (`objectPresentation`, `listPresentation`, …), default forms
(`defaultObjectForm`, `defaultListForm`, …), `characteristics`, `explanation`,
`includeHelpInContents` - are as for a catalog.

**The value of an empty parent is not set by XML load** - the platform resets it to empty
on any load, including loading its own dump. It can only be set manually in the Configurator.

## Fields

The string and object forms are the same as for attributes (see `attributes.md`). It has three own keys:

| Key | Default | Values |
|------|-----------|----------|
| `nameInDataSource` | = field name | column name; in single quotes it goes to SQL as is |
| `readOnly` | `false` | the field is not written (computed, auto-increment) |
| `allowNull` | `false` | allows `NULL` |

String form flags: `readonly`, `nullable`.

```json
"fields": [
  "id: Number(10,0) | readonly",
  { "name": "article", "type": "String(50)", "nameInDataSource": "art_code", "allowNull": true }
]
```

Allowed types: `Number`, `String`, `Date`, `Boolean`, `UUID`, `BinaryData` and a reference to an external
source table - `ExternalDataSourceTableRef.<Источник>.<Таблица>`.

Binary data: `BinaryData` - unlimited (this is how the platform writes them when importing from a DBMS),
`BinaryData(N)` - variable length, `BinaryData(N,fixed)` - fixed.

**A composite type is not allowed for a field** - the platform does not load such a configuration.

## Functions

The key is the function name. The value is a string (interpreted as `expression`) or an object.

| Key | Default | Values |
|------|-----------|----------|
| `expression` | - | expression in the source, required |
| `returns` | `String` | return value type |
| `returnValue` | `true` | `false` - a procedure, the type is not written |

Parameters are described directly in the expression as `&1`, `&2` - there is no separate key for them.
Optional ones - in curly braces `f(&1{, &2})`, variable number - `&n[]` (last only).

```json
"functions": {
  "nextKey": "NEXT VALUE FOR dbo.SimpleSequence",
  "total": { "expression": "public.f_total(&1, &2)", "returns": "Number(15,2)" }
}
```

## Add to an existing source

`meta-compile` describes the source **as a whole**: a repeated run replaces its file and issues a new
uuid, and tables that are not in the description remain on disk as orphans. To add a table or
function to an existing source, use `meta-edit`:

```json
{ "add": {
  "tables": { "sales": { "keyFields": ["id"], "fields": ["id: Number(10,0)", "summa: Number(15,2)"] } },
  "functions": { "nextKey": "NEXT VALUE FOR public.seq_key" }
} }
```

To delete a table - `meta-remove ExternalDataSource.<Источник>.Table.<Таблица>`.

## Not supported

- **OLAP cubes** (`Cube`, `DimensionTable`, `Dimension`, `Resource`).
- **Forms and modules** of tables - the form is added by the `form-add` skill, the content is assembled by `form-compile`.
  The set of purposes depends on `tableDataType`: `ObjectData` - Object/List/Choice, `NonobjectData` - Record/List/Choice.
