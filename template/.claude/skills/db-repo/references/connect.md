# Connecting a database to the repository

## connect - connect

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command connect -InfoBasePath "C:\Bases\MyDB" -RepositoryPath "\\srv01\repo\MyApp" -RepositoryUser "Ivanov" -RepositoryPassword "…"
```

| Parameter | Description |
|----------|----------|
| `-ForceReplaceCfg` | The database configuration is not empty - confirm replacing it with the configuration from the repository. **Ask the user for confirmation** |
| `-ForceBindAlreadyBindedUser` | Connect even if this user already has a configuration bound to the repository |

On an empty database `-ForceReplaceCfg` is not needed.

**Reconnecting** a database that was already connected requires both flags: the configuration in the
database is not empty (`-ForceReplaceCfg`), and this database is still assigned to the repository user
(`-ForceBindAlreadyBindedUser`).

After connecting, add `repository` to the database record in `.v8-project.json` - otherwise the other
subcommands will have to be called with explicit credentials every time, and `update` will refuse to work.

## disconnect - disconnect

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command disconnect -InfoBasePath "C:\Bases\MyDB"
```

**Ask the user for confirmation.** Disconnecting removes the binding on the repository side too:
the connection record is deleted. The database can be connected back, but this is no longer a routine
operation - both `connect` flags from the section above will be needed.

If the database has locked and modified objects, the operation will not run. `-Force` performs it
anyway, and those changes are lost.

## Extensions

An extension has its own repository: specify `-Extension "<Имя>"` together with the path to that
repository, not to the main configuration repository.
