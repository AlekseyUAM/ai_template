# DCS specifics (data composition system)

Requirements specific to DCS queries and settings that cannot be scripted
(task semantics is needed). Severity as in the other references: `[critical]` = error,
`[important]` = warning, `[minor]` = info (see reviewer "Severity scale and verdict").
**Each rule finding below is tagged with its severity** - a finding inherits the severity
of its item.

The list grows as tasks are analyzed; below - report period (standard period
and date), user parameters, optional fragments, report field composition and
report form.

## Report period: standard period and date

- [critical] **The period form is set by the specification: "for a period" - one parameter of type
  `СтандартныйПериод`; "on a date" - one date parameter.** Do not create two independent
  "start/end" dates for the user - this is extra input and a risk of a half-set period.

### "For a period" report - `СтандартныйПериод`

- [critical] **DCS fills empty period parameters of a virtual table with the composition
  parameters `НачалоПериода` and `КонецПериода` of the same name.** In query text
  leave the first two `Обороты` parameters empty:

  ```
  ИЗ РегистрНакопления.ОборотныйРегистрНакопления.Обороты(, , Авто, Организация = &Организация) КАК ОборотыРегистра
  ```

  DCS treats this as `Обороты({&НачалоПериода}, {&КонецПериода}, Авто, …)`. If the
  `НачалоПериода`/`КонецПериода` parameters are absent in the schema, DCS creates them empty, and
  the report returns data for the whole history - so declare them explicitly.

- [critical] **The `Период` parameter is of type `СтандартныйПериод` (`v8:StandardPeriod`).**
  In the schema - the empty value `Custom`; the default value is set in `dataParameters`
  of the settings variant - `ThisMonth` (without `startDate`/`endDate`; they are needed only for
  `Custom`). The parameter has `denyIncompleteValues=true`, `use=Always`.

- [critical] **The service parameters `НачалоПериода`/`КонецПериода` are hidden
  (`useRestriction=true`), with expressions `&Период.ДатаНачала` and
  `&Период.ДатаОкончания`.** Type - `xs:dateTime` with **`DateFractions=DateTime`**, not
  `Date`: otherwise `&Период.ДатаОкончания` (`23:59:59`) is truncated to `00:00:00` and data
  of the last day of the period is lost.

```xml
<parameter>
    <name>Период</name>
    <valueType><v8:Type>v8:StandardPeriod</v8:Type></valueType>
    <value xsi:type="v8:StandardPeriod">
        <v8:variant xsi:type="v8:StandardPeriodVariant">Custom</v8:variant>
        <v8:startDate>0001-01-01T00:00:00</v8:startDate>
        <v8:endDate>0001-01-01T00:00:00</v8:endDate>
    </value>
    <denyIncompleteValues>true</denyIncompleteValues>
    <use>Always</use>
</parameter>
<parameter>
    <name>НачалоПериода</name>
    <valueType>
        <v8:Type>xs:dateTime</v8:Type>
        <v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>
    </valueType>
    <useRestriction>true</useRestriction>
    <expression>&amp;Период.ДатаНачала</expression>
</parameter>
<parameter>
    <name>КонецПериода</name>
    <valueType>
        <v8:Type>xs:dateTime</v8:Type>
        <v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>
    </valueType>
    <useRestriction>true</useRestriction>
    <expression>&amp;Период.ДатаОкончания</expression>
</parameter>
```

- [important] **`КОНЕЦПЕРИОДА` and "+1 second" are not needed for a standard period.** Its
  `ДатаОкончания` is already `23:59:59`, and the `Обороты` VT includes both boundaries. Additional
  boundary handling is needed only for a date parameter (see below).

### "On a date" report - one `Период` parameter

- [critical] **The `Период` parameter is date/time (`DateFractions=DateTime`), visible
  (`useRestriction=false`), `denyIncompleteValues=true`.** In `dataParameters` of the variant
  set the default value `v8:StandardBeginningDate` with the variant
  `BeginningOfThisDay` and `userSettingID` - the user gets the standard date picker.

```xml
<parameter>
    <name>Период</name>
    <valueType>
        <v8:Type>xs:dateTime</v8:Type>
        <v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>
    </valueType>
    <value xsi:type="xs:dateTime">0001-01-01T00:00:00</value>
    <useRestriction>false</useRestriction>
    <denyIncompleteValues>true</denyIncompleteValues>
</parameter>
```

```xml
<!-- в dataParameters варианта настроек -->
<dcscor:item xsi:type="dcsset:SettingsParameterValue">
    <dcscor:parameter>Период</dcscor:parameter>
    <dcscor:value xsi:type="v8:StandardBeginningDate">
        <v8:variant xsi:type="v8:StandardBeginningDateVariant">BeginningOfThisDay</v8:variant>
    </dcscor:value>
    <dcsset:userSettingID>…</dcsset:userSettingID>
</dcscor:item>
```

