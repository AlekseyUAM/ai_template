# Boundary and point in time

## Why they are needed

- **Point in time** (`МоментВремени`) - the exact point in time = `Дата` + a ref to the
  recorder. It allows unambiguous ordering of documents that fall into the same second.
  `Объект.МоментВремени()` returns the document's point in time.
- **Boundary** (`Новый Граница(Момент, ВидГраницы)`) - defines an interval boundary with an indication of
  whether the point itself is included in the interval: `ВидГраницы.Включая` / `ВидГраницы.Исключая`.

Passing a plain `Дата` instead of `МоментВремени`/`Граница` to virtual table parameters
loses ordering within a second and captures "foreign" documents with the same date - an error.

## Use in documents (posting)

- **Control of your own document's balances after writing movements** - read balances at
  `Новый Граница(МоментВремени(), ВидГраницы.Включая)` to account for the document's own movements
  (otherwise the control "does not see" the just written movements).
- **Reading balances before your own movements** (old methodology - see
  [Balance control methodology](balance-control-methodology.md); write-off by current balances) -
  at `МоментВремени()` or `Новый Граница(МоментВремени(), ВидГраницы.Исключая)` so as NOT to
  account for your own movements.
- **Real-time posting** - behavior depends on `РежимПроведенияДокумента.Оперативный`;
  during real-time posting the current real-time timestamp is relevant. Branch the control logic
  by posting mode.
- In `СрезПоследних()`/`СрезПервых()`/`Остатки()` inside posting pass the moment/boundary
  explicitly rather than leaving the parameter empty.

## Use in reports

- **Balances on a date**: "at the end of the day" - `Новый Граница(КонецДня(ДатаОтчёта), ВидГраницы.Включая)`;
  "at the start of the day" - `Новый Граница(НачалоДня(ДатаОтчёта), ВидГраницы.Исключая)`.
- In reports a boundary by `Дате` is usually enough (without a recorder ref) - ordering
  within a second is generally not required.
- **Turnovers for a period** (`Обороты(НачалоПериода, КонецПериода)`): set the period end date
  via `КонецДня(...)`, otherwise documents of the last day do not fall into the period.
- **Boundary mirroring**: the start and end boundaries of an interval interpret
  Inclusively/Exclusively differently - make sure the boundary document is neither doubled nor lost.

## Point in time as a ref field in a query

- For a field of type `ДокументСсылка.<Документ>` the virtual field
  `МоментВремени` is available in a query: `ВЫРАЗИТЬ(Остатки.Партия КАК Документ.Поступление).МоментВремени` - the point in time (date + ref) of the document/
- `МоментВремени` is not an aggregate field: do not use it in `СУММА`/`МАКСИМУМ`/`МИНИМУМ`.

## Typical errors (review signals)

- [critical] `Остатки(Документ)` / `Остатки(Док.Дата)` - a ref/date passed instead of `МоментВремени`.
- [critical] `УстановитьПараметр("МоментВремени", <Дата или ссылка>)` without `МоментВремени()`/`Граница`.
- [important] `Новый Граница(...)` without an explicit `ВидГраницы` (unclear whether the point is included).
- [critical] Control of your own document's balances with `ВидГраницы.Исключая` (own movements not accounted for).
- [critical] `СрезПоследних()`/`Остатки()` with an empty moment parameter inside posting.
- [critical] Period end date in a report without `КонецДня`.
