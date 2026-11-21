---
name: db-list
description: Management of the 1C database registry (.v8-project.json). Use when you need to work with the database registry - list databases, register a database in the registry, find out which databases exist
argument-hint: "[add|remove|show]"
allowed-tools:
  - Read
  - Write
  - Glob
  - AskUserQuestion
---

# /db-list - Database registry management

Manages the `.v8-project.json` file - the registry of project infobases. The file stores connection parameters, aliases, and Git branch bindings.

## Usage

```
/db-list                    — показать список баз
/db-list add                — добавить базу (интерактивно)
/db-list remove <id>        — удалить базу из реестра
/db-list show <id|alias>    — подробности по базе
```

## `.v8-project.json` format

The file lives in the project root (next to `.git/`).

```json
{
  "v8path": "C:\\Program Files\\1cv8\\8.3.25.1257\\bin",
  "v8args": ["/UseHwLicenses+"],
  "databases": [
    {
      "id": "dev",
      "name": "Разработка",
      "type": "file",
      "path": "C:\\Bases\\MyApp_Dev",
      "v8path": "C:\\Program Files\\1cv8\\8.3.27.1688\\bin",
      "user": "Admin",
      "password": "",
      "aliases": ["dev", "разработка"],
      "branches": ["dev", "develop", "feature/*"],
      "configSrc": "C:\\WS\\myapp\\cfsrc",
      "repository": {
        "path": "\\\\srv01\\repo\\MyApp",
        "user": "Ivanov",
        "password": ""
      },
      "extensions": [
        {
          "name": "МоёРасширение",
          "src": "src\\cfe\\МоёРасширение",
          "repository": { "path": "\\\\srv01\\repo\\MyApp_Ext", "user": "Ivanov", "password": "" }
        }
      ]
    },
    {
      "id": "test",
      "name": "Тестовая",
      "type": "server",
      "server": "srv01",
      "ref": "MyApp_Test",
      "user": "Admin",
      "password": "123",
      "aliases": ["test", "тест"]
    }
  ],
  "default": "dev"
}
```

### Root object fields

| Field | Type | Description |
|------|-----|----------|
| `v8path` | string | 1C platform bin directory. Optional - auto-detected when not set |
| `v8args` | array | Additional `1cv8.exe` launch arguments for all skills, e.g. `["/UseHwLicenses+"]` |
| `ibcmdargs` | array | Additional `ibcmd` arguments (form `--ключ=значение`) |
| `newObjectPosition` | `"end"` / `"byName"` | Where a new object goes in the configuration composition: to the end of its kind (default) or to its place by name. Overridden in `databases[]` |
| `extensionApplyCheck` | bool | Whether to check extension applicability after loading into the database (default `true`). Disabled for one run with the `-NoApplyCheck` key |
| `externalCheck` | bool | Whether to validate external data processor/report sources with the platform before building (default `true`). Disabled for one run with the `-Checks off` key |
| `xsdPath` | string | Platform XSD schema directory for validating dumps by format version; default `.v8-xsd` next to this file. Populated by `/v8-xsd-fetch` |
| `databases` | array | Array of databases |
| `default` | string | Default database id |

### Database object fields

| Field | Type | Required | Description |
|------|-----|:------------:|----------|
| `id` | string | yes | Unique identifier (Latin letters, no spaces) |
| `name` | string | yes | Human-readable name |
| `type` | `"file"` / `"server"` | yes | Connection type |
| `path` | string | for file | Path to the file infobase directory |
| `server` | string | for server | 1C server address |
| `ref` | string | for server | Database name on the server |
| `v8path` | string | no | Platform for this database specifically - overrides the root `v8path` (see below) |
| `user` | string | no | 1C user name |
| `password` | string | no | Password |
| `aliases` | string[] | no | Alternative names for quick access |
| `branches` | string[] | no | Git branches or glob patterns (`release/*`, `feature/*`) bound to this database |
| `configSrc` | string | no | Configuration XML dump directory |
| `repository` | object | no | Configuration repository: `path`, `user`, `password` (see below) |
| `extensions` | array | no | Extensions: `name`, `src`, optional `repository` (see below) |

### Configuration repository

