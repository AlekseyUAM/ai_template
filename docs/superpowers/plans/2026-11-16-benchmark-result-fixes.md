# Доработки template по итогам benchmark — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать утверждённую спеку `docs/superpowers/specs/2026-11-16-benchmark-result-fixes-design.md`: справочник ИТОГИ, политика комментариев, waiver-таблица, ужесточение `query-analyze`/`code-analyze`/`task_status`/`bsl_ls`, чистые метрики benchmark без токенов и стоимости, запрет опасного `pkill`.

**Architecture:** Изменения точечные, по слоям: документация и промпты шаблона (`template/.claude`), Python-скрипты анализаторов и `task_status`, MCP-сервер `bsl_ls` (`app/docker/mcp`), benchmark-метрики. Каждая задача самодостаточна, покрыта тестами и коммитится локально в `main`.

**Tech Stack:** Python 3.11+ (репозиторий использует `.venv`), pytest, FastMCP (`mcp>=1.2,<2`), markdown-документация 1С/BSL.

## Global Constraints

- Все коммиты — локально в текущую ветку `main`, без `git push`.
- Не добавлять новых зависимостей.
- Русский язык документации; BSL-примеры без не-ASCII тире (`—`, `–`) и без комментариев в теле методов.
- Не менять описания benchmark-задач (`benchmark/tasks/**`) и не увеличивать их длину.
- Существующие комментарии в BSL-коде не удалять.
- `task_status.py` остаётся самодостаточным скриптом без импорта `agentmon`.
- Тесты запускать из корня репозитория, если не указано иное.
- После каждой задачи — `git status --short` и локальный коммит.

---

## Task 1: Справочник по ИТОГИ и ссылки для обнаруживаемости

**Files:**
- Create: `template/.claude/skills/bsl-coding-standards/reference/query-totals.md`
- Modify: `template/.claude/skills/bsl-coding-standards/SKILL.md`
- Modify: `template/.claude/agents/developer.md`
- Modify: `template/.claude/skills/query-review/SKILL.md`
- Modify: `template/.claude/skills/query-analyze/SKILL.md`
- Modify: `template/.claude/skills/bsl-coding-standards/reference/accumulation-registers.md`

**Interfaces:**
- Produces: файл `reference/query-totals.md`, на который ссылаются остальные задачи и который упоминает `totals-field-not-aggregated`.

- [ ] **Step 1: Создать справочник**

Создать `template/.claude/skills/bsl-coding-standards/reference/query-totals.md` ровно с содержимым:

~~~markdown
# Итоги в запросах 1С (секция ИТОГИ)

Предметная справка: семантика `ИТОГИ`, агрегаты, `NULL` в итоговых строках,
обход результата. Автоматически неагрегированные поля ловит правило
`totals-field-not-aggregated` навыка `query-analyze` (severity `error`).
Ручные проверки запросов — навык `query-review`.

## 1. Что делает ИТОГИ

`ИТОГИ` **добавляет** к результату итоговые строки. Детальные строки остаются
на месте. `СГРУППИРОВАТЬ ПО`, наоборот, сворачивает детальные строки в группы.

| Конструкция | Что делает | Детальные строки |
|---|---|---|
| `СГРУППИРОВАТЬ ПО` | сворачивает выборку в группы | исчезают |
| `ИТОГИ ... ПО` | добавляет итоговые строки к выборке | сохраняются |

`ИТОГИ` можно совмещать с `СГРУППИРОВАТЬ ПО`: первое управляет детальными
строками, второе добавляет итоговые уровни. Если нужны только свёрнутые группы,
`ИТОГИ` не нужны.

## 2. Синтаксис

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

- `ПО` обязательна.
- `ОБЩИЕ` добавляет корневую итоговую запись по всей выборке.
- Порядок группировок в `ПО` задаёт порядок уровней итогов.
- `УПОРЯДОЧИТЬ ПО` ставится **до** `ИТОГИ`; после `ИТОГИ` — синтаксическая ошибка.

## 3. Агрегатные функции

| Функция | Результат |
|---|---|
| `СУММА` | сумма значений |
| `КОЛИЧЕСТВО` | количество значений; `NULL` не учитывается |
| `КОЛИЧЕСТВО РАЗЛИЧНЫЕ` | количество различных значений; `NULL` не учитывается |
| `МАКСИМУМ` | максимальное значение |
| `МИНИМУМ` | минимальное значение |
| `СРЕДНЕЕ` | среднее значение |

## 4. Главное правило: NULL в итоговых строках

В строке итогов доступны только:

- поля, входящие в группировку `ИТОГИ` (перечисленные в `ПО`);
- агрегаты, описанные в `ИТОГИ`.

Все остальные поля в итоговой строке возвращаются как `NULL`. После обхода
результата и преобразования типов это даёт `Неопределено` и runtime-ошибки вида
«Преобразование значения к типу Булево не может быть выполнено».

Неправильно:

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

На строках итогов `Склад` будет `NULL`.

Правильно — агрегировать поле или убрать его из выборки:

```sql
ИТОГИ
    СУММА(Количество) КАК Количество,
    МАКСИМУМ(Склад) КАК Склад
ПО
    Номенклатура
```

## 5. ОБЩИЕ и иерархия

Общий итог по всей выборке:

```sql
ИТОГИ СУММА(Количество) ПО ОБЩИЕ
```

Общий итог, затем итоги по номенклатуре:

```sql
ИТОГИ СУММА(Количество) ПО ОБЩИЕ, Номенклатура
```

Для иерархического поля:

- `ИЕРАРХИЯ` — итоги по самому полю и по всем уровням вложенности;
- `ТОЛЬКО ИЕРАРХИЯ` — итоги только по уровням вложенности, без итога по самому
  полю.

## 6. Несколько группировок

Каждый уровень `ПО` создаёт отдельный уровень итогов. Обход результата требует
отдельной вложенной выборки на каждый уровень. Если группировочных полей много и
нужны итоги по их набору, используйте `АВТОНОМЕРЗАПИСИ` (см. раздел 8), а не
матрешку из вложенных циклов.

## 7. Произвольные выражения в итогах

В `ИТОГИ` можно вычислять выражения. Правила:

- выражению нужен псевдоним `КАК <поле>`; поле с таким именем должно быть в
  списке выборки;
- все поля выражения должны присутствовать в списке выборки;
- вне агрегатных функций допустимы только поля, по которым считаются итоги;
- поле группировки, итоги по которому ещё не получены, равно `NULL` — это можно
  использовать для расчёта показателя только на нужном уровне.

Пример:

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

## 8. Итоги по набору группировочных полей

Если итоги нужны по совокупности полей (например, Организация + Контрагент +
Договор), можно не строить вложенные циклы по каждому полю, а получить
идентификатор набора функцией `АВТОНОМЕРЗАПИСИ` и группировать по нему:

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

Обход результата остаётся одним уровнем `ПоГруппировкам`; реквизиты набора
получаются через `МАКСИМУМ` и не бывают `NULL` на строках итогов.

## 9. Обход результата в BSL

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

- `ПоГруппировкам` — обход итоговых группировок;
- `Прямой` — обход детальных записей (значение по умолчанию);
- второй параметр `Выбрать` — имя группировки; пропуск означает следующую
  группировку из `ИТОГИ`, явная пустая строка — детали;
- при `ОБЩИЕ` верхний уровень — общий итог; чтобы дойти до групп, нужна
  вложенная выборка от текущей записи.

## 10. Типичные ошибки

- Неагрегированное поле в `ИТОГИ` → `NULL` на итоговых строках (раздел 4).
- `УПОРЯДОЧИТЬ ПО` после `ИТОГИ` → синтаксическая ошибка.
- Обход деталей вместо группировок → итоговые строки теряются или читаются как
  детальные.
- `ОБЩИЕ` без вложенной выборки → виден только общий итог.
- `ИТОГИ` в запросе СКД → двойная агрегация и падение производительности; в СКД
  итоги задаются средствами компоновки.
- Агрегат в `ГДЕ` → ошибка; для фильтрации агрегатов используйте `ИМЕЮЩИЕ` или
  промежуточный запрос.

## 11. Источники

- «Запросы 1С:Предприятие 8. Итоги» — https://chel1c.ru/querry_summary/
- «Итоги по объединенной совокупности группировок в запросе» — https://infostart.ru/1c/articles/1328254/
- «Обход результата запроса по группировкам 1С» — https://aether-lab.ru/guides/1c-query-language/obhod-po-gruppirovkam/
- «Секция ИТОГИ в запросах 1С: агрегаты только в группировках» — https://confaster.ru/blog/itogi-zaprose-1s/
- «Язык запросов 1С 8.3 для начинающих программистов: итоги» — https://helpme1s.ru/yazyk-zaprosov-1s-8-3-dlya-nachinayushhix-programmistov-itogi
- ИТС, «Использование произвольных выражений в итогах языка запроса».
~~~

