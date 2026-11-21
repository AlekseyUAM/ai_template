# Totals in 1C queries (ИТОГИ section)

Domain reference: `ИТОГИ` semantics, aggregates, `NULL` in total rows,
result iteration. Non-aggregated fields are caught automatically by the
`totals-field-not-aggregated` rule of the `query-analyze` skill (severity `error`).
Manual query checks - the `query-review` skill.

## 1. What ИТОГИ does

`ИТОГИ` **adds** total rows to the result. Detail rows remain
in place. `СГРУППИРОВАТЬ ПО`, conversely, collapses detail rows into groups.

| Construct | What it does | Detail rows |
|---|---|---|
| `СГРУППИРОВАТЬ ПО` | collapses the selection into groups | disappear |
| `ИТОГИ ... ПО` | adds total rows to the selection | are preserved |

`ИТОГИ` can be combined with `СГРУППИРОВАТЬ ПО`: `СГРУППИРОВАТЬ ПО` manages
detail rows (collapses them), `ИТОГИ` adds total levels. If only collapsed
groups are needed, `ИТОГИ` is not needed.

## 2. Syntax

```sql
ВЫБРАТЬ
    <поля>
ИЗ
    <источники>
[ГДЕ ...]
[СГРУППИРОВАТЬ ПО ...]
[УПОРЯДОЧИТЬ ПО ...]
ИТОГИ
    [<агрегат>(...) [КАК <псевдоним>], ...]
ПО
    [ОБЩИЕ,] <Группировка1> [ИЕРАРХИЯ | ТОЛЬКО ИЕРАРХИЯ]
    [, <Группировка2> ...]
```

- `ПО` is mandatory.
- `ОБЩИЕ` adds a root total record over the whole selection.
- The order of groupings in `ПО` sets the order of total levels.
- `УПОРЯДОЧИТЬ ПО` is placed **before** `ИТОГИ`; after `ИТОГИ` - a syntax error.

## 3. Aggregate functions

| Function | Result |
|---|---|
| `СУММА` | sum of values |
| `КОЛИЧЕСТВО` | number of values; `NULL` is not counted |
| `КОЛИЧЕСТВО РАЗЛИЧНЫЕ` | number of distinct values; `NULL` is not counted |
| `МАКСИМУМ` | maximum value |
| `МИНИМУМ` | minimum value |
| `СРЕДНЕЕ` | average value |

## 4. Main rule: NULL in total rows

Only the following are available in a total row:

- fields included in the `ИТОГИ` grouping (listed in `ПО`);
- aggregates described in `ИТОГИ`.

All other fields are returned as `NULL` in the total row. When iterating the
result and using such a field in expressions/type conversion this causes
runtime errors, e.g., "Value conversion to Boolean cannot be performed".

Incorrect:

```sql
ВЫБРАТЬ
    Т.Номенклатура КАК Номенклатура,
    Т.Склад КАК Склад,
    Т.Количество КАК Количество
ИЗ
    Документ.ПриходнаяНакладная.Товары КАК Т
ИТОГИ
    СУММА(Количество) КАК Количество
ПО
    Номенклатура
```

On total rows `Склад` will be `NULL`.

Correct - aggregate the field or remove it from the selection:

```sql
ИТОГИ
    СУММА(Количество) КАК Количество,
    МАКСИМУМ(Склад) КАК Склад
ПО
    Номенклатура
```

**Choosing an aggregate for a repeating field.** If a field is the same on all detail
rows of a grouping (constant), use `МАКСИМУМ`/`МИНИМУМ`, not `СУММА`:
`МАКСИМУМ(НаименованиеНоменклатуры)`, `МАКСИМУМ(ТребуетсяКоличество)` - this is
allowed and does not produce `NULL`. `СУММА` over such a field would multiply it by the number of detail
rows (batches). `СУММА` - only for additive resources (quantity/batch cost). This rule
is also checked in the manual checklist: the "field → aggregate" table
is mandatory in `ARCHITECT.md`.

## 5. ОБЩИЕ and hierarchy

Grand total over the whole selection:

```sql
ИТОГИ СУММА(Количество) ПО ОБЩИЕ
```

Grand total, then totals by nomenclature:

```sql
ИТОГИ СУММА(Количество) ПО ОБЩИЕ, Номенклатура
```

For a hierarchical field:

- `ИЕРАРХИЯ` - totals by the field itself and all nesting levels;
- `ТОЛЬКО ИЕРАРХИЯ` - totals only by nesting levels, without a total for the
  field itself.

## 6. Several groupings

Each `ПО` level creates a separate total level. Result iteration requires
a separate nested selection per level. If there are many grouping fields and
totals are needed over their set, use `АВТОНОМЕРЗАПИСИ` (see section 8), not a
matryoshka of nested loops.

