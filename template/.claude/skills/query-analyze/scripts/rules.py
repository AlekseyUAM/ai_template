# rules.py — реестр автоматических проверок запросов 1С.
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

# Автономный бандл SDBL-парсера (см. vendor/README.md). Module-level — чтобы тесты
# могли подменять путь через monkeypatch.
_PARSER_BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "sdbl_parse.js")


@dataclass
class Finding:
    code: str
    severity: str  # error | warning | info
    line: int
    message: str


@dataclass
class Rule:
    code: str
    severity: str
    title: str
    fn: object


RULES = []


def rule(code, severity, title):
    def deco(fn):
        RULES.append(Rule(code=code, severity=severity, title=title, fn=fn))
        return fn
    return deco


def _sanitize(text):
    """Содержимое строковых литералов "..." и строчных комментариев //… заменяется
    пробелами той же длины (переводы строк сохранены). Правила, работающие по коду
    запроса, не должны срабатывать на слова внутри строк и комментариев. Длина и
    номера строк сохраняются — позиции совпадают с исходным текстом."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            out.append(' ')
            i += 1
            while i < n:
                c = text[i]
                if c == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        out.append('  ')
                        i += 2
                        continue
                    out.append(' ')
                    i += 1
                    break
                out.append('\n' if c == '\n' else ' ')
                i += 1
            continue
        if ch == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                out.append(' ')
                i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


class QueryContext:
    def __init__(self, text):
        self.text = text
        self._lines = None
        self._upper = None
        self._statements = None
        self._code = None
        self._code_upper = None
        self._model = None
        self._model_parsed = False
        self.model_error = None

    @property
    def lines(self):
        if self._lines is None:
            self._lines = self.text.split("\n")
        return self._lines

    @property
    def upper(self):
        if self._upper is None:
            self._upper = self.text.upper()  # для кириллицы длина сохраняется
        return self._upper

    @property
    def code(self):
        """Текст запроса без содержимого строк и комментариев (см. _sanitize)."""
        if self._code is None:
            self._code = _sanitize(self.text)
        return self._code

    @property
    def code_upper(self):
        if self._code_upper is None:
            self._code_upper = self.code.upper()
        return self._code_upper

    def line_of(self, pos):
        return self.text.count("\n", 0, pos) + 1

    @property
    def statements(self):
        if self._statements is None:
            out = []
            pos = 0
            for part in self.text.split(";"):
                if part.strip():
                    start = pos + (len(part) - len(part.lstrip()))
                    out.append((self.line_of(start), part))
                pos += len(part) + 1
            self._statements = out
        return self._statements

    @property
    def model(self):
        """Структурная модель запроса (BatchDocument) от вендоренного SDBL-парсера,
        или None, если разбор недоступен. Запускает `node vendor/sdbl_parse.js`,
        кеширует результат. Никогда не бросает — при любой проблеме возвращает None
        и пишет причину в self.model_error (правила по модели тогда пропускаются)."""
        if self._model_parsed:
            return self._model
        self._model_parsed = True
        if shutil.which("node") is None:
            self.model_error = "node не найден в PATH"
            return None
        if not os.path.exists(_PARSER_BUNDLE):
            self.model_error = f"бандл парсера не найден: {_PARSER_BUNDLE}"
            return None
        try:
            proc = subprocess.run(
                ["node", _PARSER_BUNDLE],
                input=self.text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            self.model_error = f"запуск node не удался: {e}"
            return None
        if proc.returncode != 0:
            self.model_error = f"node вернул код {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:200]}"
            return None
        try:
            data = json.loads(proc.stdout.decode("utf-8"))
        except ValueError as e:
            self.model_error = f"некорректный JSON от парсера: {e}"
            return None
        if isinstance(data, dict) and "error" in data:
            self.model_error = f"ошибка разбора запроса: {data['error']}"
            return None
        self._model = data
        return data


def iter_query_models(ctx):
    """Пробегает запросы-участники распарсенной модели.
    yield (line, distinct, model_dict): line — стартовая строка оператора пакета
    (из ctx.statements, best-effort; 1 если не сопоставилось), distinct — флаг
    участника объединения (False = добавлен через ОБЪЕДИНИТЬ ВСЕ), model_dict —
    QueryModel. Если модель недоступна (node/бандла нет или ошибка разбора) —
    не yield-ит ничего (правило по модели корректно пропускается)."""
    batch = ctx.model
    if not isinstance(batch, dict):
        return
    stmts = ctx.statements
    for si, stmt in enumerate(batch.get("members", []) or []):
        line = stmts[si][0] if si < len(stmts) else 1
        for member in stmt.get("members", []) or []:
            yield line, bool(member.get("distinct", False)), (member.get("model") or {})


def run_all(ctx):
    findings = []
    for r in RULES:
        findings.extend(r.fn(ctx))
    return findings


# ── Вспомогательные константы ────────────────────────────────

# Ключевые слова языка запросов 1С — пишутся заглавными.
# Список охватывает наиболее частотные слова; намеренно НЕ включаем:
# — «И», «В», «ПО» — слишком коротки, высокая вероятность совпадения с
#   идентификаторами и именами полей; дают неприемлемый уровень ложных срабатываний;
# — «ССЫЛКА», «ЗНАЧЕНИЕ», «ТИРЕ» — используются и как имена полей/реквизитов,
#   что делает их слишком шумными для эвристического поиска без парсера;
# — «ВЫБОР», «КОГДА», «ТОГДА», «ИНАЧЕ», «КОНЕЦ» — часто встречаются как имена
#   полей или псевдонимов (например «КАК Конец», «КАК Начало»); без AST-парсера
#   невозможно отличить ключевое слово ВЫБОР…КОНЕЦ от имени поля/псевдонима —
#   слишком высокая вероятность ложных срабатываний на идентификаторы.
_QUERY_KEYWORDS = [
    "ВЫБРАТЬ", "РАЗЛИЧНЫЕ", "РАЗРЕШЕННЫЕ", "ПЕРВЫЕ",
    "ИЗ", "ГДЕ", "СГРУППИРОВАТЬ", "УПОРЯДОЧИТЬ",
    "ИМЕЯ", "ОБЪЕДИНИТЬ", "ПОМЕСТИТЬ", "УНИЧТОЖИТЬ",
    "ИТОГИ", "АВТОУПОРЯДОЧИВАНИЕ", "ИЕРАРХИЯ",
    "ЛЕВОЕ", "ПРАВОЕ", "ПОЛНОЕ", "ВНУТРЕННЕЕ", "СОЕДИНЕНИЕ",
    "ПОДОБНО", "МЕЖДУ", "ЕСТЬNULL", "КАК",
]

# ── Проверки ────────────────────────────────────────────────

_MANY_TABLES_THRESHOLD = 7  # при ≥7 таблицах в одном запросе — info


@rule(code="select-star", severity="warning",
      title="ВЫБРАТЬ * — выбирать только нужные поля")
def check_select_star(ctx):
    """Проверяет наличие ВЫБРАТЬ * по AST-модели.

    Итерирует iter_query_models(ctx); если хотя бы одно поле запроса
    имеет expression == "*" — это ВЫБРАТЬ *. Одно срабатывание на запрос.
    Если модель недоступна (node/бандл отсутствуют) — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        fields = model_dict.get("fields") or []
        if any(f.get("expression") == "*" for f in fields):
            out.append(Finding(
                code="select-star",
                severity="warning",
                line=line,
                message="ВЫБРАТЬ *: выбирайте только нужные поля, а не все.",
            ))
    return out


