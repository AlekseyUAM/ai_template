---
name: db-load-git
description: Loading changes from Git into a 1C database. Use when you need to load changes from git, update the database from the repository, do a partial load from a commit
argument-hint: "[database] [source]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - AskUserQuestion
---

# /db-load-git - Loading changes from Git

Determines changed configuration files from Git data and performs a partial load into the infobase.

> If the changes include `Configuration.xml`, the platform performs a **full configuration load**, not just the changed objects.

> A deleted object leaves the database only if it is also deleted from the owner's composition (`ChildObjects` of the object or `Configuration.xml`). A deleted file that is part of an object (a module, files under `Ext/`) is not deleted by partial loading: the script lists such deletions under `[ВНИМАНИЕ]`, and if there is nothing else to load, it fails with an error. They can only be applied by a full load (`/db-load-xml -Mode Full`); to remove module code, it is enough to leave the file empty.

## Usage

```
/db-load-git [database]
/db-load-git dev                              — все незафиксированные изменения
/db-load-git dev -Source Staged               — только staged
/db-load-git dev -Source Commit -CommitRange "HEAD~3..HEAD"
/db-load-git dev -DryRun                      — только показать что будет загружено
```

## Connection parameters

Read `.v8-project.json` from the project root and resolve the database:
1. If the user specified connection parameters (path, server) - use them directly
2. If the user specified a database by name - search by id / alias / name in `.v8-project.json`
3. If not specified - match the current Git branch against `databases[].branches`
4. If the branch did not match - use `default`
Platform - `v8path` of the found database record, otherwise the root `v8path`. If neither is set - do not pass `-V8Path`.
If the file does not exist - offer `/db-list add`.
If the database used is not registered - after execution offer to add it via `/db-list add`.
If the database record has `configSrc` - use it as the configuration directory.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-load-git.py" <параметры>
```

### Script parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-V8Path <путь>` | no | Platform bin directory, or full path to `1cv8.exe` / `ibcmd.exe` |
| `-InfoBasePath <путь>` | * | File infobase |
| `-InfoBaseServer <сервер>` | * | 1C server (for a server infobase) |
| `-InfoBaseRef <имя>` | * | Database name on the server |
| `-UserName <имя>` | no | User name |
| `-Password <пароль>` | no | Password |
| `-ConfigDir <путь>` | yes | XML dump directory (git repository) |
| `-Source <источник>` | no | `All` (default) / `Staged` / `Unstaged` / `Commit` |
| `-CommitRange <range>` | for Commit | Commit range (e.g. `HEAD~3..HEAD`) |
| `-Extension <имя>` | no | Load into an extension |
| `-NoApplyCheck` | no | Do not check extension applicability after loading |
| `-Format <формат>` | no | `Hierarchical` (default) / `Plain` |
| `-DryRun` | no | Only show what will be loaded (without loading) |
| `-UpdateDB` | no | After loading, immediately update the DB configuration (`/UpdateDBCfg`) |
| `-AdditionalV8Arguments <список>` | no | Additional `1cv8.exe` launch arguments, comma-separated, e.g. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | no | Additional `ibcmd` arguments, comma-separated, in the form `--ключ=значение` |

> `*` - either `-InfoBasePath` is needed, or the pair `-InfoBaseServer` + `-InfoBaseRef`

## After execution

If `-UpdateDB` was not specified - **offer `/db-update`** to apply the changes to the DB

## Examples

```bash
# Все незафиксированные изменения
python "${CLAUDE_SKILL_DIR}/scripts/db-load-git.py" -V8Path "C:\Program Files\1cv8\8.3.25.1257\bin" -InfoBasePath "C:\Bases\MyDB" -ConfigDir "C:\WS\cfsrc" -Source All -UpdateDB

# Из диапазона коммитов
python "${CLAUDE_SKILL_DIR}/scripts/db-load-git.py" -InfoBasePath "C:\Bases\MyDB" -ConfigDir "C:\WS\cfsrc" -Source Commit -CommitRange "HEAD~3..HEAD"
```
