---
name: web-publish
description: Publishing a 1C infobase through Apache. Use when the user asks to publish a database, services, set up web access, web client, open in a browser
argument-hint: "[database]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - AskUserQuestion
---

# /web-publish - Publishing 1C through Apache

Generates `default.vrd`, configures `httpd.conf` and starts Apache HTTP Server for web access to the infobase. Downloads portable Apache if needed. Idempotent - a repeated call updates the configuration.

## Usage

```
/web-publish [database]
/web-publish dev
/web-publish dev --manual
/web-publish dev --port 9090
```

## Connection parameters

Read `.v8-project.json` from the project root and resolve the database:
1. If the user specified connection parameters (path, server) - use them directly
2. If the user specified a database by name - search by id / alias / name in `.v8-project.json`
3. If not specified - match the current Git branch against `databases[].branches`
4. If the branch did not match - use `default`

**ALWAYS pass all found parameters:**
- **`-V8Path`** - `v8path` of the found database record, otherwise the root `v8path`. If neither is set - do not pass it, but then the platform version is chosen automatically and may be the wrong one
- **`-UserName`** - from the `user` field of the found database record (if present)
- **`-Password`** - from the `password` field of the found database record (if present)
- **`-ApachePath`** - from `webPath` in `.v8-project.json` (if present)

If the `.v8-project.json` file does not exist - offer `/db-list add`.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/web-publish.py" <параметры>
```

### Script parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-V8Path <путь>` | no | Platform bin directory (for wsap24.dll) |
| `-InfoBasePath <путь>` | * | File infobase |
| `-InfoBaseServer <сервер>` | * | 1C server (for a server infobase) |
| `-InfoBaseRef <имя>` | * | Database name on the server |
| `-UserName <имя>` | no | User name |
| `-Password <пароль>` | no | Password |
| `-AppName <имя>` | no | Publication name (default from the database directory name) |
| `-ApachePath <путь>` | no | Apache root (default `tools/apache24`) |
| `-Port <порт>` | no | Port (default `8081`) |
| `-Manual` | no | Do not download - only check and give instructions |

> `*` - either `-InfoBasePath` is needed, or the pair `-InfoBaseServer` + `-InfoBaseRef`

## Multiple users of one database

A repeated call with the same AppName **replaces** the publication (idempotency). This is used for:
- changing the user: "publish under Ivanov" -> same AppName, new `-UserName`
- restart after `/web-stop`: the same call brings Apache back up

If the user asks for a **parallel** publication under another user (to test different permission sets), add a suffix to AppName:
- database `bpdemo`, user `Иванов` -> `-AppName bpdemo-ivanov`
- database `bpdemo`, user `Admin` -> `-AppName bpdemo-admin` (or just `bpdemo`)

Keywords: "one more publication", "additionally", "in parallel", "under another user without removing the current one".

## After execution

1. Report the URLs:
   - Web client: `http://localhost:{Port}/{AppName}`
   - OData: `http://localhost:{Port}/{AppName}/odata/standard.odata`
   - HTTP services: `http://localhost:{Port}/{AppName}/hs/<RootUrl>/...`
   - Web services: `http://localhost:{Port}/{AppName}/ws/<Имя>?wsdl`
2. Offer to open it in the browser
3. If a service needs testing - help compose a request
4. If the database is not registered - offer `/db-list add`

Extension services are published on par with configuration services. If an extension service still
returns 404 (HTTP) or 500 "Сервис не найден" (SOAP) - the extension has not been applied to the database:
`/db-update -Extension <имя>`.

## Examples

```bash
# Файловая база
python "${CLAUDE_SKILL_DIR}/scripts/web-publish.py" -InfoBasePath "C:\Bases\MyDB" -UserName "Admin"

# С явным именем публикации и портом
python "${CLAUDE_SKILL_DIR}/scripts/web-publish.py" -InfoBasePath "C:\Bases\MyDB" -AppName "mydb" -Port 9090

# Серверная база
python "${CLAUDE_SKILL_DIR}/scripts/web-publish.py" -InfoBaseServer "srv01" -InfoBaseRef "MyDB" -UserName "Admin" -Password "secret"

# Ручной режим (только инструкция)
python "${CLAUDE_SKILL_DIR}/scripts/web-publish.py" -InfoBasePath "C:\Bases\MyDB" -Manual
```
