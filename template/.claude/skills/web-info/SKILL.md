---
name: web-info
description: Apache and 1C web publication status - whether the server is running, which databases are published, errors. Use when the user asks about web server status, published databases, whether Apache is running
argument-hint: ""
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /web-info - Apache and 1C publication status

Shows the Apache HTTP Server state, the list of published databases and recent errors.

## Usage

```
/web-info
```

## Connection parameters

Read `.v8-project.json` from the project root. If `webPath` is set - use it as `-ApachePath`.
Default is `tools/apache24` from the project root.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/web-info.py" <параметры>
```

### Script parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-ApachePath <путь>` | no | Apache root (default `tools/apache24`) |

## How to read the output

Three sections: server state, publication list (name, URL, connection string, service tags),
tail of the Apache log.

| In the output | What it means |
|----------|------------|
| `Status: Остановлен` | Apache is not running - publications in `httpd.conf` exist, but URLs do not respond. Bring it up with `/web-publish` again |
| `Port: 9191 (не отвечает)` | The port is not listening - URLs will not open. Together with `Status: Запущен` it means the server did not start (busy port, broken config): see the errors section |
| `[WARN] Обнаружен сторонний Apache` | Another instance is running on the machine - it may hold the port; our commands do not manage it |
| `[WS HTTP OData]` | What is published for the database: SOAP services, HTTP services, standard OData |
| `+ext` (`WS+ext`) | Services supplied by configuration extensions are published too |
| `(нет публикаций)` | Apache is installed, but no database is published - `/web-publish` is needed |
| `(ошибок нет)` / `(нет файла)` | Normal, not a failure: there are no errors in the log or it has not been created yet |

The errors section holds the latest `error`-level and higher entries; informational lines are filtered
out. The log is not rotated, so an entry may be half a year old: check the date before treating it as
the cause of the current problem. The log path is printed nearby - if you need full context, read the file.

A publication line says "this is how it is configured", not "the database responds": only the
availability of Apache itself is checked, not the publications. You can verify a specific database with
a request to its URL - but note that such a request starts a 1C session and takes a license.

## Examples

```bash
# Статус по умолчанию
python "${CLAUDE_SKILL_DIR}/scripts/web-info.py"

# Указать путь к Apache
python "${CLAUDE_SKILL_DIR}/scripts/web-info.py" -ApachePath "C:\tools\apache24"
```
