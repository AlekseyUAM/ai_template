# Service operations

## set-label - label a version

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command set-label -InfoBasePath "C:\Bases\MyDB" -Label "Релиз 1.2" -Version 120 -Comment "Передано в тест"
```

Without `-Version` the label is put on the last version. A nonexistent version is an error.

## optimize - storage optimization

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command optimize -InfoBasePath "C:\Bases\MyDB"
```

Optimizes data storage in the repository. The operation is long.

## clear-cache - clear the cache

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command clear-cache -InfoBasePath "C:\Bases\MyDB" -CacheScope local
```

| `-CacheScope` | What it clears |
|---------------|------------|
| `local` (default) | Local configuration version cache |
| `global` | Global version cache |
| `db` | Local repository database |

Useful when the repository behaves strangely after a network failure or a version rollback.
