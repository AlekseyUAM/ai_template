# Movement deletion

The document movement deletion mode is set by the "Movement deletion" property (in the XML dump -
`<RegisterRecordsDeletion>`). The property value for a document is in `code_index`. The mode affects
the posting implementation, when old movements are deleted, and lock duration.

## 3 kinds of movement deletion

### 1. Delete automatically (`AutoDelete`)

The platform deletes old movements **at the start** of the posting transaction (and on re-posting),
even before `ОбработкаПроведения`.

- Implementation: no need to clear movements manually; `Движения.<Регистр>.Очистить()` is redundant.
- Locks: deletion at the start of the transaction → movement tables are locked early and for the whole
  transaction. The "heaviest" mode; with mass re-posting in a loop the effect is
  multiplicative (N early exclusive locks).

### 2. Delete automatically on unpost (`AutoDeleteOnUnpost`) - recommended

On **unposting** the platform deletes movements itself. On **posting**
there is no automatic deletion - old movements are overwritten by new records when writing the set with substitution.

- Implementation: old movements are overwritten by new ones when writing the set with substitution. To
  overwrite on re-posting you **do not need** to call `Движения.Записать()` explicitly - it is enough
  to set `Движения.<Регистр>.Записывать = Истина;`, and posting will write all sets
  with `Записывать = Истина` itself (old movements will be overwritten by new ones). Explicit clearing + writing is needed
  only in special cases - e.g., **when moving the document date forward**, then you need:
    - set `Движения.<Регистр>.Записывать = Истина;` if not already set
    - execute `Движения.Записать()`
  Since movements have not been added yet, an empty set will be written, i.e., movements are cleared.
  This is needed so that the deletion is visible to a subsequent query in the same transaction.
  - Clearing the document's old movements **when moving the document date back** is not required, since
  they do not affect a subsequent query and will be overwritten during document posting.

### 3. Do not delete automatically (`DontAutoDelete`)

The platform does not delete movements either on posting or on unposting - everything is up to the developer.

- Implementation: needed when movements are formed not only by posting (manual adjustment,
  partial set update, movements of several documents in one set).
- Locks: fully determined by the code logic.

## Why they are needed, differences

- **By implementation**: with `AutoDelete` manual clearing/writing is not required. With
  `AutoDeleteOnUnpost` it is enough to set `Движения.<Регистр>.Записывать = Истина` -
  posting will write the sets itself, old movements will be overwritten by new ones; an explicit
  `Движения.Записать()` is needed only to remove old movements from the query's view inside
  posting (e.g., when moving the date forward: `Очистить()` + `Записать()`). With
  `DontAutoDelete` deletion and writing of movements are entirely up to the developer.
- **By locks**: `AutoDelete` deletes (and locks) movements at the start of the transaction →
  locks are held longer; `AutoDeleteOnUnpost` - closer to the end → shorter. To reduce
  lock time `AutoDeleteOnUnpost` is preferred.
- **The "Write" flag peculiarity**: `Движения.Записать()` (without a register name) writes
  all modified sets and **resets** the `Записывать` flag; `Движения.<Регистр>.Записать()`
  writes one set and does **not reset** the flag.
- **Unposting with manual adjustment**: for documents where movements are edited
  manually, on unposting disable movement activity instead of deleting records
  (see the "Movement activity" section in `bsl-coding-standards`).

## Typical errors (review signals)

- [minor] `Движения.<Регистр>.Очистить()` in `ОбработкаПроведения` with `AutoDelete` mode (redundant).
- [critical] Movements are written, but `Движения.<Регистр>.Записывать = Истина` is not set → on re-posting
  old movements are not overwritten.
- [important] `AutoDelete` on a document with heavy posting / mass re-posting (long locks).
- [important] Re-posting documents in a loop (multiplicative locks).

The order of register writing and locks - see [Balance control methodology](balance-control-methodology.md)
and [Locks](locks.md).
