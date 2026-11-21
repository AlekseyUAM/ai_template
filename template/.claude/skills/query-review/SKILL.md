---
name: query-review
description: Checklist for code review of 1C queries - standards requirements that cannot be checked automatically (DB indexes, metadata, task semantics). Use when reviewing a query after /query-analyze.
allowed-tools:
 - Read
---

# /query-review - checklist for manual review of 1C queries

Requirements of the optimal query standards that are NOT
checked by the `query-analyze` script are moved here (knowledge of DB indexes,
metadata composition or task semantics is required). Check every item by eye.

Semantics of `ИТОГИ` (NULL on total rows, bypass, ОБЩИЕ/ИЕРАРХИЯ) -
[reference on TOTALS](../bsl-coding-standards/reference/query-totals.md).

The items are grouped by topic; each is a requirement and what to check by eye. Finding codes of the `query-analyze` skill (e.g. `select-star`, `vt-filter-in-where`) correspond to these topics.

The severity of each item is set on the single critical/important/minor scale (as in bsl_ls); the verdict rule is in the reviewer agent.

## General requirements for optimal queries

- [important] Minimize the selection volume - make sure the query selects exactly the data the task needs, without redundant fields and rows.
- [important] Minimize the number of DBMS calls - check for repeated same-type calls that can be combined into one query or batch.
- [important] Do not move everything into the DBMS - assess whether complex processing (sorting, folding, calculations) is simpler to perform on the 1C server side instead of complicating the query.
- [important] Conditional query texts - consider whether one complex universal query can be replaced with several simple ones selected by preconditions.
- [important] Efficient execution plan - for complex queries check the execution plan (query console / tech log / DBMS tools), make sure there is no optimizer timeout warning.
- [important] Nested subqueries - check whether nested queries were added solely for readability; if present, make sure they are required by the task.
- [important] Complex join and WHERE conditions - check for subqueries and ВЫБОР constructs in join clauses and WHERE; if present, assess whether they can be simplified.

## Aliases of data sources in queries

- [minor] Meaningfulness of the alias - make sure the source alias clearly describes its role in this query (e.g. "ОстаткиНаСкладах", not "Таблица1" or "РегистрНакопления").
- [minor] CamelCase formatting - each word in the alias starts with a capital letter; one-letter prepositions and pronouns too ("ТоварыНаСкладах", not "ТоварынаСкладах").
- [minor] Metadata class names as aliases - make sure the source alias does not match a metadata class name ("Справочник", "Документ", "РегистрНакопления", etc.), since this does not describe the source's role in the specific query.

## Ordering query results

- [critical] Presence of УПОРЯДОЧИТЬ ПО when order matters - if the algorithm depends on record order or the result is shown to the user, make sure УПОРЯДОЧИТЬ ПО is present; if absent - check that the code does not explicitly depend on order.
- [critical] NULL in sort fields - with УПОРЯДОЧИТЬ ПО, check: if a sort field is obtained via ЛЕВОЕ СОЕДИНЕНИЕ or can otherwise be NULL, wrap it in ЕСТЬNULL() for predictable sorting on different DBMS.
- [important] Reference types in УПОРЯДОЧИТЬ ПО - when showing results to the user, make sure sorting is by primitive-type fields; replace sorting by reference fields with sorting by their string representation.
- [important] Redundant УПОРЯДОЧИТЬ ПО - if the algorithm does not depend on order and the result is not shown to the user, УПОРЯДОЧИТЬ ПО must be absent (reduces DBMS load).
- [critical] РАЗЛИЧНЫЕ + УПОРЯДОЧИТЬ ПО - when using РАЗЛИЧНЫЕ, make sure УПОРЯДОЧИТЬ ПО uses only fields included in the ВЫБРАТЬ section (otherwise implicit inclusion of sort fields may break РАЗЛИЧНЫЕ).

## Checking for an empty query result

