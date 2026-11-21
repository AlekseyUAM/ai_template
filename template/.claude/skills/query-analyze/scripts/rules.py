# rules.py - registry of automatic 1C query checks.
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

# Standalone SDBL parser bundle (see vendor/README.md). Module-level so tests
# can substitute the path via monkeypatch.
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
    """The content of "..." string literals and //... line comments is replaced
    with spaces of the same length (line breaks preserved). Rules that work on query
    code must not trigger on words inside strings and comments. The length and
    line numbers are preserved - positions match the source text."""
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
        # 1C export files often start with a BOM (U+FEFF): the parser lexer does not
        # understand it -> false query-not-parseable. Strip it; line numbers stay.
        if text.startswith("\ufeff"):
            text = text[1:]
        self.text = text
        self._lines = None
        self._upper = None
        self._statements = None
        self._code = None
        self._code_upper = None
        self._model = None
        self._model_parsed = False
        self.model_error = None
        # Set only when the parser ran and returned a syntax error
        # ({"error": ...}) - unlike an infrastructure skip (no node/bundle).
        self.parse_error = None
        self.parse_line = None

    @property
    def lines(self):
        if self._lines is None:
            self._lines = self.text.split("\n")
        return self._lines

    @property
    def upper(self):
        if self._upper is None:
            self._upper = self.text.upper()  # for Cyrillic the length is preserved
        return self._upper

    @property
    def code(self):
        """Query text without the content of strings and comments (see _sanitize)."""
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
        """Structural query model (BatchDocument) from the vendored SDBL parser,
        or None if parsing is unavailable. Runs `node vendor/sdbl_parse.js`,
        caches the result. Never throws - on any problem returns None
        and writes the reason to self.model_error (model rules are then skipped)."""
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
            self.parse_error = str(data["error"])
            m = re.search(r"разбора\s+(\d+):", self.parse_error)
            self.parse_line = int(m.group(1)) if m else None
            self.model_error = f"ошибка разбора запроса: {self.parse_error}"
            return None
        self._model = data
        return data


def iter_query_models(ctx):
    """Walks the member queries of the parsed model.
    yield (line, distinct, model_dict): line - start line of the package statement
    (from ctx.statements, best-effort; 1 if not matched), distinct - flag of a
    union member (False = added via ОБЪЕДИНИТЬ ВСЕ), model_dict -
    QueryModel. If the model is unavailable (no node/bundle or parse error) -
    yields nothing (the model rule is correctly skipped)."""
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


# ── Query text parseability ─────────────────────

@rule(code="query-not-parseable", severity="warning",
      title="Текст запроса не разбирается парсером — не откроется конструктором")
def check_query_not_parseable(ctx):
    """If the SDBL parser returned a syntax error, the query text will not open in
    the query designer (and is usually incorrect).

    This is a SEPARATE situation from an infrastructure layer skip (no node/bundle):
    there the model is unavailable for an external reason, while here the parser ran
    and reported that the text is syntactically invalid. So it is recorded as a
    finding, not as "checks skipped". ctx.parse_error is set only when the parser
    responds with `{"error": ...}`.
    """
    _ = ctx.model  # make sure the parser ran and parse_error is recorded
    if not ctx.parse_error:
        return []
    return [Finding(
        code="query-not-parseable",
        severity="warning",
        line=ctx.parse_line or 1,
        message=(
            f"Текст запроса не разбирается парсером языка запросов и не откроется "
            f"конструктором: {ctx.parse_error}"
        ),
    )]


# ── Helper constants ────────────────────────────────

# Keywords of the 1C query language - written in uppercase.
# The list covers the most frequent words; we intentionally do NOT include:
# - «И», «В», «ПО» - too short, high chance of matching
#   identifiers and field names; they give an unacceptable false-positive rate;
# - «ССЫЛКА», «ЗНАЧЕНИЕ», «ТИРЕ» - also used as field/attribute names,
#   which makes them too noisy for heuristic search without a parser;
# - «ВЫБОР», «КОГДА», «ТОГДА», «ИНАЧЕ», «КОНЕЦ» - often occur as names
#   of fields or aliases (e.g. «КАК Конец», «КАК Начало»); without an AST parser
#   it is impossible to distinguish the ВЫБОР…КОНЕЦ keyword from a field/alias name -
#   too high a chance of false positives on identifiers.
_QUERY_KEYWORDS = [
    "ВЫБРАТЬ", "РАЗЛИЧНЫЕ", "РАЗРЕШЕННЫЕ", "ПЕРВЫЕ",
    "ИЗ", "ГДЕ", "СГРУППИРОВАТЬ", "УПОРЯДОЧИТЬ",
    "ИМЕЯ", "ОБЪЕДИНИТЬ", "ПОМЕСТИТЬ", "УНИЧТОЖИТЬ",
    "ИТОГИ", "АВТОУПОРЯДОЧИВАНИЕ", "ИЕРАРХИЯ",
    "ЛЕВОЕ", "ПРАВОЕ", "ПОЛНОЕ", "ВНУТРЕННЕЕ", "СОЕДИНЕНИЕ",
    "ПОДОБНО", "МЕЖДУ", "ЕСТЬNULL", "КАК",
]

# ── Checks ────────────────────────────────────────────────

_MANY_TABLES_THRESHOLD = 7  # with >=7 tables in one query - info


@rule(code="select-star", severity="warning",
      title="ВЫБРАТЬ * — выбирать только нужные поля")