- [critical] **In the `Остатки` VT the period is a point in time, the boundary is strict.** End-of-day
  balances are obtained with an upper boundary in the query text:

  ```
  ИЗ РегистрНакопления.ОстаточныйРегистрНакопления.Остатки(
          ДОБАВИТЬКДАТЕ(КОНЕЦПЕРИОДА(&Период, ДЕНЬ), СЕКУНДА, 1),
          Организация = &Организация) КАК ОстаткиРегистра
  ```

  `Остатки` has **two** parameters - `<Период>, <Условие>`; an extra empty position
  (`Остатки(дата, , условие)`) is a query error, not a "parameter skip".
  `КОНЕЦПЕРИОДА(&Период, ДЕНЬ)` gives `23:59:59`, `+1 СЕКУНДА` shifts to the start of
  the next day; passing a "bare" date without `КОНЕЦПЕРИОДА` cuts off the last day's data
  (see also [boundary and point in time](boundary-and-moment.md)).

- [important] **`Граница`/`МоментВремени` can be passed to DCS only programmatically.**
  The composition schema itself cannot declare a parameter of such a type, so in DCS
  the boundary is formed in query text (`КОНЕЦПЕРИОДА(...)` + 1 second) or by a
  standard period. If the report is composed programmatically and the parameter is filled from
  code, the `Граница`/`МоментВремени` object is allowed.

## User parameters

- [critical] **Parameters filled by the user (`Период`, `Организация`) must be visible -
  `useRestriction=false`.** Do not "hide" them with the `availableAsField=false` flag: this flag
  forbids using the parameter as a field but does not control its visibility in the parameter list.
  Only service parameters computed from others (`НачалоПериода`, `КонецПериода`) must be
  hidden (`useRestriction=true`).

- [important] **Set a `title` for every user parameter** ("Period",
  "Organization", "Period start", "Period end") - otherwise the user sees the
  technical name.

- [important] **Mandatory user parameters - `denyIncompleteValues=true`;
  if the parameter must always participate in composition - `use=Always`.** Otherwise DCS
  may use an auto-generated parameter instead of the declared one.

- [important] **Set the default value in the settings variant (`dataParameters`), not
  in the schema parameter's `<value>`.** For a standard period - `ThisMonth`; for a
  date - `StandardBeginningDate`/`BeginningOfThisDay`.

- [important] **Set `userSettingID` for every user parameter in `dataParameters`.**
  Without it the parameter does not get into user settings and
  cannot be changed. Service `НачалоПериода`/`КонецПериода` do not need `userSettingID` -
  they are computed from `Период`.

- [important] **A user filter parameter does not become a report field.** If
  `Организация` participates only in the VT condition (`Организация = &Организация`), do not
  add it to `ВЫБРАТЬ` or to the variant selection while it is not a specification column.

## Optional parameters and fragments - curly braces

- **Wrap optional parameters/conditions in `{ }`, and do not glue query text with
  concatenation/`СтрЗаменить`** [important]. Manual assembly is allowed only per the general
  `query-review` rule: if `validate_query` is available and every part / the axial text
  passes validation; otherwise - a finding [important].

A DCS query fragment wrapped in `{ }` is included in the query **only if** the related
parameter is filled (or the field is selected by the user). This is the standard way to make a filter
optional - without manual query text gluing and without extra conditions when the
parameter is empty:

```
{&ПодразделениеОрганизации}
```

Optional conditions and whole fields are wrapped the same way, e.g.,
`{ГДЕ Подразделение = &Подразделение}`. `{ }` is the standard way: do not substitute
optional parameters with concatenation/`СтрЗаменить` if `{ }` is enough for the task.
Manual assembly - only per the general `query-review` rule about `validate_query`;
otherwise it is a finding [important].

## Report field composition - strictly per the specification

- [critical] **The report has exactly the columns listed in the specification.** Do not add
  fields "just in case" to the query, data set, calculated fields or selection.
  An extra column is the same error as a missing one: the user sees the wrong report,
  and support gets an unspecified data model.
- [important] **Do not extend the query with joins for cosmetic reasons.** For example, to hide
  the cost of a service, do not add the `Услуга` flag to the query if it is not in the specification.
  If the requirement cannot be met without a service flag - this is an open question to
  the spec author, not a reason to change the query composition on your own.
- [important] **The field name in the data set, calculated field and selection matches the
  specification column name.** If a register resource has a different name, rename it with an alias in the
  query (`СтоимостьОборот КАК Себестоимость`) and use this alias everywhere - in the
  set, formulas and selection. Do not create a second calculated field with a different name and a
  title equal to the specification column name: a "foreign" field appears in the selection, and totals/format
  may reference the other one.

  Bad: a set field `Себестоимость`, a calculated field `СебестоимостьУслуги` with the
  title "Cost", the selection contains `СебестоимостьУслуги`. Good: the query has
  `... КАК Себестоимость`, the selection contains `Себестоимость`; if an empty
  value is needed for a service, that is a separate requirement, and its approach is agreed with the spec author.