- [important] Emptiness check - if the goal is only to know whether rows exist, use `РезультатЗапроса.Пустой()`, not `Выбрать()` + `Следующий()`: the `Выбрать()` call is more expensive than `Пустой()`.
- [minor] No redundant Пустой() before iteration - if the result will be iterated anyway (`Выбрать()` + `Следующий()` or `Выгрузить()`), a preliminary `Пустой()` call is not needed and must be absent.

## Executing a query and getting the result (BSL code)

- [important] Justification of ВыполнитьПакет() - `ВыполнитьПакет()` is justified only when the batch has several queries **returning a result** (regular `ВЫБРАТЬ` without `ПОМЕСТИТЬ`), and each selection must be iterated separately. If only one query returns a result - a single `ВЫБРАТЬ`, or a batch via `;` where all queries except the final `ВЫБРАТЬ` are `ПОМЕСТИТЬ` into temp tables - replace with `Выполнить()` (returns the result of the last query). The key is the number of queries returning a result, not the number of `;`: `ПОМЕСТИТЬ` does not produce a result. A sign of a needless batch is accessing the result by index `...ВыполнитьПакет()[N]` when exactly one array element is actually used; filling temp tables via `ПОМЕСТИТЬ` is not by itself a reason for a batch.
- [important] Justification of Выгрузить() - `РезультатЗапроса.Выгрузить()` materializes the whole result into an in-memory `ТаблицуЗначений` (allocation, filling, column typing) - this is always noticeable overhead proportional to the selection volume. Check that unloading is really needed: if the result is only iterated once sequentially - use `Выбрать()` + `Следующий()` (streaming selection without materializing the whole table). `Выгрузить()` is appropriate when the result needs operations as on a collection: indexed search (`НайтиСтроки`, `Индексы`), multiple passes, passing the table to other code or to the client, group operations by means of `ТаблицыЗначений`. Do not unload "out of habit" for a single pass. The same applies to `.Выгрузить().Количество()` just for counting - see the "Counting records" section.
- [important] Syntax of selection from a query result - `РезультатЗапроса.Выбрать()` returns a `ВыборкаИзРезультатаЗапроса` object. When accessing its methods and properties, always verify the syntax via `1c_platform` (`getMembers`/`getMember`, see the `mcp-usage` skill), do not guess:
  - properties: `<Имя поля>` (`<Field name>`) - selection fields defined by the query;
  - methods: `Владелец` (`Owner`), `Выбрать` (`Select`), `Группировка` (`Group`), `Количество` (`Count`), `НайтиСледующий` (`FindNext`), `Получить` (`Get`), `Сбросить` (`Reset`), `Следующий` (`Next`), `СледующийПоЗначениюПоля` (`NextByFieldValue`), `ТипЗаписи` (`RecordType`), `Уровень` (`Level`).

## Use of ОБЪЕДИНИТЬ and ОБЪЕДИНИТЬ ВСЕ

- [important] Need to remove duplicates - if query-analyze flagged ОБЪЕДИНИТЬ without ВСЕ, check: are duplicates between the combined selections really to be eliminated? If not - replace with ОБЪЕДИНИТЬ ВСЕ. If yes - justify the need for deduplication in the waiver table DEVELOP.md (query-review tool).

## The ПОДОБНО operator

- [critical] Escaping special characters for user input - if the template value comes from the user (via the &Шаблон parameter), make sure special characters (%, _, [, ], ^, ~) are escaped before being passed to the query; it is recommended to use ОбщегоНазначения.СформироватьСтрокуДляПоискаВЗапросе (BSP) or an equivalent.
- [critical] The СПЕЦСИМВОЛ keyword when escaping is present - if the query uses character escaping in the template, make sure the construct is supplemented with the СПЕЦСИМВОЛ keyword specifying the chosen escape character.
- [critical] Template length no more than 1024 characters - when using dynamically calculated templates, make sure the string length does not exceed 1024 characters (MS SQL 2005 limitation).
- [important] Parameterized template with a leading wildcard - if the template is passed as a parameter (&Шаблон) and the code visibly adds "%" in front of it (e.g. «"%" + ОбщегоНазначения.СформироватьСтрокуДляПоискаВЗапросе(...)»), consciously assess the performance impact: it will be a full table scan.

