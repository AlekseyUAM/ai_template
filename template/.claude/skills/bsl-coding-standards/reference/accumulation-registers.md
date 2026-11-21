# Accumulation registers: storage, virtual tables and aggregates

Reference for designing queries and reports over accumulation registers. The checks below
are manual: query structure and task semantics are not derived from XML automatically.
Severity as in the other references: `[critical]` = error, `[important]` = warning,
`[minor]` = info. A finding inherits the severity of its item.

## How the register is structured

- Movements are stored in a separate table. A register of type **"Balances"** has the
  "ВидДвижения" field (receipt/expense); type **"Turnovers"** does not: receipt is written as plus,
  expense as minus.
- Totals: type "Balances" has a balances table, type "Turnovers" has a turnovers table.
  Totals are maintained monthly (and, for balances, additionally at the current date). The field
  `_Splitter` is the totals split for parallel writing.
- Virtual tables (VT) are not stored in the database: the platform builds SQL from the passed
  parameters and register totals settings.
- The **"Turnovers"** VT is available for both types. For type "Balances" it reads the movements table;
  for type "Turnovers" it reads turnover totals and takes only the uncalculated period from
  movements.
- The **"Balances"** and **"Balances and turnovers"** VTs are available only for type "Balances". If
  totals usage is disabled, the "Balances" VT does not work.

## What virtual tables return

| VT | Result composition | Features |
|---|---|---|
| `Обороты(НачалоПериода, КонецПериода, Периодичность, Условие)` | one row per combination of dimensions (and period, if periodicity is set); for each resource - `РесурсОборот`, and for a register of type "Balances" also `РесурсПриход`/`РесурсРасход` | **already grouped**: turnovers by dimensions are computed by the platform |
| `Остатки(Период, Условие)` | one row per combination of dimensions; for each resource - `РесурсОстаток` | the upper period boundary is treated as `< Период`; a movement exactly at that second does not fall in |
| `ОстаткиИОбороты(...)` | opening balance, receipt, expense, turnover, closing balance | the heaviest VT: joins movements for the period with balances; over a long period it reads a large volume of movements |

If periodicity is set, the result contains fields `ПериодДень`, `ПериодМесяц`
etc., and grouping is performed by period and dimensions. This is also VT work, not a
reason to add your own `СГРУППИРОВАТЬ ПО`.

## Queries to accumulation registers

- [important] **Do not add `СГРУППИРОВАТЬ ПО` to a selection from the "Turnovers"/"Balances" VT.** The VT already
  aggregates resources by dimensions (and period). Grouping by all VT fields is extra
  work and a sign of misunderstanding the model. `СГРУППИРОВАТЬ ПО` is allowed only if
  the join/expression really multiplies rows; then group by the added
  field, not by the entire VT composition.
- [important] **Dimension filters - in the VT parameters, not in `ГДЕ` after it.** The condition
  `Организация = &Организация` is passed as the fourth VT parameter: the platform embeds
  it into SQL and uses indexes/totals. A condition in `ГДЕ` is applied after the whole VT
  is selected and may read extra data.
- [important] **Upper period boundary.** For the "Turnovers" VT the period end is inclusive; for the
  "Balances" VT it is exclusive (`<`), so for balances at the end of a day/second pass the
  boundary of the next moment (e.g., `ДОБАВИТЬКДАТЕ(КОНЕЦПЕРИОДА(&Дата, ДЕНЬ), СЕКУНДА, 1)`).
  Do not mix `МоментВремени`/`Граница` with VT parameters - values are passed there.
- [critical] **Do not use the physical register table where a VT is needed.** The direct
  movements table does not account for totals and requires an explicit `Активность = Истина`; the VT
  accounts for activity itself and can use totals. The direct table is appropriate only for
  service tasks (e.g., a full pass over movements), and then the activity condition
  is mandatory.