- [important] **Report columns are selection fields + grouping fields.** With the "Auto"
  item the grouping field is output automatically; if by the template its column must be empty
  in detail rows, do not duplicate the field in the selection. Example - a report over a
  balances register: structure `Номенклатура > детальные записи`, selection
  `Партия, Количество, Стоимость`; `Номенклатура` is set only in the structure. If a repeated value
  in detail rows is required by the template, the field can be included in the selection.

  `skd-validate -ExpectedFields` checks only the selection and may report
  `missing from selection` for such a field; verify columns with `skd-info -Mode variant` (selection +
  groupings), not only by the selection list.

## Report form

- [important] **Do not create a custom `ФормаОтчета` (and do not assign `defaultForm`) unless
  the specification requires it.** The platform builds the report form from the DCS automatically; the auto form
  is more reliable and requires no form files. A custom form - only on an explicit requirement
  (e.g., a non-standard interface), and then it must be validated separately.

## DCS query and register virtual tables

- [critical] **Respect the virtual table signature - extra empty positions do not
  "skip" a parameter but shift it.** `Остатки(<Период>, <Условие>)` - two
  parameters; `Обороты(<НачалоПериода>, <КонецПериода>, <Периодичность>, <Условие>)` -
  four; `ОстаткиИОбороты(<НачалоПериода>, <КонецПериода>, <Периодичность>,
  <МетодДополненияПериодами>, <Условие>)` - five. Do not copy an "empty comma" from
  another VT.
- [important] **Set the VT periodicity per the specification; `Авто` - only if another
  periodicity is not required.** `Обороты(, , Авто, Организация = &Организация)` -
  when periodicity does not matter. If the specification or meaning requires `День`, `Месяц`,
  `Регистратор` etc., set it explicitly. Empty boundaries are filled by the
  `НачалоПериода`/`КонецПериода` parameters (see the "Report period" section).
- [important] **`Авто` periodicity does not make the `Период` field a report column.** If
  periodicity is not output, do not add `Период` to `ВЫБРАТЬ` - select only fields
  from the specification.
- [important] **Do not add `СГРУППИРОВАТЬ ПО` to a selection from the "Turnovers"/"Balances"
  virtual table.** The VT already groups the result by dimensions (and period).
  More - [accumulation registers](accumulation-registers.md).
- [important] **Dimension filters - in the VT parameters**, not in `ГДЕ` after it; the upper
  period boundary - per the rules of the selected VT (see the section above).
- [important] **Query fields - only those needed by the report.** Service fields for calculations
  are allowed only if they really participate in a formula, and are not output to the
  selection; their presence is recorded in `DEVELOP.md` with justification.

## Check before submission

- [ ] The period is arranged per report type: "for a period" - `Период` of type `СтандартныйПериод`
  + hidden `НачалоПериода`/`КонецПериода` (`DateTime`, expressions
  `&Период.ДатаНачала`/`&Период.ДатаОкончания`); "on a date" - one `Период`
  (`DateTime`, `StandardBeginningDate`/`BeginningOfThisDay`).
- [ ] In the query to `Обороты` the first two boundaries are empty, the third is the periodicity per the specification
  (`Авто` if another is not required); the schema has the parameters
  `НачалоПериода`/`КонецПериода` with expressions from `Период`. In the query to
  `Остатки` there are exactly two parameters (`<Период>, <Условие>`), end of day - `КОНЕЦПЕРИОДА` +
  1 second, no extra empty positions.
- [ ] `Период` and `Организация` are visible (`useRestriction=false`), have `title` and
  `denyIncompleteValues=true`; default values - in the variant's `dataParameters`;
  user parameters have `userSettingID`.
- [ ] Service `НачалоПериода`/`КонецПериода` are hidden (`useRestriction=true`), type
  `DateTime` (not `Date`).
- [ ] Verify the variant columns against the specification: `skd-info <tpl> -Mode variant -Name <вариант>` -
  selection fields + grouping fields; a grouping field is not duplicated in the selection if
  by the template it is output only as a grouping row.
- [ ] Run `skd-validate <tpl> -ExpectedFields "<колонки ТЗ через запятую>"` -
  the check catches extra/missing fields and a field replaced by a calculated one with the same
  title. `missing from selection` for a grouping field is a known validator limitation, verify
  against the variant structure.
- [ ] The query has no `СГРУППИРОВАТЬ ПО` over a VT without justification (the validator warns).
- [ ] A custom report form was not created if the specification does not require it.