## Rounding results of arithmetic operations in queries

- [critical] Order of division operands - if the order of the numerator is significantly less than the order of the denominator, swap the operands: perform multiplication before division (0.02 * 9287492 / 28346 instead of 0.02 / 28346 * 9287492) to avoid losing precision on the intermediate result.
- [critical] ВЫРАЗИТЬ on division operands - when using ВЫРАЗИТЬ on operands, check that the specified precision is minimally sufficient to represent the values (excessive overstatement reduces the precision of subsequent calculations and slows the query).
- [critical] ВЫРАЗИТЬ on the division result - if ВЫРАЗИТЬ is applied to the division result, make sure the precision is minimal but sufficient to represent the result values; take into account the limit of 31 digits in total.
- [critical] Multiplication of fractional values without ВЫРАЗИТЬ - if both factors can have a fractional part, assess the need for the ВЫРАЗИТЬ(... КАК Число(m,n)) wrapper to stabilize precision on different DBMS; query-analyze does not detect this case automatically.

## ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ

- [important] Justification of ПОЛНОЕ СОЕДИНЕНИЕ - if query-analyze flagged ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ, make sure the query cannot be rewritten via ОБЪЕДИНИТЬ ВСЕ + grouping; if there are objective reasons - record the reason in the waiver table DEVELOP.md (query-review tool).
- [important] Two or more ПОЛНЫХ СОЕДИНЕНИЯ in one query - a particularly critical case for PostgreSQL; if there is more than one ПОЛНОЕ СОЕДИНЕНИЕ in one statement, perform a load test or provide justification.

## Restrictions on using nested queries in a join condition

- [important] Alternative via a temp table - if query-analyze flagged a nested query in a join condition, make sure it is rewritten via a temp table (ПОМЕСТИТЬ): this is the standard way to avoid performance and compatibility problems.
- [critical] Semantics of the "latest slice" via ПО - if a nested subquery in a join condition was used to get the "latest slice" (МАКСИМУМ by period, date, etc. with a condition on an external field), check that the reworked query via a temp table preserves the correct filter semantics.

## Joins with nested queries and virtual tables

- [important] Join with a nested query - the "few records" exception - if query-analyze flagged a join with a subquery, make sure it does not fall under the exception ("the nested query scans few records"); if it does, record the reason in the waiver table DEVELOP.md (query-review tool); otherwise - rewrite via a temp table.
- [important] Join with a virtual table - if the query joins a virtual table (РегистрНакопления.*.Остатки, РегистрСведений.*.СрезПоследних, etc.) it is better to move the virtual table access into a separate query with results saved in a temp table.
- [important] Nested joins (implicit subqueries) - check whether the query contains the construct "ЛЕВОЕ СОЕДИНЕНИЕ А ЛЕВОЕ СОЕДИНЕНИЕ Б ПО... ПО..." (the second ПО belongs to the first СОЕДИНЕНИЕ, creating an implicit subquery); if present, replace with sequential joins or a temp table.

## Dereferencing composite-type reference fields in the query language

