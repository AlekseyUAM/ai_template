---
name: xdto-info
description: Analyze 1C XDTO package structure - types, properties, entry points. Use as a preparation step when writing code that creates and fills an XDTO object, when parsing incoming XML, and to find out which packages exist in the configuration
argument-hint: <PackagePath> [-Namespace <URI>|-Package <name>] [-Name <Type>] [-Depth N] [-RequiredOnly] [-Mode used-by] [-Limit N] [-Offset N] [-OutFile <file>]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /xdto-info - Analyze XDTO package structure

Shows the type structure in 1C terms: which value type to assign, what is required,
where a nested object is needed, which values are allowed. Replaces reading `Package.bin`
or XSD with manual translation of `xs:decimal` → `Число` and `lowerBound="0"` → optional.

## Parameters

| Parameter | Required | Description |
|----------|--------------|----------|
| `PackagePath` | yes | Package directory or configuration source root. Alias - `-Path` |
| `Namespace` | no | Select a package by namespace (when the path is the source root) |
| `Package` | no | Select a package by metadata object name |
| `Name` | no | Type name. Without a selected package, searched across the whole configuration |
| `Depth` | no | Nesting expansion depth for nested objects. Default 1 |
| `RequiredOnly` | no | Keep only required properties - a skeleton for "fill the required". An optional object goes away with its content |
| `Mode` | no | `used-by` - show who references the type |
| `Limit` / `Offset` | no | Pagination. Default 150 lines |
| `OutFile` | no | Write the result to a file (UTF-8 BOM) |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xdto-info.py" -PackagePath "<путь>"
```

## What it shows

The entry point is determined by the path: source root - a list of packages; package directory -
its content.

| Call | Result |
|---|---|
| `-PackagePath src` | all configuration packages: name, type count, namespace |
| `-PackagePath src/XDTOPackages/ОбменСБанком` | imports, entry points, type lists |
| `... -Name ПлатежныйДокумент` | type structure for filling |
| `... -Name ПлатежныйДокумент -Depth 3` | same with nested objects expanded |
| `... -Mode used-by -Name СуммаТип` | who references the type, including neighboring packages |

## When the namespace and type are known but the package name is not

This happens most often: the namespace and type name are visible in code or in a sample XML,
but the package name is not. The call repeats the string you start from:

```bash
# ФабрикаXDTO.Тип("urn:1C.ru:ClientBankExchange", "ПлатежныйДокумент")
... -PackagePath src -Namespace "urn:1C.ru:ClientBankExchange" -Name ПлатежныйДокумент
```

If only the type name is known - pass `-Name` and the source root: the type is found
across all packages. With several matches the skill shows exactly where, so you can refine.

## What is in the output

Properties are shown as they are to be filled in code: the value type in 1C notation
and with restrictions (`Строка(6)`, `Число(18,2)`), requiredness and collections -
by flags; for enum types the allowed values are listed. An unmarked
property is optional.

Notations that are not self-evident are explained by the skill right in the output -
and only those that occur in it.

## Typical workflow

1. `/xdto-info src` - which packages exist
2. `/xdto-info src -Namespace "<URI>"` - package entry points and types
3. `/xdto-info src -Namespace "<URI>" -Name <Тип> -Depth 2` - structure for code
4. Before editing a type: `-Mode used-by -Name <Тип>` - who is affected

If you need the XML schema itself rather than a summary, use `/xdto-decompile`.