def check_select_star(ctx):
    """Checks for ВЫБРАТЬ * using the AST model.

    Iterates iter_query_models(ctx); if at least one query field
    has expression == "*", this is ВЫБРАТЬ *. One hit per query.
    If the model is unavailable (no node/bundle), the rule is skipped.
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
    """Counts tables in each query using the AST model.

    The standard says: "5-7 tables in one query may already
    be a lot". The threshold of 7 tables is the upper bound of this range;
    a deliberately conservative info-level heuristic.
    If the model is unavailable (no node/bundle), the rule is skipped.
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


# ── Query text formatting ─────────────────────

# Regular expression to detect a keyword in non-uppercase form.
# Strategy: for each keyword, search for it with the IGNORECASE flag.
# If the found fragment differs from the reference (uppercase),
# the word is written incorrectly.
_KW_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE | re.UNICODE)
    for kw in _QUERY_KEYWORDS
]
# Mapping of pattern to the reference word
_KW_PATTERN_MAP = list(zip(_KW_PATTERNS, _QUERY_KEYWORDS))


@rule(code="keyword-lowercase", severity="warning",
      title="Ключевые слова запроса должны быть заглавными")
def check_keyword_lowercase(ctx):
    """Checks that query language keywords are written in uppercase.

    "All query language keywords are written in capital letters".
    Scans ctx.code (without strings and comments) to avoid triggering on
    words inside string literals and comments.
    Skips matches immediately preceded by «.» - that is a field
    dereference (e.g. Т.Конец), not a keyword.
    """
    out = []
    seen_positions = set()
    code = ctx.code
    for pattern, expected in _KW_PATTERN_MAP:
        for m in pattern.finditer(code):
            if m.start() in seen_positions:
                continue
            # Skip «Таблица.конец» and similar field dereferences
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


# ── Data source aliases ────────────────────

@rule(code="alias-starts-with-underscore", severity="warning",
      title="Псевдоним источника данных не должен начинаться с подчёркивания")
def check_alias_starts_with_underscore(ctx):
    """Checks DATA SOURCE aliases using the AST model.

    Iterates iter_query_models(ctx); for each source from model_dict["tables"]
    checks the alias field. Field aliases (model_dict["fields"][].alias) are not
    touched. If the model is unavailable (no node/bundle), the rule
    is skipped.
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
    """Checks DATA SOURCE aliases using the AST model.

    Iterates iter_query_models(ctx); for each source from model_dict["tables"]
    checks the alias field. Field aliases (model_dict["fields"][].alias) are not
    touched. If the model is unavailable (no node/bundle), the rule
    is skipped.
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


@rule(code="alias-collides-with-field", severity="warning",
      title="Псевдоним источника совпадает с именем поля — платформа не разрешит «Псевдоним.Реквизит» (неоднозначное поле)")
def check_alias_collides_with_field(ctx):
    """Flags a source whose alias matches a field name of ANOTHER table.

    This is the most common class of agent errors (errors 1 and 3 in errors.md): a table
    is given an alias matching the name of a dimension/attribute/tabular section field
    (`Номенклатура`, `Партия`, `Организация`...). The platform then cannot
    resolve the reference `Псевдоним.Реквизит` and reports:
        «Неоднозначное поле "Номенклатура.Ссылка"».

    Works on the AST model: collects source aliases (table.alias) and field
    names (path) from the select list, WHERE conditions and join keys together with their
    owning table (tableId). If the alias of source T matches the name
    of a field belonging to ANOTHER table (tableId != id of table T), the reference
    `T.…` is ambiguous -> finding. A match with a field of table T itself
    (normal situation) is not flagged.

    Severity=warning: with an actual reference `Псевдоним.Реквизит` this is a hard
    platform error (the query does not compile); a high-confidence heuristic,
    but formally the reference might not occur.
    If the model is unavailable, the rule is skipped.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        tables = model_dict.get("tables") or []
        alias_to_id = {}
        alias_disp = {}
        for t in tables:
            a = t.get("alias") or ""
            if a:
                alias_to_id[a.upper()] = t.get("id")
                alias_disp.setdefault(a.upper(), a)
        if not alias_to_id:
            continue
        # (field_name_upper, owner_table_id) from fields, conditions and joins
        refs = []
        for f in model_dict.get("fields") or []:
            p = f.get("path")
            if p:
                refs.append((p.upper(), f.get("tableId")))
        for c in model_dict.get("conditions") or []:
            p = c.get("path")
            if p:
                refs.append((p.upper(), c.get("tableId")))
        for j in model_dict.get("joins") or []:
            join_refs = [(j.get("leftPath"), j.get("leftTableId")),
                         (j.get("rightPath"), j.get("rightTableId"))]
            for c in j.get("conditions") or []:
                join_refs.append((c.get("leftPath"), c.get("leftTableId")))
                join_refs.append((c.get("rightPath"), c.get("rightTableId")))
            for p, tid in join_refs:
                if p:
                    refs.append((p.upper(), tid))
        reported = set()
        for name_upper, owner_id in refs:
            tid = alias_to_id.get(name_upper)
            if tid is not None and tid != owner_id and name_upper not in reported:
                reported.add(name_upper)
                out.append(Finding(
                    "alias-collides-with-field", "warning", line,
                    f"Псевдоним источника «{alias_disp[name_upper]}» совпадает с именем поля "
                    f"другой таблицы — обращение «{alias_disp[name_upper]}.Реквизит» станет "
                    f"неоднозначным (ошибка платформы «Неоднозначное поле»). "
                    f"Дайте источнику непересекающийся псевдоним "
                    f"(например «Спр{alias_disp[name_upper]}», «Док{alias_disp[name_upper]}»).",
                ))
    return out


@rule(code="query-one-line", severity="info",
      title="Запрос написан в одну строку — следует структурировать")
def check_query_one_line(ctx):
    """Detects ВЫБРАТЬ statements written entirely on one line.

    "The query text must be structured, one should not write
    a query on one line, even a short one".
    Checks each package statement: if the whole statement contains no \\n,
    starts with ВЫБРАТЬ and contains the word ИЗ, the query is on one line.
    This excludes false positives on nested subqueries inside
    a multi-line outer query.
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