- [important] Dereferencing a composite field via a dot - find all occurrences of "Таблица.Поле.Реквизит" in the query; for each of them determine (from configuration metadata) whether "Поле" is a composite type. If yes - this is an implicit join with ALL tables included in the composite type, which can produce dozens of left joins. Critical with RLS.
- [important] Using ВЫРАЗИТЬ when dereferencing a composite field - if dereferencing a composite field is necessary, make sure ВЫРАЗИТЬ(Поле КАК КонкретныйТип).Реквизит is used together with КОГДА... ССЫЛКА... ТОГДА. Direct "Таблица.СоставноеПоле.Реквизит" without ВЫРАЗИТЬ is a standard violation.
- [important] Redundant types in a composite field - if metadata declares a field as a composite type with several variants, check: does the type include only actually used reference types (not "any reference", not "reference to any document")? Redundant types should be removed by editing metadata.
- [important] Denormalization as an alternative - if a composite-type field is used in the query only to get one attribute (e.g. "Регистратор.Дата"), consider moving this attribute into the source table (an additional attribute "ДатаРегистратора"): this eliminates the implicit join entirely.

## Efficient query conditions

- [important] Indexing of main condition fields - make sure fields used in WHERE, ON and virtual table conditions are indexed in the corresponding metadata table. Not checked automatically - metadata knowledge is required.
- [important] OR across different fields in a WHERE condition - if query-analyze did not flag it, check: does the condition "Поле1 = А ИЛИ Поле2 = В" across different fields lack a covering index condition? Such a pattern is not reduced to "В" and prevents using one index; it is recommended to rewrite via ОБЪЕДИНИТЬ ВСЕ.
- [important] Arithmetic over a field as the only/main condition - check for a construct like "Таблица.Поле - 1 > 0" without a preceding index condition; arithmetic over a field blocks index use. If present - move it to an additional condition or introduce a calculated indexed field.
- [important] Several roles with different RLS for one right - check the role design: assigning a user two or more roles with different RLS on one metadata object produces OR in DBMS queries even when there is no OR in the query text, making the condition non-indexed.

## Mismatch of indexes and query conditions

> Index reference (which indexes the platform creates for DB tables automatically): see [reference/indexes-db-tables.md](reference/indexes-db-tables.md).

- [important] WHERE condition covered by a suitable index - for each condition in the WHERE section, make sure the table has an index containing all condition fields at the very beginning, consecutively without "gaps".
- [important] Join ON condition covered by an index - for each condition in the ON join section, make sure there is a suitable index on the fields used.
- [important] Virtual table parameters covered by an index - for virtual tables (Остатки, СрезПоследних, etc.) make sure the parameters passed to the condition correspond to fields at the beginning of the table's main index.
- [important] No "gap" in the index - if a condition uses fields from the middle of an index but the field preceding them in the index is not set - the index is used only partially; check whether dimensions need reordering or additional indexing.
- [important] Need to create a new index - if none of the existing indexes covers the condition, consider indexing the attribute/dimension (with additional ordering for catalogs and documents); avoid creating indexes "just in case" and on low-selectivity fields.

## Additional indexes

- [important] Applicability of additional indexes - make sure the configuration is designed for CORP platform licenses; if the target audience is only PROF licenses, additional indexes cannot be used.
- [important] Performance without additional indexes - make sure the query runs at acceptable speed with additional indexes disabled on a typical volume up to 100 000-1 000 000 records; test both modes: with indexes enabled and disabled.
- [important] Result achievable without additional indexes - if acceptable performance can be achieved by regular attribute indexing (the "Index" property), use it instead of an additional index.
- [important] Included fields (non-key) - if a field is used in the query only in the ВЫБРАТЬ section, not in WHERE/ON, add it to the additional index as an included (non-indexed) field, not as a key field; this frees space for additional key fields.

## Using virtual tables instead of movement tables

- [important] Direct access to the movement table - check whether the query reads the register movement table directly (e.g. `РегистрНакопления.ТоварыНаСкладах` without a virtual table suffix). Using the movement table is highly undesirable: it contains the maximum number of records, and processing them heavily loads the system. Allowed only with justification in the waiver table DEVELOP.md (query-review tool).
- [important] Virtual tables based on totals - make sure the query uses virtual tables calculated from totals: such a query is most optimal. Correspondence between register kind and virtual tables:

| Register kind | Virtual tables |
|---|---|
| Turnover accumulation register | `Обороты` |
| Balance accumulation register | `Обороты` (no ready data - calculated from the movement table), `Остатки`, `ОстаткиИОбороты` |
| Periodic information register | `СрезПервых`, `СрезПоследних` |
| Accounting register | `ДвиженияССубконто`, `Обороты`, `ОборотыДтКт`, `Остатки`, `ОстаткиИОбороты`, `Субконто` |

## Accessing virtual tables

- [important] Simplicity of virtual table conditions - make sure conditions passed to virtual table parameters are simple constructs like "Измерение = Значение"; subqueries and implicit dot joins (Ссылка.Реквизит) in VT parameters are allowed only when all restrictions-2.2 are met (one subquery, no joins, no dot access to header attributes from a tabular section, no conditions in temp tables).
- [important] Subquery in VT parameters - if a virtual table condition uses a subquery, make sure: it has only one table, no explicit or implicit joins (including dot access from a reference), no access to header attributes from a tabular section; for a temp table - no WHERE section.
- [important] Several subqueries in VT parameters - if several conditions with subqueries are needed, choose one most selective (filtering out the maximum records); move the other conditions to the outer query or materialize them beforehand via temp tables.
- [important] Extra grouping over a VT - if the query reads `РегистрНакопления.*.Обороты`/`Остатки` and contains `СГРУППИРОВАТЬ ПО` over VT fields, check whether it is needed: the VT already aggregates by dimensions (and period). Grouping is needed only if a join/expression really multiplies rows; then group by the added field, not by the whole VT composition.

## Efficient access to the Остатки VT

- [important] Date in Остатки VT parameters - if query-analyze flagged the Остатки VT with a period, make sure: are historical balances on a specific date really needed? If the goal is current balances, remove the date (leave the first parameter empty): the platform will read only the stored current balances table without grouping.
- [important] Using the Остатки VT instead of ОстаткиИОбороты - if only balances are needed (without turnovers), make sure the query accesses "Остатки", not "ОстаткиИОбороты": ОстаткиИОбороты always reads the movement table, which is slower.
- [important] All dimensions of the Остатки VT used in the outer query - for the most efficient plan without totals splitting: check from the register metadata that all its dimensions are either present in the ВЫБРАТЬ section of the outer query or participate in join conditions; omitted dimensions force the DBMS to add grouping to the subquery.
- [important] Totals splitting mode - if an accumulation or accounting register runs in totals splitting mode, remember: even when other conditions are met (no date, all dimensions used) the platform will also read the movement table; assess whether this mode is justified given reduced write parallelism and read performance.

## Using temp tables

- [important] Data volume in a temp table - make sure the temp table does not contain hundreds of thousands of records: such a volume significantly reduces write performance and may exhaust disk space; for large data switch to batch processing in portions.
- [important] Minimum data set in a temp table - make sure only data really needed by subsequent queries is put into the temp table; extra rows and fields are extra write load and space.
- [important] Temp table not created in a loop - check the BSL code: a temp table must not be created (ПОМЕСТИТЬ) and dropped (УНИЧТОЖИТЬ) in a loop if it can be created once before the loop.
- [important] Temp table not copied just for renaming - make sure that instead of copying a temp table to another temp table only to rename it, the table name is passed as a parameter.
- [important] Indexing on JOIN - if query-analyze flagged a temp table without ИНДЕКСИРОВАТЬ ПО that participates in a join, make sure the index is really needed: for small temp tables (less than 1000 records) no index is needed; if the temp table is large - add ИНДЕКСИРОВАТЬ ПО over the join condition (ON) fields.
- [important] Indexing with В (...) - if query-analyze flagged a temp table without ИНДЕКСИРОВАТЬ ПО used in В (...), make sure: for small temp tables no index is needed; if the temp table is large - add ИНДЕКСИРОВАТЬ ПО over the fields from the subquery selection list in В (...).
- [important] Several conditions using a temp table - if a temp table is used simultaneously in several joins/В conditions and only one of them is checked often, build an index only for the most frequently checked condition.

