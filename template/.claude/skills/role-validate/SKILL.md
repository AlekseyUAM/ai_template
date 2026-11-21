---
name: role-validate
description: Validate a 1C role. Use after creating or modifying a role to verify correctness
argument-hint: <RightsPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
---

# /role-validate - validation of a 1C role

Checks the correctness of the role's `Rights.xml`: XML format, namespace, global flags, object types, right names, RLS restrictions, templates. Optionally checks role metadata (UUID, name, synonym).

## Parameters

| Parameter    | Req. | Default | Description                                     |
|--------------|:-----:|---------|-------------------------------------------------|
| RightsPath   | yes   | -       | Path to the role (directory or `Rights.xml`)    |
| Detailed     | no    | -       | Verbose output (all checks, including successful ones) |
| MaxErrors    | no    | 30      | Max errors before stopping (default 30)         |
| OutFile      | no    | -       | Write the result to a file (UTF-8 BOM)          |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/role-validate.py" -RightsPath "Roles/МояРоль"
```

## What counts as an error

An error (return code 1), not a warning:

- an object type that has no rights in roles (`Enum`, `CommonModule`, `CommonPicture`, `ScheduledJob`, etc.) - a configuration with a rights block on an enum does not load into the infobase, and Configurator hangs without messages;
- an unknown object type (typo);
- a right name that this type does not have;
- a nesting kind impossible for this type, and an invalid right on a nested object;
- a right on a service as a whole (`HTTPService.Имя` etc.) - the platform checks the nested object (URL template method, operation, channel), and a role with a root right silently does not work: routes respond `403 Недостаточно прав`.

Full type-to-rights lists and nesting kinds are in `role-compile/dsl-reference.md`.