# ── Ordering of query results ───────────────

@rule(code="autoorder-with-first", severity="error",
      title="АВТОУПОРЯДОЧИВАНИЕ с ПЕРВЫЕ запрещено")
def check_autoorder_with_first(ctx):
    """Detects combined use of ПЕРВЫЕ and АВТОУПОРЯДОЧИВАНИЕ using the AST model.

    "Using the ПЕРВЫЕ construct together with the
    АВТОУПОРЯДОЧИВАНИЕ construct is prohibited".
    Iterates iter_query_models(ctx); for each query checks for
    order.auto == True and selection.top. If the model is unavailable, it is skipped.
    This rule is mutually exclusive with autoorder-not-recommended: with auto+has_first
    only error is emitted, with auto without has_first - only warning.
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
    """Flags union members added via ОБЪЕДИНИТЬ (with deduplication).

    in general one should use ОБЪЕДИНИТЬ ВСЕ, since
    ОБЪЕДИНИТЬ (without ВСЕ) removes fully identical rows, which
    is time-consuming even if identical rows provably cannot occur.
    Exception: when removing duplicates is a necessary condition of correctness.
    Severity=info, since this is a recommendation.

    Works on the AST model: iter_query_models returns distinct=True for
    members added via ОБЪЕДИНИТЬ (without ВСЕ). If the model is unavailable,
    the rule is skipped.
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


# ── ПОДОБНО operator ─────────────────────────────────

def _iter_like_params(ctx):
    """Generator: yields (line, param) for each ПОДОБНО condition from the AST model.

    Iterates iter_query_models(ctx); for each query walks
    conditions[]. If cond["operator"] == "ПОДОБНО" and param is a non-empty string,
    returns (line, param). If the model is unavailable, returns nothing.
    """
    for line, distinct, model in iter_query_models(ctx):
        for cond in model.get("conditions") or []:
            if cond.get("operator") == "ПОДОБНО":
                param = cond.get("param")
                if param and isinstance(param, str):
                    yield line, param


def _like_literal_content(param):
    """Extracts the content of the first string literal from param.

    If param.lstrip() starts with '"', scans up to the closing '"' (a doubled
    '""' = escaped quote) and returns the inner content.
    Otherwise returns None.
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
            break  # end of literal
        parts.append(c)
        i += 1
    return ''.join(parts)


@rule(code="like-leading-wildcard", severity="warning",
      title="ПОДОБНО с ведущим спецсимволом — индекс не используется")
def check_like_leading_wildcard(ctx):
    """Flags ПОДОБНО where the pattern starts with % or _ (leading wildcard).

    Reads the operand from the AST model conditions[].param - only the ПОДОБНО operand,
    without noise from arithmetic in other WHERE conditions.
    Severity=warning: direct performance impact.
    Parameters (&Шаблон) and fields are skipped - the value is unknown.
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
    """Flags ПОДОБНО where the pattern contains unescaped '['.

    Reads the operand from the AST model conditions[].param.
    Determines the escape character: looks for СПЕЦСИМВОЛ "..." in param (case-insensitive).
    Flags if literal_content contains '[' not preceded by the escape character.
    Severity=error: guaranteed failure on IBM DB2.
    """
    out = []
    for line, param in _iter_like_params(ctx):
        content = _like_literal_content(param)
        if content is None:
            continue
        # Determine the escape character: СПЕЦСИМВОЛ "X" in param
        escape_char = None
        m = re.search(r'(?i)СПЕЦСИМВОЛ\s+"(.)', param)
        if m:
            escape_char = m.group(1)
        # Check for an unescaped '['
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
    """Flags ПОДОБНО where the pattern is built by concatenation or is a field.

    Reads the operand from the AST model conditions[].param.
    Flags if param contains '+' (concatenation) OR the operand does not start
    with '"' (string literal) and does not start with '&' (parameter).
    Severity=warning: violation of the standard's item 1.
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


# ── Rounding of arithmetic operation results ──────

@rule(code="division-without-cast", severity="warning",
      title="Деление без ВЫРАЗИТЬ(... КАК Число(m,n)) — точность может различаться на разных СУБД")
def check_division_without_cast(ctx):
    """Flags division (/) not wrapped in ВЫРАЗИТЬ(... КАК Число(m,n)).

    in arithmetic division operations the result precision
    may differ across DBMSs. It is recommended to specify the precision explicitly
    via ВЫРАЗИТЬ(... КАК Число(m,n)).

    Works on the AST model: for each field checks fields[].expression.
    Flags if expression contains '/' AND expression (in uppercase)
    does not start with 'ВЫРАЗИТЬ(' (i.e. the division result is not wrapped).
    If the model is unavailable, the rule is skipped.
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
    """Flags the СРЕДНЕЕ aggregate function not wrapped in ВЫРАЗИТЬ(... КАК Число(m,n)).

    the СРЕДНЕЕ aggregate function may produce results of different precision
    on different DBMSs. ВЫРАЗИТЬ(СРЕДНЕЕ(...) КАК Число(m,n)) is recommended.

    Works on the AST model: if a field has func == "Среднее" (i.e. СРЕДНЕЕ is not
    wrapped in any expression - in particular, not in ВЫРАЗИТЬ), a
    warning is emitted. When СРЕДНЕЕ is wrapped in ВЫРАЗИТЬ, the parser represents the whole
    field as expression (not func), so no double hits occur.
    If the model is unavailable, the rule is skipped.
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
    """Flags use of FULL OUTER JOIN using the AST model.

    "in general it is not recommended to use the
    ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ construct in queries" - especially with two or more
    such constructs, when performance on PostgreSQL drops significantly.
    Severity=warning: the standard is a methodological recommendation ("not recommended"),
    not a prohibition.

    Works on the AST model: joins[].leftAll == True AND joins[].rightAll == True is
    the sign of ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ. One hit per query if it
    contains at least one full join. If the model is unavailable, it is skipped.
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
                break  # one hit per query
    return out