## Counting records in queries

- [important] Record count via КОЛИЧЕСТВО, not СУММА - if query-analyze flagged СУММА(1) or ЕСТЬNULL(СУММА(1), 0), replace with КОЛИЧЕСТВО(*) or КОЛИЧЕСТВО(<Поле>): using СУММА(1) leads to overflow at >=10 million records due to the default number precision (7 digits).
- [important] ВЫРАЗИТЬ precision in conditional counting - if query-analyze flagged СУММА(ВЫБОР...ТОГДА 1...) without ВЫРАЗИТЬ, make sure the literal 1 is wrapped in ВЫРАЗИТЬ(1 КАК ЧИСЛО(17, 0)): at >=10 million conditional records overflow is inevitable without explicitly increasing precision.
- [important] Counting records in 1C code (BSL) instead of the query - check whether the code fetches all records from the DBMS (Выбрать() + Следующий() or Выгрузить() +.Количество()) only to count them; such a pattern cannot be detected in query text - it is checked only by analyzing the surrounding BSL code.

## Repeated execution of similar queries

- [important] Query not executed in a loop - check the BSL code around the query: if the call "Запрос.Выполнить()" or "МенеджерВременныхТаблиц" is inside a loop (Для каждого / Пока / Цикл), make sure this is one of the allowed exceptions - portioned processing, virtual tables with a slice date, noticeable complication of one query.
- [important] Object set - В condition instead of a series of queries - if the query filters by one object (parameter &Объект = Ссылка) and the call repeats in a loop over a list, rewrite to the condition "В (&СписокОбъектов)" and pass the whole list as one parameter.
- [important] ОБЪЕДИНИТЬ ВСЕ for different-type objects - if same-type data is queried from different tables one by one, combine the statements into one batch or via ОБЪЕДИНИТЬ ВСЕ.
- [important] BSP: functions for working with lists - when using BSP, check that instead of ЗначениеРеквизитаОбъекта / КонтактнаяИнформацияОбъекта in a loop, their "list" variants are called (ЗначениеРеквизитаОбъектов / КонтактнаяИнформацияОбъектов).
- [important] Allowed exceptions justified - if a series of queries in a loop is left intentionally, make sure the justification is in the waiver table DEVELOP.md (query-review tool; one of the exceptions of item 2: performance degradation with a VT with a slice date, portioned processing in the update handler / group posting / data load).

## Enabling totals for periodic information registers

- [important] Conditions for enabling totals - if the query accesses СрезПоследних/СрезПервых of a periodic information register without specifying a date (the first VT parameter is empty), check all four conditions from item 1 against metadata: (1) a large data volume is expected in the register; (2) queries to the slice at the current moment are executed often; (3) conditions in VT parameters are set only on dimension values and allowed separators; (4) register RLS uses only dimensions and allowed separators. If all four conditions are met - consider enabling "Allow totals: slice last/first".
- [important] Conditions for disabling totals - if queries to the slice are always (or most often) executed on a specific date (the first VT parameter is not empty) or conditions in VT parameters contain subqueries/dot access to attributes of related tables - enabling totals will not give a speedup; make sure totals are not enabled.
- [important] Alternative query variant - if totals are not applied due to an explicit date in VT parameters, consider whether the query can be split into two paths: one - without a date (uses totals), the other - with a date (regular query); the path is chosen by a preliminary check for records with a future date.
- [important] Totals recalculation not required - make sure the configuration has no separate mechanism for forced totals recalculation; the platform updates totals automatically when a record set is written. Exception: if somewhere in the code РегистрСведенийМенеджер.УстановитьИспользованиеИтогов(Ложь) is called - make sure this is justified and totals are subsequently enabled back.

## Formatting query texts

