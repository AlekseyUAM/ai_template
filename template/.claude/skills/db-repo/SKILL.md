---
name: db-repo
description: Working with a 1C configuration repository. Use when you need to lock objects, commit changes to the configuration repository, get changes from it, connect a database to the repository
argument-hint: <lock|unlock|commit|update> [database] -Objects "<objects>"
allowed-tools:
  - Bash
  - Read
  - Glob
  - AskUserQuestion
---

# /db-repo - 1C configuration repository

Locking and committing objects, getting changes, connecting a database, version history,
repository administration.

> A 1C configuration repository, not a Git repository.

## Usage

```
/db-repo lock   [database] -Objects "Справочник.Номенклатура"
/db-repo commit [database] -Objects "Справочник.Номенклатура" -Comment "Добавлен Артикул"
/db-repo unlock [database] -Objects "Справочник.Номенклатура"
/db-repo update [database]
```

## Workflow

In a database connected to a repository, sources are loaded **only partially** and **only for locked**
objects. Follow the steps strictly:

```
0. /db-repo update <база>                      — начать с актуального состояния
1. /db-repo lock <база> -Objects "Справочник.Номенклатура"
2. если шаг 0 или 1 напечатал «локальная конфигурация изменена, получено объектов из хранилища: N» —
   выгрузи названные объекты: /db-dump-xml <база> <каталог> -Mode Partial -ObjectsFile "<файл из вывода>"
3. правки в исходниках: /meta-edit, /form-edit, /skd-edit, /meta-compile и т. д.
4. /db-load-xml <каталог> <база> -Mode Partial -Files "Catalogs/Номенклатура.xml,…" -UpdateDB
5. /db-repo commit <база> -Objects "Справочник.Номенклатура" -Comment "…"
```

Do step 0 whenever work does not continue immediately after the previous cycle: edits
must rely on the current state - including objects you do not change but use.

Step 2 cannot be skipped: locking and updating pull fresh versions from the repository, and loading
sources taken earlier will roll back someone else's changes - silently, without an error.

**What can be locked at all.** Individual repository objects - the object itself, as well as its
**forms, templates, and commands**. Attributes, tabular sections, dimensions, and resources are **not**
separate objects: they are edited as part of the owner.

| What you edit | What to lock |
|-------------|-----------------|
| An attribute, tabular section, dimension, resource, object module | the object itself: `Справочник.Контрагенты` |
| An existing form, template, command | that object itself: `Справочник.Контрагенты.Форма.ФормаЭлемента` |
| Adding a new form, template, command | the owner object; when committing, name the new object too |
| Adding a new configuration object | only the root: `Конфигурация`. The object itself does not exist yet - it cannot be locked; when committing, name it too |

Lock the minimum of what you edit: the wider the lock, the more conflicts with colleagues.
Locking an object does not lock its forms and templates - use `-WithChildren` for that.

## Connection parameters

Read `.v8-project.json` from the project root and resolve the database:
1. If the user specified connection parameters - use them directly
2. If the user specified a database by name - search by id / alias / name
3. If not specified - match the current Git branch against `databases[].branches`
4. If the branch did not match - use `default`

Platform - `v8path` of the found database record, otherwise the root `v8path`. If neither is set - do not pass `-V8Path`.