# ── Nested queries in a join condition ───────────

@rule(code="subquery-in-join-condition", severity="warning",
      title="Вложенный запрос в условии соединения (ПО) — не следует")
def check_subquery_in_join_condition(ctx):
    """Flags nested ВЫБРАТЬ in a join condition (ПО).

    "One should not use nested queries in a join condition.
    This can significantly slow down the query and (in some
    cases) make it completely unusable on some DBMSs".
    Severity=warning: the standard formulates a recommendation ("should not"), not
    a categorical prohibition - although the consequences on some DBMSs are serious.

    Works on the AST model: iterates joins[].conditions[] of each query;
    if a condition has custom=True and its expression (in uppercase)
    contains the word «ВЫБРАТЬ», it is a nested subquery in a join condition.
    Nested queries in ИЗ (table.subquery) and in ВЫБРАТЬ fields
    do not get into joins.conditions and are not flagged.
    One hit per query containing at least one such condition.
    If the model is unavailable, the rule is skipped.
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


# ── Joins with nested queries and virtual tables ──

@rule(code="join-to-subquery", severity="warning",
      title="Соединение с вложенным запросом (ИЗ) — не следует, используйте временную таблицу")
def check_join_to_subquery(ctx):
    """Flags a join where one of the data sources is a nested query.

    "When writing queries, one should not use joins
    with nested queries. Only metadata objects or temporary
    tables should be joined to each other".
    Severity=warning: the standard formulates a recommendation ("should not"), not
    a categorical prohibition; an exception is allowed when the subquery scans
    few records.

    Works on the AST model: builds a map {id -> table} for each query;
    for each join checks whether the joined table has the «subquery» key.
    Virtual tables (table.virtual) are NOT flagged by this rule - they have
    a separate manual requirement in the checklist.
    One hit per query, even if there are several subqueries.
    If the model is unavailable, the rule is skipped.
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


# ── Efficient query conditions ─────────────────────

# Functions applied to fields in ГДЕ/ПО conditions - they block index use.
# Standard: string functions -> replace with ПОДОБНО.
# Standard: date functions -> replace with МЕЖДУ.
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
    """Flags a WHERE condition where a string or date function is applied to a field.

    "WRONG: ПОДСТРОКА(Таблица.Поле, 1, 6) = "строка"" - blocks the index;
    the standard prescribes replacing it with ПОДОБНО or a calculated field.
    "WRONG: МЕСЯЦ(Таблица.Поле) = 1" - blocks the index;
    the standard prescribes replacing it with МЕЖДУ &НачалоПериода И &КонецПериода.

    Severity=warning: the standard shows a "WRONG" example, implicitly prohibiting
    the pattern ("one must not use ... functions" in the main condition).

    Works on the AST model: triggers only if the query has NO
    structured condition (custom=False) - i.e. the function is applied in the main
    condition. If a structured (potentially indexable) condition is present, the function
    is considered additional - the standard allows this, and the rule does not trigger
    (without metadata the main/additional distinction cannot be made exactly, so we take
    a conservative criterion that excludes false positives). If the model
    is unavailable, it is skipped.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        conds = model_dict.get("conditions") or []
        if any(not c.get("custom", True) for c in conds):
            continue  # there is a structured (index) condition -> function is additional -> OK
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
                break  # one hit per query
    return out


@rule(code="case-as-sole-condition", severity="warning",
      title="ВЫБОР как единственное условие ГДЕ — индекс не используется")
def check_case_as_sole_condition(ctx):
    """Flags ВЫБОР (CASE WHEN) acting as the sole WHERE condition.

    "The ВЫБОР expression may only be used in additional conditions".
    "WRONG: ГДЕ ВЫБОР КОГДА … ТОГДА … ИНАЧЕ … КОНЕЦ" - index search
    is not applied. "RIGHT": ВЫБОР after the main condition, combined with И.

    Severity=warning: the standard formulates a restriction ("only in additional conditions"),
    and an absolute prohibition only when there is no indexable main condition.

    Works on the AST model: if conditions[] contains at least one custom condition
    with expression starting with «ВЫБОР», AND there is no structured
    condition (custom=False), then ВЫБОР is the sole/main condition.
    If the model is unavailable, it is skipped.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        conds = model_dict.get("conditions") or []
        has_structured = any(not c.get("custom", True) for c in conds)
        if has_structured:
            continue  # there is a structured (index) condition -> ВЫБОР is additional -> OK
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
                break  # one hit per query
    return out