@rule(code="many-joins", severity="info",
      title="Слишком много соединений в одном запросе")
def check_many_joins(ctx):
    """Считает таблицы в каждом запросе по AST-модели.

    Стандарт указывает: «много может быть уже и 5–7 таблиц в
    одном запросе». Порог 7 таблиц — верхняя граница этого диапазона;
    осознанно консервативная эвристика уровня info.
    Если модель недоступна (node/бандл отсутствуют) — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        table_count = len(model_dict.get("tables") or [])
        if table_count >= _MANY_TABLES_THRESHOLD:
            out.append(Finding(
                code="many-joins",
                severity="info",
                line=line,
                message=(
                    f"В запросе {table_count} таблиц — "
                    f"5–7 таблиц в одном запросе уже считается много. "
                    f"Разбейте запрос на более простые части."
                ),
            ))
    return out


# ── Оформление текстов запросов ─────────────────────

# Регулярное выражение для обнаружения ключевого слова в НЕ-верхнем регистре.
# Стратегия: для каждого ключевого слова ищем его с флагом IGNORECASE.
# Если найденный фрагмент отличается от эталонного (верхний регистр),
# значит слово написано неправильно.
_KW_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE | re.UNICODE)
    for kw in _QUERY_KEYWORDS
]
# Сопоставление паттерна с эталонным словом
_KW_PATTERN_MAP = list(zip(_KW_PATTERNS, _QUERY_KEYWORDS))


@rule(code="keyword-lowercase", severity="warning",
      title="Ключевые слова запроса должны быть заглавными")
def check_keyword_lowercase(ctx):
    """Проверяет, что ключевые слова языка запросов написаны в верхнем регистре.

    «Все ключевые слова языка запросов пишутся заглавными буквами».
    Сканирует ctx.code (без строк и комментариев), чтобы не срабатывать на
    слова внутри строковых литералов и комментариев.
    Пропускает совпадения, непосредственно предшествующие «.» — это разыменование
    поля (например Т.Конец), а не ключевое слово.
    """
    out = []
    seen_positions = set()
    code = ctx.code
    for pattern, expected in _KW_PATTERN_MAP:
        for m in pattern.finditer(code):
            if m.start() in seen_positions:
                continue
            # Пропускаем «Таблица.конец» и подобные разыменования полей
            if m.start() > 0 and code[m.start() - 1] == '.':
                continue
            found = m.group()
            if found != expected:
                seen_positions.add(m.start())
                out.append(Finding(
                    code="keyword-lowercase",
                    severity="warning",
                    line=ctx.line_of(m.start()),
                    message=(
                        f"Ключевое слово «{found}» написано не заглавными буквами "
                        f"(должно быть «{expected}»)."
                    ),
                ))
    return out


# ── Псевдонимы источников данных ────────────────────

@rule(code="alias-starts-with-underscore", severity="warning",
      title="Псевдоним источника данных не должен начинаться с подчёркивания")
def check_alias_starts_with_underscore(ctx):
    """Проверяет псевдонимы ИСТОЧНИКОВ ДАННЫХ по AST-модели.

    Итерирует iter_query_models(ctx); для каждого источника из model_dict["tables"]
    проверяет поле alias. Псевдонимы полей (model_dict["fields"][].alias) не
    затрагиваются. Если модель недоступна (node/бандл отсутствуют) — правило
    пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for table in model_dict.get("tables") or []:
            alias = table.get("alias") or ""
            if not alias:
                continue
            if alias.startswith("_"):
                out.append(Finding(
                    "alias-starts-with-underscore", "warning",
                    line,
                    f"Псевдоним источника «{alias}» начинается с подчёркивания — запрещено.",
                ))
    return out


@rule(code="alias-single-char", severity="warning",
      title="Псевдоним источника данных не должен состоять из одного символа")
