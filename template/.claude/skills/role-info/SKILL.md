---
name: role-info
description: Compact summary of 1C role rights from Rights.xml - objects, rights, RLS, restriction templates. Use for rights audit - which objects and actions are available, RLS restrictions
argument-hint: <RightsPath>
allowed-tools:
  - Bash
  - Read
---

# /role-info - 1C role analysis

Parses the role's `Rights.xml` and produces a compact summary: objects are grouped by type, only granted rights are shown. Compression: thousands of XML lines -> 50-150 lines of text.

## Usage

```
/role-info <RightsPath>
```

**RightsPath** - path to the role's `Rights.xml` file (usually `Roles/ИмяРоли/Ext/Rights.xml`).

## Running the script

```bash
python "${CLAUDE_SKILL_DIR}/scripts/role-info.py" -RightsPath <path> -OutFile <output.txt>
```

### Parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-RightsPath` | yes | Path to Rights.xml |
| `-ShowDenied` | no | Show denied rights (hidden by default) |
| `-Limit` | no | Max output lines (default `150`). `0` = no limit |
| `-Offset` | no | Skip N lines - for pagination (default `0`) |
| `-OutFile` | no | Write the result to a file (UTF-8 BOM). Without it - output to console |

**Important:** Always use `-OutFile` and read the result with the Read tool. Direct console output via bash breaks Cyrillic.

For a large role when output is truncated:
```bash
... -Offset 150            # пагинация: пропустить первые 150 строк
```
