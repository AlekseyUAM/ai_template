# Information registers: storage, slices and writing

Reference for designing queries and code that works with information registers.
The checks are manual: register properties and query semantics are not derived from XML automatically.
Severity as in the other references: `[critical]` = error, `[important]` = warning,
`[minor]` = info. A finding inherits the severity of its item.

## How the register is structured

- An information register is a flat table: rows are records, columns are dimensions, resources and
  attributes. The "resource/attribute" distinction is logical; in the DBMS both are stored the same way.
- **Dimensions** are included in all indexes in Configurator order. An index works when
  the filter starts with the first index field; therefore dimension order affects queries.
- A register can be **independent** (key - dimensions; possibly period) or
  **subordinate to a recorder** (the key contains the recorder and line number).
- A **periodic** register stores several values over time. Periodicity
  "By recorder position" allows several records in one second and produces the most
  complex slice query.
- In 8.3 a periodic register can have **slice totals tables** enabled (`СрезПоследних`
  or `СрезПервых`, both if needed). A slice table stores only one - the most current -
  record per combination of dimensions. Maintaining the slice
  adds queries on every register write.

## Slice queries

- [critical] **Dimension filters - in the virtual table parameters, not in `ГДЕ`
  after the slice.** `СрезПоследних(&Дата, Измерение1 = &Значение1)` filters records before
  computing the slice; the same filter in `ГДЕ` forces the platform to first read all
  register records, compute the slice and only then filter. On a file infobase this is
  guaranteed extra reading, on SQL - a risk of a bad plan.
- [important] **`СрезПоследних(<Дата>, ...)` does not use the slice totals table.** Totals
  apply only to the most current slice - when the period is not specified in the VT
  (`СрезПоследних(, ...)`). If the query always goes to a date, enabling the totals table
  is pointless: it only adds write overhead.
- [important] **`СрезПоследних` is a two-level query, `ПоПозицииРегистратора` is a
  three-level one.** Do not join many slices in a row without necessity; query
  complexity grows fast.
- [important] **Periodicity "By recorder position" - only if two records with the same
  dimensions in one second are really possible.** Otherwise it is extra
  complexity and a worse query plan.
- [important] **Do not use a slice if the whole history is needed.** `СрезПоследних` returns
  only the last record as of a date; for history/dynamics read the register directly (with
  a period condition if needed).
- [important] **There is no slice for a non-periodic register.** Do not design `СрезПоследних`
  for a register without periodicity.

## Reading the slice in BSL

The manager call `РегистрСведений.<Имя>.СрезПоследних(Период, Отбор)` returns a
`ТаблицаЗначений` of rows. Take the row with `[0]` / `Выбрать()` and read resources
and attributes by name:

```bsl
Срез = РегистрСведений.КурсыВалют.СрезПоследних(
    ТекущаяДата(), Новый Структура("Валюта", Валюта));
Курс = ?(Срез.Количество() > 0, Срез[0].Курс, 0);
```

`Период` and `Отбор` are optional; the result always has the shape of a table, even
for a single row. An empty slice is a table with zero rows - check `Количество()`
before reading `[0]`.

## Writing the register

- [important] **The write mode is chosen by task:**
  - `Записать(Истина)` - substitution: records by the set filter are deleted first,
    then new ones are inserted. If no filter is set, everything is deleted - this is a common
    cause of data loss.
  - `Записать(Ложь)` - addition with a uniqueness check: the platform looks for duplicates by
    key and fails on a conflict.
  - `ОбменДанными.Загрузка = Истина` + `Записать(Ложь)` - the fastest mode without
    checks; allowed only when uniqueness is guaranteed by logic/architecture
    (e.g., exchange load).
- [important] **Before substitution set `Отбор` by dimensions.** Otherwise `Записать(Истина)`
  clears the whole register, not only the needed set.
- [important] **The record manager is for point editing of one record.** For record
  sets it is less efficient: on `Прочитать()` the platform runs an additional
  query and deletes the old record when a dimension changes.
- [important] **Do not enable slice totals tables "just in case".** Every document write
  to such a register adds slice maintenance queries; with mass
  posting this is a noticeable load on the DBMS and the 1C server.
- [minor] **Design dimension order for frequent queries.** The clustered index
  must cover the most frequent filter; if needed, add an indexed
  dimension/attribute.

## Design

- [critical] **An information register is for data that is not numerical accounting by
  dimensions.** Numerical balances/turnovers are an accumulation register; reference
  values, settings, rates, prices by dimensions - an information register. Do not substitute one
  object for another.
- [important] **Periodicity, independence/subordination and key uniqueness - by
  task.** A periodic register without necessity complicates queries and writing;
  lack of uniqueness control produces duplicates.
- [important] **Fill check of dimensions/resources** - per the checklist
  [metadata design](metadata-design.md).

## Checklist before submission

- [ ] Dimension filters are in the parameters of `СрезПоследних`/`СрезПервых`.
- [ ] If the slice is always by date, the slice totals table is not enabled without a reason.
- [ ] For history the register itself is used, not a slice.
- [ ] `Записать(Истина)` is used with `Отбор` set.
- [ ] The `ОбменДанными.Загрузка = Истина` mode is applied only where uniqueness
      is guaranteed.
- [ ] Periodicity "By recorder position" is not used without necessity.
- [ ] Dimension order matches frequent queries.