- [ ] **Step 2: Добавить ссылки в `bsl-coding-standards/SKILL.md`**

В YAML `description` добавить слово `ИТОГИ` (например, после «запросы, СКД»).
В конце раздела «Регистры накопления и виртуальные таблицы» (перед «Регистры
сведений») добавить:

```markdown
## Итоги в запросах (ИТОГИ)

> Полная справка (синтаксис, агрегаты, NULL в итоговых строках, ОБЩИЕ/ИЕРАРХИЯ,
> произвольные выражения, обход результата) —
> [Итоги в запросах](reference/query-totals.md). Прочитай перед проектированием
> запроса с `ИТОГИ` и при разборе runtime-ошибок на итоговых строках.

- [критичная] **Неагрегированные поля в ИТОГИ** — поле, не входящее в группировку
  `ИТОГИ` и не обёрнутое в агрегат, на строках итогов равно `NULL`. Это ловит
  `query-analyze` (`totals-field-not-aggregated`, error), но проверяй и глазами:
  каждое «голое» поле списка выбора должно быть либо в `ПО`, либо в агрегате.
```

- [ ] **Step 3: Добавить ссылку в `developer.md`**

В пункте 2 «Порядок действий», в блоке «Запросы», после фразы про `query-review`
добавить:

```markdown
   Если запрос использует `ИТОГИ`, перед проектированием прочитай
   [справку по ИТОГИ](../skills/bsl-coding-standards/reference/query-totals.md):
   неагрегированные поля на строках итогов возвращаются как `NULL`.
```

- [ ] **Step 4: Добавить ссылки в `query-review` и `query-analyze`**

В `template/.claude/skills/query-review/SKILL.md` в первом абзаце после
«Проверяй каждый пункт глазами.» добавить:

```markdown
Семантика `ИТОГИ` (NULL на итоговых строках, обход, ОБЩИЕ/ИЕРАРХИЯ) —
[справка по ИТОГИ](../bsl-coding-standards/reference/query-totals.md).
```

В `template/.claude/skills/query-analyze/SKILL.md` у пункта
`totals-field-not-aggregated` добавить после описания:

```markdown
  Подробнее о семантике итогов и способах исправления —
  [справка по ИТОГИ](../bsl-coding-standards/reference/query-totals.md).
```

- [ ] **Step 5: Добавить «см. также» в `accumulation-registers.md`**

В конец файла добавить:

```markdown
## См. также

- [Итоги в запросах](query-totals.md) — `ИТОГИ`, агрегаты и `NULL` на итоговых
  строках.
```

- [ ] **Step 6: Проверить ссылки**

Run:
```bash
python - <<'PY'
from pathlib import Path
root = Path('template/.claude/skills/bsl-coding-standards')
for rel in ['reference/query-totals.md']:
    assert (root / rel).is_file(), rel
texts = [
    Path('template/.claude/skills/bsl-coding-standards/SKILL.md'),
    Path('template/.claude/agents/developer.md'),
    Path('template/.claude/skills/query-review/SKILL.md'),
    Path('template/.claude/skills/query-analyze/SKILL.md'),
    Path('template/.claude/skills/bsl-coding-standards/reference/accumulation-registers.md'),
]
for p in texts:
    t = p.read_text(encoding='utf-8')
    assert 'query-totals.md' in t, p
print('ok')
PY
```
Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add template/.claude/skills/bsl-coding-standards/reference/query-totals.md \
        template/.claude/skills/bsl-coding-standards/SKILL.md \
        template/.claude/agents/developer.md \
        template/.claude/skills/query-review/SKILL.md \
        template/.claude/skills/query-analyze/SKILL.md \
        template/.claude/skills/bsl-coding-standards/reference/accumulation-registers.md
git commit -m "docs(template): справочник по ИТОГИ и ссылки на него"
```

---

## Task 2: Политика комментариев, waiver-таблица и чистка `query-review`

**Files:**
- Modify: `template/.claude/agents/developer.md`
- Modify: `template/.claude/skills/bsl-coding-standards/SKILL.md`
- Modify: `template/.claude/skills/query-review/SKILL.md`
- Modify: `template/.claude/agents/reviewer.md`
- Modify: `template/.claude/skills/task-orchestration/SKILL.md`

**Interfaces:**
- Produces: правила «комментарии только в заголовках» и формат waiver-таблицы `DEVELOP.md`, на который ссылаются `query-review` и `reviewer`.

- [ ] **Step 1: Добавить разделы в `developer.md`**

Между концом «Порядок действий» (пункт 4) и заголовком `## Разбор возврата на
доработку` вставить:

```markdown
## Комментарии в BSL

В теле `Процедура`/`Функция`, между операторами и **внутри текста запроса**
комментарии не пишем. Допустимы только:

- заголовок модуля (краткое назначение);
- описание метода перед объявлением (`// Описание`, `// Параметры`,
  `// Возвращаемое значение`, `// Пример`).

Существующие комментарии не удаляй. Исключение — обязательные маркеры
`mark_changes` (см. раздел ниже). Если нужно объяснить неочевидное решение или
отклонённое замечание анализатора — пиши в `DEVELOP.md`, а не в код.

## Отклонённые замечания анализаторов (waiver)

Каждый `error`/`warning` любого анализатора (`bsl_ls`, `code-analyze`,
`query-analyze`) либо исправляется, либо попадает в таблицу `DEVELOP.md`:

```markdown
| Инструмент | Код | Файл:строка | Решение | Ссылка на ТЗ/дизайн |
|---|---|---|---|---|
| query-analyze | vt-filter-in-where | src/cf/.../Module.bsl:125 | фильтр по индексу обязателен по условиям задачи | TASK.md, п. «Остатки» |
```

«Решение» объясняет, почему замечание не исправляется; «Ссылка» указывает на
конкретную строку `TASK.md`/`ANALYZE.md`/`ARCHITECT.md` или справки, которая
доказывает, что нарушения нет. Общая фраза «шум анализатора» waiver'ом не
является. Если отклонённых замечаний нет — явно напиши
`Отклонённых замечаний нет.`
```

- [ ] **Step 2: Усилить правило в `bsl-coding-standards/SKILL.md`**

Заменить пункт:

```markdown
- [минорная] **Без бесполезных комментариев** — не писать описания, не добавляющие информации
  (например «Процедура-обработчик события …» к очевидному обработчику).
```

на:

```markdown
- [важная] **Только в заголовках** — комментарии в BSL допустимы только в заголовке
  модуля и в описании метода перед объявлением. В теле `Процедура`/`Функция`,
  между операторами и внутри текста запроса комментарии не пишем. Существующие
  комментарии не удаляем.
- [минорная] **Без бесполезных комментариев** — не пересказывать код и не писать
  описания, не добавляющие информации (например «Процедура-обработчик события …»
  к очевидному обработчику).
