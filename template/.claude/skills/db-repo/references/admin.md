# Repository administration

## create - create a repository

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command create -InfoBasePath "C:\Bases\MyDB" -RepositoryPath "C:\Repo\MyApp" -RepositoryUser "Admin" -RepositoryPassword "…"
```

| Parameter | Description |
|----------|----------|
| `-NoBind` | Do not connect the database to the created repository |
| `-AllowConfigurationChanges` | Enable configuration changes if the configuration is on vendor support without this ability |
| `-ChangesAllowedRule <правило>` | Rule for objects whose changes are allowed by the vendor |
| `-ChangesNotRecommendedRule <правило>` | Same for "changes not recommended" |

Rules: `ObjectNotEditable`, `ObjectIsEditableSupportEnabled`, `ObjectNotSupported`.

Without `-NoBind` the database is immediately connected to the created repository. Creation is version 1.

For an extension: `-Extension "<Имя>"` and a separate path - an extension has its own repository.

## add-user - create a user

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command add-user -InfoBasePath "C:\Bases\MyDB" -NewUser "Ivanov" -NewUserPassword "…" -Rights LockObjects
```

| Right | What it grants |
|-------|----------|
| `ReadOnly` | View |
| `LockObjects` | Locking objects |
| `ManageConfigurationVersions` | Changing the set of versions |
| `Administration` | Administrative functions |

`-RestoreDeletedUser` - restore a deleted user with the same name. If a user with that name
exists, it will **not** be added. The executing user must have administrative rights.

## copy-users - copy users from another repository

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command copy-users -InfoBasePath "C:\Bases\MyDB" -SourcePath "\\srv01\repo\Other" -SourceUser "Admin" -SourcePassword "…"
```

`-SourcePath`, `-SourceUser`, `-SourcePassword` describe the **source** repository. Deleted users
are not copied; existing ones are not overwritten.
