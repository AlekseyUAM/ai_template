# Balance control methodology

Balance control during document posting is implemented by one of two methodologies.
The choice of methodology determines the order of actions in `ОбработкаПроведения` and the lock scheme.
Register composition, their dimensions/resources and the totals split mode are in `code_index`.

## Old methodology (longer lock)

Order:
1. Set a managed lock (`БлокировкаДанных`) on the read data -
   **exclusive** if these data will be modified later.
2. Read the current balances by a query.
3. Check balance sufficiency.
4. Form and write movements.

The lock is held from reading until the end of the transaction → the lock interval is long.

**When it applies:** when register data is needed to form the movements themselves -
movement values depend on the current state of balances. The classic case is
batch accounting/cost write-off: you need to read batch balances to
calculate the write-off amount. See [Locks](locks.md).

## New methodology (shorter lock)

Order:
1. Form movements (without reading balances beforehand).
2. For controlled sets: `Движения.<Регистр>.БлокироватьДляИзменения = Истина`.
3. Write movements (`Движения.Записать()`).
4. Find **negative** balances by a query at your document's boundary
   (`Новый Граница(МоментВремени(), ВидГраницы.Включая)`).
5. If there are negative balances - `Отказ = Истина` with a message to the user.

`БлокироватьДляИзменения = Истина` disables the totals splitter (splitter column) for
the written dimension set from the moment of writing until the end of the transaction - this is not
a read with a lock but protection of totals. The "lock" interval is short → higher concurrency.

**When it applies:** when all data for forming movements is in the document itself
(movements do not depend on current balances), and control is needed only for non-negativity.

## Differences in locking

| | Old methodology | New methodology |
|---|---|---|
| Explicit lock | `БлокировкаДанных` **before** reading balances | `БлокироватьДляИзменения = Истина` on write |
| Balance reading | before writing own movements | after writing own movements (at the boundary) |
| Duration | the whole transaction | from write to the end of the transaction |
| Concurrency | lower | higher |

## Order with several registers

- First write registers that do NOT require balance control (`БлокироватьДляИзменения = Ложь`),
  in a stable order.
- At the end - registers with control (`БлокироватьДляИзменения = Истина`) and the negative
  balance control query. Balance control - as close to the transaction end as possible.
- Totals split does not speed up a scenario with balance control (there is no effect with control).

## Typical errors (review signals)

- [critical] **Old methodology:** reading balances without a preceding managed lock.
- [critical] **New methodology:** `БлокироватьДляИзменения` is set **after** `Записать()` (does not take effect).
- [critical] **New methodology:** control of negative balances of your own document without a correct boundary
  (own movements not accounted for) - see [Boundary and point in time](boundary-and-moment.md).
- [important] **Both methodologies:** balance query/`Выполнить()` in a loop instead of one query over the list.
