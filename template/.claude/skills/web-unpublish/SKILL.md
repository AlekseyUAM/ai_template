---
name: web-unpublish
description: Removing a 1C web publication from Apache. Use when the user asks to remove a publication, delete web access to a database
argument-hint: "<appname | --all>"
allowed-tools:
  - Bash
  - Read
  - Glob
  - AskUserQuestion
---

# /web-unpublish - Removing a 1C web publication from Apache

Removes the publication block from `httpd.conf` and the `publish/{appname}` directory inside Apache. If no other publications remain - removes the global 1C block and stops Apache. With the `--all` flag it removes all publications at once.

> **Warning:** this skill manages only web publications in Apache (blocks in `httpd.conf` + the `publish/` directory). It does **NOT** delete project directories, `upload/`, databases or sources.

## Usage

```
/web-unpublish <appname>
/web-unpublish bpdemo
/web-unpublish --all
```

## Connection parameters

Read `.v8-project.json` from the project root. If `webPath` is set - use it as `-ApachePath`.
Default is `tools/apache24` from the project root.

If the user did not specify `appname` and did not specify `--all`, run `/web-info` to show the publication list and ask which one to remove.

If the user asks to remove **all** publications - use `-All`.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/web-unpublish.py" <параметры>
```

### Script parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-AppName <имя>` | * | Publication name |
| `-All` | * | Remove all publications |
| `-ApachePath <путь>` | no | Apache root (default `tools/apache24`) |

> `*` - either `-AppName` is needed, or `-All`

## Examples

```bash
# Удалить одну публикацию
python "${CLAUDE_SKILL_DIR}/scripts/web-unpublish.py" -AppName "bpdemo"

# Удалить все публикации
python "${CLAUDE_SKILL_DIR}/scripts/web-unpublish.py" -All

# С указанием пути
python "${CLAUDE_SKILL_DIR}/scripts/web-unpublish.py" -AppName "mydb" -ApachePath "C:\tools\apache24"
```