def check_alias_single_char(ctx):
    """Проверяет псевдонимы ИСТОЧНИКОВ ДАННЫХ по AST-модели.

    Итерирует iter_query_models(ctx); для каждого источника из model_dict["tables"]
    проверяет поле alias. Псевдонимы полей (model_dict["fields"][].alias) не
    затрагиваются. Если модель недоступна (node/бандл отсутствуют) — правило
    пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for table in model_dict.get("tables") or []:
            alias = table.get("alias") or ""
            if not alias:
                continue
            if len(alias) == 1:
                out.append(Finding(
                    "alias-single-char", "warning",
                    line,
                    f"Псевдоним источника «{alias}» состоит из одного символа — запрещено.",
                ))
    return out


@rule(code="query-one-line", severity="info",
      title="Запрос написан в одну строку — следует структурировать")
def check_query_one_line(ctx):
    """Обнаруживает операторы ВЫБРАТЬ, записанные целиком в одну строку.

    «Текст запроса должен быть структурирован, не следует писать
    запрос в одну строку, даже короткий».
    Проверяет каждый оператор пакета: если весь оператор не содержит \\n,
    начинается с ВЫБРАТЬ и содержит слово ИЗ — значит запрос в одну строку.
    Это исключает ложные срабатывания на встроенные подзапросы внутри
    многострочного внешнего запроса.
    """
    out = []
    for start_line, stmt in ctx.statements:
        stmt_upper = stmt.upper().strip()
        if (
            stmt_upper.startswith("ВЫБРАТЬ")
            and " ИЗ " in stmt_upper
            and "\n" not in stmt
        ):
            out.append(Finding(
                code="query-one-line",
                severity="info",
                line=start_line,
                message=(
                    "Запрос записан в одну строку. Структурируйте текст запроса "
                    "для улучшения читаемости."
                ),
            ))
    return out


# ── Упорядочивание результатов запроса ───────────────

@rule(code="autoorder-with-first", severity="error",
      title="АВТОУПОРЯДОЧИВАНИЕ с ПЕРВЫЕ запрещено")
def check_autoorder_with_first(ctx):
    """Обнаруживает совместное использование ПЕРВЫЕ и АВТОУПОРЯДОЧИВАНИЕ по AST-модели.

    «Использование конструкции ПЕРВЫЕ совместно с конструкцией
    АВТОУПОРЯДОЧИВАНИЕ запрещено».
    Итерирует iter_query_models(ctx); для каждого запроса проверяет наличие
    order.auto == True и selection.top. Если модель недоступна — пропускается.
    Правило взаимоисключающе с autoorder-not-recommended: при auto+has_first
    выдаётся только error, при auto без has_first — только warning.
    """
    out = []
    for line, distinct, model in iter_query_models(ctx):
        auto = bool((model.get("order") or {}).get("auto"))
        has_first = bool((model.get("selection") or {}).get("top"))
        if auto and has_first:
            out.append(Finding(
                code="autoorder-with-first",
                severity="error",
                line=line,
                message=(
                    "ПЕРВЫЕ совместно с АВТОУПОРЯДОЧИВАНИЕ запрещено — "
                    "результат непредсказуем."
                ),
            ))
    return out


# ── ОБЪЕДИНИТЬ vs ОБЪЕДИНИТЬ ВСЕ ────────────────────

@rule(code="union-without-all", severity="info",
      title="ОБЪЕДИНИТЬ без ВСЕ выполняет дорогостоящее удаление дублей")
def check_union_without_all(ctx):
    """Флагует членов объединения, добавленных через ОБЪЕДИНИТЬ (с дедупликацией).

    в общем случае следует использовать ОБЪЕДИНИТЬ ВСЕ, так как
    ОБЪЕДИНИТЬ (без ВСЕ) выполняет удаление полностью одинаковых строк, что
    затратно по времени даже если одинаковых строк заведомо быть не может.
    Исключение: когда удаление дублей является необходимым условием корректности.
    Severity=info, т.к. это рекомендация.

    Работает по AST-модели: iter_query_models возвращает distinct=True для
    членов, добавленных через ОБЪЕДИНИТЬ (без ВСЕ). Если модель недоступна —
    правило пропускается.
    """
    out = []
    for line, distinct, model in iter_query_models(ctx):
        if distinct:
            out.append(Finding(
                code="union-without-all",
                severity="info",
                line=line,
                message=(
                    "Использовано ОБЪЕДИНИТЬ (с устранением дубликатов); "
                    "если дубликаты невозможны/неважны — используйте ОБЪЕДИНИТЬ ВСЕ."
                ),
            ))
    return out


# ── Оператор ПОДОБНО ─────────────────────────────────

def _iter_like_params(ctx):
    """Генератор: для каждого условия ПОДОБНО по AST-модели yield (line, param).

    Итерирует iter_query_models(ctx); для каждого запроса проходит по
    conditions[]. Если cond["operator"] == "ПОДОБНО" и param — непустая строка,
    возвращает (line, param). Если модель недоступна — не возвращает ничего.
    """
    for line, distinct, model in iter_query_models(ctx):
        for cond in model.get("conditions") or []:
            if cond.get("operator") == "ПОДОБНО":
                param = cond.get("param")
                if param and isinstance(param, str):
                    yield line, param


def _like_literal_content(param):
    """Извлекает содержимое первого строкового литерала из param.

    Если param.lstrip() начинается с '"', сканирует до закрывающей '"' (двойной
    '""' = экранированная кавычка) и возвращает внутреннее содержимое.
    Иначе возвращает None.
    """
    s = param.lstrip()
    if not s or s[0] != '"':
        return None
    i = 1
    parts = []
    n = len(s)
    while i < n:
        c = s[i]
        if c == '"':
            if i + 1 < n and s[i + 1] == '"':
                parts.append('"')
                i += 2
                continue
            break  # конец литерала
        parts.append(c)
        i += 1
    return ''.join(parts)


@rule(code="like-leading-wildcard", severity="warning",
      title="ПОДОБНО с ведущим спецсимволом — индекс не используется")
def check_like_leading_wildcard(ctx):
    """Флагует ПОДОБНО, где шаблон начинается с % или _ (ведущий wildcard).

    Читает операнд из AST-модели conditions[].param — только операнд ПОДОБНО,
    без засорения арифметикой из других условий WHERE.
    Severity=warning: прямое влияние на производительность.
    Параметры (&Шаблон) и поля пропускаются — значение неизвестно.
    """
    out = []
    for line, param in _iter_like_params(ctx):
        content = _like_literal_content(param)
        if content is not None and content and content[0] in ('%', '_'):
            out.append(Finding(
                code="like-leading-wildcard",
                severity="warning",
                line=line,
                message="Шаблон ПОДОБНО начинается с % или _ — индекс не используется.",
            ))
    return out


@rule(code="like-square-brackets", severity="error",
      title="ПОДОБНО с [...] или [^...] — не работает на IBM DB2")
def check_like_square_brackets(ctx):
    """Флагует ПОДОБНО, где шаблон содержит незаэкранированные '['.

    Читает операнд из AST-модели conditions[].param.
    Определяет символ-экранировщик: ищет СПЕЦСИМВОЛ "..." в param (case-insensitive).
    Флагует, если в literal_content есть '[', не предшествуемый символом экранировщика.
    Severity=error: гарантированный сбой на IBM DB2.
    """
    out = []
    for line, param in _iter_like_params(ctx):
        content = _like_literal_content(param)
        if content is None:
            continue
        # Определить символ экранировщика: СПЕЦСИМВОЛ "X" в param
        escape_char = None
        m = re.search(r'(?i)СПЕЦСИМВОЛ\s+"(.)', param)
        if m:
            escape_char = m.group(1)
        # Проверить наличие незаэкранированного '['
        flagged = False
        for idx, ch in enumerate(content):
            if ch == '[':
                if escape_char is None:
                    flagged = True
                    break
                if idx == 0 or content[idx - 1] != escape_char:
                    flagged = True
                    break
        if flagged:
            out.append(Finding(
                code="like-square-brackets",
                severity="error",
                line=line,
                message="Шаблон ПОДОБНО содержит [набор] — не работает на IBM DB2.",
            ))
    return out


@rule(code="like-concatenation", severity="warning",
      title="ПОДОБНО: шаблон формируется полем/конкатенацией")
def check_like_concatenation(ctx):
    """Флагует ПОДОБНО, где шаблон собирается конкатенацией или является полем.

    Читает операнд из AST-модели conditions[].param.
    Флагует, если param содержит '+' (конкатенация) ИЛИ операнд не начинается
    с '"' (строковый литерал) и не начинается с '&' (параметр).
    Severity=warning: нарушение п.1 стандарта.
    """
    out = []
    for line, param in _iter_like_params(ctx):
        op = param.strip()
        if '+' in param or (not op.startswith('"') and not op.startswith('&')):
            out.append(Finding(
                code="like-concatenation",
                severity="warning",
                line=line,
                message="Шаблон ПОДОБНО формируется полем/конкатенацией, а не литералом/параметром.",
            ))
    return out


# ── Округление результатов арифметических операций ──────

@rule(code="division-without-cast", severity="warning",
      title="Деление без ВЫРАЗИТЬ(... КАК Число(m,n)) — точность может различаться на разных СУБД")
def check_division_without_cast(ctx):
    """Флагует деление (/), не обёрнутое в ВЫРАЗИТЬ(... КАК Число(m,n)).

    при арифметических операциях деления точность результата
    может различаться на разных СУБД. Рекомендуется явно указывать разрядность
    через ВЫРАЗИТЬ(... КАК Число(m,n)).

    Работает по AST-модели: для каждого поля проверяет fields[].expression.
    Флагует, если expression содержит '/' И expression (в верхнем регистре)
    не начинается с 'ВЫРАЗИТЬ(' (то есть результат деления не обёрнут).
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for field in model_dict.get("fields") or []:
            expr = field.get("expression") or ""
            if not expr:
                continue
            if "/" not in expr:
                continue
            expr_upper = expr.upper()
            if expr_upper.startswith("ВЫРАЗИТЬ("):
                continue
            out.append(Finding(
                code="division-without-cast",
                severity="warning",
                line=line,
                message=(
                    "Деление без явной разрядности: рекомендуется обернуть результат (или операнды) "
                    "в ВЫРАЗИТЬ(... КАК Число(m,n)) — точность может различаться на разных СУБД."
                ),
            ))
    return out


