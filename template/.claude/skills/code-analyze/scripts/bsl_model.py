# bsl_model.py — лёгкий парсер структуры модуля BSL (1С).
#
# Не полный AST выражений: даёт токены, вырезание строк/комментариев и
# СТРУКТУРУ модуля — методы (Процедура/Функция), вложенные блоки
# (Если/Цикл/Попытка), объявления Перем и параметры методов. Этого достаточно
# для структурных правил вида «вызов внутри цикла», «переменная объявлена через
# Перем», «параметр метода». Где правилу нужен разбор выражений — оно работает
# по тексту (ctx.code) консервативно либо выносится в ручной чеклист.
#
# Ключевые слова распознаются в обоих регистрах и на русском/английском
# (платформа поддерживает англоязычные ключевые слова).

import re

# ── Токенизация ──────────────────────────────────────────────

# Идентификатор BSL: буква/подчёркивание, затем буквы/цифры/подчёркивания.
_IDENT_RE = re.compile(r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*", re.UNICODE)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?", re.UNICODE)


class Token:
    __slots__ = ("kind", "value", "line", "col", "pos")

    def __init__(self, kind, value, line, col, pos):
        self.kind = kind      # 'ident' | 'number' | 'string' | 'comment'
                              # | 'directive' | 'preproc' | 'op'
        self.value = value    # для string — внутреннее содержимое без кавычек
        self.line = line
        self.col = col
        self.pos = pos

    def __repr__(self):
        v = self.value if len(self.value) <= 20 else self.value[:17] + "..."
        return f"Token({self.kind}, {v!r}, L{self.line})"


def tokenize(text):
    """Разбивает текст модуля на токены. Строки и комментарии сохраняются как
    отдельные токены (их содержимое правила обычно игнорируют). Переводы строк
    не порождают токенов — номер строки хранится в каждом токене."""
    tokens = []
    i, n = 0, len(text)
    line, line_start = 1, 0

    def col(pos):
        return pos - line_start + 1

    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            line_start = i + 1
            i += 1
            continue
        if ch in " \t\r":
            i += 1
            continue
        # Строковый литерал "..."
        if ch == '"':
            start, start_line, start_col = i, line, col(i)
            i += 1
            buf = []
            while i < n:
                c = text[i]
                if c == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                if c == "\n":
                    line += 1
                    line_start = i + 1
                buf.append(c)
                i += 1
            tokens.append(Token("string", "".join(buf), start_line, start_col, start))
            continue
        # Комментарий //…
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            start, start_col = i, col(i)
            j = i + 2
            while j < n and text[j] != "\n":
                j += 1
            tokens.append(Token("comment", text[i:j], line, start_col, start))
            i = j
            continue
        # Директива компиляции &НаКлиенте / &AtClient
        if ch == "&":
            start, start_col = i, col(i)
            m = _IDENT_RE.match(text, i + 1)
            val = m.group() if m else ""
            end = m.end() if m else i + 1
            tokens.append(Token("directive", val, line, start_col, start))
            i = end
            continue
        # Инструкция препроцессора #Если / #Область …
        if ch == "#":
            start, start_col = i, col(i)
            j = i + 1
            while j < n and text[j] != "\n":
                j += 1
            tokens.append(Token("preproc", text[i:j], line, start_col, start))
            i = j
            continue
        # Идентификатор
        m = _IDENT_RE.match(text, i)
        if m:
            tokens.append(Token("ident", m.group(), line, col(i), i))
            i = m.end()
            continue
        # Число
        m = _NUMBER_RE.match(text, i)
        if m:
            tokens.append(Token("number", m.group(), line, col(i), i))
            i = m.end()
            continue
        # Оператор/пунктуация — одиночный символ
        tokens.append(Token("op", ch, line, col(i), i))
        i += 1

    return tokens


