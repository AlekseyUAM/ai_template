---
name: xdto-compile
description: Create a 1C XDTO package from an XML schema (XSD). Use when you need to add an XDTO package to the configuration - for exchange, integration, a web service or an external XML format
argument-hint: -XsdPath <file.xsd>|-Xsd <schema> -OutputDir <source-dir> [-Name <name>] [-Synonym <synonym>] [-Comment <text>] [-Force]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /xdto-compile - Create an XDTO package from an XML schema

Builds an XDTO package from an XML schema: `XDTOPackages/<Имя>.xml`,
`XDTOPackages/<Имя>/Ext/Package.bin` and registration in `Configuration.xml`.

Input is a regular XML schema; write it the same way as for any other tool.

## Parameters

| Parameter | Required | Description |
|----------|--------------|----------|
| `XsdPath` | one of two | Path to the XML schema file. Alias - `-Path` |
| `Xsd` | one of two | Schema as a string, instead of `-XsdPath` |
| `OutputDir` | yes | Configuration or extension source directory - where `Configuration.xml` is |
| `Name` | no | Metadata object name. By default - from `xs:appinfo`, otherwise the XSD file name sanitized for a 1C identifier |
| `Synonym` | no | Synonym (string). By default - from `xs:appinfo`, otherwise the package name. For several languages, set the synonym in the schema with an `xs:appinfo` block |
| `Comment` | no | Comment. By default - from `xs:appinfo` |
| `Force` | no | Overwrite an existing package. Without it the skill refuses to overwrite an already built package |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xdto-compile.py" -XsdPath "<схема.xsd>" -OutputDir "<каталог-исходников>"
```

Examples:
```bash
... -XsdPath bank.xsd -OutputDir src -Name ОбменСБанком -Synonym "Обмен с банком"
... -XsdPath fss.xsd  -OutputDir src -Force
```

## Read the warnings

XSD is more expressive than the XDTO model. Everything that does not map one-to-one, the skill maps
approximately and **writes about it**:

```
Предупреждения (2) — конструкции XSD без точного соответствия в модели XDTO:
  ! Документ : вложенная xs:choice уплощена в последовательность — выбор одного из вариантов не сохранён
  ! Документ : кратность на вложенной частице (<xs:sequence minOccurs/maxOccurs>) не выражается в модели XDTO
```

Such a message means the package was built but the schema was simplified. If the simplification is
unacceptable - change the schema (for example, split `xs:choice` variants into different types),
do not ignore it.

What maps approximately: nested `xs:sequence`/`xs:choice` (flattened into a flat property
list), `xs:all` (becomes a sequence), multiplicity on a particle,
`substitutionGroup`, `xs:key`/`keyref`/`unique`, `xs:redefine`.

`xs:group` and `xs:attributeGroup` are expanded by reference - their content lands in the type.
`xs:include` is ignored: dependencies in XDTO resolve by namespace only,
so an included schema must be built as a separate package and `include` replaced with `import`.

## See what was produced

The package model is in `Ext/Package.bin`. Despite the extension, it is textual XML,
but there is usually no need to read it directly: `/xdto-info` shows the built package content,
and `/xdto-decompile` shows the full schema.

## Dependencies between packages

`<xs:import namespace="…"/>` resolves by namespace among configuration
or extension packages. If there is no package with such a namespace, the platform silently
substitutes the type with `xs:anyType` on load - without an error. Build dependencies first, then
the dependent package, and verify the result via `/xdto-validate`.

Which packages are already built is visible in `ChildObjects` of `Configuration.xml`.

## What XSD cannot express

Two things the XDTO model can do but XML Schema cannot: `nillable` on an attribute and `qualified`
on an individual property. They are written as attributes from the model namespace:

```xml
<xs:attribute name="Представление" type="xs:string"
              xmlns:xdto="http://v8.1c.ru/8.1/xdto" xdto:nillable="true"/>
```

The schema remains valid - validators ignore such attributes. The full list
and the XSD <-> XDTO mapping table are in [xsd-reference.md](xsd-reference.md).

Metadata object properties can be set directly in the schema:

```xml
<xs:annotation>
    <xs:appinfo>
        <xdto:package xmlns:xdto="http://v8.1c.ru/8.1/xdto">
            <xdto:name>ОбменСБанком</xdto:name>
            <xdto:synonym lang="ru">Обмен с банком</xdto:synonym>
        </xdto:package>
    </xs:appinfo>
</xs:annotation>
```

## Typical workflow

1. Get an XSD from the counterparty (or dump the schema of an existing package: `/xdto-decompile`)
2. `/xdto-compile -XsdPath <файл> -OutputDir <каталог-исходников>` - read the warnings
3. `/xdto-validate <каталог-исходников>/XDTOPackages/<Имя>` - make sure the types resolved
4. `/db-load-xml` + `/db-update`

Editing an existing package: pointwise - `/xdto-edit`; to rework the schema entirely -
`/xdto-decompile` → edit XSD → `/xdto-compile -Force`.
