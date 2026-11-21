---
name: support-edit
description: Switch the support state of a typical 1C configuration. Use when you need to enable editing of the configuration or a specific object on support ("locked")
argument-hint: -Path <path> -Set editable|off-support|locked | -Capability on|off
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /support-edit - switch 1C support state

Changes support rules of a typical configuration: allows editing an object/configuration on support, removes from support, enables/disables the ability to change. This is a deliberate action - usually after a `support-guard` refusal (the refusal itself prints a ready command for the specific case).

Acts on the dump only; to apply it in the infobase - load the dump (full load).

## Commands

| What you need | Command |
|-----------|---------|
| Allow editing an object | `-Path <объект> -Set editable` |
| Remove an object from support | `-Path <объект> -Set off-support` |
| Return an object to support ("locked") | `-Path <объект> -Set locked` |
| Allow adding new objects to the configuration | `-Path <каталог дампа> -Set editable` |
| Enable / disable the ability to change the whole configuration | `-Path <каталог дампа> -Capability on` / `off` |

`-Path` - the same path that `support-guard` rejected (object, form, template or dump directory).

```bash
python "${CLAUDE_SKILL_DIR}/scripts/support-edit.py" -Path "Catalogs/Контрагенты.xml" -Set editable
```

## editable or off-support?

- **editable** - edits are allowed, the object **keeps receiving vendor updates** (merge conflicts are possible on update). Choose when you want to modify and keep receiving updates.
- **off-support** - the object is **removed from support**: edits are free, vendor updates no longer arrive for it. This is not deletion of the object. Choose when you take the object out of updates.

## If the change ability is disabled

If the whole configuration is read-only (typical "out of the box"), per-object `-Set` will not work - the skill will suggest running `-Capability on` first. This enables the change ability (all objects remain locked), after which you open the needed ones pointwise via `-Set editable`.