There is no need to pass repository credentials: the database record is found by the passed
connection parameters (`-InfoBasePath` or `-InfoBaseServer` + `-InfoBaseRef`), and credentials are taken
from its `repository`. They can be set explicitly with the `-Repository*` parameters.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command <подкоманда> <параметры>
```

### Work cycle

| Subcommand | What it does |
|------------|------------|
| `lock` | Lock objects |
| `unlock` | Cancel the lock |
| `commit` | Commit changes to the repository |
| `update` | Get changes from the repository |

### Parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| `-InfoBasePath <путь>` | * | File infobase |
| `-InfoBaseServer <сервер>` | * | 1C server |
| `-InfoBaseRef <имя>` | * | Database name on the server |
| `-UserName <имя>` | no | Database user |
| `-Password <пароль>` | no | Database user password |
| `-Objects <список>` | cond. | Comma-separated objects. For `lock`, `unlock`, `commit` it is required unless `-All` is set |
| `-ObjectsFile <путь>` | no | File with the object list, one name per line |
| `-All` | no | Operation on the whole configuration - instead of `-Objects`, not together with it |
| `-WithChildren` | no | Together with subordinate objects to full depth |
| `-Comment <текст>` | no | Commit comment (`commit`). Multi-line - as is, with line breaks |
| `-KeepLocked` | no | Keep objects locked after committing |
| `-Revised` | no | Get locked objects if required |
| `-Force` | no | Varies by subcommand - see below |
| `-Extension <имя>` | no | Work with the extension's repository |
| `-RepositoryPath <путь>` | no | Repository explicitly, instead of the registry |
| `-RepositoryUser <имя>` | no | Repository user explicitly |
| `-RepositoryPassword <пароль>` | no | Repository user password explicitly |
| `-AdditionalV8Arguments <список>` | no | Additional `1cv8.exe` arguments, comma-separated |

> `*` - either `-InfoBasePath` is needed, or the pair `-InfoBaseServer` + `-InfoBaseRef`

### `-Force`

| Subcommand | What it does |
|------------|------------|
| `unlock` | **Loses local edits**: objects are overwritten by the version from the repository |
| `commit` | Tries to clear references to deleted objects instead of failing |
| `update` | Confirms adding and deleting configuration objects |

### Object names

An object is `Справочник.Номенклатура`. A form, template, command - by full path:
`Документ.ЗаказПокупателя.Форма.ФормаДокумента`, `Справочник.Номенклатура.Макет.Печать`.
The configuration root is `Конфигурация`.

If an object is "not found", this is not always a typo: it may have appeared in the repository later
than the database was updated (`/db-repo update`), or it is not a repository object at all - an
attribute or tabular section.

## Result

A zero exit code does not mean something changed. A zero code also covers "already locked", "nothing to
update", "nothing to commit", and a partial lock - when some objects are taken by others while the rest
are locked and can be edited.

**Read the output text, not just the code.** It also contains the list of objects received from the
repository, which requires re-dumping before editing.

## Operations requiring user confirmation

Before these operations **ask for confirmation**:

| Operation | Why |
|----------|--------|
| `lock -All` | Locks **the whole configuration**: on a large database it takes long and blocks the whole team |
| `unlock -Force` | Local edits of locked objects are lost |
| `disconnect` | The database loses its connection to the repository, including on the repository side |
| `connect -ForceReplaceCfg` | The database configuration is replaced by the configuration from the repository |

`update` will not run if the database record does not declare `repository` and credentials are not set
explicitly: on a database not connected to a repository this command replaces the whole configuration
with its contents and reports success.

## Extensions

An extension has its own repository with its own path. Specify `-Extension "<Имя>"` - credentials are
taken from the database record's `extensions[].repository`. Subcommands work the same for the main
configuration and for an extension.

## Other tasks

| File | About |
|------|---------|
| [connect.md](references/connect.md) | Connecting and disconnecting a database to/from the repository |
| [history.md](references/history.md) | Version history, report, dumping a version to CF |
| [admin.md](references/admin.md) | Creating a repository, users and rights |
| [service.md](references/service.md) | Version labels, optimization, cache clearing |

## Examples

```bash
# Захватить справочник вместе с подчинёнными объектами
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command lock -InfoBasePath "C:\Bases\MyDB" -Objects "Справочник.Номенклатура" -WithChildren

# Захватить корень — он нужен, чтобы добавить или удалить объект конфигурации
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command lock -InfoBasePath "C:\Bases\MyDB" -Objects "Конфигурация"

# Поместить новый объект: он уже существует, поэтому называется вместе с корнем
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command commit -InfoBasePath "C:\Bases\MyDB" -Objects "Конфигурация,Справочник.Склады" -Comment "Добавлен справочник Склады"

# Поместить с комментарием, оставив захват
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command commit -InfoBasePath "C:\Bases\MyDB" -Objects "Справочник.Номенклатура" -Comment "Добавлен реквизит Артикул" -KeepLocked

# Получить изменения из хранилища
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command update -InfoBasePath "C:\Bases\MyDB"

# Серверная база, расширение
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command lock -InfoBaseServer "srv01" -InfoBaseRef "MyApp_Dev" -UserName "Admin" -Extension "МоёРасширение" -Objects "Справочник.Номенклатура"
```

## After execution

- `lock` or `update` reported received objects - run `/db-dump-xml -Mode Partial` with the
  file named in the output, and only then edit the sources
- after `lock` edits go through `/db-load-xml -Mode Partial` and `/db-update`
- changes are ready - offer `/db-repo commit` with a comment
