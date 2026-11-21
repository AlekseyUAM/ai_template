---
name: xdto-decompile
description: Dump a 1C XDTO package to an XML schema (XSD). Use when you need to get the schema of an existing package - to rework it entirely, hand it to a counterparty or move the package to another configuration
argument-hint: <PackagePath> [-OutFile <file.xsd>]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /xdto-decompile - Dump an XDTO package to an XML schema

Turns an XDTO package into a regular XML schema - readable and editable.
Replaces reading `Ext/Package.bin` directly.

## Parameters

| Parameter | Required | Description |
|----------|--------------|----------|
| `PackagePath` | yes | Package directory, path to `Ext/Package.bin` or to the metadata object's `<Имя>.xml`. Alias - `-Path` |
| `OutFile` | no | Write the schema to a file (UTF-8 with BOM). Without it - output to stdout |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xdto-decompile.py" -PackagePath "<путь>"
```

Examples:
```bash
... -PackagePath src/XDTOPackages/ОбменСБанком
... -PackagePath src/XDTOPackages/ОбменСБанком -OutFile bank.xsd
```

## Reworking the schema entirely

`/xdto-decompile` → edit XSD → `/xdto-compile -Force` returns the package without loss,
including the metadata object name, synonym and comment - they are dumped
to `xs:annotation/xs:appinfo`.

This path also gives a versioned copy of the package: change `targetNamespace` in the schema and build
it with the `-Name` of the new package - the name and synonym are set by `/xdto-compile` flags, there is no
need to edit them inside the schema. When changing the namespace, also fix **the `xmlns` declaration
with the same URI**: internal references use it as a prefix. Replacing all occurrences of the
string is not allowed - the import of a namespace for which the old URI is a prefix would suffer
(`urn:пример:обмен` and `urn:пример:обмен:legacy`).

This path is needed when the schema is changed broadly or you first need to understand how it is
structured. To fix one property, there is no need to read the whole schema - use `/xdto-edit`.
If you need not the schema but a summary of "what to assign and what is required", use `/xdto-info`.

In the schema you may encounter attributes with the `xdto:` prefix - this is how things
XML Schema cannot express are written (for example `nillable` on an attribute). The schema remains
valid; validators ignore such attributes. Usually they should not be touched; the meaning of
each is described in `xsd-reference.md` of the `/xdto-compile` skill.

## Passing the schema outside

The resulting XSD can be given to the counterparty as is - it is valid and does not lose
package data. The built-in "Export XML schema" command in Configurator is worse
for this: it loses `nillable` on attribute properties.
