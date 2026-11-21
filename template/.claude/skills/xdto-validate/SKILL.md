---
name: xdto-validate
description: Validate a 1C XDTO package. Use after creating or modifying an XDTO package to verify correctness
argument-hint: <PackagePath> [-ConfigDir <dir>] [-Detailed] [-MaxErrors N] [-OutFile <file>]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /xdto-validate - XDTO package validation

Checks the package model, the metadata object and its link to the configuration.
Each finding is printed on a separate line with an explanation. Exit code `1` on errors.

## Parameters

| Parameter | Required | Description |
|----------|--------------|----------|
| `PackagePath` | yes | Package directory, `Ext/Package.bin` or metadata object `<Имя>.xml`. Alias - `-Path` |
| `ConfigDir` | no | Source root. By default determined by the package location |
| `Detailed` | no | Show successful checks, not only problems |
| `MaxErrors` | no | Stop after N errors. Default 20 |
| `OutFile` | no | Write the report to a file |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xdto-validate.py" -PackagePath "<путь>"
```

`[ERROR]` - the platform will not accept such a package or will accept it incorrectly.
`[WARN]` - the package works, but there is a risk worth knowing.

## Why run it if the package loads anyway

The platform does not diagnose some defects: it silently substitutes an unresolved type from a foreign
namespace with `xs:anyType`, and the package looks loaded until
`ФабрикаXDTO` returns a structureless value at runtime. Such things are visible only
statically - before loading into the infobase.

## Typical workflow

1. `/xdto-compile`, `/xdto-edit` or rework via `/xdto-decompile` → `/xdto-compile -Force`
2. `/xdto-validate <путь>` - before loading into the infobase
3. `/db-load-xml` + `/db-update`