@rule(code="avg-without-cast", severity="warning",
      title="СРЕДНЕЕ без ВЫРАЗИТЬ(... КАК Число(m,n)) — точность может различаться на разных СУБД")
def check_avg_without_cast(ctx):
    """Флагует агрегатную функцию СРЕДНЕЕ, не обёрнутую в ВЫРАЗИТЬ(... КАК Число(m,n)).

    агрегатная функция СРЕДНЕЕ может давать результат разной точности
    на разных СУБД. Рекомендуется ВЫРАЗИТЬ(СРЕДНЕЕ(...) КАК Число(m,n)).

    Работает по AST-модели: если поле имеет func == "Среднее" (т.е. СРЕДНЕЕ не
    обёрнуто ни в какое выражение — в частности, не в ВЫРАЗИТЬ), то выдаётся
    предупреждение. Когда СРЕДНЕЕ обёрнуто в ВЫРАЗИТЬ, парсер представляет всё
    поле как expression (не func), поэтому двойных срабатываний не бывает.
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for field in model_dict.get("fields") or []:
            func = field.get("func") or ""
            if func.upper() == "СРЕДНЕЕ":
                out.append(Finding(
                    code="avg-without-cast",
                    severity="warning",
                    line=line,
                    message=(
                        "СРЕДНЕЕ без явной разрядности: рекомендуется обернуть в "
                        "ВЫРАЗИТЬ(СРЕДНЕЕ(...) КАК Число(m,n)) — точность может различаться "
                        "на разных СУБД."
                    ),
                ))
    return out


# ── ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ ────────────────────────

@rule(code="full-join", severity="warning",
      title="ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ не рекомендуется — снижает производительность на PostgreSQL")
def check_full_join(ctx):
    """Флагует использование ПОЛНОГО ВНЕШНЕГО СОЕДИНЕНИЯ по AST-модели.

    «в общем случае не рекомендуется использовать конструкцию
    ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ в запросах» — в особенности при наличии двух и более
    таких конструкций, когда производительность на PostgreSQL значительно снижается.
    Severity=warning: стандарт является методической рекомендацией («не рекомендуется»),
    а не запретом.

    Работает по AST-модели: joins[].leftAll == True И joins[].rightAll == True —
    признак ПОЛНОГО ВНЕШНЕГО СОЕДИНЕНИЯ. Одно срабатывание на запрос, если в нём
    присутствует хотя бы одно ПОЛНОЕ СОЕДИНЕНИЕ. Если модель недоступна — пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for join in model_dict.get("joins") or []:
            if join.get("leftAll") and join.get("rightAll"):
                out.append(Finding(
                    code="full-join",
                    severity="warning",
                    line=line,
                    message=(
                        "ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ не рекомендуется: "
                        "значительно снижает производительность на PostgreSQL. "
                        "По возможности перепишите запрос через ОБЪЕДИНИТЬ ВСЕ."
                    ),
                ))
                break  # одно срабатывание на запрос
    return out


# ── Вложенные запросы в условии соединения ───────────

@rule(code="subquery-in-join-condition", severity="warning",
      title="Вложенный запрос в условии соединения (ПО) — не следует")
def check_subquery_in_join_condition(ctx):
    """Флагует вложенные ВЫБРАТЬ в условии соединения (ПО).

    «Не следует использовать вложенные запросы в условии соединения.
    Это может привести к значительному замедлению запроса и (в отдельных
    случаях) к его полной неработоспособности на некоторых СУБД».
    Severity=warning: стандарт формулирует рекомендацию («не следует»), а не
    категорический запрет — хотя последствия на отдельных СУБД серьёзны.

    Работает по AST-модели: итерирует joins[].conditions[] каждого запроса;
    если условие имеет custom=True и его expression (в верхнем регистре)
    содержит слово «ВЫБРАТЬ» — это вложенный подзапрос в условии соединения.
    Вложенные запросы в ИЗ (table.subquery) и в полях ВЫБРАТЬ
    не попадают в joins.conditions и не флагуются.
    Одно срабатывание на каждый запрос, содержащий хотя бы одно такое условие.
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        found = False
        for join in model_dict.get("joins") or []:
            if found:
                break
            for cond in join.get("conditions") or []:
                if cond.get("custom") and "ВЫБРАТЬ" in (cond.get("expression") or "").upper():
                    found = True
                    break
        if found:
            out.append(Finding(
                code="subquery-in-join-condition",
                severity="warning",
                line=line,
                message=(
                    "Вложенный запрос в условии соединения (ПО): "
                    "может значительно замедлить запрос или привести к его "
                    "неработоспособности на некоторых СУБД. "
                    "Перепишите через временную таблицу."
                ),
            ))
    return out


# ── Соединения с вложенными запросами и виртуальными таблицами ──

@rule(code="join-to-subquery", severity="warning",
      title="Соединение с вложенным запросом (ИЗ) — не следует, используйте временную таблицу")
def check_join_to_subquery(ctx):
    """Флагует соединение, в котором один из источников данных является вложенным запросом.

    «При написании запросов не следует использовать соединения
    с вложенными запросами. Следует соединять друг с другом только объекты
    метаданных или временные таблицы».
    Severity=warning: стандарт формулирует рекомендацию («не следует»), а не
    категорический запрет; исключение допускается, когда подзапрос сканирует
    мало записей.

    Работает по AST-модели: строит map {id → table} для каждого запроса;
    для каждого join проверяет, есть ли у joined-таблицы ключ «subquery».
    Виртуальные таблицы (table.virtual) НЕ флагуются этим правилом — для них
    отдельное ручное требование в чеклисте.
    Одно срабатывание на запрос, даже если подзапросов несколько.
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        tables_by_id = {t["id"]: t for t in (model_dict.get("tables") or [])}
        found = False
        for join in model_dict.get("joins") or []:
            if found:
                break
            joined_id = join.get("joinedTableId")
            if not joined_id:
                # Fallback: check both sides
                for tid in (join.get("leftTableId"), join.get("rightTableId")):
                    tbl = tables_by_id.get(tid) if tid else None
                    if tbl and "subquery" in tbl:
                        found = True
                        break
            else:
                tbl = tables_by_id.get(joined_id)
                if tbl and "subquery" in tbl:
                    found = True
        if found:
            out.append(Finding(
                code="join-to-subquery",
                severity="warning",
                line=line,
                message=(
                    "Соединение с вложенным запросом: оптимизатор СУБД не может оценить "
                    "объём подзапроса, что приводит к непредсказуемому плану выполнения. "
                    "Перепишите через временную таблицу."
                ),
            ))
    return out


