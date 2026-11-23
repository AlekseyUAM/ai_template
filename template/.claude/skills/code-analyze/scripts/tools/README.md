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

# Updating event handler data

`../event_handlers.json` is the snapshot used by `check_event_handlers.py`:
event contracts (handler names, signatures, optional parameters) for
object/manager/recordset/value-manager/application/command modules.
**Models do not need to read this file** - the script reads it.

The generator reads the syntax assistant directly from `.hbk`, so `bsl-ctx`
and the platform installation are not needed at analysis time:

```bash
python tools/update_event_handlers.py \
    --hbk "C:/Program Files (x86)/1cv8/8.3.27.2170/bin/shcntx_ru.hbk" \
    --out ../event_handlers.json --platform 8.3.27.2170
```

Instead of `--hbk` an already extracted help directory can be passed:
`--html-dir <каталог с objects/>`. The generator:

1. reads the `FileStorage` ZIP from the `.hbk` container;
2. scans `objects/**/events/*.html` and the paired `.st` handler templates
   (`Процедура Имя(Параметры)` / `Procedure Name(Parameters)`);
3. marks parameters with "Значение по умолчанию" in the help as optional
   (optional trailing parameters may be omitted in a handler);
4. maps owner types (`ДокументОбъект`, `РегистрСведенийНаборЗаписей`, ...) to
   module keys (`Document.ObjectModule`, `InformationRegister.RecordSetModule`);
5. writes the snapshot.

After updating, run the tests:

```bash
python -m pytest tests/ -q
```

Form modules are intentionally not included: their handlers are bound in
`Form.xml`, and name-based signature checks produce false positives. HTTP/Web/
integration service modules are included as `handler_name_arbitrary` and are
not signature-checked.

`EXTRA_SIGNATURES` in the generator adds accepted overloads that are not in the
base help page. Currently it contains the BSP report signature
`ПриКомпоновкеРезультата(…, АдресХранилища)`. The catalog
`ПередЗаписью(Отказ, РежимЗаписи, РежимПроведения)` is deliberately NOT
added: `РежимПроведения` is document-specific, so such a catalog handler is a
defect.