- [minor] Field aliases (КАК) - make sure all selection fields (especially attributes like "Объект.Реквизит.Вложенный") have an explicit alias via КАК, and that the keyword КАК precedes the alias.
- [important] Programmatic query assembly - assembling query text from parts by concatenation or substituting/changing pieces via `СтрЗаменить` is allowed only if `validate_query` (MCP `1c-md`) is available and everything listed below is fulfilled:
  - **the source query text (exactly as written in the source, the whole literal) passes `validate_query`** - before substitution;
  - only places where the source text remains a valid query are replaced: parameters like `&ОсобыйПараметр` or neutral substrings (`"1 = 1"`, `"2 = 2"`, etc.); in code - `СтрЗаменить(ТекстЗапроса, "&ОсобыйПараметр", "<фрагмент>")`;
  - with concatenation, **each part** is standalone query text and passes `validate_query`.
  Arbitrary placeholders (`!НАПРАВЛЕНИЕСОРТИРОВКИ!`, `%1`, `{0}`) are forbidden: text with them does not pass `validate_query` and does not open in the designer. If the direction/mode cannot be expressed by a parameter - use two static texts. Checking the variant after substitution does not replace checking the source literal. If `validate_query` is unavailable or at least one part / the source literal fails the check - this is an **important** finding (blocks acceptance).

## Queries in dynamic lists

- [important] Simplicity of the dynamic list query - assess whether the architecture can be simplified: move calculated states/aggregates into a separate information register with background calculation so the query becomes a simple read of one table.
- [important] Dynamic reading mode - make sure the appropriate mode is selected for the dynamic list: for a large data volume - "dynamic reading enabled" with the main table assigned; use the "main table not set" mode only for obviously small selections.
- [important] РАЗЛИЧНЫЕ and СГРУППИРОВАТЬ ПО - make sure the dynamic list query has no РАЗЛИЧНЫЕ and СГРУППИРОВАТЬ ПО constructs: they significantly "weigh down" the query and slow down the list.
- [important] ВЫБОР in join conditions and WHERE - make sure the ВЫБОР construct is not used in the WHERE clause or in ON join conditions: this is separately prohibited for dynamic lists.
- [important] Ordering by a calculated ВЫБОР - make sure УПОРЯДОЧИТЬ ПО does not sort by a field obtained via the ВЫБОР construct, including custom ordering; this is unacceptable for dynamic lists.
- [important] Number of joined tables - make sure the dynamic list query joins a minimal number of real tables; optimal is one table assigned as the main one; the guideline maximum is 4 tables; with a larger number consider data denormalization.
- [important] Joins with virtual tables - make sure joins with virtual tables are allowed only in strictly limited cases: СрезПоследних/СрезПервых with a knowingly small volume, Остатки VT without a date (stored totals), Остатки VT with a full set of dimensions to work without grouping.
- [important] Temp tables - if the dynamic list uses temp tables, make sure their volume is knowingly small: temp tables are not cached and are refilled on each read of a data portion.
- [critical] Main table of the dynamic list - make sure the main table is assigned in the dynamic list properties on the form: this is required for correct dynamic reading and for applying RLS restrictions.
- [important] Composite type fields - make sure that in joins, filters and ordering composite-type fields contain only reference types; when the specific type is known in advance - use ВЫРАЗИТЬ(Поле КАК КонкретныйТип).
- [important] Field indexing - check indexing of fields used for joins, conditions, quick filters, ordering and grouping; also provide indexes for fields by which the user often sorts the list.
- [important] Check under incomplete rights (RLS) - check the dynamic list speed specifically in the mode with configured data access restrictions (RLS): RLS conditions are automatically added to queries and can significantly slow the list.
- [important] Auxiliary columns via ПриПолученииДанныхНаСервере - if the dynamic list needs auxiliary columns that do not require filtering/sorting/grouping, consider moving them to the ПриПолученииДанныхНаСервере handler; all data for such columns should be selected in one query for all passed rows at once.
