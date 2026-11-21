---
name: xdto-edit
description: Point edits of a 1C XDTO package. Use when you need to add, change or delete a type or property in an existing package, rename the package, change the namespace
argument-hint: <PackagePath> -Operation <operation> [-Target <path>] [-Value <value>] [-NoValidate]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /xdto-edit - Point edits of an XDTO package

Changes one package element without reading and rewriting the whole schema - for large
packages (`EnterpriseData` is about a megabyte) this is the only practical path.

If you need to rework the schema entirely or first understand how it is structured, use
`/xdto-decompile` → edit XSD → `/xdto-compile -Force`.

## Parameters

| Parameter | Required | Description |
|----------|--------------|----------|
| `PackagePath` | yes | Package directory, `Ext/Package.bin` or `<Имя>.xml`. Alias - `-Path` |
| `Operation` | yes | Operation from the table below |
| `Target` | depends | Address: type name or `Тип.Свойство` path |
| `Value` | depends | XSD fragment, literal, URI or text. `@путь` - take content from a file |
| `NoValidate` | no | Do not run `xdto-validate` after the edit |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xdto-edit.py" -PackagePath "<путь>" -Operation <op> -Target "<адрес>" -Value "<значение>"
```

## Operations

| Operation | `-Target` | `-Value` |
|---|---|---|
| `add-property` | type name | `<xs:element>` or `<xs:attribute>` |
| `replace-property` | `Тип.Свойство` | new declaration entirely |
| `remove-property` | `Тип.Свойство` | - |
| `add-type` | - | `<xs:complexType>` or `<xs:simpleType>` |
| `remove-type` | type name | - |
| `add-enum` | value type name | literal |
| `add-import` | - | namespace URI |
| `rename` | - | new metadata object name |
| `set-synonym` | - | synonym |
| `set-comment` | - | comment |
| `set-namespace` | - | new namespace URI |

Batch via `;;` where a list makes sense: `remove-property`, `remove-type`,
`add-enum`, `add-import`.

```bash
... -Operation add-property -Target "Платёж" -Value '<xs:element name="Комментарий" type="xs:string" minOccurs="0"/>'
... -Operation remove-property -Target "Платёж.Комментарий ;; Платёж.Черновик"
... -Operation add-enum -Target "ВидДокумента" -Value "Инкассо ;; Аккредитив"
... -Operation rename -Value ОбменСБанком
```

Content is always described by an XML schema fragment - the same language as in
`/xdto-compile`. There are no separate parameters like `-MinOccurs`: to change a property,
provide its new declaration entirely via `replace-property`.

A length restriction and other facets are set by a nested type:

```xml
<xs:element name="Комментарий" minOccurs="0">
    <xs:simpleType>
        <xs:restriction base="xs:string"><xs:maxLength value="200"/></xs:restriction>
    </xs:simpleType>
</xs:element>
```

Pass a multiline fragment as a file: `-Value "@frag.xsd"`. Inline through the shell is
reliable only for one-line fragments without nested quotes.

## Addressing

Path `Тип.Свойство`. The dot is safe: type and property names are 1C identifiers.
The path continues into inline types: `ПлатежныйДокумент.ДатаСписано.ИдПлатежа`.

To see what is in the package and what the needed type is called, use `/xdto-info`.
Before editing a type, `/xdto-info -Mode used-by -Name <Тип>` is useful: it shows
who the change will affect.

## What rename and namespace change entail

`rename` changes the name in the metadata object, renames the `<Имя>.xml` file and the
`<Имя>/` directory, and fixes the registration in `Configuration.xml`. The new name is checked for
validity as a 1C identifier and for availability.

`set-namespace` changes `targetNamespace`, all internal references to own types
and the metadata object's `<Namespace>`. Packages that import the old namespace are
**not changed** - during versioning they must keep pointing to the old one.
The skill lists them; if the change is not versioned, fix their imports yourself.

After the edit, `/xdto-validate` runs automatically - disable it with `-NoValidate`.

## Typical workflow

1. `/xdto-info <пакет>` - find the needed type
2. `/xdto-info <пакет> -Mode used-by -Name <Тип>` - if you change an existing one
3. `/xdto-edit <пакет> -Operation <op> …`
4. `/db-load-xml` + `/db-update`