- [important] **"Balances and turnovers" - not for long periods.** The VT reads movements for the whole
  period and joins them with balances. If only turnovers are needed - take "Turnovers"; if
  only the balance - "Balances". For an annual report "Balances and turnovers" can become a
  bottleneck.
- [important] **Do not output extra fields "just in case".** Every field in the query/data
  set must be needed by the report or a calculation. Fields and joins beyond the specification are a reason
  for an open question, not for unauthorized extension of the model.
- [important] **Do not read the recorder "via dot".** A report over a register must not
  dereference `Регистратор.Реквизит`: this is an implicit join, and in a distributed infobase the recorder
  may be absent. The needed data must be in register dimensions/resources/attributes.
- [minor] **Dimension order and indexes.** Dimensions are included in indexes in
  Configurator order; an index works when the filter starts with the leading dimensions. Take
  this into account when designing a register and a query.

## Aggregates of turnover registers

- [important] **Aggregates - only for proven performance needs.** These are separate
  tables with their own periodicity and dimension composition; they must be enabled and
  rebuilt manually (`РегистрыНакопления.<Регистр>.ОбновитьАгрегаты()`), unlike
  totals which the platform maintains automatically.
- [important] **An aggregate helps only when its dimension composition and periodicity match
  the query.** If the aggregate lacks a dimension used by the report, the platform does
  not use it and the query may become slower.
- [minor] **Measure first.** Aggregates make sense with hundreds of thousands/millions of records
  and a proven performance problem; for small registers this is extra
  infrastructure.

## Posting documents over accumulation registers

This reference covers typical posting pitfalls; take the metadata of a specific register from
`code_index` (register type, resources, dimensions, fill requirement, movement
deletion mode).

### Filling movements

- [critical] **`Период` is filled in every movement record.** During posting the platform
  does not set it: an empty period leads to the error
  "Record is invalid! Period cannot be empty!". Write `Движение.Период = Дата;`
  (or the date required by business logic) for every `Движения.<Регистр>.Добавить()`.
- [critical] **Register of type "Balances":** `ВидДвижения` is filled (`Приход`/`Расход`),
  resources are written **positive**. A negative resource in a balances register is a model
  error: `Обороты.<Ресурс>Расход` will remain empty, the balance will reconcile arithmetically, but
  the "Receipt/Expense" breakdowns and reports over them will be wrong.
  ```bsl
  Движение.ВидДвижения = ВидДвиженияНакопления.Расход;
  Движение.Количество = КоличествоВПартии;
  Движение.Стоимость = СтоимостьПартии;
  ```
- **Register of type "Turnovers":** there is no `ВидДвижения` - resources are written with a sign
  (expense - minus).
- [important] **Resource sign.** Resources for which negative movements are formed
  (expense, write-off) must have `AllowedSign = Any` in metadata; with `Nonnegative`
  the platform rejects writing a negative movement. For a balances register this item
  does not cancel the previous one: the direction is set by `ВидДвижения`, not by a minus.
- A resource in a movement is a value in the sense of the specification (batch cost, sale amount,
  quantity), not a "just in case" calculated value. Do not add allocations
  and recalculations that are not in the specification.
- [critical] **Do not store the selection object.** `Партии.Добавить(Выборка)` adds the
  `ВыборкаИзРезультатаЗапроса` object itself, which the platform reuses on each
  `Следующий()` - all array elements point to the last row. Copy the fields into a
  `Структура`/`ТаблицаЗначений` or iterate a nested selection (see below).

### Writing movements and reading in a transaction

- `Движения.<Регистр>.Записывать = Истина` - the set will be written by the platform after
  `ОбработкаПроведения` (before the transaction completes).
- To **read your own movements by a query inside the procedure** (balance control,
  re-posting), an explicit `Движения.<Регистр>.Записать()` is needed: the query does not see the set
  that exists only in memory.
- After an explicit `Движения.Записать()` the `Записывать` flag is reset - for automatic
  writing of subsequent movements set it again.