A database connected to a 1C configuration repository **accepts no Configurator operation**
without repository credentials - this applies not only to `/db-repo` but also to `/db-load-xml`,
`/db-dump-xml`, `/db-update`, `/db-load-git`. Credentials are taken from the database record's
`repository`; there is no need to pass them on every call.

| Field | Type | Required | Description |
|------|-----|:------------:|----------|
| `repository.path` | string | yes | Repository directory or `tcp://<хост>[:<порт>]/<имя>` |
| `repository.user` | string | no | **Repository** user. Not inherited from the database `user` |
| `repository.password` | string | no | Repository user password |

An extension has **its own repository** with its own path, so one `repository` is not enough:

| Field | Type | Required | Description |
|------|-----|:------------:|----------|
| `extensions[].name` | string | yes | Extension name, as in the configuration |
| `extensions[].src` | string | no | Extension XML sources directory |
| `extensions[].repository` | object | no | Extension repository. An extension without a repository is the usual case |

The repository password is as much a secret as the database `password`; keep `.v8-project.json` in `.gitignore`.

> **Network repository.** Address - `tcp://<хост>[:<порт>]/<имя>`, default port 1542.
> Served by the repository server. If it is unavailable, the platform responds "Соединение с
> хранилищем конфигурации не установлено" - the same message as when credentials are missing.

## Database resolution algorithm

This algorithm is used by ALL skills (`db-*`, and also the `1c-batch` `build-epf`/`dump-epf` commands) to determine the target database.

1. If the user specified **connection parameters** (path, server) - use them directly
2. If the user specified a **database by name** - look for a match in this order:
   1. By `id` (exact match)
   2. By `aliases` (array match taking morphology into account: "тестовую" = "тестовая" = "тестовой")
   3. By `name` (fuzzy match taking morphology and case into account)
3. If the user **did not specify** a database - match the current Git branch against `databases[].branches`:
   - Exact match: branch `dev` -> `"branches": ["dev"]`
   - Glob pattern: branch `release/2.1` -> `"branches": ["release/*"]`
4. If the branch did not match - use `default`
5. If nothing is found or the result is ambiguous - ask the user
6. If the `.v8-project.json` file is not found - ask for connection parameters and offer to create the file

After execution: if the database used is not registered - offer to add it via `/db-list add`.

### Platform selection

Order: explicit `-V8Path` in the call -> database record `v8path` -> root `v8path` -> auto-detection.
The script finds the database record itself by matching connection parameters against `databases[]` -
no need to pass `-V8Path` by hand. The per-database field is needed when project databases run on
different platform versions: the XML dump format is set by the platform that dumps, while
auto-detection takes the newest installed one.

If `v8path` is not set anywhere, the script takes the newest installed platform itself:
on Windows from `C:\Program Files\1cv8\*\bin\1cv8.exe`, on Linux/macOS from
`/opt/1cv8/*/1cv8` (search sorted by version descending).

## Operations

### Show the database list

Read `.v8-project.json` and output a table:

```
ID      Имя           Тип      Путь/Сервер              По умолч.
dev     Разработка    file     C:\Bases\MyApp_Dev       ✓
test    Тестовая      server   srv01/MyApp_Test
```

### Add a database

Ask the user via AskUserQuestion:
- id, name, type (file/server)
- path (for file) or server + ref (for server)
- user, password (optional)
- aliases, branches (optional)
- if the database is under a configuration repository - `repository`: path, user, password

Add it to the `databases` array. If this is the first database - set it as `default`.

### Delete a database

Remove it from the `databases` array by id. If the deleted one was `default` - ask for a new default.

### Database details

Output all fields of the given database.

## Building the connection string

For use in other skills' command templates:

**File infobase:**
```
/F "<path>"
```

**Server infobase:**
```
/S "<server>/<ref>"
```

**Authentication** (added when user is set):
```
/N"<user>" /P"<password>"
```

> **Important**: no space between `/N` and the name. No space between `/P` and the password. If the password is empty - omit `/P` entirely.

**Configuration repository** (if the database has `repository` set) - skill scripts substitute it
themselves by matching connection parameters against the registry record:
```
/ConfigurationRepositoryF"<path>" /ConfigurationRepositoryN"<user>" /ConfigurationRepositoryP"<password>"
```