# ── Эффективные условия запросов ─────────────────────

# Функции, применяемые к полям в условиях ГДЕ/ПО — блокируют использование индекса.
# Стандарт строковые функции → заменять на ПОДОБНО.
# Стандарт функции дат → заменять на МЕЖДУ.
_CONDITION_FUNCTIONS = re.compile(
    r"^(?:"
    r"ПОДСТРОКА|СТРОКА|СТРДЛИНА|СТРНАЙТИ|ВРЕГ|НРЕГ|СОКРЛ|СОКРП|СОКРЛП|СИМВОЛ|"
    r"МЕСЯЦ|ГОД|ДЕНЬ|ДЕНЬНЕДЕЛИ|ЧАС|МИНУТА|СЕКУНДА|"
    r"НАЧАЛОПЕРИОДА|КОНЕЦПЕРИОДА|ДОБАВИТЬКДАТЕ|РАЗНОСТЬДАТ|"
    r"ДАТАВРЕМЯ|КВАРТАЛ"
    r")\(",
    re.UNICODE,
)


@rule(code="function-in-condition", severity="warning",
      title="Функция применяется к полю в условии ГДЕ — индекс не используется")
def check_function_in_condition(ctx):
    """Флагует условие WHERE, где строковая или датовая функция применяется к полю.

    «НЕПРАВИЛЬНО: ПОДСТРОКА(Таблица.Поле, 1, 6) = "строка"» — блокирует индекс;
    стандарт предписывает заменять на ПОДОБНО или вычисляемое поле.
    «НЕПРАВИЛЬНО: МЕСЯЦ(Таблица.Поле) = 1» — блокирует индекс;
    стандарт предписывает заменять на МЕЖДУ &НачалоПериода И &КонецПериода.

    Severity=warning: стандарт показывает пример «НЕПРАВИЛЬНО», неявно запрещая
    паттерн («нельзя использовать … функции» в основном условии).

    Работает по AST-модели: срабатывает, только если в запросе НЕТ ни одного
    структурного условия (custom=False) — т.е. функция применена в основном
    условии. При наличии структурного (потенциально индексного) условия функция
    считается дополнительной — стандарт это допускает, и правило не срабатывает
    (без метаданных основное/дополнительное точно не различить, поэтому берём
    консервативный критерий, исключающий ложные срабатывания). Если модель
    недоступна — пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        conds = model_dict.get("conditions") or []
        if any(not c.get("custom", True) for c in conds):
            continue  # есть структурное (индексное) условие → функция в дополнительном → OK
        for cond in conds:
            if not cond.get("custom"):
                continue
            expr = (cond.get("expression") or "").upper().lstrip()
            if _CONDITION_FUNCTIONS.match(expr):
                out.append(Finding(
                    code="function-in-condition",
                    severity="warning",
                    line=line,
                    message=(
                        "Функция применяется к полю в основном условии ГДЕ — "
                        "поиск по индексу невозможен. "
                        "Для строковых функций используйте ПОДОБНО, "
                        "для функций дат — МЕЖДУ."
                    ),
                ))
                break  # одно срабатывание на запрос
    return out


@rule(code="case-as-sole-condition", severity="warning",
      title="ВЫБОР как единственное условие ГДЕ — индекс не используется")
def check_case_as_sole_condition(ctx):
    """Флагует ВЫБОР (CASE WHEN) в роли единственного условия ГДЕ.

    «Выражение ВЫБОР можно использовать только в дополнительных условиях».
    «НЕПРАВИЛЬНО: ГДЕ ВЫБОР КОГДА … ТОГДА … ИНАЧЕ … КОНЕЦ» — поиск по индексу
    не применяется. «ПРАВИЛЬНО»: ВЫБОР после основного условия, объединённого по И.

    Severity=warning: стандарт формулирует ограничение («можно только в доп. условиях»),
    а абсолютный запрет — лишь при отсутствии индексного основного условия.

    Работает по AST-модели: если conditions[] содержит хотя бы одно custom-условие
    с expression, начинающимся с «ВЫБОР», И при этом нет ни одного структурного
    условия (custom=False), то ВЫБОР является единственным/основным условием.
    Если модель недоступна — пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        conds = model_dict.get("conditions") or []
        has_structured = any(not c.get("custom", True) for c in conds)
        if has_structured:
            continue  # есть структурное (индексное) условие → ВЫБОР в дополнительном месте → OK
        for cond in conds:
            if not cond.get("custom"):
                continue
            expr = (cond.get("expression") or "").upper().lstrip()
            if expr.startswith("ВЫБОР ") or expr.startswith("ВЫБОР\n") or expr == "ВЫБОР":
                out.append(Finding(
                    code="case-as-sole-condition",
                    severity="warning",
                    line=line,
                    message=(
                        "Выражение ВЫБОР используется как единственное/основное условие ГДЕ — "
                        "поиск по индексу не применяется. "
                        "ВЫБОР допустим только как дополнительное условие "
                        "(после основного индексного через И)."
                    ),
                ))
                break  # одно срабатывание на запрос
    return out


# ── Обращения к виртуальным таблицам ────────────────

@rule(code="vt-filter-in-where", severity="warning",
      title="Условие на виртуальную таблицу в ГДЕ — следует передать в параметры виртуальной таблицы")