- [important] A repeated `Движения.Записать()` is a resource-intensive operation with locks;
  call it only when you really need to read movements in the same transaction.
- Deletion of movements on unposting is the document property
  `RegisterRecordsDeletion = AutoDeleteOnUnpost`; on re-posting old movements are
  replaced by writing the selected sets (`RegisterRecordsWritingOnPost`).

### Building the filter and iterating the result

- [important] **Select balances by document data in the VT parameters**, and do not read all
  balances of the organization with filtering after the join:
  `Номенклатура В (ВЫБРАТЬ ... ИЗ <ТЧ документа> ГДЕ НЕ Услуга)`.
- [important] **Grouping - by query means:** `ИТОГИ ПО <измерение>` and iteration
  `Результат.Выбрать(ОбходРезультатаЗапроса.ПоГруппировкам)`; inside a grouping -
  a nested selection (`ВыборкаПоНоменклатуре.Выбрать()`). This is shorter and more reliable than manual
  grouping with arrays of copied rows.
- [important] **Services and other non-writable-off rows** - process them in the same iteration by a flag
  computed by the query (`МАКСИМУМ(<Реквизит>)`), not by a second pass over the tabular section.
- [important] **`УПОРЯДОЧИТЬ ПО`** - standalone aliases only. Do not wrap an
  alias in a function (`ЕСТЬNULL(ДатаПартии, ...)` gives "Field not found"): sorting
  must go by the result column.
- [important] **Sorting batches by moment** - `Партия.МоментВремени` (FIFO/LIFO),
  without joining the document for the date; more - in
  [Boundary and point in time](boundary-and-moment.md).
- [important] **Join with a virtual table** - via materialization
  (`ПОМЕСТИТЬ <ВТ>` + `ИНДЕКСИРОВАТЬ ПО`), not a direct join with a VT.
- [minor] **One query per posting.** Additional reads (accounting policy,
  date by ref) are allowed, but not in a loop and not instead of one aggregating query.
- [critical] **Application refusal - not an exception.** In `ОбработкаПроведения`, insufficient
  balance/missing settings is `Отказ = Истина` + `ОбщегоНазначения.СообщитьПользователю`;
  `ВызватьИсключение` aborts the transaction abnormally and deprives the user of the message.
- [critical] **Negative resources in a register of type "Balances"** instead of
  `ВидДвижения = Расход`: the balance reconciles, but `Обороты.<Ресурс>Расход` will be empty,
  and reports over the "Expense" breakdown will be wrong.

### Posting checklist

- [ ] `Период` is filled in every movement.
- [ ] For a "Balances" register `ВидДвижения` is filled, resources are non-negative; for
  "Turnovers" the resource sign matches the direction; `AllowedSign` matches the
  sign of movements.
- [ ] No `Выборка` objects are stored in arrays/structures.
- [ ] Balances are selected by tabular section data in the VT parameters.
- [ ] Grouping and iteration - `ИТОГИ` + `ОбходРезультатаЗапроса.ПоГруппировкам`, nested selection.
- [ ] `УПОРЯДОЧИТЬ ПО` - without functions of aliases; batches - by `МоментВремени`.
- [ ] The balance lock is taken before reading (see [Locks](locks.md)).
- [ ] Application refusals - `Отказ` + message, not an exception.
- [ ] Old movements are cleared/replaced on re-posting and date shift.

## Checklist before submitting a query/report

- [ ] The source is a VT, not the physical movements table (unless there is a special reason).
- [ ] Dimension filters are in the VT parameters.
- [ ] No `СГРУППИРОВАТЬ ПО` over VT fields without justification.
- [ ] The upper period boundary is correct for the selected VT.
- [ ] The query has no fields/joins beyond the specification; every field is used.
- [ ] For a long period "Balances and turnovers" is not used without necessity.
- [ ] No recorder dereferencing "via dot".
- [ ] If aggregates are used, they are really needed and are rebuilt by schedule.
