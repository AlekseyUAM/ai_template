---
name: coding-errors
description: Typical 1C coding errors - signatures and collections, metadata names, query checks, validate_query failures, date literals.
---

# Typical coding errors (mandatory)

Common to all BSL code of the task - both the implementation (`develop`) and the tests
(`tests`). Stage-specific rules are in the stage checklists.

1. **Check signatures** before use: `1c_platform` (rule `mcp-usage`), especially when
   working with collections - `Массив`, `Структура`, `Соответствие`, `ТаблицаЗначений`,
   `СписокЗначений`, `ДеревоЗначений`: their method sets differ, do not transfer methods
   from one collection to another (for example, `Массив` has no `Соединить` - use
   `СтрСоединить(Массив, Разделитель)`).
2. **Clarify metadata names via `code_index`, do not guess**: full names of
   catalogs, documents, registers, attributes and their types check against the configuration
   code index. A guessed name does not exist in the infobase - the code fails at runtime.
3. **Check every written/changed query text with `query-analyze`.** Run **both** scripts
   (`extract_queries.py` + `analyze_query.py`) and `validate_query` on the literal
   exactly as it is written in the source. Exit code `2` from `extract_queries.py` means
   the query was not extracted - not a clean result. Stubs `!...!`, `%1`, `{0}` in the
   query text are forbidden; substitution - only into valid places (`&ОсобыйПараметр`,
   `1 = 1`). Record the result in the stage report (`TESTS.md`/`DEVELOP.md`).
4. **`validate_query`: tool failure vs query defect.** `valid: false` - the query text is
   defective: fix the text, do not retry the tool unchanged. If the response has no verdict
   (transport/HTTP/server error, for example `Тип не определен ...`), make at most one
   retry, then record the tool failure in the stage report and continue - do not loop.
5. **`bsl_ls` and dates.** `bsl_ls` does not parse date literals `#...#` (ParseError);
   use `Дата(Год, Месяц, День)` or `Дата(Год, Месяц, День, Час, Мин, Сек)`.
   Do not waste time on a diagnostic probe of this limitation.
