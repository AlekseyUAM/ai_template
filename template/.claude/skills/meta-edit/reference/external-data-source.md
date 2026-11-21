# External data sources

Point edits inside an already created source: a field into a table, a table and a function into the source.
The source as a whole is assembled by the `meta-compile` skill - a repeated run replaces the source file,
issues a new uuid and leaves tables that are not in the description as orphans.

## add-field - table field

The table file is edited: `ExternalDataSources/<Источник>/Tables/<Таблица>.xml`.

A field is specified as a regular attribute, plus three own keys: `nameInDataSource` (default - the field name),
`readOnly`, `allowNull`. String form flags - `readonly`, `nullable`.

```json
{ "add": { "fields": [
  "barcode: String(20) | nullable",
  { "name": "cost", "type": "Number(15,2)", "nameInDataSource": "cost_net", "readOnly": true }
] } }
```

Field types: `Number`, `String`, `Date`, `Boolean`, `UUID`, `BinaryData` and a reference to a table of the same
source - `ExternalDataSourceTableRef.<Источник>.<Таблица>`. A composite type is forbidden by the platform.

## add-tables / add-functions - in the source file

The source file is edited: `ExternalDataSources/<Источник>.xml`. A table is the only operation of the skill
that creates a **file**: `<Источник>/Tables/<Имя>.xml` plus the name in the source `ChildObjects`.
The table and function syntax is the same as in the `meta-compile` skill (`reference/external-data-source.md` there).

```json
{ "add": {
  "tables": { "sales": { "keyFields": ["id"], "fields": ["id: Number(10,0)", "summa: Number(15,2)"] } },
  "functions": { "nextKey": "NEXT VALUE FOR public.seq_key" }
} }
```

When adding a table, the keys `characteristics` and `default*Form` are not supported - the skill rejects them
rather than silently swallowing them. Characteristics are set when assembling the source by the `meta-compile` skill,
the form is assigned by the `form-add` skill.

## Deletion

A table is deleted by the `meta-remove` skill: `ExternalDataSource.<Источник>.Table.<Таблица>` - together with the file
and the entry in `ChildObjects`. The whole source - `ExternalDataSource.<Источник>`.
