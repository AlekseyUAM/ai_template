# Locks

Register composition, their dimensions and the configuration's data lock control mode are
in `code_index`.

## Object and transaction locks

**Object** locks protect an application object (catalog item, document) from
simultaneous modification in different sessions; they are not directly tied to a DBMS
transaction. There are two kinds:

- **Optimistic** - the platform automatically controls the object version: on write
  it checks whether the object version has changed since it was read into memory; if the object
  was already modified by another session, the write is rejected with an error ("Object version … is out of date").
  It requires no explicit call and triggers itself when writing a previously read object.
- **Pessimistic** - an explicit lock `Заблокировать()` /
  `ЗаблокироватьДанныеДляРедактирования` on an object or ref: forbids other sessions
  to start editing these data (set when opening the object for editing in a form,
  before modifying from code). Not needed during exchange load and in exclusive operations
  (IB update).

**Transaction** locks are DBMS locks within a transaction. They can be automatic
(set by the platform according to the isolation level) and managed (`БлокировкаДанных`, set by the developer).

## Managed and automatic

- **Automatic mode** - the platform sets locks itself via a high DBMS isolation
  level (Repeatable Read / Serializable). Many redundant locks, higher risk of
  escalation and deadlocks.
- **Managed mode** (recommended) - Read Committed isolation level, the developer sets
  locks explicitly via `БлокировкаДанных`. Fewer locks, higher concurrency.
  In managed mode the `ДЛЯ ИЗМЕНЕНИЯ` construct in query text is **meaningless** - do not
  use it; use `БлокировкаДанных` for locking.

The mode is set by the configuration property "Data lock control mode" (and can be
overridden per object). Check via `code_index`.

## Exclusive and shared

- **Shared** (`РежимБлокировкиДанных.Разделяемый`) - set so that data is not
  modified by other transactions. Other transactions can still read the data
  (and set their own shared locks) but cannot modify it.
- **Exclusive** (`РежимБлокировкиДанных.Исключительный`) - besides prohibiting modification,
  it prohibits even reading these data by other transactions that set
  managed locks.
- Rule: when reading **followed by modification**, set an **exclusive** lock
  **before** reading (otherwise escalating a shared lock to exclusive causes a deadlock).
  When reading **without modification** (e.g., to form movements) - shared on the
  read data, exclusive on the modified data.

## Example of correct use

```bsl
Блокировка = Новый БлокировкаДанных;

ЭлементБлокировки = Блокировка.Добавить("РегистрНакопления.ПартииНоменклатуры");
ЭлементБлокировки.Режим = РежимБлокировкиДанных.Исключительный;
ЭлементБлокировки.ИсточникДанных = ИсточникНоменклатуры; // ТЧ документа или выгрузка запроса
ЭлементБлокировки.ИспользоватьИзИсточникаДанных("Номенклатура", "Номенклатура");

Блокировка.Заблокировать(); // обязательно внутри транзакции
```

What matters here:

- `ИсточникДанных` is a table (document tabular section, query result upload)
  whose rows are used to build lock conditions. This locks only the dimension
  combinations actually processed, not the whole register.
- `ИспользоватьИзИсточникаДанных("ИзмерениеБлокировки", "КолонкаИсточника")` maps
  the dimension of the locked register to a data source column.
- `.Заблокировать()` has an effect **only inside a transaction**; a call outside a transaction is
  a silent no-op (data is not protected).

An alternative to a data source is to set dimension values element by element:
`ЭлементБлокировки.УстановитьЗначение("Номенклатура", Номенклатура);`

Signatures:

- `БлокировкаДанных.Добавить(<ПолноеИмяТаблицы>)` - returns a lock element;
  the name of the locked register is specified here, in `Добавить`.
- `ЭлементБлокировкиДанных.Режим` - defaults to
  `РежимБлокировкиДанных.Исключительный`; the property is set explicitly for a shared
  lock.
- `БлокировкаДанных.Заблокировать()` - no parameters.

Example for a document with the tabular section `СписокНоменклатуры` and the register `Товары`:

```bsl
Блокировка = Новый БлокировкаДанных;
ЭлементБлокировки = Блокировка.Добавить("РегистрНакопления.Товары");
ЭлементБлокировки.ИсточникДанных = СписокНоменклатуры;
ЭлементБлокировки.ИспользоватьИзИсточникаДанных("Номенклатура", "Номенклатура");
ЭлементБлокировки.УстановитьЗначение("Организация", Организация);
Блокировка.Заблокировать();
```

## Using the Диапазон object

To lock an interval of dimension values (rather than a single value), pass the
`Диапазон` object to `УстановитьЗначение`:

```bsl
ЭлементБлокировки.УстановитьЗначение("Период", Новый Диапазон(ДатаНачала, ДатаОкончания));
```

A range of dimension values is locked - useful for periodic information registers and
locks by a date/moment interval. See [Boundary and point in time](boundary-and-moment.md).

The choice of balance control methodology and the order of actions - see
[Balance control methodology](balance-control-methodology.md).
