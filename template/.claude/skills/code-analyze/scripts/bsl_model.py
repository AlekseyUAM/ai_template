# bsl_model.py - lightweight parser of BSL (1C) module structure.
#
# Not a full expression AST: it provides tokens, string/comment stripping and
# the module STRUCTURE - methods (Процедура/Функция), nested blocks
# (Если/Цикл/Попытка), Перем declarations and method parameters. That is enough
# for structural rules like "call inside a loop", "variable declared via
# Перем", "method parameter". Where a rule needs expression parsing, it works
# on the text (ctx.code) conservatively or is moved to the manual checklist.
#
# Keywords are recognized in both cases and in Russian/English
# (the platform supports English keywords).

import re

# ── Tokenization ─────────────────────────────────────────────

# BSL identifier: letter/underscore, then letters/digits/underscores.
_IDENT_RE = re.compile(r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*", re.UNICODE)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?", re.UNICODE)


class Token:
    __slots__ = ("kind", "value", "line", "col", "pos")

    def __init__(self, kind, value, line, col, pos):
        self.kind = kind      # 'ident' | 'number' | 'string' | 'comment'
                              # | 'directive' | 'preproc' | 'op'
        self.value = value    # for string - inner content without quotes
        self.line = line
        self.col = col
        self.pos = pos

    def __repr__(self):
        v = self.value if len(self.value) <= 20 else self.value[:17] + "..."
        return f"Token({self.kind}, {v!r}, L{self.line})"


def tokenize(text):
    """Split module text into tokens. Strings and comments are kept as
    separate tokens (rules usually ignore their content). Line breaks
    do not produce tokens - the line number is stored in each token."""
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
        # String literal "..."
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
        # Comment //...
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            start, start_col = i, col(i)
            j = i + 2
            while j < n and text[j] != "\n":
                j += 1
            tokens.append(Token("comment", text[i:j], line, start_col, start))
            i = j
            continue
        # Compilation directive &НаКлиенте / &AtClient
        if ch == "&":
            start, start_col = i, col(i)
            m = _IDENT_RE.match(text, i + 1)
            val = m.group() if m else ""
            end = m.end() if m else i + 1
            tokens.append(Token("directive", val, line, start_col, start))
            i = end
            continue
        # Preprocessor instruction #Если / #Область ...
        if ch == "#":
            start, start_col = i, col(i)
            j = i + 1
            while j < n and text[j] != "\n":
                j += 1
            tokens.append(Token("preproc", text[i:j], line, start_col, start))
            i = j
            continue
        # Identifier
        m = _IDENT_RE.match(text, i)
        if m:
            tokens.append(Token("ident", m.group(), line, col(i), i))
            i = m.end()
            continue
        # Number
        m = _NUMBER_RE.match(text, i)
        if m:
            tokens.append(Token("number", m.group(), line, col(i), i))
            i = m.end()
            continue
        # Operator/punctuation - single character
        tokens.append(Token("op", ch, line, col(i), i))
        i += 1

    return tokens


def sanitize(text):
    """Content of strings "..." and comments //... is replaced with spaces of the same
    length (line breaks preserved). Length and line numbers are preserved -
    positions match the source text. For text rules that must not
    fire on words inside strings and comments."""
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


# ── Structure keywords ───────────────────────────────────────

# Block openers -> block type.
_OPENERS = {
    "ПРОЦЕДУРА": "procedure", "PROCEDURE": "procedure",
    "ФУНКЦИЯ": "function", "FUNCTION": "function",
    "ЕСЛИ": "if", "IF": "if",
    "ПОКА": "loop", "WHILE": "loop",
    "ДЛЯ": "loop", "FOR": "loop",
    "ПОПЫТКА": "try", "TRY": "try",
}
# Block closers -> type of the block they close.
_CLOSERS = {
    "КОНЕЦПРОЦЕДУРЫ": "procedure", "ENDPROCEDURE": "procedure",
    "КОНЕЦФУНКЦИИ": "function", "ENDFUNCTION": "function",
    "КОНЕЦЕСЛИ": "if", "ENDIF": "if",
    "КОНЕЦЦИКЛА": "loop", "ENDDO": "loop",
    "КОНЕЦПОПЫТКИ": "try", "ENDTRY": "try",
}
# Markers of the block body start (end of the header).
_BODY_MARKERS = {"ТОГДА", "THEN", "ЦИКЛ", "DO"}
_VAR_KW = {"ПЕРЕМ", "VAR"}
_EXPORT_KW = {"ЭКСПОРТ", "EXPORT"}
_BYVAL_KW = {"ЗНАЧ", "VAL"}


class Block:
    """Module structure node. For methods name/is_export/directive/
    params are filled. header_end_line - the body start marker line (Тогда/Цикл) or the
    method header line."""

    __slots__ = ("kind", "name", "is_export", "directive", "params",
                 "loop_var", "header_line", "header_end_line", "end_line",
                 "parent", "children")

    def __init__(self, kind, header_line):
        self.kind = kind            # 'procedure'|'function'|'if'|'loop'|'try'
        self.name = None
        self.is_export = False
        self.directive = None       # 'НаКлиенте' etc. (without &)
        self.params = []            # parameter names (for methods)
        self.loop_var = None        # loop variable (for Для ... = ...)
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
        """First line of the block body (after the header)."""
        return self.header_end_line

    def __repr__(self):
        tag = self.name or self.kind
        return f"Block({self.kind}:{tag}, L{self.header_line}-{self.end_line})"


def _parse_method_header(tokens, start_idx, block):
    """Fill name/params/is_export of a method from tokens starting at the
    opener index (ПРОЦЕДУРА/ФУНКЦИЯ). Returns the index of the token after ')'."""
    i = start_idx + 1
    n = len(tokens)
    # Method name
    if i < n and tokens[i].kind == "ident":
        block.name = tokens[i].value
        i += 1
    # Opening parenthesis
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
                    pass  # skip Знач, the name is the next identifier
                elif expect_name:
                    block.params.append(t.value)
                    expect_name = False
            i += 1
    # Export after parentheses (until the end of the header line)
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
    """Collect Перем declarations: list of (name, line, is_export)."""
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
    """Structural model of a BSL module."""

    def __init__(self, text):
        self.text = text
        self._tokens = None
        self._sanitized = None
        self._blocks = None       # tree: list of root blocks
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
        """Build the block tree with a single pass over code tokens."""
        tokens = self.tokens
        roots = []
        all_blocks = []
        stack = []
        # Compilation directive found before the nearest method.
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
                    # loop variable: Для <var> = ...  (not Для Каждого)
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
                # Pop from the stack up to and including the expected block type.
                while stack:
                    blk = stack.pop()
                    blk.end_line = t.line
                    if blk.kind == want:
                        break
                i += 1
                continue
            i += 1

        # Unclosed blocks (broken code) - close them at the last line.
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
        """List of (name, line, is_export) of all Перем declarations."""
        if self._vars is None:
            self._vars = _collect_vars(self.tokens)
        return self._vars

    def method_at(self, line):
        """Method whose body contains the line (or None)."""
        for m in self.methods:
            if m.header_line <= line <= m.end_line:
                return m
        return None

    def is_in_loop(self, line):
        """True if the line is inside the body of at least one loop."""
        for lp in self.loops:
            if lp.body_start_line <= line <= lp.end_line:
                return True
        return False