def sanitize(text):
    """Содержимое строк "…" и комментариев //… заменяется пробелами той же
    длины (переводы строк сохранены). Длина и номера строк сохраняются —
    позиции совпадают с исходным текстом. Для текстовых правил, которые не
    должны срабатывать на слова внутри строк и комментариев."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            out.append(" ")
            i += 1
            while i < n:
                c = text[i]
                if c == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        out.append("  ")
                        i += 2
                        continue
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ── Ключевые слова структуры ─────────────────────────────────

# Открыватели блоков → тип блока.
_OPENERS = {
    "ПРОЦЕДУРА": "procedure", "PROCEDURE": "procedure",
    "ФУНКЦИЯ": "function", "FUNCTION": "function",
    "ЕСЛИ": "if", "IF": "if",
    "ПОКА": "loop", "WHILE": "loop",
    "ДЛЯ": "loop", "FOR": "loop",
    "ПОПЫТКА": "try", "TRY": "try",
}
# Закрыватели блоков → тип блока, который они закрывают.
_CLOSERS = {
    "КОНЕЦПРОЦЕДУРЫ": "procedure", "ENDPROCEDURE": "procedure",
    "КОНЕЦФУНКЦИИ": "function", "ENDFUNCTION": "function",
    "КОНЕЦЕСЛИ": "if", "ENDIF": "if",
    "КОНЕЦЦИКЛА": "loop", "ENDDO": "loop",
    "КОНЕЦПОПЫТКИ": "try", "ENDTRY": "try",
}
# Маркеры начала тела блока (конец заголовка).
_BODY_MARKERS = {"ТОГДА", "THEN", "ЦИКЛ", "DO"}
_VAR_KW = {"ПЕРЕМ", "VAR"}
_EXPORT_KW = {"ЭКСПОРТ", "EXPORT"}
_BYVAL_KW = {"ЗНАЧ", "VAL"}


class Block:
    """Узел структуры модуля. Для методов заполнены name/is_export/directive/
    params. header_end_line — строка маркера начала тела (Тогда/Цикл) или строка
    заголовка метода."""

    __slots__ = ("kind", "name", "is_export", "directive", "params",
                 "loop_var", "header_line", "header_end_line", "end_line",
                 "parent", "children")

    def __init__(self, kind, header_line):
        self.kind = kind            # 'procedure'|'function'|'if'|'loop'|'try'
        self.name = None
        self.is_export = False
        self.directive = None       # 'НаКлиенте' и т.п. (без &)
        self.params = []            # имена параметров (для методов)
        self.loop_var = None        # переменная цикла (для Для … = …)
        self.header_line = header_line
        self.header_end_line = header_line
        self.end_line = header_line
        self.parent = None
        self.children = []

    @property
    def is_method(self):
        return self.kind in ("procedure", "function")

    @property
    def body_start_line(self):
        """Первая строка тела блока (после заголовка)."""
        return self.header_end_line

    def __repr__(self):
        tag = self.name or self.kind
        return f"Block({self.kind}:{tag}, L{self.header_line}-{self.end_line})"


def _parse_method_header(tokens, start_idx, block):
    """Заполняет name/params/is_export у метода по токенам, начиная с индекса
    открывателя (ПРОЦЕДУРА/ФУНКЦИЯ). Возвращает индекс токена после ')'."""
    i = start_idx + 1
    n = len(tokens)
    # Имя метода
    if i < n and tokens[i].kind == "ident":
        block.name = tokens[i].value
        i += 1
    # Открывающая скобка
    if i < n and tokens[i].kind == "op" and tokens[i].value == "(":
        i += 1
        depth = 1
        expect_name = True
        while i < n and depth > 0:
            t = tokens[i]
            if t.kind == "op" and t.value == "(":
                depth += 1
            elif t.kind == "op" and t.value == ")":
                depth -= 1
            elif depth == 1 and t.kind == "op" and t.value == ",":
                expect_name = True
            elif depth == 1 and t.kind == "ident":
                up = t.value.upper()
                if up in _BYVAL_KW:
                    pass  # пропускаем Знач, имя — следующий идентификатор
                elif expect_name:
                    block.params.append(t.value)
                    expect_name = False
            i += 1
    # Экспорт после скобок (до конца строки заголовка)
    header_line = tokens[start_idx].line
    j = i
    while j < n and tokens[j].line <= header_line + 3:
        t = tokens[j]
        if t.kind == "ident" and t.value.upper() in _EXPORT_KW:
            block.is_export = True
            break
        if t.kind == "op" and t.value == ";":
            break
        j += 1
    return i


def _collect_vars(tokens):
    """Собирает объявления Перем: список (имя, строка, is_export)."""
    out = []
    n = len(tokens)
    i = 0
    while i < n:
        t = tokens[i]
        if t.kind == "ident" and t.value.upper() in _VAR_KW:
            i += 1
            is_export = False
            names = []
            while i < n:
                tt = tokens[i]
                if tt.kind == "op" and tt.value == ";":
                    break
                if tt.kind == "ident":
                    up = tt.value.upper()
                    if up in _EXPORT_KW:
                        is_export = True
                    else:
                        names.append((tt.value, tt.line))
                i += 1
            for nm, ln in names:
                out.append((nm, ln, is_export))
        i += 1
    return out


class Module:
    """Структурная модель модуля BSL."""

    def __init__(self, text):
        self.text = text
        self._tokens = None
        self._sanitized = None
        self._blocks = None       # дерево: список корневых блоков
        self._all_blocks = None
        self._methods = None
        self._vars = None
        self._loops = None

    @property
    def tokens(self):
        if self._tokens is None:
            self._tokens = tokenize(self.text)
        return self._tokens

    @property
    def sanitized(self):
        if self._sanitized is None:
            self._sanitized = sanitize(self.text)
        return self._sanitized

    def _build(self):
        """Строит дерево блоков однопроходным сканированием токенов кода."""
        tokens = self.tokens
        roots = []
        all_blocks = []
        stack = []
        # Директива компиляции, встреченная перед ближайшим методом.
        pending_directive = None
        n = len(tokens)
        i = 0
        while i < n:
            t = tokens[i]
            if t.kind == "directive":
                pending_directive = t.value
                i += 1
                continue
            if t.kind not in ("ident",):
                i += 1
                continue
            up = t.value.upper()
            if up in _OPENERS:
                kind = _OPENERS[up]
                blk = Block(kind, t.line)
                blk.parent = stack[-1] if stack else None
                if blk.parent:
                    blk.parent.children.append(blk)
                else:
                    roots.append(blk)
                all_blocks.append(blk)
                if kind in ("procedure", "function"):
                    blk.directive = pending_directive
                    pending_directive = None
                    nxt = _parse_method_header(tokens, i, blk)
                    stack.append(blk)
                    i = nxt
                    continue
                if kind == "loop":
                    # переменная цикла: Для <var> = …  (не Для Каждого)
                    if i + 1 < n and tokens[i + 1].kind == "ident":
                        if tokens[i + 1].value.upper() not in ("КАЖДОГО", "EACH"):
                            blk.loop_var = tokens[i + 1].value
                        elif i + 2 < n and tokens[i + 2].kind == "ident":
                            blk.loop_var = tokens[i + 2].value
                stack.append(blk)
                i += 1
                continue
            if up in _BODY_MARKERS and stack:
                top = stack[-1]
                if top.header_end_line == top.header_line and top.kind in ("if", "loop"):
                    top.header_end_line = t.line
                i += 1
                continue
            if up in _CLOSERS:
                want = _CLOSERS[up]
                # Снимаем со стека до блока ожидаемого типа включительно.
                while stack:
                    blk = stack.pop()
                    blk.end_line = t.line
                    if blk.kind == want:
                        break
                i += 1
                continue
            i += 1

        # Незакрытые блоки (битый код) — закрываем по последней строке.
        last_line = tokens[-1].line if tokens else 1
        for blk in stack:
            blk.end_line = last_line

        self._blocks = roots
        self._all_blocks = all_blocks

    @property
    def blocks(self):
        if self._blocks is None:
            self._build()
        return self._blocks

    @property
    def all_blocks(self):
        if self._all_blocks is None:
            self._build()
        return self._all_blocks

    @property
    def methods(self):
        if self._methods is None:
            self._methods = [b for b in self.all_blocks if b.is_method]
        return self._methods

    @property
    def loops(self):
        if self._loops is None:
            self._loops = [b for b in self.all_blocks if b.kind == "loop"]
        return self._loops

    @property
    def var_declarations(self):
        """Список (имя, строка, is_export) всех объявлений Перем."""
        if self._vars is None:
            self._vars = _collect_vars(self.tokens)
        return self._vars

    def method_at(self, line):
        """Метод, в теле которого находится строка (или None)."""
        for m in self.methods:
            if m.header_line <= line <= m.end_line:
                return m
        return None

    def is_in_loop(self, line):
        """True, если строка находится в теле хотя бы одного цикла."""
        for lp in self.loops:
            if lp.body_start_line <= line <= lp.end_line:
                return True
        return False
