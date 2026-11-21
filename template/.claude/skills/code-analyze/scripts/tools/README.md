# Updating system enum data

`../system_enums.json` is a snapshot of platform help for the
`system-enum-value` and `reserved-system-name` rules: 664 system enums
(2914 values) and 8 value sets (517 values), Russian and English names.
**Models do not need to read this file** - `rules.py` reads it.

## Source

Data is captured from `shcntx_ru.hbk` of the installed 1C platform via
`bsl-ctx` (the same help parsing used by platform-context MCP servers). The
installed `1c_platform` MCP (`mcp-bsl-context`) exposes methods, properties and
types, but not the list of system enums/sets, so the snapshot is updated by the
generator.

```bash
bsl-ctx capture "<каталог платформы 1С>" -o corpus.sqlite
bsl-ctx parse --all --db corpus.sqlite --out parsed.jsonl
python tools/update_system_names.py --corpus corpus.sqlite --parsed parsed.jsonl \
    --out system_enums.json --platform 8.3.27.2170
```

Commands are run from the `scripts/` directory. After updating:

```bash
python -m pytest tests/ -q
```

The generator uses only the Python standard library; `bsl-ctx` is needed only
to update the snapshot.