# ── Access to virtual tables ────────────────

@rule(code="vt-filter-in-where", severity="warning",
      title="Условие на виртуальную таблицу в ГДЕ — следует передать в параметры виртуальной таблицы")
def check_vt_filter_in_where(ctx):
    """Flags WHERE conditions that filter a virtual table field directly.

    "It is not recommended to access virtual tables using
    conditions in the ГДЕ section". With such a query the DBMS first extracts all records
    of the virtual table and then filters them - the optimizer cannot choose
    an efficient plan. Filters should be passed to the virtual table parameters.
    Severity=warning: the standard formulates "Not recommended" (item 1).

    Works on the AST model: builds a map {id -> table} for each query;
    if a table has the "virtual" key, the table is virtual.
    Then walks conditions[]: if tableId matches the id of a virtual
    table, the condition filters a VT via ГДЕ -> flag.
    Conditions on non-virtual tables are ignored.
    If the model is unavailable, the rule is skipped.
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


# ── Efficient access to the Остатки VT ───────────────

# The «.Остатки» suffix in fullName is a sign of the balances VT of an accumulation or accounting register.
# ОстаткиИОбороты has the «.ОстаткиИОбороты» suffix and does not fall under this rule.
_OSTATOK_SUFFIX = re.compile(r"\.Остатки$", re.UNICODE | re.IGNORECASE)


@rule(code="ostatok-with-period", severity="info",
      title="ВТ Остатки: указана дата — СУБД также читает таблицу движений")
def check_ostatok_with_period(ctx):
    """Flags access to the «Остатки» VT with a filled date parameter.

    if a date is passed as the first parameter when accessing the «Остатки»
    virtual table, the 1C platform generates a query that reads not only
    the stored balances table but also the movements table (a slower nested
    query with grouping). To get CURRENT balances no date is needed -
    the first parameter should be left empty.

    Signal: for a virtual table with the «.Остатки» suffix in fullName, the
    virtual.period field is filled (the parser puts the first parameter in parentheses there if it
    is non-empty). An empty first parameter (…, Условие = …) or no parentheses
    means "current balances" - the rule does not trigger.

    The rule does NOT duplicate vt-filter-in-where (that one flags ГДЕ conditions on
    any virtual tables). This rule flags the period parameter
    specific to the Остатки VT.

    If the model is unavailable (no node/bundle), the rule is skipped.
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


# ── Number of virtual table parameters ─────────────────

# VT signatures are fixed. Fewer parameters are allowed (omitted ones get
# default values), MORE is a platform syntax error: the query does not
# compile. The parser stores extra arguments in virtual.extraArgs.
# For an accounting register the exact number depends on the chart of accounts subconto and
# the register correspondence - we take the maximum (with subconto and correspondence),
# so we catch only guaranteed extra parameters (fail-open by metadata).
_VT_SIGNATURES = {
    ("РЕГИСТРНАКОПЛЕНИЯ", "ОСТАТКИ"): ("Период", "Условие"),
    ("РЕГИСТРНАКОПЛЕНИЯ", "ОБОРОТЫ"):
        ("НачалоПериода", "КонецПериода", "Периодичность", "Условие"),
    ("РЕГИСТРНАКОПЛЕНИЯ", "ОСТАТКИИОБОРОТЫ"):
        ("НачалоПериода", "КонецПериода", "Периодичность", "МетодДополнения", "Условие"),
    ("РЕГИСТРСВЕДЕНИЙ", "СРЕЗПОСЛЕДНИХ"): ("Период", "Условие"),
    ("РЕГИСТРСВЕДЕНИЙ", "СРЕЗПЕРВЫХ"): ("Период", "Условие"),
}

_VT_MAX_ARGS = {
    ("РЕГИСТРНАКОПЛЕНИЯ", "ОСТАТКИ"): 2,
    ("РЕГИСТРНАКОПЛЕНИЯ", "ОБОРОТЫ"): 4,
    ("РЕГИСТРНАКОПЛЕНИЯ", "ОСТАТКИИОБОРОТЫ"): 5,
    ("РЕГИСТРСВЕДЕНИЙ", "СРЕЗПОСЛЕДНИХ"): 2,
    ("РЕГИСТРСВЕДЕНИЙ", "СРЕЗПЕРВЫХ"): 2,
    ("РЕГИСТРБУХГАЛТЕРИИ", "ОСТАТКИ"): 4,
    ("РЕГИСТРБУХГАЛТЕРИИ", "ОБОРОТЫ"): 8,
    ("РЕГИСТРБУХГАЛТЕРИИ", "ОБОРОТЫДТКТ"): 8,
    ("РЕГИСТРБУХГАЛТЕРИИ", "ОСТАТКИИОБОРОТЫ"): 7,
    ("РЕГИСТРБУХГАЛТЕРИИ", "ДВИЖЕНИЯССУБКОНТО"): 5,
}


@rule(code="vt-too-many-params", severity="error",
      title="У виртуальной таблицы передано больше параметров, чем допускает сигнатура")