def check_vt_filter_in_where(ctx):
    """Флагует условия ГДЕ, которые фильтруют поле виртуальной таблицы напрямую.

    «Не рекомендуется обращаться к виртуальным таблицам при помощи
    условий в секции ГДЕ». При таком запросе СУБД сначала извлечёт все записи
    виртуальной таблицы, а затем отфильтрует их — оптимизатор не может выбрать
    эффективный план. Фильтры следует передавать в параметры виртуальной таблицы.
    Severity=warning: стандарт формулирует «Не рекомендуется» (п.1).

    Работает по AST-модели: строит map {id → table} для каждого запроса;
    если у таблицы есть ключ "virtual", таблица — виртуальная.
    Затем проходит по conditions[]: если tableId совпадает с id виртуальной
    таблицы — условие фильтрует ВТ через ГДЕ → флаг.
    Условия на НЕ-виртуальные таблицы игнорируются.
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        tables_by_id = {t["id"]: t for t in (model_dict.get("tables") or [])}
        virtual_ids = {tid for tid, t in tables_by_id.items() if "virtual" in t}
        if not virtual_ids:
            continue
        flagged_ids = set()
        for cond in model_dict.get("conditions") or []:
            tid = cond.get("tableId")
            if tid and tid in virtual_ids and tid not in flagged_ids:
                flagged_ids.add(tid)
                tbl = tables_by_id[tid]
                vt_name = tbl.get("fullName") or tid
                out.append(Finding(
                    code="vt-filter-in-where",
                    severity="warning",
                    line=line,
                    message=(
                        f"Условие ГДЕ фильтрует поле виртуальной таблицы «{vt_name}»: "
                        f"передайте условие в параметры виртуальной таблицы, "
                        f"а не в секцию ГДЕ — иначе СУБД не может выбрать оптимальный план."
                    ),
                ))
    return out


# ── Эффективное обращение к ВТ Остатки ───────────────

# Суффикс «.Остатки» в fullName — признак ВТ Остатки накопления или бухгалтерии.
# ОстаткиИОбороты имеет суффикс «.ОстаткиИОбороты» и не попадает под это правило.
_OSTATOK_SUFFIX = re.compile(r"\.Остатки$", re.UNICODE | re.IGNORECASE)


@rule(code="ostatok-with-period", severity="info",
      title="ВТ Остатки: указана дата — СУБД также читает таблицу движений")
def check_ostatok_with_period(ctx):
    """Флагует обращение к ВТ «Остатки», у которой заполнен параметр даты.

    если при обращении к виртуальной таблице «Остатки» в первый параметр
    передаётся дата, платформа 1С генерирует запрос, который читает не только
    хранимую таблицу остатков, но и таблицу движений (более медленный вложенный
    запрос с группировкой). Для получения ТЕКУЩИХ остатков дату указывать не нужно —
    следует оставить первый параметр пустым.

    Сигнал: у виртуальной таблицы с суффиксом «.Остатки» в fullName заполнено
    поле virtual.period (парсер помещает туда первый параметр в скобках, если он
    непустой). Пустой первый параметр (…, Условие = …) или отсутствие скобок
    означает «текущие остатки» — правило не срабатывает.

    Правило НЕ дублирует vt-filter-in-where (тот флагует условия ГДЕ на
    любые виртуальные таблицы). Данное правило флагует параметр периода,
    специфичный именно для ВТ Остатки.

    Если модель недоступна (node/бандл отсутствуют) — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for tbl in model_dict.get("tables") or []:
            virtual = tbl.get("virtual")
            if not virtual:
                continue
            full_name = tbl.get("fullName") or ""
            if not _OSTATOK_SUFFIX.search(full_name):
                continue
            period = virtual.get("period")
            if period:
                out.append(Finding(
                    code="ostatok-with-period",
                    severity="info",
                    line=line,
                    message=(
                        f"ВТ «{full_name}»: передана дата в первый параметр «{period}» — "
                        f"платформа будет читать хранимую таблицу остатков И таблицу движений. "
                        f"Для текущих остатков уберите дату (оставьте первый параметр пустым)."
                    ),
                ))
    return out


# ── Использование временных таблиц ──────────────────────

def _temp_table_used_in_join(member_model, temp_name_upper):
    """True, если temporaryTableName (верхний регистр) участвует в JOIN данного запроса."""
    tables_by_id = {t["id"]: t for t in (member_model.get("tables") or [])}
    temp_ids = {
        tid for tid, t in tables_by_id.items()
        if (t.get("fullName") or "").upper() == temp_name_upper
    }
    if not temp_ids:
        return False
    for join in member_model.get("joins") or []:
        for side in (join.get("leftTableId"), join.get("rightTableId"),
                     join.get("seedTableId"), join.get("joinedTableId")):
            if side and side in temp_ids:
                return True
    return False


def _temp_table_used_in_in_subquery(member_model, temp_name_upper):
    """True, если temp table встречается в подзапросе В (...) в данном запросе."""
    for cond in member_model.get("conditions") or []:
        if cond.get("operator") != "В":
            continue
        subq = cond.get("subquery")
        if not subq:
            continue
        for sq_stmt in subq.get("members", []) or []:
            for tbl in (sq_stmt.get("model") or {}).get("tables") or []:
                if (tbl.get("fullName") or "").upper() == temp_name_upper:
                    return True
    return False


@rule(code="temp-table-join-no-index", severity="warning",
      title="Временная таблица участвует в соединении, но создана без ИНДЕКСИРОВАТЬ ПО")
def check_temp_table_join_no_index(ctx):
    """Флагует ПОМЕСТИТЬ-оператор, если ВТ используется в JOIN, но не имеет ИНДЕКСИРОВАТЬ ПО.

    «Большая временная таблица участвует в соединении (не важно,
    с какой стороны). В индекс следует добавлять поля, участвующие в условии ПО».
    Автоматически слово «большая» проверить нельзя (неизвестен объём данных),
    поэтому правило срабатывает при отсутствии ИНДЕКСИРОВАТЬ ПО независимо от объёма —
    это консервативная эвристика уровня warning.

    Алгоритм:
    1. Собрать имена всех ВТ, созданных без ИНДЕКСИРОВАТЬ ПО в пакете.
    2. Пройти по следующим операторам пакета; если ВТ участвует в joins[] —
       сообщить об отсутствии индекса на операторе ПОМЕСТИТЬ.

    Работает только по AST-модели. Если модель недоступна — пропускается.
    """
    batch = ctx.model
    if not isinstance(batch, dict):
        return []
    stmts_batch = batch.get("members", []) or []
    stmts_src = ctx.statements  # (line, text) для каждого оператора

    # Шаг 1: для каждого оператора пакета собрать map createTemp-ВТ → (line, has_idx)
    # Индекс оператора в пакете совпадает с индексом в ctx.statements.
    temp_table_info = {}  # name_upper → (line, has_idx)
    for si, stmt in enumerate(stmts_batch):
        line = stmts_src[si][0] if si < len(stmts_src) else 1
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            if model.get("queryType") == "createTemp":
                name = (model.get("tempTableName") or "").upper()
                if name:
                    has_idx = bool(model.get("indexing"))
                    # Сохраняем первое вхождение (самое ранее) с флагом индекса.
                    if name not in temp_table_info:
                        temp_table_info[name] = (line, has_idx)
                    elif has_idx:
                        # appendTemp с индексом — обновляем флаг.
                        temp_table_info[name] = (temp_table_info[name][0], True)

    out = []
    flagged = set()
    # Шаг 2: смотрим все операторы на предмет использования ВТ в JOIN.
    for si, stmt in enumerate(stmts_batch):
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            for name_upper, (create_line, has_idx) in temp_table_info.items():
                if has_idx:
                    continue  # индекс есть — всё нормально
                if name_upper in flagged:
                    continue
                if _temp_table_used_in_join(model, name_upper):
                    flagged.add(name_upper)
                    out.append(Finding(
                        code="temp-table-join-no-index",
                        severity="warning",
                        line=create_line,
                        message=(
                            f"Временная таблица «{name_upper}» участвует в соединении, "
                            f"но создана без ИНДЕКСИРОВАТЬ ПО — добавьте индекс по полям "
                            f"условия соединения (ПО)."
                        ),
                    ))
    return out


