# Repository version history

## report - version report

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command report -InfoBasePath "C:\Bases\MyDB" -OutputFile "C:\tmp\repo.txt"
```

| Parameter | Description |
|----------|----------|
| `-OutputFile <путь>` | Where to save the report. Optional |
| `-NBegin <номер>` | From which version. `-1` - last only |
| `-NEnd <номер>` | Up to which version |
| `-DateBegin` / `-DateEnd` | Date boundaries |
| `-GroupByObject` | Group by objects |
| `-GroupByComment` | Group by comment |
| `-ReportFormat <txt\|mxl>` | Default `txt` |

`txt` - tab-separated, parsed line by line.

> Do not build a full report on a production repository - thousands of versions. If you need the head
> version - `-NBegin -1`. A long report is not printed to the output: narrow the selection with the
> parameters below.

## dump-cfg - dump a version to CF

```bash
python "${CLAUDE_SKILL_DIR}/scripts/db-repo.py" -Command dump-cfg -InfoBasePath "C:\Bases\MyDB" -OutputFile "C:\tmp\v120.cf" -Version 120
```

Without `-Version` (or with `-1`) the last version is dumped.
