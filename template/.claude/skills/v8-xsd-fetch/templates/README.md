# .v8-xsd - XSD schemas of the 1C:Enterprise 8 platform

Directory for XSD schemas of the configuration XML dump format. Skills use them to validate a dump
without a database: element order, value types, allowed enum values.

No schemas - no validation; everything else works as usual.

## Layout

```
.v8-xsd/
├── 2.20/        схемы версии формата 2.20 (атрибут version корня MetaDataObject)
│   └── *.xsd
├── 2.21/
└── source.json  откуда и когда загружено
```

File names do not matter: a schema is found by `targetNamespace`. Schemas dumped from your own
platform (`ФабрикаXDTO.ЭкспортСхемыXML`) work too.

## How to populate

With the `/v8-xsd-fetch` skill - it downloads schemas from the
[yellow-hammer/namespace-forest](https://github.com/yellow-hammer/namespace-forest)
repository (directory `schemas/designer/<версия формата>/`).

Or manually: copy the needed version directories from `schemas/designer/` of the same repository.

Another directory is set by the `xsdPath` key in `.v8-project.json`.

## License

The schemas (`*.xsd`) are part of the "1С:Предприятие 8" product, owned by ООО "1С-Софт".
Use is governed by the 1C license agreement. Do not include them in the repository.

## Credits

Thanks to Ivan Karlo for [namespace-forest](https://github.com/yellow-hammer/namespace-forest) -
schemas collected and arranged by format version, updated automatically.