def check_vt_too_many_params(ctx):
    """Flags VT calls with arguments beyond the signature.

    A typical code generation error: a dimension filter is passed as a SEPARATE
    argument after an empty «Условие»:
        РегистрНакопления.Товары.Остатки(<Период>, , Организация = &Организация)
    The «Остатки» VT has the signature (Период, Условие) - there is no third parameter; the platform
    reports a compilation error. Correct:
        РегистрНакопления.Товары.Остатки(<Период>, Организация = &Организация)

    Works on the AST model: the parser puts arguments beyond the signature into
    virtual.extraArgs (see sdblParser.ts). Fewer parameters are not flagged -
    omitted parameters get default values. For an accounting register
    the number of parameters depends on subconto/correspondence (no metadata),
    so only the guaranteed maximum is checked.

    Severity=error: the platform will refuse to compile the query.
    If the model is unavailable, the rule is skipped.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        for tbl in model_dict.get("tables") or []:
            virtual = tbl.get("virtual")
            if not virtual:
                continue
            extra = virtual.get("extraArgs") or []
            if not extra:
                continue
            full_name = tbl.get("fullName") or ""
            parts = full_name.split(".")
            if len(parts) < 3:
                continue
            key = (parts[0].upper(), parts[2].upper())
            max_args = _VT_MAX_ARGS.get(key)
            if max_args is None:
                continue  # unknown VT - do not flag (fail-open)
            sig = _VT_SIGNATURES.get(key)
            sig_text = (
                f" ({', '.join(sig)})" if sig
                else " (состав зависит от субконто/корреспонденции регистра)"
            )
            extras_text = ", ".join(
                f"«{e.strip()}»" if e.strip() else "«пустой»" for e in extra
            )
            out.append(Finding(
                "vt-too-many-params", "error", line,
                f"ВТ «{full_name}»: параметров передано {max_args + len(extra)}, "
                f"а сигнатура допускает не более {max_args}{sig_text}. "
                f"Сверх сигнатуры: {extras_text}. Платформа такой запрос не "
                f"скомпилирует. Фильтры по измерениям передавайте в параметр "
                f"«Условие», а не отдельными аргументами.",
            ))
    return out


# ── Use of temporary tables ──────────────────────

def _temp_table_used_in_join(member_model, temp_name_upper):
    """True if temporaryTableName (uppercase) participates in a JOIN of this query."""
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
    """True if the temp table occurs in a В (...) subquery in this query."""
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
    """Flags a ПОМЕСТИТЬ statement if the VT is used in a JOIN but has no ИНДЕКСИРОВАТЬ ПО.

    "A large temporary table participates in a join (no matter
    on which side). The index should include the fields involved in the ПО condition".
    The word "large" cannot be checked automatically (the data volume is unknown),
    so the rule triggers when ИНДЕКСИРОВАТЬ ПО is absent regardless of volume -
    a conservative warning-level heuristic.

    Algorithm:
    1. Collect the names of all VTs created without ИНДЕКСИРОВАТЬ ПО in the package.
    2. Walk the following package statements; if a VT participates in joins[] -
       report the missing index on the ПОМЕСТИТЬ statement.

    Works only on the AST model. If the model is unavailable, it is skipped.
    """
    batch = ctx.model
    if not isinstance(batch, dict):
        return []
    stmts_batch = batch.get("members", []) or []
    stmts_src = ctx.statements  # (line, text) for each statement

    # Step 1: for each package statement build a map createTemp VT -> (line, has_idx)
    # The statement index in the package matches the index in ctx.statements.
    temp_table_info = {}  # name_upper -> (line, has_idx)
    for si, stmt in enumerate(stmts_batch):
        line = stmts_src[si][0] if si < len(stmts_src) else 1
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            if model.get("queryType") == "createTemp":
                name = (model.get("tempTableName") or "").upper()
                if name:
                    has_idx = bool(model.get("indexing"))
                    # Keep the first occurrence (earliest) with the index flag.
                    if name not in temp_table_info:
                        temp_table_info[name] = (line, has_idx)
                    elif has_idx:
                        # appendTemp with an index - update the flag.
                        temp_table_info[name] = (temp_table_info[name][0], True)

    out = []
    flagged = set()
    # Step 2: check all statements for VT use in JOIN.
    for si, stmt in enumerate(stmts_batch):
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            for name_upper, (create_line, has_idx) in temp_table_info.items():
                if has_idx:
                    continue  # index present - fine
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
    """Flags a ПОМЕСТИТЬ statement if the VT is used in a В (...) condition but has no ИНДЕКСИРОВАТЬ ПО.

    "Access to the temporary table is performed in a subquery
    of the logical operator В (...) construct. The index should include the
    temporary table fields from the select list that correspond to the ones listed on the left
    side of the logical operator В (...)".

    The algorithm is similar to check_temp_table_join_no_index, but checks subqueries
    in conditions[].subquery (operator == "В") of the following package statements.

    Works only on the AST model. If the model is unavailable, it is skipped.
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


# ── Counting records in queries ─────────

# Regular expression: expression == "СУММА(1)" or "ЕСТЬNULL(СУММА(1), 0)"
# (allowing possible spaces around 1 and the comma).
_SUM_ONE_RE = re.compile(
    r"^(?:ЕСТЬNULL\s*\(\s*)?СУММА\s*\(\s*1\s*\)(?:\s*,\s*0\s*\))?$",
    re.IGNORECASE | re.UNICODE,
)

# Regular expression: expression == "СУММА(ВЫБОР ... КОНЕЦ)"
# where the expression contains «ТОГДА 1» or «ИНАЧЕ 1» (counter in units),
# but does NOT contain «ВЫРАЗИТЬ» (not wrapped with extended precision).
_SUM_CASE_ONE_RE = re.compile(
    r"^СУММА\s*\(ВЫБОР\s+",
    re.IGNORECASE | re.UNICODE,
)
# Check for «ТОГДА 1» or «ИНАЧЕ 1» (without ВЫРАЗИТЬ) in the body of СУММА(ВЫБОР...).
_CASE_HAS_LITERAL_1 = re.compile(
    r"(?:ТОГДА|ИНАЧЕ)\s+1(?:\s|$|\))",
    re.IGNORECASE | re.UNICODE,
)