## 7. Arbitrary expressions in totals

Expressions can be computed in `ИТОГИ`. Rules:

- the expression needs an alias `КАК <поле>`; a field with that name must be in the
  select list;
- all expression fields must be present in the select list;
- arbitrary expressions (arithmetic, `ВЫБОР`, functions) are allowed in `ИТОГИ`
  provided that only grouping fields are used outside aggregates;
  the expression gets its alias from the select list;
- outside aggregate functions only fields for which totals are calculated are allowed;
- a grouping field whose totals have not been obtained yet equals `NULL` - this can be
  used to calculate an indicator only at the desired level.

Example:

```sql
ВЫБРАТЬ
    Т.Номенклатура КАК Номенклатура,
    Т.Оборот КАК Оборот,
    Т.Прибыль КАК Прибыль,
    100 * Т.Прибыль / Т.Оборот КАК ПроцентПрибыли
ИЗ
    РегистрНакопления.УчетПрибыли.Обороты КАК Т
ИТОГИ
    СУММА(Оборот) КАК Оборот,
    СУММА(Прибыль) КАК Прибыль,
    100 * СУММА(Прибыль) / СУММА(Оборот) КАК ПроцентПрибыли
ПО
    Номенклатура
```

An expression in `ИТОГИ` is built only from aggregates, so it is defined on
total rows too; `Т.Прибыль`/`Т.Оборот` in the select list are detail row values.

## 8. Totals over a set of grouping fields

If totals are needed over a combination of fields (e.g., Organization + Counterparty +
Contract), you can avoid building nested loops per field and instead get a
set identifier with the `АВТОНОМЕРЗАПИСИ` function and group by it:

```sql
ВЫБРАТЬ
    ВТ.Контрагент КАК Контрагент,
    ВТ.Договор КАК Договор,
    ВТ.Сумма КАК Сумма,
    АВТОНОМЕРЗАПИСИ(ВТ.Контрагент, ВТ.Договор) КАК ИдентификаторНабора
ИЗ
    ВТ_ИсходнаяТаблица КАК ВТ
ИТОГИ
    МАКСИМУМ(Контрагент),
    МАКСИМУМ(Договор),
    СУММА(Сумма)
ПО
    ИдентификаторНабора
```

Result iteration remains one `ПоГруппировкам` level; set attributes
are obtained via `МАКСИМУМ` and are never `NULL` on total rows.

## 9. Result iteration in BSL

```bsl
Результат = Запрос.Выполнить();
ВыборкаПоНоменклатуре = Результат.Выбрать(ОбходРезультатаЗапроса.ПоГруппировкам);
Пока ВыборкаПоНоменклатуре.Следующий() Цикл
    Детали = ВыборкаПоНоменклатуре.Выбрать(ОбходРезультатаЗапроса.Прямой);
    Пока Детали.Следующий() Цикл
        Имя = Детали.Номенклатура;
    КонецЦикла;
КонецЦикла;
```

- `ПоГруппировкам` - iteration of total groupings;
- `Прямой` - iteration of detail records (the default);
- the second `Выбрать` parameter is the grouping name; omitting it means the next
  grouping from `ИТОГИ`, an explicit empty string - details;
- with `ОБЩИЕ` the top level is the grand total; to reach the groups you need
  a nested selection from the current record.

## 10. Typical errors

- Non-aggregated field in `ИТОГИ` → `NULL` on total rows (section 4).
- `УПОРЯДОЧИТЬ ПО` after `ИТОГИ` → syntax error.
- Iterating details instead of groupings → total rows are lost or read as
  detail rows.
- `ОБЩИЕ` without a nested selection → only the grand total is visible.
- `ИТОГИ` in a DCS query → double aggregation and a performance drop; in DCS
  totals are set by composition means.
- Aggregate in `ГДЕ` → error; to filter aggregates use `ИМЕЮЩИЕ` or
  an intermediate query.

## 11. Sources

- "1C:Enterprise 8 queries. Totals" - https://chel1c.ru/querry_summary/
- "Totals over a combined set of groupings in a query" - https://infostart.ru/1c/articles/1328254/
- "Iterating a 1C query result by groupings" - https://aether-lab.ru/guides/1c-query-language/obhod-po-gruppirovkam/
- "ИТОГИ section in 1C queries: aggregates only in groupings" - https://confaster.ru/blog/itogi-zaprose-1s/
- "1C 8.3 query language for novice programmers: totals" - https://helpme1s.ru/yazyk-zaprosov-1s-8-3-dlya-nachinayushhix-programmistov-itogi
- ITS, "Using arbitrary expressions in query language totals".
