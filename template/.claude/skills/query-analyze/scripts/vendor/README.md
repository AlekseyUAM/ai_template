# vendor/ — автономный SDBL-парсер запросов 1С

`sdbl_parse.js` — самодостаточный бандл боевого парсера языка запросов 1С из
проекта [`query_console_vscode`](https://github.com/Nikolay-Shirokov) (модуль
`src/core/query/sdblParser.ts`, функция `parseBatch`). Протестирован на большом
корпусе запросов. Метаданные конфигурации не требуются.

## Использование

```bash
printf 'ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т' | node sdbl_parse.js
```

Читает текст запроса (в т.ч. пакет из нескольких операторов через `;`) из stdin,
печатает JSON-модель. При ошибке разбора — `{"error": "<текст>"}` (код выхода 0).

## Пересборка

```bash
QUERY_CONSOLE_REPO=/путь/к/query_console_vscode ./build-parser.sh
```

Требует `node` + `esbuild` (есть в `query_console_vscode`). Рантайм использования —
только `node` (бандл самодостаточен, `npm install` не нужен).

## Форма модели (справочник для правил)

Верхний уровень — `BatchDocument`:

```
{ "members": [ <BatchStatement>, ... ] }        // операторы пакета (разделены ;)
```

Каждый `BatchStatement` — объединение (`ОБЪЕДИНИТЬ`):

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

`QueryModel` (ключи присутствуют по мере наличия в запросе):

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

Правила навыка `query-analyze` читают эту модель через `QueryContext.model`
(см. `../rules.py`). Если `node`/бандл недоступны или разбор упал — модель равна
`None`, и правила по модели корректно пропускаются (текстовые правила работают).