@rule(code="temp-table-in-no-index", severity="warning",
      title="Временная таблица используется в подзапросе В (...), но создана без ИНДЕКСИРОВАТЬ ПО")
def check_temp_table_in_no_index(ctx):
    """Флагует ПОМЕСТИТЬ-оператор, если ВТ используется в условии В (...), но нет ИНДЕКСИРОВАТЬ ПО.

    «Обращение к временной таблице выполняется в подзапросе
    конструкции логического оператора В (...). В индекс следует добавлять поля
    временной таблицы из списка выбора, соответствующие перечисленным с левой
    стороны логического оператора В (...)».

    Алгоритм аналогичен check_temp_table_join_no_index, но проверяет подзапросы
    в conditions[].subquery (operator == "В") следующих операторов пакета.

    Работает только по AST-модели. Если модель недоступна — пропускается.
    """
    batch = ctx.model
    if not isinstance(batch, dict):
        return []
    stmts_batch = batch.get("members", []) or []
    stmts_src = ctx.statements

    temp_table_info = {}
    for si, stmt in enumerate(stmts_batch):
        line = stmts_src[si][0] if si < len(stmts_src) else 1
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            if model.get("queryType") == "createTemp":
                name = (model.get("tempTableName") or "").upper()
                if name:
                    has_idx = bool(model.get("indexing"))
                    if name not in temp_table_info:
                        temp_table_info[name] = (line, has_idx)
                    elif has_idx:
                        temp_table_info[name] = (temp_table_info[name][0], True)

    out = []
    flagged = set()
    for si, stmt in enumerate(stmts_batch):
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            for name_upper, (create_line, has_idx) in temp_table_info.items():
                if has_idx:
                    continue
                if name_upper in flagged:
                    continue
                if _temp_table_used_in_in_subquery(model, name_upper):
                    flagged.add(name_upper)
                    out.append(Finding(
                        code="temp-table-in-no-index",
                        severity="warning",
                        line=create_line,
                        message=(
                            f"Временная таблица «{name_upper}» используется в подзапросе "
                            f"В (...), но создана без ИНДЕКСИРОВАТЬ ПО — добавьте индекс "
                            f"по полям из списка выбора подзапроса."
                        ),
                    ))
    return out


# ── Вычисление количества записей в запросах ─────────

# Регулярное выражение: expression == "СУММА(1)" или "ЕСТЬNULL(СУММА(1), 0)"
# (с учётом возможных пробелов вокруг 1 и запятой).
_SUM_ONE_RE = re.compile(
    r"^(?:ЕСТЬNULL\s*\(\s*)?СУММА\s*\(\s*1\s*\)(?:\s*,\s*0\s*\))?$",
    re.IGNORECASE | re.UNICODE,
)

# Регулярное выражение: expression == "СУММА(ВЫБОР ... КОНЕЦ)"
# где выражение содержит «ТОГДА 1» или «ИНАЧЕ 1» (счётчик в единицах),
# но НЕ содержит «ВЫРАЗИТЬ» (не обёрнуто с расширенной разрядностью).
_SUM_CASE_ONE_RE = re.compile(
    r"^СУММА\s*\(ВЫБОР\s+",
    re.IGNORECASE | re.UNICODE,
)
# Проверяем «ТОГДА 1» или «ИНАЧЕ 1» (без ВЫРАЗИТЬ) в теле СУММА(ВЫБОР...).
_CASE_HAS_LITERAL_1 = re.compile(
    r"(?:ТОГДА|ИНАЧЕ)\s+1(?:\s|$|\))",
    re.IGNORECASE | re.UNICODE,
)


@rule(code="sum-one-for-count", severity="warning",
      title="СУММА(1) вместо КОЛИЧЕСТВО(*) — переполнение при ≥10 млн записей")
