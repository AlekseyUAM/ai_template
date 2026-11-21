# Metadata design checklist (properties of created objects)

Properties that must be set **at the metadata design stage** and checked before
writing code. Checked by the architect (design) and the reviewer (detection).

`meta-validate` catches only structural XML correctness. **No one checks the semantics of
properties (fill requirement, register type, resource precision, posting mode)
except this checklist** - that is why a metadata-level defect (e.g., an empty register
dimension in a movement) reaches production unnoticed.

Severity as in the other references: `[critical]` = error, `[important]` = warning,
`[minor]` = info (see reviewer "Severity scale and verdict"). **Every check
item below is tagged with its severity** - a finding inherits the severity of its item.

Properties are divided into **basic platform** (applicable to any configuration) and
**BSP/standard configuration integration** (apply ONLY if the configuration is built on BSP -
check via `code_index` that the corresponding subsystems/subscriptions exist; otherwise the item
is not applicable and does not count as a finding).

## General properties (any object)
- **Synonym** is filled and meaningfully describes the object - participates in the UI [important].
- **Name** follows the naming standard: document - singular; without filler words
  ("Документ…") whose removal does not change the meaning [minor].
- **Comment** - do not fill; it is a development service field [minor].
- **Object/record presentation** - singular; **List presentation** - plural;
  do not set if it matches the synonym [minor].

## Fill check (key item)
For **any** attribute, dimension, resource or tabular section that is mandatory in all
scenarios by task logic - the property **"Fill check" =
"Raise error"** [important].
- For registers this applies to both **dimensions and resources**: an empty dimension
  (Organization / Nomenclature / Batch) in a movement is
  almost always a data error that metadata must cut off [important].
- The reverse scheme ("Do not check" + manual checks in `ОбработкаПроверкиЗаполнения`)
  is not recommended - constraints must be described in metadata [minor].

## Catalog
- **Name length** - by task; **code length** - 0 if the code carries no
  application meaning [minor].
- **Hierarchy**, **owners**, **predefined items** - set by meaning and specification;
  mismatch with the specification breaks the data model [important].
- Attributes: **fill value** for known default values; **choice
  parameters** / **choice parameter links** if value selection is constrained or depends on
  other attributes (fill requirement - see "Fill check") [minor].

## Document
- **Numbering**: deliberately set the number type and length, allowed length, periodicity,
  uniqueness control, auto-numbering (specific values - by task and configuration
  convention) [minor].
- **Posting**:
  - **Posting** = Allow if the document forms movements; otherwise Deny [important].
  - **Real-time posting** - set deliberately (usually Deny if real-time
    balance control is not required) [important].
  - **Movement deletion** - choose the mode by the task scenario: see
    [movements](movements-deletion.md). The mode must match the posting/clearing
    logic; mismatch - [critical].
  - **Movement writing on posting** = "Write selected" (not "Write all") [important].
- **Movement composition (recorders)**: every register the document writes to
  is assigned as a recorder; there are no extra recorders [important].
- Header and tabular section attributes: fill check of mandatory ones (see "Fill check");
  ref types - to existing objects (verify with `code_index`) [important].
- **Posting service data are not attributes.** Flags/markers that are computed
  in `ПередЗаписью` and needed only in `ОбработкаПроведения`/`ПриЗаписи` within one
  write transaction (date shift, need to clear movements etc.) must be passed
  via the `ДокументОбъект.ДополнительныеСвойства` structure. Creating **document
  attributes for them is forbidden** [important]: an attribute is a permanent entity in the storage
  structure, form and reports, while the value lives only during the write; do not use module
  variables for such passing either [important].

## Accumulation register
- **Register type** - **Balances** or **Turnovers** - matches the accounting nature;
  a wrong type breaks accounting semantics [critical].
- **Dimensions**: the full accounting key composition; mandatory ones → fill check
  "Raise error" [important]. A **leading** dimension - for ref dimensions whose deletion
  makes the register record meaningless [minor].
- **Resources**: Number type with **deliberate precision and scale** (quantity and amounts -
  different scale); insufficient precision = lost cents or overflow [important].
- **Attributes** (optional dimensions) - only if needed for filtering/decryption;
  do not bloat the accounting key with them [minor].

## Information register
- **Periodicity** and **write mode** (independent / subordinate to recorder) - by task [important].
- **Leading** dimension, **main filter**, duplicate prohibition (uniqueness key) - by
  meaning; lack of key uniqueness produces duplicate records [important].
- Dimensions / resources / attributes: fill check of mandatory ones (see "Fill
  check") [important].

## DCS report
- **Main data composition schema** is set (`mainDataCompositionSchema`), the DCS template is created and
  checked [critical].
- **Report field composition** - strictly per the specification; do not add service fields/joins without
  justification. More - [DCS specifics](skd-specifics.md) [critical].
- **A custom report form** (`defaultForm` / `ФормаОтчета`) is not created unless the specification
  requires it: the platform builds an auto form from the DCS. A custom form is an extra object and a risk
  of malfunction [important].

## BSP/standard configuration integration (conditional - only if the configuration is on BSP)
Check via `code_index` that the corresponding subsystems/subscriptions/roles exist.
If the configuration is not on BSP, the section is not applicable (does not count as a finding).
- **Roles and rights** for the new object [important].
- **Privileged mode on posting/unposting** - if the configuration has
  access rights restrictions [important].
- **Numbering** - prefix/number control subscriptions [minor].
- **Distributed infobase/exchange plans**, **functional options**, **printing**, **versioning**,
  **change prohibition dates** - per configuration requirements [minor].