@rule(code="sum-one-for-count", severity="warning",
      title="СУММА(1) вместо КОЛИЧЕСТВО(*) — переполнение при ≥10 млн записей")
def check_sum_one_for_count(ctx):
    """Flags СУММА(1) and ЕСТЬNULL(СУММА(1), 0) as a replacement for КОЛИЧЕСТВО(*).

    "when calculating the number of records one should always use
    the КОЛИЧЕСТВО function, not СУММА". With 10 million records or more
    СУММА(1) overflows due to the default number precision (7 digits)
    that 1C:Enterprise uses in the DBMS. Severity=warning: the standard
    formulates a recommendation ("one should use КОЛИЧЕСТВО, not СУММА");
    the consequence (overflow) occurs only with large volumes.

    Works on the AST model: checks fields[].expression for a match with
    СУММА(1) or ЕСТЬNULL(СУММА(1), 0). If the model is unavailable, it is skipped.
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
    """Flags СУММА(ВЫБОР...ТОГДА 1...) without ВЫРАЗИТЬ(1 КАК ЧИСЛО(17,0)).

    when a conditional count cannot be expressed via КОЛИЧЕСТВО,
    "one should extend the number precision using ВЫРАЗИТЬ(1 КАК ЧИСЛО(17, 0))".
    Without ВЫРАЗИТЬ the default number precision (7 digits) cannot count
    more than 10 million conditional records. Severity=warning: "should" (recommendation).

    Works on the AST model: if expression starts with СУММА(ВЫБОР and contains
    «ТОГДА 1» or «ИНАЧЕ 1» (counter - a literal one), but does not contain
    «ВЫРАЗИТЬ», it is flagged.
    If the model is unavailable, the rule is skipped.
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
            # ВЫРАЗИТЬ present - already wrapped correctly
            if "ВЫРАЗИТЬ" in expr_upper:
                continue
            # Make sure this is a counter (ТОГДА 1 or ИНАЧЕ 1)
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


# ── Queries in dynamic lists ───────────────────

def _all_sources_are_temp(member_model, known_temp_names_upper):
    """True if ALL data sources of the query are temporary tables (no dot in fullName
    and fullName matches the name of a previously created VT - or no dot at all if
    VT names are unknown). Empty source list -> False (no point in flagging).
    """
    tables = member_model.get("tables") or []
    if not tables:
        return False
    for tbl in tables:
        full_name = tbl.get("fullName") or ""
        # Real metadata tables always contain a dot (Справочник.Товары).
        # Temporary tables do not.
        if "." in full_name:
            return False
        if known_temp_names_upper and full_name.upper() not in known_temp_names_upper:
            # Name not found among known VTs - most likely not a VT, skip.
            return False
    return True


@rule(code="last-query-from-temp-only", severity="warning",
      title="Последний запрос пакета выбирает только из временной таблицы — это уже не динамический список")
def check_last_query_from_temp_only(ctx):
    """Flags a package whose last SELECT statement selects data ONLY
    from temporary tables (no real metadata table).

    "If the last query of a dynamic list selects data
    only from a previously created temporary table, it is no longer a dynamic list,
    and its query, and most likely the metadata used by the query,
    should be redesigned".

    Algorithm:
    1. Collect the names of all VTs created via ПОМЕСТИТЬ in the package.
    2. Find the last statement with queryType == "select" (or without queryType).
    3. If all its data sources are temporary tables from step 1, flag it.

    Severity=warning: the wording "should be redesigned" (a recommendation).
    One hit per whole package.
    If the model is unavailable, the rule is skipped.
    """
    batch = ctx.model
    if not isinstance(batch, dict):
        return []
    stmts_batch = batch.get("members", []) or []
    if not stmts_batch:
        return []
    stmts_src = ctx.statements

    # Step 1: collect VT names from createTemp statements.
    known_temp = set()
    for stmt in stmts_batch:
        for member in stmt.get("members", []) or []:
            model = member.get("model") or {}
            if model.get("queryType") == "createTemp":
                name = (model.get("tempTableName") or "").upper()
                if name:
                    known_temp.add(name)

    if not known_temp:
        return []  # no temporary tables - rule is not applicable

    # Step 2: find the last SELECT statement (not createTemp, not dropTemp).
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

    # Step 3: check that all sources of the last SELECT are from VTs.
    last_stmt = stmts_batch[last_select_si]
    for member in last_stmt.get("members", []) or []:
        model = member.get("model") or {}
        qt = model.get("queryType") or "select"
        if qt != "select":
            continue
        if not _all_sources_are_temp(model, known_temp):
            return []  # at least one union member reads a real table

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


# ── Section order: УПОРЯДОЧИТЬ ПО must come before ИТОГИ ──

_KW_ITOGI = re.compile(r"\bИТОГИ\b", re.UNICODE)
_KW_ORDER = re.compile(r"\bУПОРЯДОЧИТЬ\b", re.UNICODE)


@rule(code="order-after-totals", severity="error",
      title="УПОРЯДОЧИТЬ ПО после ИТОГИ — нарушен порядок секций (синтаксическая ошибка платформы)")
def check_order_after_totals(ctx):
    """Flags УПОРЯДОЧИТЬ ПО located AFTER the ИТОГИ section.

    Error 2 in errors.md: the platform requires a strict section order
    (…УПОРЯДОЧИТЬ ПО -> АВТОУПОРЯДОЧИВАНИЕ -> ИТОГИ) and reports the syntax error
    «Синтаксическая ошибка "УПОРЯДОЧИТЬ"». IMPORTANT: the vendored SDBL parser is
    LENIENT about this order - it parses the query without error (silently dropping УПОРЯДОЧИТЬ),
    so query-not-parseable does NOT catch this error. A separate text
    check is needed.

    Works on text (no AST): in each package statement (ctx.statements), over the
    sanitized text (without strings/comments), searches for the keywords ИТОГИ and
    УПОРЯДОЧИТЬ; if УПОРЯДОЧИТЬ comes after ИТОГИ, it is a finding. Subqueries with
    their own УПОРЯДОЧИТЬ (ПЕРВЫЕ … УПОРЯДОЧИТЬ) appear in the text before the top-level
    ИТОГИ, so they do not cause a false hit.

    Severity=error: guaranteed compilation failure of the query on the platform.
    """
    out = []
    for line, stmt in ctx.statements:
        code = _sanitize(stmt).upper()
        mi = _KW_ITOGI.search(code)
        mo = _KW_ORDER.search(code)
        if mi and mo and mo.start() > mi.start():
            rel_line = code.count("\n", 0, mo.start())
            out.append(Finding(
                "order-after-totals", "error", line + rel_line,
                "УПОРЯДОЧИТЬ ПО расположено после ИТОГИ — нарушен обязательный порядок "
                "секций (…УПОРЯДОЧИТЬ ПО → ИТОГИ). Платформа выдаст синтаксическую ошибку. "
                "Переставьте УПОРЯДОЧИТЬ ПО перед ИТОГИ.",
            ))
    return out


# ── ИТОГИ: non-aggregated non-grouping fields ────

@rule(code="totals-field-not-aggregated", severity="error",
      title="Поле выводится при ИТОГИ, но не агрегировано и не входит в группировку — на строках-итогах NULL")
def check_totals_field_not_aggregated(ctx):
    """Flags a "bare" field in a query with ИТОГИ that is included neither in the
    ИТОГИ grouping nor in an aggregate.

    Error 4 in errors.md: `ИТОГИ ПО Номенклатура` without aggregates for the fields
    `Услуга`, `Потребность`. When traversing `ОбходРезультатаЗапроса.ПоГруппировкам`
    (and on ОБЩИЕ rows) non-grouping non-aggregated fields are returned as
    NULL. As a side effect this causes a runtime error like «Преобразование значения к типу
    Булево не может быть выполнено» when such a NULL field is used in a condition.

    Works on the AST model: if the query has a totals section, then for each
    "bare" field of the select list (has path, no func, no expression) it checks
    whether it is in totals.groupFields (by selectAlias or path) or in
    totals.totalFields (by operandAlias). If not, the field becomes NULL on
    totals rows -> finding. Calculated fields (expression) and aggregates (func) are not
    flagged. If the model is unavailable, the rule is skipped.

    Severity=error: leads to NULL in the data and usually to a runtime error
    when traversing the result. The finding blocks acceptance.
    """
    out = []
    for line, distinct, model_dict in iter_query_models(ctx):
        totals = model_dict.get("totals")
        if not totals:
            continue
        group_aliases = set()
        group_paths = set()
        for g in totals.get("groupFields") or []:
            sa = g.get("selectAlias")
            if sa:
                group_aliases.add(sa.upper())
            gp = g.get("path")
            if gp:
                group_paths.add(gp.upper())
        total_aliases = set()
        for t in totals.get("totalFields") or []:
            oa = t.get("operandAlias")
            if oa:
                total_aliases.add(oa.upper())
        for f in model_dict.get("fields") or []:
            if f.get("func") or f.get("expression"):
                continue  # aggregate or calculated field - not "bare"
            path = f.get("path")
            if not path:
                continue
            alias = f.get("alias") or path
            au = alias.upper()
            pu = path.upper()
            if au in group_aliases or pu in group_paths or au in total_aliases:
                continue
            out.append(Finding(
                "totals-field-not-aggregated", "error", line,
                f"Поле «{alias}» выводится, но в секции ИТОГИ не входит ни в группировку, "
                f"ни в агрегат — на строках-итогах (обход ПоГруппировкам, строки ОБЩИЕ) "
                f"оно вернётся как NULL. Добавьте для него агрегат в ИТОГИ "
                f"(например МАКСИМУМ({alias})) или уберите поле из списка выбора.",
            ))
    return out


@rule(code="autoorder-not-recommended", severity="warning",
      title="АВТОУПОРЯДОЧИВАНИЕ не рекомендуется — разработчик не контролирует поля сортировки")
def check_autoorder_not_recommended(ctx):
    """Warns about any use of АВТОУПОРЯДОЧИВАНИЕ without ПЕРВЫЕ using the AST model.

    "In other cases the АВТОУПОРЯДОЧИВАНИЕ construct is also not
    recommended, since the developer does not control which
    fields will be used for ordering".
    Iterates iter_query_models(ctx); for each query checks order.auto == True.
    If the same query has selection.top, it is covered by the error rule
    autoorder-with-first, so no warning is emitted here (no double hits).
    If the model is unavailable, the rule is skipped.
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