def check_sum_one_for_count(ctx):
    """Флагует СУММА(1) и ЕСТЬNULL(СУММА(1), 0) как замену КОЛИЧЕСТВО(*).

    «при вычислении количества записей следует всегда использовать
    функцию КОЛИЧЕСТВО, а не СУММА». При количестве записей 10 млн. и более
    СУММА(1) переполняется из-за разрядности числа по умолчанию (7 знаков),
    которую использует 1С:Предприятие в СУБД. Severity=warning: стандарт
    формулирует рекомендацию («следует использовать КОЛИЧЕСТВО, а не СУММА»);
    последствие (переполнение) наступает лишь при больших объёмах.

    Работает по AST-модели: проверяет fields[].expression на совпадение с
    СУММА(1) или ЕСТЬNULL(СУММА(1), 0). Если модель недоступна — пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for field in model_dict.get("fields") or []:
            expr = (field.get("expression") or "").strip()
            if not expr:
                continue
            if _SUM_ONE_RE.match(expr.upper()):
                out.append(Finding(
                    code="sum-one-for-count",
                    severity="warning",
                    line=line,
                    message=(
                        f"СУММА(1) (или ЕСТЬNULL(СУММА(1), 0)) не следует использовать для подсчёта записей: "
                        f"при ≥10 млн. записей произойдёт переполнение из-за разрядности числа по умолчанию. "
                        f"Используйте КОЛИЧЕСТВО(*)."
                    ),
                ))
    return out


@rule(code="sum-case-without-cast", severity="warning",
      title="СУММА(ВЫБОР...ТОГДА 1...) без ВЫРАЗИТЬ — переполнение при ≥10 млн записей")
def check_sum_case_without_cast(ctx):
    """Флагует СУММА(ВЫБОР...ТОГДА 1...) без ВЫРАЗИТЬ(1 КАК ЧИСЛО(17,0)).

    когда условный подсчёт нельзя выразить через КОЛИЧЕСТВО,
    «следует расширить разрядность числа с помощью ВЫРАЗИТЬ(1 КАК ЧИСЛО(17, 0))».
    Без ВЫРАЗИТЬ разрядность числа по умолчанию (7 знаков) не даёт посчитать
    более 10 млн. условных записей. Severity=warning: «следует» (рекомендация).

    Работает по AST-модели: если expression начинается с СУММА(ВЫБОР и содержит
    «ТОГДА 1» или «ИНАЧЕ 1» (счётчик — литеральная единица), но не содержит
    «ВЫРАЗИТЬ» — флагуется.
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for field in model_dict.get("fields") or []:
            expr = (field.get("expression") or "").strip()
            if not expr:
                continue
            expr_upper = expr.upper()
            if not _SUM_CASE_ONE_RE.match(expr_upper):
                continue
            # Есть ВЫРАЗИТЬ — уже обёрнуто корректно
            if "ВЫРАЗИТЬ" in expr_upper:
                continue
            # Убеждаемся, что это счётчик (ТОГДА 1 или ИНАЧЕ 1)
            if _CASE_HAS_LITERAL_1.search(expr_upper):
                out.append(Finding(
                    code="sum-case-without-cast",
                    severity="warning",
                    line=line,
                    message=(
                        "СУММА(ВЫБОР...ТОГДА 1...) без ВЫРАЗИТЬ(1 КАК ЧИСЛО(17, 0)): "
                        "при ≥10 млн. условных записей произойдёт переполнение. "
                        "Оберните литерал 1 в ВЫРАЗИТЬ(1 КАК ЧИСЛО(17, 0))."
                    ),
                ))
    return out


# ── Запросы в динамических списках ───────────────────

def _all_sources_are_temp(member_model, known_temp_names_upper):
    """True, если ВСЕ источники данных запроса — временные таблицы (нет точки в fullName
    и fullName совпадает с именем ранее созданной ВТ — или вообще нет точки, если
    имена ВТ неизвестны). Пустой список источников → False (нет смысла флаговать).
    """
    tables = member_model.get("tables") or []
    if not tables:
        return False
    for tbl in tables:
        full_name = tbl.get("fullName") or ""
        # Реальные таблицы метаданных всегда содержат точку (Справочник.Товары).
        # Временные таблицы — нет.
        if "." in full_name:
            return False
        if known_temp_names_upper and full_name.upper() not in known_temp_names_upper:
            # Имя не найдено среди известных ВТ — скорее всего это не ВТ, пропуск.
            return False
    return True


@rule(code="last-query-from-temp-only", severity="warning",
      title="Последний запрос пакета выбирает только из временной таблицы — это уже не динамический список")
def check_last_query_from_temp_only(ctx):
    """Флагует пакет, в котором последний оператор SELECT выбирает данные ТОЛЬКО
    из временных таблиц (нет ни одной реальной таблицы метаданных).

    «Если последний запрос динамического списка выбирает данные
    только из ранее созданной временной таблицы, то это уже не динамический список
    и следует перепроектировать его запрос и, скорее всего, метаданные,
    используемые запросом».

    Алгоритм:
    1. Собрать имена всех ВТ, созданных через ПОМЕСТИТЬ в пакете.
    2. Найти последний оператор с queryType == "select" (или без queryType).
    3. Если все его источники данных — временные таблицы из шага 1 — флаговать.

    Severity=warning: формулировка «следует перепроектировать» (рекомендация).
    Одно срабатывание на весь пакет.
    Если модель недоступна — правило пропускается.
    """
    batch = ctx.model
    if not isinstance(batch, dict):
        return []
    stmts_batch = batch.get("members", []) or []
    if not stmts_batch:
        return []
    stmts_src = ctx.statements

    # Шаг 1: собрать имена ВТ из createTemp-операторов.
    known_temp = set()
    for stmt in stmts_batch:
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            if model.get("queryType") == "createTemp":
                name = (model.get("tempTableName") or "").upper()
                if name:
                    known_temp.add(name)

    if not known_temp:
        return []  # нет временных таблиц — правило неприменимо

    # Шаг 2: найти последний SELECT-оператор (не createTemp, не dropTemp).
    last_select_si = None
    for si, stmt in enumerate(stmts_batch):
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            qt = model.get("queryType") or "select"
            if qt == "select":
                last_select_si = si
                break

    if last_select_si is None:
        return []

    # Шаг 3: проверить, что все источники последнего SELECT — из ВТ.
    last_stmt = stmts_batch[last_select_si]
    for member in last_stmt.get("members", []) or []:
        model = member.get("model") or {}
        qt = model.get("queryType") or "select"
        if qt != "select":
            continue
        if not _all_sources_are_temp(model, known_temp):
            return []  # хотя бы один участник объединения читает реальную таблицу

    line = stmts_src[last_select_si][0] if last_select_si < len(stmts_src) else 1
    return [Finding(
        code="last-query-from-temp-only",
        severity="warning",
        line=line,
        message=(
            "Последний запрос пакета выбирает данные только из временной таблицы — "
            "при использовании в динамическом списке платформа не будет использовать "
            "динамическое считывание данных. Перепроектируйте запрос, чтобы основная "
            "таблица метаданных читалась напрямую."
        ),
    )]


@rule(code="autoorder-not-recommended", severity="warning",
      title="АВТОУПОРЯДОЧИВАНИЕ не рекомендуется — разработчик не контролирует поля сортировки")
def check_autoorder_not_recommended(ctx):
    """Предупреждает о любом использовании АВТОУПОРЯДОЧИВАНИЕ без ПЕРВЫЕ по AST-модели.

    «В остальных случаях конструкцию АВТОУПОРЯДОЧИВАНИЕ также не
    рекомендуется использовать, так как разработчик не контролирует, какие именно
    поля будут использованы для упорядочивания».
    Итерирует iter_query_models(ctx); для каждого запроса проверяет order.auto == True.
    Если тот же запрос имеет selection.top — он покрывается error-правилом
    autoorder-with-first, поэтому warning здесь не выдаётся (нет двойных срабатываний).
    Если модель недоступна — правило пропускается.
    """
    out = []
    for line, distinct, model in iter_query_models(ctx):
        auto = bool((model.get("order") or {}).get("auto"))
        has_first = bool((model.get("selection") or {}).get("top"))
        if auto and not has_first:
            out.append(Finding(
                code="autoorder-not-recommended",
                severity="warning",
                line=line,
                message=(
                    "АВТОУПОРЯДОЧИВАНИЕ не рекомендуется — "
                    "упорядочивайте явно через УПОРЯДОЧИТЬ ПО."
                ),
            ))
    return out
