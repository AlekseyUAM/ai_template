# vendor/ - standalone SDBL parser for 1C queries

`sdbl_parse.js` is a self-contained bundle of the production 1C query language parser from the
[`query_console_vscode`](https://github.com/Nikolay-Shirokov) project (module
`src/core/query/sdblParser.ts`, function `parseBatch`). Tested on a large query
corpus. Configuration metadata is not required.

## Usage

```bash
printf 'ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т' | node sdbl_parse.js
```

Reads query text (including a batch of several statements separated by `;`) from stdin,
prints a JSON model. On parse error - `{"error": "<текст>"}` (exit code 0).

## Rebuild

```bash
QUERY_CONSOLE_REPO=/путь/к/query_console_vscode ./build-parser.sh
```

Requires `node` + `esbuild` (available in `query_console_vscode`). At runtime
only `node` is needed (the bundle is self-contained, `npm install` is not required).

## Model shape (reference for rules)

Top level is `BatchDocument`:

```
{ "members": [ <BatchStatement>, ... ] }        // операторы пакета (разделены ;)
```

Each `BatchStatement` is a union (`ОБЪЕДИНИТЬ`):

```
{ "members": [ <UnionMember>, ... ] }            // участники объединения
```

`UnionMember`:

```
{
  "name": "Запрос 1",
  "distinct": false,          // ВАЖНО: false = участник добавлен через ОБЪЕДИНИТЬ ВСЕ,
                              //        true  = через ОБЪЕДИНИТЬ (с дедупликацией).
                              //        У первого участника всегда false.
  "model": <QueryModel>
}
```

`QueryModel` (keys are present as they occur in the query):

```
{
  "tables":  [ { "id":"t0", "fullName":"Справочник.Товары", "alias":"Т",
                 "virtual": {...}? } ],           // источники данных; alias — псевдоним ИСТОЧНИКА
  "fields":  [ { "tableId":"t0", "path":"Код", "qualified":true },
               { "tableId":"", "path":"", "expression":"Т.Цена * Т.Кол", "alias":"Сумма" },
               { "tableId":"", "path":"", "expression":"*", "alias":"Поле1" } ],  // ВЫБРАТЬ * => field.expression == "*"
  "joins":   [ { "leftTableId":"t1", "rightTableId":"t0",
                 "leftAll":true, "rightAll":false,     // вид соединения:
                 ...                                   //   inner: leftAll=false, rightAll=false
                 "conditions":[ {"custom":true,"expression":"..."} ] } ],
                                                       //   left/right: один All=true
                                                       //   ПОЛНОЕ ВНЕШНЕЕ: leftAll=true И rightAll=true
  "conditions": [ { "tableId":"t0", "path":"Имя", "operator":"ПОДОБНО",
                    "param":"\"%абв\"",               // операнд ПОДОБНО: строковый литерал в кавычках,
                                                       //   либо &Параметр, либо выражение/поле, либо "a"+"b"
                    "expression":"Т.Имя ПОДОБНО \"%абв\"" } ],
  "selection": { ... },                              // ПЕРВЫЕ / РАЗЛИЧНЫЕ / РАЗРЕШЕННЫЕ
  "order":   { "fields":[ {"path":"Код","direction":"asc"} ], "auto": false },
                                                       // АВТОУПОРЯДОЧИВАНИЕ => order.auto == true
  "queryType": "createTemp",                          // select | createTemp | appendTemp | dropTemp (ПОМЕСТИТЬ/УНИЧТОЖИТЬ)
  "tempTableName": "ВТ_Товары",
  "totals": { ... }                                   // ИТОГИ
}
```

Virtual table parameters are stored in `virtual` (`period`, `condition`,
`startPeriod`, …). Arguments passed beyond the VT signature (a platform error -
the query does not compile) are collected in `virtual.extraArgs`; they are flagged by the
`vt-too-many-params` rule.

The rules of the `query-analyze` skill read this model via `QueryContext.model`
(see `../rules.py`). If `node`/the bundle are unavailable or parsing fails, the model is
`None`, and model-based rules are correctly skipped (text rules still work).