```

- [ ] **Step 3: Убрать требования писать комментарии из `query-review`**

В `template/.claude/skills/query-review/SKILL.md` выполнить замены:

1. В пункте про дедупликацию заменить
   `Если да — убедиться в наличии комментария, объясняющего необходимость дедупликации.`
   на
   `Если да — обосновать необходимость дедупликации в waiver-таблице DEVELOP.md (инструмент query-review).`
2. В пункте про ПОЛНОЕ СОЕДИНЕНИЕ заменить
   `при наличии объективных причин — добавить комментарий с обоснованием.`
   на
   `при наличии объективных причин — зафиксировать причину в waiver-таблице DEVELOP.md (инструмент query-review).`
3. В пункте про соединение с вложенным запросом заменить
   `если попадает, добавить комментарий с обоснованием; иначе — переписать через временную таблицу.`
   на
   `если попадает, зафиксировать причину в waiver-таблице DEVELOP.md (инструмент query-review); иначе — переписать через временную таблицу.`
4. В пункте про прямое чтение таблицы движений заменить
   `Допустимо только при наличии комментария с обоснованием.`
   на
   `Допустимо только при обосновании в waiver-таблице DEVELOP.md (инструмент query-review).`
5. В пункте про запросы в цикле заменить
   `убедиться, что в коде присутствует комментарий с обоснованием (одно из исключений п.2:`
   на
   `убедиться, что обоснование есть в waiver-таблице DEVELOP.md (инструмент query-review; одно из исключений п.2:`
6. Удалить два пункта в конце раздела про запросы:

```markdown
- [минорная] Комментарии к сложным запросам — в запросах с вложенными подзапросами, объединениями или несколькими соединениями должны быть комментарии, объясняющие назначение каждой таблицы или секции.
- [минорная] Комментарий к объекту Запрос — при создании объекта Запрос в коде рядом должен быть комментарий с описанием цели запроса.
```

- [ ] **Step 4: Проверка waiver в `reviewer.md`**

В конце Шага 3 (перед разделом «Куда и как записать вердикт») добавить:

```markdown
**Проверка waiver-таблицы.** Прочитай таблицу «Отклонённые замечания
анализаторов» в `DEVELOP.md`. Для каждой строки проверь, что «Ссылка на
ТЗ/дизайн» указывает на конкретное место и действительно снимает находку.
Waiver без такой ссылки или со ссылкой «шум анализатора» недействителен:
находка возвращается в вердикт с исходной severity.
```

- [ ] **Step 5: Передача waiver в `task-orchestration/SKILL.md`**

В разделе «Продолжение субагента (SendMessage)», в шаблоне re-brief после
`Вердикт: <вердикт>.` добавить фразу:

```markdown
> Если в `DEVELOP.md` есть waiver-таблица — передай её ревьюеру вместе с
> вердиктом.
```

- [ ] **Step 6: Проверить, что требований о комментариях в коде не осталось**

Run:
```bash
grep -n "комментари" template/.claude/skills/query-review/SKILL.md
```
Expected: остались только упоминания waiver-таблицы и общие слова; строк с
«добавить комментарий», «должен быть комментарий», «наличии комментария» нет.
Дополнительно:
```bash
grep -n "Только в заголовках" template/.claude/skills/bsl-coding-standards/SKILL.md
grep -n "waiver" template/.claude/agents/developer.md template/.claude/agents/reviewer.md
```
Expected: совпадения есть.

- [ ] **Step 7: Commit**

```bash
git add template/.claude/agents/developer.md \
        template/.claude/skills/bsl-coding-standards/SKILL.md \
        template/.claude/skills/query-review/SKILL.md \
        template/.claude/agents/reviewer.md \
        template/.claude/skills/task-orchestration/SKILL.md
git commit -m "docs(template): комментарии только в заголовках, waiver-таблица"
```

---

## Task 3: query-analyze — severity error и исправление extractor

**Files:**
- Modify: `template/.claude/skills/query-analyze/scripts/rules.py`
- Modify: `template/.claude/skills/query-analyze/scripts/extract_queries.py`
- Modify: `template/.claude/skills/query-analyze/SKILL.md`
- Test: `template/.claude/skills/query-analyze/scripts/tests/test_rules.py`
- Test: `template/.claude/skills/query-analyze/scripts/tests/test_extract.py`

**Interfaces:**
- Consumes: `extract_queries.extract_query_strings` возвращает `ExtractedQuery.text` без ведущих `//`-строк.
- Produces: `extract_queries` CLI возвращает `2` при `Запрос.Текст`/`Новый Запрос` без извлечённых запросов; `totals-field-not-aggregated` имеет severity `error`.

- [ ] **Step 1: Написать падающие тесты для extractor**

Добавить в `template/.claude/skills/query-analyze/scripts/tests/test_extract.py`:

```python
from extract_queries import main


def test_leading_comment_lines_stripped():
    src = '\tЗапрос.Текст = "// Комментарий\n// Ещё\nВЫБРАТЬ 1";'
    res = extract_query_strings(src)
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ 1"


def test_leading_comment_lines_with_pipes_stripped():
    src = '\tЗапрос.Текст = "// Комментарий\n|\t// Ещё\n|\tВЫБРАТЬ 1";'
    res = extract_query_strings(src)
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ 1"


def test_main_warns_when_query_text_without_literal(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_text(
        'Процедура Тест()\n'
        '\tЗапрос.Текст = СтрШаблон("%1", "не запрос");\n'
        'КонецПроцедуры\n',
        encoding="utf-8",
    )
    assert main(["-Path", str(path)]) == 2
    err = capsys.readouterr().err
    assert "извлечено 0 запросов" in err


def test_main_warns_on_new_query_without_literal(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_text(
        'Процедура Тест()\n\tЗапрос = Новый Запрос;\n\tЗапрос.Текст = "не запрос";\nКонецПроцедуры\n',
        encoding="utf-8",
    )
    assert main(["-Path", str(path)]) == 2
    assert "извлечено 0 запросов" in capsys.readouterr().err


def test_main_no_warning_when_query_extracted(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_text('\tЗапрос.Текст = "ВЫБРАТЬ 1";\n', encoding="utf-8")
    assert main(["-Path", str(path)]) == 0
    assert "извлечено 0 запросов" not in capsys.readouterr().err


def test_main_no_warning_when_query_text_only_in_comment(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_text('// Запрос.Текст = "ВЫБРАТЬ 1";\nХ = 1;\n', encoding="utf-8")
    assert main(["-Path", str(path)]) == 0
    assert "извлечено 0 запросов" not in capsys.readouterr().err


def test_main_no_fail_suppresses_loud_exit(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_text(
        'Процедура Тест()\n\tЗапрос.Текст = "не запрос";\nКонецПроцедуры\n',
        encoding="utf-8",
    )
    assert main(["-Path", str(path), "-NoFail"]) == 0
    assert "извлечено 0 запросов" in capsys.readouterr().err
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run:
```bash
cd template/.claude/skills/query-analyze/scripts && python -m pytest tests/test_extract.py -q
```
Expected: FAIL — `ImportError: cannot import name 'main'` либо падения на
`test_leading_comment_lines_stripped` / предупреждении.

- [ ] **Step 3: Реализовать extractor**

В `extract_queries.py` после `QUERY_KEYWORDS` добавить:

```python
_QUERY_TEXT_RE = re.compile(r"\bЗапрос\s*\.\s*Текст\b", re.IGNORECASE)
_NEW_QUERY_RE = re.compile(r"\bНовый\s+Запрос\b", re.IGNORECASE)


def _strip_leading_comments(text: str) -> str:
    """Убрать ведущие пустые строки и строки-комментарии //..."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("//"):
            i += 1
            continue
        break
    return "\n".join(lines[i:])


def _sanitize_bsl(source: str) -> str:
    """Заменить строки и комментарии пробелами, сохранив переводы строк."""
    out = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch == '"':
            out.append(" ")
            i += 1
            while i < n:
                c = source[i]
                if c == '"':
                    if i + 1 < n and source[i + 1] == '"':
                        out.append("  ")
                        i += 2
                        continue
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)
```

В `extract_query_strings` заменить:

```python
            text = _unpipe("".join(raw))
```

на:

```python
            text = _strip_leading_comments(_unpipe("".join(raw)))
```

В `main` добавить аргумент:

```python
    parser.add_argument("-NoFail", action="store_true",
                        help="не возвращать код 2 при нулевом извлечении")
```

Заменить цикл обработки файлов на:

```python
    warnings = []
    for file in targets:
        try:
            with open(file, encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            continue
        found = extract_queries_from_xml(source) if args.Xml else extract_query_strings(source)
        for q in found:
            blocks.append(f"# {file}:{q.line_start}\n{q.text}")
        if not args.Xml and not found:
            sanitized = _sanitize_bsl(source)
            if _QUERY_TEXT_RE.search(sanitized) or _NEW_QUERY_RE.search(sanitized):
                warnings.append(file)
```

После цикла, перед `print("\n--- 8< ---\n".join(blocks))`, добавить:

```python
    for file in warnings:
        print(
            f"ВНИМАНИЕ: {file}: есть 'Запрос.Текст'/'Новый Запрос', но извлечено "
            f"0 запросов — query-analyze не проверит запрос. Проверьте текст "
            f"запроса вручную.",
            file=sys.stderr,
        )
```

Изменить финальный `return 0` на:

```python
    return 0 if args.NoFail or not warnings else 2
```

- [ ] **Step 4: Запустить тесты extractor**

Run:
```bash
cd template/.claude/skills/query-analyze/scripts && python -m pytest tests/test_extract.py -q
```
Expected: PASS.

- [ ] **Step 5: Поднять severity `totals-field-not-aggregated`**

В `rules.py`:

- в декораторе правила заменить `severity="warning"` на `severity="error"`;
- в `Finding("totals-field-not-aggregated", "warning", line, ...)` заменить
  `"warning"` на `"error"`;
- в docstring заменить `Severity=warning:` на `Severity=error:` и добавить, что
  находка блокирует приёмку.

Добавить тест в `tests/test_rules.py` после существующих тестов
`totals-field-not-aggregated`:

```python
@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_totals_field_not_aggregated_is_error():
    q = (
        "ВЫБРАТЬ Т.Номенклатура КАК Номенклатура, Т.Услуга КАК Услуга "
        "ИЗ РегистрСведений.Цены КАК Т "
        "ИТОГИ ПО Номенклатура"
    )
    ctx = rules.QueryContext(q)
    hits = [f for f in rules.run_all(ctx)
            if f.code == "totals-field-not-aggregated"]
    assert hits and hits[0].severity == "error"
```

- [ ] **Step 6: Запустить тесты query-analyze**

Run:
```bash
cd template/.claude/skills/query-analyze/scripts && python -m pytest tests -q
```
Expected: PASS (тесты без `node` могут быть skipped).

- [ ] **Step 7: Обновить `query-analyze/SKILL.md`**

- В списке классов ошибок заменить `totals-field-not-aggregated` (**важная**)`
  на `totals-field-not-aggregated` (**критичная**).
- В разделе про `extract_queries.py` добавить абзац:

```markdown
`extract_queries.py` срезает ведущие `//`-строки перед проверкой и печатает
предупреждение в stderr (код возврата `2`), если в модуле есть
`Запрос.Текст`/`Новый Запрос`, но извлечено 0 запросов. Это означает, что
`query-analyze` не проверил запрос: отсутствие находок в таком прогоне — не
«чисто». Флаг `-NoFail` отключает код `2`.
```

- [ ] **Step 8: Commit**

```bash
git add template/.claude/skills/query-analyze/scripts/rules.py \
        template/.claude/skills/query-analyze/scripts/extract_queries.py \
        template/.claude/skills/query-analyze/SKILL.md \
        template/.claude/skills/query-analyze/scripts/tests/test_rules.py \
        template/.claude/skills/query-analyze/scripts/tests/test_extract.py
git commit -m "feat(query-analyze): error для неагрегированных ИТОГИ и извлечение запросов с комментариями"
```

---

## Task 4: code-analyze — числовые аккумуляторы и use-before-assignment

**Files:**
- Modify: `template/.claude/skills/code-analyze/scripts/rules.py`
- Modify: `template/.claude/skills/code-analyze/SKILL.md`
- Test: `template/.claude/skills/code-analyze/scripts/tests/test_rules.py`

**Interfaces:**
- Produces: правило `use-before-assignment` (severity `warning`) и обновлённое поведение `string-concat-in-loop`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/test_rules.py`:

```python
# ── string-concat-in-loop: числовые аккумуляторы ─────────────

def test_numeric_accumulator_in_loop_not_flagged():
    text = (
        "Для Каждого Строка Из Товары Цикл\n"
        "    Сумма = Сумма + Строка.Цена * Строка.Количество;\n"
        "КонецЦикла;\n"
    )
    assert "string-concat-in-loop" not in codes(text)


def test_numeric_sebestoimost_accumulator_not_flagged():
    text = (
        "Пока Выборка.Следующий() Цикл\n"
        "    Себестоимость = Себестоимость + Выборка.Стоимость;\n"
        "КонецЦикла;\n"
    )
    assert "string-concat-in-loop" not in codes(text)


# ── use-before-assignment ────────────────────────────────────

def test_conditional_assignment_used_after_if_flagged():
    text = (
        "Процедура ОбработкаПроведения(Отказ)\n"
        "    Если МетодСписания = \"ФИФО\" Тогда\n"
        "        ТекстЗапроса = \"ВЫБРАТЬ 1\";\n"
        "    КонецЕсли;\n"
        "    Запрос.Текст = ТекстЗапроса;\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" in codes(text)


def test_conditional_assignment_with_else_not_flagged():
    text = (
        "Процедура Тест()\n"
        "    Если Условие Тогда\n"
        "        Текст = \"А\";\n"
        "    Иначе\n"
        "        Текст = \"Б\";\n"
        "    КонецЕсли;\n"
        "    Сообщить(Текст);\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)


def test_assignment_before_if_not_flagged():
    text = (
        "Процедура Тест()\n"
        "    Текст = \"по умолчанию\";\n"
        "    Если Условие Тогда\n"
        "        Текст = \"А\";\n"
        "    КонецЕсли;\n"
        "    Сообщить(Текст);\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)


def test_parameter_used_after_if_not_flagged():
    text = (
        "Процедура Тест(Текст)\n"
        "    Если Условие Тогда\n"
        "        Текст = \"А\";\n"
        "    КонецЕсли;\n"
        "    Сообщить(Текст);\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)


def test_module_var_used_after_if_not_flagged():
    text = (
        "Перем Текст;\n"
        "Процедура Тест()\n"
        "    Если Условие Тогда\n"
        "        Текст = \"А\";\n"
        "    КонецЕсли;\n"
        "    Сообщить(Текст);\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)


def test_loop_var_used_after_if_not_flagged():
    text = (
        "Процедура Тест()\n"
        "    Для Н = 1 По 3 Цикл\n"
        "        Если Условие Тогда\n"
        "            Н = Н + 1;\n"
        "        КонецЕсли;\n"
        "        Сообщить(Н);\n"
        "    КонецЦикла;\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)


def test_two_assignments_not_flagged():
    text = (
        "Процедура Тест()\n"
        "    Если Условие1 Тогда\n"
        "        Текст = \"А\";\n"
        "    КонецЕсли;\n"
        "    Если Условие2 Тогда\n"
        "        Текст = \"Б\";\n"
        "    КонецЕсли;\n"
        "    Сообщить(Текст);\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)


def test_use_only_inside_branch_not_flagged():
    text = (
        "Процедура Тест()\n"
        "    Если Условие Тогда\n"
        "        Текст = \"А\";\n"
        "        Сообщить(Текст);\n"
        "    КонецЕсли;\n"
        "КонецПроцедуры\n"
    )
    assert "use-before-assignment" not in codes(text)
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run:
```bash
cd template/.claude/skills/code-analyze/scripts && python -m pytest tests/test_rules.py -q
```
Expected: FAIL — числовые аккумуляторы пока флагуются, правила
`use-before-assignment` пока нет.

- [ ] **Step 3: Реализовать числовые аккумуляторы**

После `_NON_STRING_OP_RE` добавить:

```python
# Имена-аккумуляторы чисел: «Сумма = Сумма + …» — арифметика, не строки.
_NUMERIC_ACCUMULATOR_RE = re.compile(
    r"(?i)(сумм|стоимост|себестоим|количеств|итог|цен[аы]?|ндс|вес|объ[её]м|"
    r"ставк|процент|сальдо|остат|оборот|прибыл|убыт|рентабельн|начислен|"
    r"удержан|дней|часов|минут|секунд)"
)
```

В `check_string_concat_in_loop` после получения `lhs, rhs` добавить:

```python
            if _NUMERIC_ACCUMULATOR_RE.search(lhs):
                continue
```

Обновить docstring правила: числовые аккумуляторы не флагуются.

- [ ] **Step 4: Реализовать `use-before-assignment`**

Добавить в конец `rules.py`:

```python
# ── use-before-assignment ────────────────────────────────────

_ELSE_RE = re.compile(r"^\s*(Иначе|ИначеЕсли|Else|ElsIf)\b",
                      re.IGNORECASE | re.UNICODE)


def _ident_use_re(name: str):
    return re.compile(
        r"(?<![A-Za-zА-Яа-яЁё0-9_])" + re.escape(name)
        + r"(?![A-Za-zА-Яа-яЁё0-9_])",
        re.IGNORECASE | re.UNICODE,
    )


@rule(code="use-before-assignment", severity="warning",
      title="Переменная присваивается только в ветке Если и используется после блока")
def check_use_before_assignment(ctx):
    """Флагует локальную переменную, которая инициализируется только внутри
    `Если` без `Иначе` и используется после `КонецЕсли`.

    Консервативно: параметры, объявления `Перем`, переменные циклов, повторные
    присваивания и любая ветка `Иначе`/`ИначеЕсли` исключают находку.
    """
    out = []
    model = ctx.model
    module_vars = {name for name, _line, _export in model.var_declarations}
    for method in model.methods:
        params = set(method.params)
        loop_vars = {
            loop.loop_var for loop in model.loops
            if loop.loop_var
            and method.header_line <= loop.header_line <= method.end_line
        }
        skip = params | module_vars | loop_vars
        assignments = {}
        for ln in range(method.header_line + 1, method.end_line):
            m = _ASSIGN_RE.match(ctx.code_line(ln))
            if not m:
                continue
            name = m.group(1)
            if name in skip:
                continue
            assignments.setdefault(name, []).append(ln)

        if_blocks = [
            block for block in model.all_blocks
            if block.kind == "if"
            and method.header_line <= block.header_line <= method.end_line
        ]
        for name, lines in assignments.items():
            if len(lines) != 1:
                continue
            assign_line = lines[0]
            enclosing = [
                block for block in if_blocks
                if block.header_line <= assign_line <= block.end_line
            ]
            if not enclosing:
                continue
            block = max(enclosing, key=lambda item: item.header_line)
            if any(_ELSE_RE.match(ctx.code_line(ln))
                   for ln in range(block.header_line, block.end_line + 1)):
                continue
            use_re = _ident_use_re(name)
            for ln in range(block.end_line + 1, method.end_line + 1):
                if use_re.search(ctx.code_line(ln)):
                    out.append(Finding(
                        "use-before-assignment", "warning", ln,
                        f"Переменная «{name}» присваивается только внутри ветки "
                        f"Если (строка {assign_line}) без Иначе и используется "
                        f"после блока. Если условие не выполнится, переменная "
                        f"останется Неопределено; инициализируйте её до ветвления.",
                    ))
                    break
    return out
```

- [ ] **Step 5: Запустить тесты code-analyze**

Run:
```bash
cd template/.claude/skills/code-analyze/scripts && python -m pytest tests -q
```
Expected: PASS.

- [ ] **Step 6: Обновить `code-analyze/SKILL.md`**

- В таблице правил у `string-concat-in-loop` добавить «кроме числовых
  аккумуляторов (`Сумма`, `Стоимость`, `Количество` и т.п.)».
- Добавить строку:

```markdown
| `use-before-assignment` | warning | Переменная инициализируется только в ветке `Если` без `Иначе` и используется после блока — возможен `Неопределено` |
```

- В разделе «Границы анализа» добавить: правило консервативное, ловит только
  одиночное условное присваивание.

- [ ] **Step 7: Commit**

```bash
git add template/.claude/skills/code-analyze/scripts/rules.py \
        template/.claude/skills/code-analyze/SKILL.md \
        template/.claude/skills/code-analyze/scripts/tests/test_rules.py
git commit -m "feat(code-analyze): числовые аккумуляторы и use-before-assignment"
```

---

## Task 5: task_status — done только из running, restart, корректные runs

**Files:**
- Modify: `template/.claude/tools/task_status.py`
- Modify: `template/.claude/rules/cyclic-review-workflow.md`
- Modify: `template/.claude/skills/task-orchestration/SKILL.md`
- Modify: `template/.claude/rules/task-lifecycle.md`
- Test: `app/tests/env/test_task_status_cli.py`

**Interfaces:**
- Produces: `task_status.py <dir> <stage> restart`; `done` разрешён только из `running`; `running` при уже `running` — ошибка.

- [ ] **Step 1: Обновить/добавить тесты**

В `app/tests/env/test_task_status_cli.py`:

1. В `test_cli_sets_status_and_files` перед `done` добавить
   `mod.main([str(d), "develop", "running"])`.
2. Заменить `test_cli_runs_rerun_without_done_keeps_iteration` на:

```python
def test_cli_running_twice_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    with pytest.raises(SystemExit, match="restart"):
        mod.main([str(d), "develop", "running"])
```

3. Добавить:

```python
def test_cli_done_without_running_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    with pytest.raises(SystemExit, match="running"):
        mod.main([str(d), "develop", "done"])


def test_cli_restart_closes_open_run_and_increments(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "restart"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["status"] == "running"
    assert dev["iteration"] == 2
    assert len(dev["runs"]) == 2
    assert dev["runs"][0]["finished_at"] is not None
    assert dev["runs"][1]["iteration"] == 2
    assert dev["runs"][1]["finished_at"] is None


def test_cli_restart_from_done_starts_new_iteration(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    mod.main([str(d), "develop", "restart"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["status"] == "running"
    assert dev["iteration"] == 2
    assert all(r["finished_at"] is not None for r in dev["runs"][:-1])
    assert dev["runs"][-1]["finished_at"] is None


def test_cli_restart_first_run_is_iteration_one(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "restart"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["iteration"] == 1
    assert dev["runs"][0]["iteration"] == 1
    assert dev["runs"][0]["finished_at"] is None
```

4. Заменить тест `test_cli_pending_keeps_iteration_when_never_finished` на
   `test_cli_pending_then_running_increments_iteration`:

```python
def test_cli_pending_then_running_increments_iteration(tmp_path):
    """После возврата в pending следующий running — новая итерация."""
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "pending"])
    mod.main([str(d), "develop", "running"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["iteration"] == 2
    assert [run["iteration"] for run in dev["runs"]] == [1, 2]
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_task_status_cli.py -q
```
Expected: FAIL — `restart` неизвестный статус; `done` без `running` проходит.

- [ ] **Step 3: Реализовать `task_status.py`**

1. В `VALID` добавить `"restart"`.
2. Добавить helpers после `_db_update_block`:

```python
def _close_open_runs(stage: dict, now: str) -> None:
    for run in stage.get("runs") or []:
        if isinstance(run, dict) and run.get("finished_at") is None:
            run["finished_at"] = now


def _restart_stage(stage: dict, data: dict) -> None:
    """Начать новый прогон этапа, закрыв все открытые runs[]."""
    now = _now_iso()
    runs = stage.get("runs") or []
    _close_open_runs(stage, now)
    stage["iteration"] = (
        int(stage.get("iteration", 1)) + 1 if runs else 1)
    stage["status"] = "running"
    stage["started_at"] = now
    stage["finished_at"] = None
    stage.setdefault("runs", []).append(
        {"iteration": stage["iteration"], "started_at": now,
         "finished_at": None})
    if stage.get("name") == "develop" and _truthy(data.get("update_db")):
        data["db_update"] = {"started_at": None, "finished_at": None}


def _refresh_overall(data: dict) -> None:
    overall = _overall_status(data.get("stages", []))
    data["status"] = overall
    now = _now_iso()
    if overall == "running" and not data.get("started_at"):
        data["started_at"] = now
    if overall in ("done", "failed"):
        data["finished_at"] = now
    elif data.get("finished_at"):
        data["finished_at"] = None
```

3. Полностью заменить существующую функцию `_apply_update` на:

```python
def _apply_update(data: dict, stage: str, status: str, files, task_dir) -> None:
    for s in data.get("stages", []):
        if s["name"] == stage:
            if status == "approve":
                s["approved"] = True
            elif status == "restart":
                _restart_stage(s, data)
                data["stage"] = stage
                _refresh_overall(data)
                return
            else:
                if status == "running":
                    if s.get("status") == "running":
                        raise SystemExit(
                            f"ОШИБКА (running): этап '{stage}' уже running. "
                            f"Для нового прогона используйте restart.")
                    msg = _gate_block(data, stage)
                    if msg:
                        raise SystemExit("ОШИБКА (гейт): " + msg)
                    _close_open_runs(s, _now_iso())
                if status == "done":
                    if s.get("status") != "running":
                        raise SystemExit(
                            f"ОШИБКА (done): этап '{stage}' не в running "
                            f"(текущий статус: {s.get('status')}). "
                            f"Сначала переведите этап в running.")
                    msg = _db_update_block(data, stage, status)
                    if msg:
                        raise SystemExit("ОШИБКА (БД): " + msg)
                    if not any(run.get("finished_at") is None
                               for run in (s.get("runs") or [])):
                        raise SystemExit(
                            f"ОШИБКА (done): у этапа '{stage}' нет открытого "
                            f"прогона. Запустите этап через running или restart.")
                if status == "pending" and stage in AUTO_ARCHIVE_STAGES:
                    _archive_verdicts(Path(task_dir), data)
                s["status"] = status
                data["stage"] = stage
                changed = s.setdefault("changed_files", [])
                for f in (files or []):
                    if f not in changed:
                        changed.append(f)
                if stage == "develop" and status in ("pending", "running") \
                        and _truthy(data.get("update_db")):
                    data["db_update"] = {"started_at": None, "finished_at": None}
                now_stage = _now_iso()
                if status == "running":
                    has_history = (bool(s.get("runs"))
                                   or s.get("finished_at") is not None)
                    if has_history:
                        s["iteration"] = int(s.get("iteration", 1)) + 1
                    else:
                        s.setdefault("iteration", 1)
                    s["started_at"] = now_stage
                    s["finished_at"] = None
                    s.setdefault("runs", []).append(
                        {"iteration": s.get("iteration", 1),
                         "started_at": now_stage, "finished_at": None})
                elif status in ("done", "failed"):
                    s["finished_at"] = now_stage
                    for run in reversed(s.get("runs") or []):
                        if run.get("finished_at") is None:
                            run["finished_at"] = now_stage
                            break
                elif status == "pending":
                    for run in reversed(s.get("runs") or []):
                        if run.get("finished_at") is None:
                            run["finished_at"] = now_stage
                            break
            _refresh_overall(data)
            return
    raise SystemExit(f"неизвестный этап: {stage}")
```

4. В docstring модуля и `help` CLI описать `restart` и запрет `done` без
   `running`.

- [ ] **Step 4: Запустить тесты task_status**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_task_status_cli.py -q
```
Expected: PASS.

- [ ] **Step 5: Обновить документацию**

- `template/.claude/rules/cyclic-review-workflow.md` — в раздел «Управление
  итерациями этапа» добавить:

```markdown
`done` переводится только из `running`. Повторный запуск этапа без возврата на
доработку — команда `restart`: она закрывает открытый прогон, увеличивает
`iteration` и начинает новый. `pending` используется только для возврата на
доработку (и архивирует вердикты).
```

- `template/.claude/skills/task-orchestration/SKILL.md` — в раздел «Статусы»
  добавить то же правило и строку про `restart`.
- `template/.claude/rules/task-lifecycle.md` — в п. 3 добавить: «`done` — только
  из `running`; для повторного запуска — `restart`».

- [ ] **Step 6: Commit**

```bash
git add template/.claude/tools/task_status.py \
        template/.claude/rules/cyclic-review-workflow.md \
        template/.claude/skills/task-orchestration/SKILL.md \
        template/.claude/rules/task-lifecycle.md \
        app/tests/env/test_task_status_cli.py
git commit -m "feat(task_status): done только из running, restart, корректные runs"
```

---

## Task 6: bsl_ls — обязательный sha256, file_path, сырые counts в REVIEW.md

**Files:**
- Modify: `app/docker/mcp/bsl_check_server.py`
- Modify: `app/docker/mcp/bsl-ls.Dockerfile`
- Modify: `docs/mcp/bsl-ls.md`
- Modify: `template/.claude/skills/mcp-usage/SKILL.md`
- Modify: `template/.claude/rules/verify-with-syntax-checker.md`
- Modify: `template/.claude/agents/developer.md`
- Modify: `template/.claude/agents/reviewer.md`
- Modify: `template/.claude/hooks/bsl_nudge.py`
- Test: `app/tests/env/test_bsl_check_server.py`
- Test: `app/tests/env/test_bsl_nudge.py`

**Interfaces:**
- Produces: `check(sha256, code=None, file_path=None, config=None, filename="Module.bsl")`; ответ содержит `sha256`, `source`, `counts`, `bytes`.
- Produces: в `REVIEW.md` обязательная таблица «Сырые счётчики анализаторов».

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_bsl_check_server.py`:

```python
import hashlib


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_run_check_sha256_mismatch_rejected_before_java():
    calls = []
    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256="0" * 64,
                        run=lambda *a, **k: calls.append(1))
    assert res["ok"] is False
    assert "sha256" in res["summary"]
    assert calls == []


def test_run_check_sha256_match_ok():
    code = "Код"
    report = _report([])

    def fake_run(cmd, **kwargs):
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(
            _json.dumps(report), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    res = mod.run_check(code, "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha(code), run=fake_run)
    assert res["ok"] is True
    assert res["sha256"] == _sha(code)


def test_prepare_input_requires_sha256():
    code, filename, expected, source, error = mod.prepare_input(
        code="x", file_path=None, sha256="", filename="Module.bsl")
    assert code is None
    assert "sha256" in error


def test_prepare_input_requires_exactly_one_source():
    code, filename, expected, source, error = mod.prepare_input(
        code="x", file_path="y", sha256="0" * 64, filename="Module.bsl")
    assert code is None
    assert "ровно один" in error


def test_prepare_input_reads_file(tmp_path):
    path = tmp_path / "Module.bsl"
    path.write_text("ВЫБРАТЬ 1", encoding="utf-8")
    code, filename, expected, source, error = mod.prepare_input(
        code=None, file_path=str(path), sha256=_sha("ВЫБРАТЬ 1"),
        filename="Module.bsl")
    assert error is None
    assert code == "ВЫБРАТЬ 1"
    assert filename == "Module.bsl"
    assert source == "file"


def test_prepare_input_missing_file(tmp_path):
    code, filename, expected, source, error = mod.prepare_input(
        code=None, file_path=str(tmp_path / "nope.bsl"),
        sha256="0" * 64, filename="Module.bsl")
    assert code is None
    assert "file_path" in error


def test_counts_in_result():
    report = _report([{"path": "Module.bsl", "diagnostics": [
        {"range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 0, "character": 1}},
         "severity": 1, "code": "E"},
        {"range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 0, "character": 1}},
         "severity": 2, "code": "W"},
    ]}])

    def fake_run(cmd, **kwargs):
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(
            _json.dumps(report), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha("Код"), run=fake_run)
    assert res["counts"]["Error"] == 1
    assert res["counts"]["Warning"] == 1
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_bsl_check_server.py -q
```
Expected: FAIL — нет `prepare_input`, `run_check` не проверяет `sha256`.

- [ ] **Step 3: Реализовать сервер**

В `bsl_check_server.py` добавить `import hashlib` и `import re`, константу
`_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")`, функции:

```python
def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _counts(diagnostics: list[dict]) -> dict:
    counts = {"Error": 0, "Warning": 0, "Information": 0, "Hint": 0}
    for diag in diagnostics:
        severity = diag.get("severity") or ""
        if severity in counts:
            counts[severity] += 1
    return counts


def _result(*, ok: bool, summary: str, sha256: str, source: str,
            raw_bytes: int, diagnostics: list[dict] | None = None) -> dict:
    diagnostics = diagnostics or []
    return {"ok": ok, "count": len(diagnostics),
            "counts": _counts(diagnostics), "diagnostics": diagnostics,
            "summary": summary, "sha256": sha256, "source": source,
            "bytes": raw_bytes}


def prepare_input(code, file_path, sha256, filename):
    """Проверить аргументы check и вернуть (code, filename, sha, source, error)."""
    expected = str(sha256 or "").strip().lower()
    if not expected:
        return None, filename, expected, "code", (
            "sha256 обязателен: вычисли его по файлу "
            "(sha256sum Module.bsl) и передай вместе с code.")
    if not _SHA256_RE.match(expected):
        return None, filename, expected, "code", (
            "sha256 должен быть 64 hex-символа.")
    if (code is None) == (file_path is None):
        return None, filename, expected, "code", (
            "передайте ровно один источник: code или file_path.")
    source = "code"
    if file_path is not None:
        try:
            code = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            return None, filename, expected, "file", (
                f"не удалось прочитать file_path: {exc}. В Docker-контейнере "
                f"путь проекта не виден — передайте code+sha256.")
        source = "file"
        if filename == "Module.bsl":
            filename = Path(file_path).name
    return code, filename, expected, source, None
```

Переписать `run_check`:

```python
def run_check(code: str, filename: str, jar: str, config: str | None = None,
              java: str = "java", run=subprocess.run,
              expected_sha256: str | None = None,
              source: str = "code") -> dict:
    code = code if isinstance(code, str) else str(code or "")
    raw_bytes = len(code.encode("utf-8"))
    actual_sha = _sha256_hex(code)
    if expected_sha256 is not None:
        expected = str(expected_sha256).strip().lower()
        if not _SHA256_RE.match(expected):
            return _result(ok=False, summary="sha256 должен быть 64 hex-символа.",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        if actual_sha != expected:
            return _result(
                ok=False,
                summary=(f"sha256 не совпадает: передан {expected}, фактический "
                         f"{actual_sha}. Текст не соответствует файлу — не "
                         f"перепечатывай модуль, передай его как есть."),
                sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    if raw_bytes > MAX_CODE_BYTES:
        return _result(ok=False,
                       summary=f"код слишком большой (> {MAX_CODE_BYTES} байт)",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    if config and len(config.encode("utf-8")) > MAX_CONFIG_BYTES:
        return _result(ok=False,
                       summary=f"config слишком большой (> {MAX_CONFIG_BYTES} байт)",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    filename = Path(filename or "Module.bsl").name or "Module.bsl"
    if filename in _RESERVED_FILENAMES:
        return _result(ok=False,
                       summary=f"имя файла {filename!r} зарезервировано под настройки анализа",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    tmp = tempfile.mkdtemp(prefix="bsl-check-")
    try:
        srcdir = Path(tmp) / "src"
        outdir = Path(tmp) / "out"
        srcdir.mkdir(parents=True, exist_ok=True)
        (srcdir / filename).write_text(code, encoding="utf-8")
        if config:
            (srcdir / ".bsl-language-server.json").write_text(config, encoding="utf-8")
        cmd = [java, "-jar", jar, "analyze",
               "--srcDir", str(srcdir),
               "--outputDir", str(outdir),
               "--reporter", "json"]
        try:
            proc = run(cmd, capture_output=True, text=True,
                       timeout=ANALYZE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return _result(ok=False,
                           summary=f"BSL LS не завершился за {ANALYZE_TIMEOUT_SECONDS} с",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        except Exception as exc:
            return _result(ok=False,
                           summary=f"Не удалось запустить BSL LS: {exc}",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        report_path = outdir / "bsl-json.json"
        if not report_path.exists():
            stderr = (getattr(proc, "stderr", "") or "").strip()
            code_ = getattr(proc, "returncode", "?")
            return _result(ok=False,
                           summary=stderr or f"Отчёт не создан (код возврата {code_}).",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return _result(ok=False, summary=f"Не удалось прочитать отчёт: {exc}",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        diagnostics = parse_report(report, filename)
        return _result(ok=True, summary=_summary(diagnostics),
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                       diagnostics=diagnostics)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

В `build_server` заменить инструмент `check` на:

```python
    @mcp.tool()
    def check(sha256: str, code: str | None = None,
              file_path: str | None = None,
              config: str | dict | None = None,
              filename: str = "Module.bsl") -> dict:
        """Статический анализ кода 1С (BSL) на соответствие стандартам.

        sha256 — обязательный SHA-256 файла (64 hex). Вычисли по самому файлу:
            sha256sum Module.bsl
        code — точный текст модуля; не перепечатывай его вручную.
        file_path — альтернатива code: сервер прочитает файл сам, если путь виден
            в контейнере. В стандартном Docker-развёртывании проект не смонтирован;
            используйте code+sha256.
        config — содержимое .bsl-language-server.json (строкой-JSON или объектом).
        filename — имя файла для отчёта (по умолчанию Module.bsl).
        """
        prepared, filename, expected, source, error = prepare_input(
            code, file_path, sha256, filename)
        if error:
            return _result(ok=False, summary=error, sha256=expected,
                           source=source, raw_bytes=0)
        return run_check(prepared, filename, jar=jar,
                         config=_as_config_text(config),
                         expected_sha256=expected, source=source)
```

- [ ] **Step 4: Запустить тесты сервера**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_bsl_check_server.py -q
```
Expected: PASS.

- [ ] **Step 5: Обновить `bsl_nudge.py` и его тест**

В `bsl_nudge.py` заменить текст сообщения на:

```python
                "[ai1c] Изменён BSL-модуль — прогони статический анализ "
                "(навык mcp-usage, MCP bsl_ls, mcp__bsl_ls__check) с обязательным "
                "sha256 файла; текст модуля не перепечатывай."
```

В `test_bsl_nudge.py` проверка `assert "mcp__bsl_ls__check" in ...` остаётся
верной; новый текст сообщения содержит эту подстроку, поэтому тест менять не
нужно.

- [ ] **Step 6: Обновить документацию**

- `docs/mcp/bsl-ls.md`: заменить сигнатуру `check(code, config, filename)` на
  `check(sha256, code|file_path, config, filename)`, добавить пример:
  ```bash
  sha=$(sha256sum src/cf/CommonModules/Модуль/Ext/Module.bsl | cut -d' ' -f1)
  ```
  и пояснить, что без `sha256` вызов отклоняется, а `file_path` работает только
  при видимом пути.
- `template/.claude/skills/mcp-usage/SKILL.md`: в разделе `bsl_ls` добавить
  обязательный `sha256` и запрет перепечатывать модуль.
- `template/.claude/rules/verify-with-syntax-checker.md`: добавить:
  ```markdown
  Перед вызовом вычисли sha256 файла (`sha256sum <файл>` или
  `shasum -a 256 <файл>`) и передай его в `check`. Без `sha256` инструмент
  отклонит вызов. Не перепечатывай модуль вручную.
  ```
- `template/.claude/agents/developer.md`: в пункте 3 добавить ту же инструкцию.
- `template/.claude/agents/reviewer.md`: в Шаге 2 добавить, что `bsl_ls`
  вызывается с `sha256`; в «Выход» добавить обязательную секцию:

  ```markdown
  - **секцию `## Сырые счётчики анализаторов`** — таблица:

    | Инструмент | Файл/объект | error | warning | info | sha256 / сырая сводка |
    |---|---|---|---|---|---|

    Цифры берутся из вывода инструментов, а не из прозы. Для `bsl_ls` —
    `sha256` и `summary`; для `code-analyze`/`query-analyze` — counts по строкам
    `severity | код | строка`. Недоступный слой — строка с `—` и критичная
    находка «слой не отработал». Писать «0 ошибок» без этой таблицы запрещено.
  ```

- [ ] **Step 7: Запустить тесты документации/хуков**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_bsl_nudge.py app/tests/env/test_content_deploy.py app/tests/env/test_template_docs.py -q
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/docker/mcp/bsl_check_server.py \
        app/docker/mcp/bsl-ls.Dockerfile \
        docs/mcp/bsl-ls.md \
        template/.claude/skills/mcp-usage/SKILL.md \
        template/.claude/rules/verify-with-syntax-checker.md \
        template/.claude/agents/developer.md \
        template/.claude/agents/reviewer.md \
        template/.claude/hooks/bsl_nudge.py \
        app/tests/env/test_bsl_check_server.py \
        app/tests/env/test_bsl_nudge.py
git commit -m "feat(bsl-ls): обязательный sha256, file_path и сырые counts"
```

---

## Task 7: benchmark-метрики без токенов и с субагентами

**Files:**
- Modify: `benchmark/bench_run.py`
- Modify: `benchmark/bench_metrics.py`
- Modify: `benchmark/bench_analysis.py`
- Modify: `benchmark/README.md`
- Test: `benchmark/tests/test_bench_metrics.py`
- Test: `benchmark/tests/test_bench_e2e.py`

**Interfaces:**
- Produces: `_stream_metrics` без `cost_usd`/`usage`; `_task_log_dirs` учитывает identifier/folder; `cycle_metrics` суммирует субагентов.

- [ ] **Step 1: Написать/обновить падающие тесты**

В `benchmark/tests/test_bench_metrics.py`:

1. В `test_render_digest_contains_key_sections` заменить
   `"stream": {"num_turns": 12, "cost_usd": 0.5}` на
   `"stream": {"num_turns": 12, "session_id": "s"}`.
2. В `test_render_digest_none_values_rendered_as_dash` заменить
   `"stream": {"num_turns": 1, "cost_usd": None, "session_id": None}` на
   `"stream": {"num_turns": 1, "session_id": None}` и удалить строки
   `assert "cost=—" in text` и `assert "cost=None" not in text`.
3. Добавить:

```python
from types import SimpleNamespace


def test_task_log_dirs_uses_identifier_and_folder(tmp_path):
    logs = tmp_path / "logs"
    (logs / "task##002").mkdir(parents=True)
    task = SimpleNamespace(folder="task##002", identifier="#002",
                           raw={"id": 24})
    dirs = mod._task_log_dirs(tmp_path, task)
    assert logs / "task##002" in dirs
    assert logs / "task#002" in dirs
    assert logs / "task#24" in dirs
    assert logs / "task##24" in dirs


def test_cycle_metrics_includes_subagents(tmp_path):
    main = {"test_runs": 1, "smoke_runs": 1,
            "edits": {"src/cfe/ЮнитТесты/Module.bsl": 1}}
    sub = {"test_runs": 3, "smoke_runs": 0,
           "edits": {"src/cfe/ЮнитТесты/Module.bsl": 2}}
    metrics = mod.cycle_metrics(
        {"stages": []}, {}, {"main": main, "subagents": [sub]})
    assert metrics["test_runs"] == 4
    assert metrics["smoke_runs"] == 1
    assert metrics["test_module_edits"] == 3
```

   В тесте нужен импорт `bench_metrics` как `mod`; в файле уже импортируются
   функции напрямую. Добавить `import bench_metrics as mod` в начало.

В `benchmark/tests/test_bench_e2e.py` удалить `"total_cost_usd": 0.1` из
фейкового результата.

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run:
```bash
.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py benchmark/tests/test_bench_e2e.py -q
```
Expected: FAIL — digest содержит cost, `_task_log_dirs` не учитывает identifier,
`cycle_metrics` не суммирует субагентов.

- [ ] **Step 3: Реализовать изменения**

`benchmark/bench_run.py`, `_stream_metrics`:

```python
def _stream_metrics(run: ClaudeRun) -> dict:
    result = run.stream.result or {}
    return {
        "session_id": run.stream.session_id,
        "parse_errors": run.stream.parse_errors,
        "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"),
        "is_error": result.get("is_error"),
    }
```

`benchmark/bench_metrics.py`, `render_digest`:

```python
        lines.append(f"- Агент: turns={stream.get('num_turns')}, "
                     f"session={_opt(session)}")
```

`benchmark/bench_metrics.py`, `_task_log_dirs`:

```python
def _task_log_dirs(project_dir: Path, task) -> list[Path]:
    """Каталоги логов задачи: по id, identifier и фактической папке."""
    logs = project_dir / "logs"
    raw = task.raw if isinstance(getattr(task, "raw", None), dict) else {}
    task_id = raw.get("id")
    identifier = str(getattr(task, "identifier", "") or "").lstrip("#")
    folder = str(getattr(task, "folder", "") or "")
    candidates = []
    if identifier:
        candidates += [logs / f"task#{identifier}", logs / f"task##{identifier}"]
    if folder:
        candidates.append(logs / folder)
    if isinstance(task_id, int) and not isinstance(task_id, bool):
        candidates += [logs / f"task#{task_id}", logs / f"task##{task_id}"]
    seen = set()
    result = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result
```

`collect_task_state`: дедуплицировать `result.json`:

```python
    test_results = []
    seen = set()
    for log_dir in _task_log_dirs(project_dir, task):
        result_path = log_dir / "result.json"
        if not result_path.is_file():
            continue
        resolved = result_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            test_results.append(data)
```

`summarize_transcripts`: в словарь субагента добавить:

```python
            "edits": summary["edits"],
            "smoke_runs": summary["smoke_runs"],
```

`cycle_metrics`:

```python
def cycle_metrics(task_json: dict, state: dict, transcript: dict) -> dict:
    agents = [transcript.get("main") or {}]
    agents += [item for item in (transcript.get("subagents") or [])
               if isinstance(item, dict)]
    test_runs = sum(int(agent.get("test_runs") or 0) for agent in agents)
    smoke_runs = sum(int(agent.get("smoke_runs") or 0) for agent in agents)
    test_edits = 0
    for agent in agents:
        for path, count in (agent.get("edits") or {}).items():
            if "ЮнитТесты" in path and "/src/cfe/" in f"/{path}":
                test_edits += int(count)
    by_kind = state.get("archives_by_kind") or {}
    return {
        "tests_iteration": _stage_iteration(task_json, "tests"),
        "review_iteration": _stage_iteration(task_json, "review"),
        "review_archives": len(by_kind.get("review") or []),
        "develop_archives": len(by_kind.get("develop") or []),
        "testing_archives": len(by_kind.get("testing") or []),
        "tests_archives": len(by_kind.get("tests") or []),
        "test_runs": test_runs,
        "smoke_runs": smoke_runs,
        "test_module_edits": test_edits,
        "review_verdict": (state.get("verdicts") or {}).get("REVIEW.md"),
    }
```

`benchmark/bench_analysis.py`, в формате ответа:

```python
1. `## Сводка прогона` — таблица «задача → лимит → факт → исход → этапы → итерации →
   тесты → вердикт ревью», пометка о --force.
```

`benchmark/README.md` — добавить в «Результаты»:

```markdown
Токены и стоимость не собираются: `metrics.json` и дайджест содержат время,
итерации, инструменты и тестовые прогоны, но не `usage`/`cost_usd`.
```

- [ ] **Step 4: Запустить тесты benchmark**

Run:
```bash
.venv/bin/python -m pytest benchmark/tests -q
```
Expected: PASS.

- [ ] **Step 5: Проверить, что токенов/стоимости не осталось**

Run:
```bash
grep -rn "cost_usd\|total_cost_usd\|\"usage\"" benchmark --include='*.py'
```
Expected: пусто (кроме исторических `docs/`; их не трогаем).

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench_run.py benchmark/bench_metrics.py \
        benchmark/bench_analysis.py benchmark/README.md \
        benchmark/tests/test_bench_metrics.py benchmark/tests/test_bench_e2e.py
git commit -m "feat(bench): метрики без токенов/стоимости и с субагентами"
```

---

## Task 8: Запрет опасного pkill в промптах

**Files:**
- Modify: `template/.claude/agents/developer.md`
- Modify: `template/.claude/agents/developer-tests.md`

**Interfaces:**
- Produces: явный запрет `pkill -f "1cv8 ENTERPRISE"` в обоих промптах.

- [ ] **Step 1: Добавить правило в `developer.md`**

В раздел «Границы» добавить:

```markdown
**Процессы 1С.** Никогда не выполняй `pkill -f "1cv8 ENTERPRISE"`: шаблон
матчит собственную командную строку, shell убивает сам себя (`Exit code 144`) и
может задеть чужие сеансы. Безопасно: `pkill -f '[1]cv8'`,
`pgrep -f '[1]cv8'` + точечный `kill <pid>`; предпочитай `run-tests.py` и
`1c-batch` — они убивают только своё дерево процессов по таймауту.
```

- [ ] **Step 2: Добавить правило в `developer-tests.md`**

В раздел «Границы» добавить тот же абзац (можно со ссылкой на
`task-orchestration`, раздел «Процессы 1С и ожидание»).

- [ ] **Step 3: Проверить**

Run:
```bash
grep -n "pkill" template/.claude/agents/developer.md template/.claude/agents/developer-tests.md
```
Expected: в обоих файлах есть `pkill -f '[1]cv8'` и запрет
`pkill -f "1cv8 ENTERPRISE"`.

- [ ] **Step 4: Commit**

```bash
git add template/.claude/agents/developer.md \
        template/.claude/agents/developer-tests.md
git commit -m "docs(template): запрет опасного pkill по 1cv8"
```

---

## Task 9: Финальная проверка

**Files:** нет новых.

- [ ] **Step 1: Прогнать все затронутые тесты**

Run:
```bash
.venv/bin/python -m pytest \
  app/tests/env/test_task_status_cli.py \
  app/tests/env/test_bsl_check_server.py \
  app/tests/env/test_bsl_nudge.py \
  app/tests/env/test_content_deploy.py \
  app/tests/env/test_template_docs.py \
  benchmark/tests -q
cd template/.claude/skills/query-analyze/scripts && python -m pytest tests -q
cd ../code-analyze/scripts && python -m pytest tests -q
```
Expected: все тесты PASS (часть AST-тестов может быть skipped без `node`).

- [ ] **Step 2: Ручные проверки**

```bash
cd /home/uam/projects/ai_template
printf 'Процедура П()\n\tЗапрос.Текст = "// Комментарий\n// Ещё\nВЫБРАТЬ 1";\nКонецПроцедуры\n' > /tmp/lead.bsl
python template/.claude/skills/query-analyze/scripts/extract_queries.py -Path /tmp/lead.bsl
printf 'Процедура П()\n\tЗапрос.Текст = "не запрос";\nКонецПроцедуры\n' > /tmp/nolit.bsl
python template/.claude/skills/query-analyze/scripts/extract_queries.py -Path /tmp/nolit.bsl; echo "rc=$?"
printf 'Процедура П()\n\tЕсли У Тогда\n\t\tТ = "а";\n\tКонецЕсли;\n\tСообщить(Т);\nКонецПроцедуры\n' > /tmp/uba.bsl
python template/.claude/skills/code-analyze/scripts/analyze_code.py /tmp/uba.bsl
```
Expected:
- первый вызов печатает запрос `ВЫБРАТЬ 1` без ведущих комментариев;
- второй — предупреждение в stderr и `rc=2`;
- третий — находка `warning | use-before-assignment`.

- [ ] **Step 3: Проверить git-состояние и историю**

Run:
```bash
git status --short
git log --oneline -12
```
Expected: рабочее дерево чистое; видны коммиты задач 1–8.

- [ ] **Step 4: Итоговый коммит (если остались правки)**

Если `git status --short` не пуст:
```bash
git add -A
git commit -m "chore: финальная проверка доработок benchmark"
```
Если пуст — ничего не делать.
