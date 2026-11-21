---
name: cfe-diff
description: Analysis of a 1C configuration extension (CFE) - composition, borrowed objects, interceptors, transfer check. Use when you need to understand what an extension contains or check whether insertions were transferred to the configuration
argument-hint: -ExtensionPath <path> -ConfigPath <path> [-Mode A|B]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cfe-diff - Configuration extension analysis

Analyzes an extension in two modes: change overview (Mode A) or transfer check (Mode B).

## Parameters

| Parameter | Description | Default |
|----------|----------|--------------|
| `ExtensionPath` | Path to the extension (required) | - |
| `ConfigPath` | Path to the configuration (required) | - |
| `Mode` | `A` (overview) / `B` (transfer check) | `A` |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cfe-diff.py" -ExtensionPath src\cfe\extname -ConfigPath src\cf -Mode A
```

## Mode A - extension overview

For each object shows:
- `[BORROWED]` - borrowed: interceptors (`&Перед`, `&После`, `&ИзменениеИКонтроль`, `&Вместо`), own attributes/tabular sections/forms
- `[OWN]` - own: number of attributes, tabular sections, forms

For each form of a borrowed object shows:
- `(borrowed)` / `(own)` - borrowed or own form
- callType events of the form and elements
- callType on commands

## Mode B - transfer check

For each `&ИзменениеИКонтроль` extracts `#Вставка`/`#КонецВставки` blocks from the extension and searches for them in the corresponding configuration module.

Statuses:
- `[TRANSFERRED]` - code found in the configuration
- `[NOT_TRANSFERRED]` - code not found
- `[NEEDS_REVIEW]` - no `#Вставка` blocks or the configuration module not found

## Examples

```bash
# Обзор — что изменено в расширении
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Mode A

# Проверка переноса — все ли #Вставка перенесены
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Mode B
```
