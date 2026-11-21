---
name: web-stop
description: Stopping Apache HTTP Server. Use when the user asks to stop the web server, Apache, terminate web publication
argument-hint: ""
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /web-stop - Stopping Apache

Stops Apache HTTP Server. Publications are preserved - on the next `/web-publish` the server starts again.

## Usage

```
/web-stop
```

## Connection parameters

Read `.v8-project.json` from the project root. If `webPath` is set - use it as `-ApachePath`.
Default is `tools/apache24` from the project root.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/web-stop.py" <параметры>
```

### Script parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-ApachePath <путь>` | no | Apache root (default `tools/apache24`) |

## After execution

Offer the user:
- **Restart** - `/web-publish <база>` (a repeated call brings Apache up with the existing publications)
- **Removing publications** - `/web-unpublish <имя>` or `/web-unpublish --all`

## Examples

```bash
# Остановить Apache
python "${CLAUDE_SKILL_DIR}/scripts/web-stop.py"

# С указанием пути
python "${CLAUDE_SKILL_DIR}/scripts/web-stop.py" -ApachePath "C:\tools\apache24"
```
