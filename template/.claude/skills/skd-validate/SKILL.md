---
name: skd-validate
description: Validate a 1C data composition schema (DCS). Use after creating or modifying a DCS to check correctness
argument-hint: <TemplatePath> [-Detailed] [-MaxErrors 20] [-ExpectedFields "Поле1,Поле2,..."]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /skd-validate - DCS (DataCompositionSchema) validation

Checks the structural correctness of a data composition schema Template.xml. Detects format errors, broken references, duplicate names.


## Parameters

| Parameter    | Req.  | Default | Description                                           |
|--------------|:-----:|---------|---------------------------------------------------------|
| TemplatePath | yes   | -       | Path to Template.xml or the template directory          |
| Detailed     | no    | -       | Detailed output (all checks, including successful ones)  |
| MaxErrors    | no    | 20      | Stop after N errors                                     |
| OutFile      | no    | -       | Write the result to a file                              |
| ExpectedFields | no  | -       | Report columns per the specification, comma/semicolon separated - enables the semantic selection check |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/skd-validate.py" -TemplatePath "src/МойОтчёт/Templates/ОсновнаяСхема"
python "${CLAUDE_SKILL_DIR}/scripts/skd-validate.py" -TemplatePath "Catalogs/Номенклатура/Templates/СКД/Ext/Template.xml"
# Для отчёта: всегда передавай колонки ТЗ — иначе состав выборки не проверяется
python "${CLAUDE_SKILL_DIR}/scripts/skd-validate.py" -TemplatePath "<Template.xml>" \
  -ExpectedFields "Номенклатура,Количество,Себестоимость,Продажа,Прибыль"
```

## Semantic checks

The structural check (`XML`, references, types) does not answer the question "is this the right report".
Additionally the validator checks:

- **`-ExpectedFields`** - the variant selection must reference exactly the specification columns:
  - a missing column - `[ERROR]`;
  - an extra column - `[ERROR]`;
  - substitution of a column by a calculated field with a different name and the same title
    (for example, `СебестоимостьУслуги` with the title "Себестоимость" instead of the field
    `Себестоимость`) - `[ERROR]`;
  - another data set field beyond the specification - `[WARN]`: a service field/join must be
    justified and not output in the selection.
- **`GROUP BY` over a virtual table** - if the query reads
  `РегистрНакопления.<Регистр>.Обороты/Остатки/ОстаткиИОбороты` and contains
  `СГРУППИРОВАТЬ ПО`, a `[WARN]` is issued: the VT already aggregates by dimensions, grouping
  is needed only for a join that multiplies rows.
- **Title collision** - a selected calculated field with a title matching the
  name of another field is marked `[WARN]`: use the specification field, not a renamed
  calculated one.

The result `Validation OK` **without** `-ExpectedFields` means "the structure is correct", but
not "the report composition matches the specification". For reports always pass `-ExpectedFields` and
additionally verify with `skd-info -Mode variant`.

## XSD check

## XSD check

The order of elements, types and values are additionally compared with the platform XSD schemas if they are downloaded into the project. Otherwise the final line ends with `XSD not checked: <причина>` - this is not "everything checked". When the check is needed (for example, the platform says "the order of occurrence is violated"), download the schemas of the export format version - the `version` attribute in `Configuration.xml` - via `/v8-xsd-fetch -Versions <версия>` and run again. The same for `[WARN] XSD: no schemas for format <версия>`.

Violation: `XSD <версия>, line N: <родитель>/<элемент>: <что не так>`.

- `must come before <X>` - move the element directly before `<X>`, do not change its content. `duplicate` - remove the duplicate. `not allowed in <P>` - the element does not belong here. Otherwise - text about an invalid value.
- `[WARN]` with `(no schemas for <версия>)` - compared against schemas of a newer version: a guideline, not a verdict.
- If you just built or changed the template with `/skd-compile` or `/skd-edit`, the violation is a skill defect: report it to the user.
