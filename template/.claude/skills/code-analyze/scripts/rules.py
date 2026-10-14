# rules.py — реестр автоматических проверок BSL-кода 1С.
#
# Правила работают по структурной модели модуля (bsl_model.Module) — токены,
# методы, циклы, объявления Перем. Модель строится на чистом Python, без
# внешних зависимостей, поэтому (в отличие от query-analyze) правила не
# «пропускаются» — модель доступна всегда.
#
# Мы НЕ дублируем диагностики BSL Language Server (bsl_ls): здесь только
# проверки, которых в bsl_ls нет. Требования, которые нельзя надёжно
# заскриптовать, вынесены в ручной чеклист навыка bsl-coding-standards.

import re
from dataclasses import dataclass

import bsl_model


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


class ModuleContext:
    """Контекст анализа одного модуля. Ленивая обёртка над bsl_model.Module."""

    def __init__(self, text):
        self.text = text
        self._model = None
        self._lines = None
        self._code = None

    @property
    def model(self):
        if self._model is None:
            self._model = bsl_model.Module(self.text)
        return self._model

    @property
    def lines(self):
        if self._lines is None:
            self._lines = self.text.split("\n")
        return self._lines

    @property
    def code(self):
        """Текст без содержимого строк и комментариев (длина/строки сохранены)."""
        if self._code is None:
            self._code = self.model.sanitized
        return self._code

    def code_line(self, lineno):
        """Санитизированная строка по номеру (1-based) или ''."""
        code_lines = self.code.split("\n")
        if 1 <= lineno <= len(code_lines):
            return code_lines[lineno - 1]
        return ""


def run_all(ctx):
    findings = []
    for r in RULES:
        findings.extend(r.fn(ctx))
    return findings


# ── Массовая конкатенация строк ──────────────────────────────

# Присваивание-аккумулятор: «Имя = … Имя … » с оператором «+».
_ASSIGN_RE = re.compile(
    r"^\s*([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*=\s*(.+)$",
    re.UNICODE,
)


# Операторы, выдающие булев/сравнительный аккумулятор (не конкатенацию строк):
# при их наличии в правой части «+» — это арифметика/логика, а не строки.
_NON_STRING_OP_RE = re.compile(
    r"(<>|<=|>=|[<>])|(?<![A-Za-zА-Яа-яЁё0-9_])(И|ИЛИ|НЕ|And|Or|Not)(?![A-Za-zА-Яа-яЁё0-9_])",
    re.UNICODE | re.IGNORECASE,
)


@rule(code="string-concat-in-loop", severity="warning",
      title="Конкатенация строк в цикле — используйте СтрСоединить")
def check_string_concat_in_loop(ctx):
    """Флагует накопление строки конкатенацией внутри цикла.

    «При массовых операциях конкатенации строк следует использовать методы
    платформы СтрРазделить и СтрСоединить». Классический сигнал —
    аккумулятор «Текст = Текст + …» в теле цикла: на больших объёмах это
    квадратично по времени и памяти. Порог (≈1000 операций) скриптом неизвестен,
    поэтому severity=warning, а сообщение поясняет условие применимости.

    Работает по модели: для каждого цикла сканирует строки его тела; флагует
    присваивание, где левая часть повторяется в правой и присутствует «+».
    Чтобы не ловить булевы/сравнительные аккумуляторы (частое ложное срабатывание,
    напр. `Флаг = Флаг Или X + 1 > 0`), находка НЕ выдаётся, если в правой части есть
    операторы сравнения (`<`,`>`,`<=`,`>=`,`<>`) или логические операторы
    (И/ИЛИ/НЕ/And/Or/Not). Числовые суммы без таких операторов (`Сумма = Сумма + Цена`)
    отличить от строк по тексту нельзя — эвристика их не разделяет (проверь при ревью).
    """
    out = []
    seen = set()
    model = ctx.model
    for loop in model.loops:
        for ln in range(loop.header_end_line + 1, loop.end_line):
            if ln in seen:
                continue
            text_line = ctx.code_line(ln)
            m = _ASSIGN_RE.match(text_line)
            if not m:
                continue
            lhs, rhs = m.group(1), m.group(2)
            if "+" not in rhs:
                continue
            if not re.search(r"\b" + re.escape(lhs) + r"\b", rhs, re.UNICODE | re.IGNORECASE):
                continue
            # Логический/сравнительный аккумулятор — не строки, пропускаем.
            if _NON_STRING_OP_RE.search(rhs):
                continue
            seen.add(ln)
            out.append(Finding(
                    code="string-concat-in-loop",
                    severity="warning",
                    line=ln,
                    message=(
                        f"Конкатенация-аккумулятор «{lhs}» в цикле: на массовых объёмах "
                        f"(≈1000+ операций) это медленно и расходует память. "
                        f"Накапливайте части в Массив и соберите через СтрСоединить."
                    ),
                ))
    return out


# ── Поиск в коллекциях значений ──────────────────────────────

# Список колонок: два и более идентификатора через запятую.
_COLUMN_LIST_RE = re.compile(
    r"^\s*[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*\s*"
    r"(?:,\s*[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*\s*)+$",
    re.UNICODE,
)
_FIND_NAMES = {"НАЙТИ", "FIND"}


@rule(code="tv-find-multiple-columns", severity="warning",
      title="ТаблицаЗначений.Найти по нескольким колонкам — индекс не используется")
def check_tv_find_multiple_columns(ctx):
    """Флагует вызов «.Найти(Значение, "Кол1, Кол2")» с несколькими колонками.

    «Не следует использовать метод Найти для поиска по нескольким колонкам …
    метод Найти выполняет поиск с применением индекса только по одному полю».
    При нескольких колонках поиск идёт перебором всех строк.
    Для поиска по нескольким колонкам используйте НайтиСтроки с индексом,
    совпадающим со структурой поиска.

    Сигнал: вызов «.Найти(» , среди аргументов которого есть строковый литерал —
    список из двух и более колонок через запятую. severity=warning.
    """
    out = []
    tokens = ctx.model.tokens
    n = len(tokens)
    k = 0
    while k < n - 2:
        t = tokens[k]
        if (t.kind == "op" and t.value == "."
                and tokens[k + 1].kind == "ident"
                and tokens[k + 1].value.upper() in _FIND_NAMES
                and tokens[k + 2].kind == "op" and tokens[k + 2].value == "("):
            # Собрать аргументы до парной ')'.
            j = k + 3
            depth = 1
            col_literal = None
            while j < n and depth > 0:
                tj = tokens[j]
                if tj.kind == "op" and tj.value == "(":
                    depth += 1
                elif tj.kind == "op" and tj.value == ")":
                    depth -= 1
                elif depth == 1 and tj.kind == "string" and _COLUMN_LIST_RE.match(tj.value):
                    col_literal = tj.value.strip()
                j += 1
            if col_literal is not None:
                out.append(Finding(
                    code="tv-find-multiple-columns",
                    severity="warning",
                    line=tokens[k + 1].line,
                    message=(
                        f"Найти по нескольким колонкам («{col_literal}»): индекс применяется "
                        f"только по одному полю — поиск пойдёт перебором всех строк. "
                        f"Используйте НайтиСтроки с индексом, совпадающим со структурой поиска."
                    ),
                ))
            k = j
            continue
        k += 1
    return out


# ── Правила образования имён переменных ──────────────────────

def _iter_var_names(model):
    """yield (имя, строка, источник) для объявленных Перем и параметров методов."""
    for name, line, _is_export in model.var_declarations:
        yield name, line, "переменная"
    for m in model.methods:
        for p in m.params:
            yield p, m.header_line, "параметр"


@rule(code="var-name-starts-with-underscore", severity="warning",
      title="Имя переменной начинается с подчёркивания — запрещено")
def check_var_name_starts_with_underscore(ctx):
    """Флагует переменные и параметры, чьё имя начинается с «_».

    «Имена переменных запрещается начинать с подчёркивания».
    Проверяются объявления Перем и параметры методов — там имя заведомо является
    именем переменной (в отличие от произвольных обращений через точку).
    """
    out = []
    for name, line, kind in _iter_var_names(ctx.model):
        if name.startswith("_"):
            out.append(Finding(
                code="var-name-starts-with-underscore",
                severity="warning",
                line=line,
                message=f"Имя ({kind}) «{name}» начинается с подчёркивания — запрещено стандартом.",
            ))
    return out


@rule(code="var-name-single-char", severity="info",
      title="Имя переменной из одного символа — допустимо только для счётчиков циклов")
def check_var_name_single_char(ctx):
    """Флагует односимвольные имена объявленных Перем и параметров.

    «Имена переменных не должны состоять из одного символа. Использование
    односимвольных имён допускается только для счётчиков циклов».
    Счётчики циклов (Для Сч = …) объявляются в заголовке цикла, а не через Перем
    и не являются параметрами, поэтому под правило не попадают. severity=info —
    это стилистическая рекомендация.
    """
    out = []
    for name, line, kind in _iter_var_names(ctx.model):
        if len(name) == 1:
            out.append(Finding(
                code="var-name-single-char",
                severity="info",
                line=line,
                message=(
                    f"Имя ({kind}) «{name}» состоит из одного символа — "
                    f"односимвольные имена допустимы только для счётчиков циклов."
                ),
            ))
    return out


# ── Вызов исключений в коде ──────────────────────────────────

_RAISE_NAMES = {"ВЫЗВАТЬИСКЛЮЧЕНИЕ", "RAISE"}
_CANCEL_PARAM = {"ОТКАЗ", "CANCEL"}


@rule(code="raise-in-cancel-event", severity="info",
      title="ВызватьИсключение в обработчике с параметром Отказ — рассмотрите установку Отказ")
def check_raise_in_cancel_event(ctx):
    """Флагует ВызватьИсключение в методе, имеющем параметр «Отказ».

    «Неприемлемо в событиях ОбработкаПроверкиЗаполнения, ОбработкаПроведения,
    ПередЗаписью, ПриЗаписи, ПередУдалением и т.п. вызывать исключения для выдачи
    останавливающих предупреждений, которые должен отработать пользователь.
    Вместо этого следует устанавливать параметр Отказ в значение Истина и
    выводить сообщения пользователю» — так пользователь увидит все причины сразу.

    Параметр «Отказ» — надёжный признак такого обработчика (он и есть штатный
    механизм остановки). severity=info: стандарт допускает исключение, когда
    ситуация действительно исключительная, — это подсказка к ревью, а не вердикт.
    """
    model = ctx.model
    cancel_methods = [
        m for m in model.methods
        if any(p.upper() in _CANCEL_PARAM for p in m.params)
    ]
    if not cancel_methods:
        return []
    out = []
    for t in model.tokens:
        if t.kind == "ident" and t.value.upper() in _RAISE_NAMES:
            for m in cancel_methods:
                if m.header_line <= t.line <= m.end_line:
                    out.append(Finding(
                        code="raise-in-cancel-event",
                        severity="info",
                        line=t.line,
                        message=(
                            f"ВызватьИсключение в обработчике «{m.name}» с параметром Отказ: "
                            f"для останавливающих предупреждений пользователю устанавливайте "
                            f"Отказ = Истина и выводите сообщения (если ситуация не исключительная)."
                        ),
                    ))
                    break
    return out


# ── Перехват исключений в коде ───────────────────────────────

@rule(code="error-description-without-stack", severity="info",
      title="ОписаниеОшибки() не возвращает стек — используйте ПодробноеПредставлениеОшибки")
def check_error_description_without_stack(ctx):
    """Флагует вызов глобальной функции ОписаниеОшибки().

    «Не следует использовать функцию ОписаниеОшибки вместо функции
    ОбработкаОшибок.ПодробноеПредставлениеОшибки, т.к. она неинформативна для
    разработчика, потому что не возвращает стек в тексте ошибки».

    Детектируется идентификатор ОписаниеОшибки, за которым следует «(», и который
    не является обращением через точку (то есть именно глобальная функция).
    """
    out = []
    toks = ctx.model.tokens
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "ident" or t.value.upper() != "ОПИСАНИЕОШИБКИ":
            continue
        if not (i + 1 < n and toks[i + 1].kind == "op" and toks[i + 1].value == "("):
            continue
        if i > 0 and toks[i - 1].kind == "op" and toks[i - 1].value == ".":
            continue  # обращение через точку — не глобальная функция
        out.append(Finding(
            code="error-description-without-stack",
            severity="info",
            line=t.line,
            message=(
                "ОписаниеОшибки() не возвращает стек вызовов и неинформативна для "
                "разработчика — используйте ОбработкаОшибок.ПодробноеПредставлениеОшибки()."
            ),
        ))
    return out


# ── Определение типа значения переменной ─────────────────────

def _followed_by_string_compare(toks, j, n):
    """True, если с индекса j идёт сравнение (= или <>) со строковым литералом."""
    if j >= n:
        return False
    if toks[j].kind == "op" and toks[j].value == "=":
        k = j + 1
    elif (j + 1 < n and toks[j].kind == "op" and toks[j].value == "<"
          and toks[j + 1].kind == "op" and toks[j + 1].value == ">"):
        k = j + 2
    else:
        return False
    for m in range(k, min(k + 3, n)):
        if toks[m].kind == "string":
            return True
    return False


@rule(code="type-check-via-metadata-name", severity="warning",
      title="Тип определяется сравнением Метаданные().Имя со строкой — используйте ТипЗнч() = Тип()")
def check_type_check_via_metadata_name(ctx):
    """Флагует определение типа через сравнение «…Метаданные().Имя = "Имя"».

    «Определение типа значения переменной необходимо выполнять путём его
    сравнения с типом, а не каким-либо другим методом». ПРАВИЛЬНО:
    ТипЗнч(Ссылка) = Тип("ДокументСсылка.…"); НЕПРАВИЛЬНО:
    Ссылка.Метаданные().Имя = "…".

    Детектируется последовательность токенов «.Метаданные ( ) . Имя», за которой
    следует сравнение (=/<>) со строковым литералом. Обращения к Метаданные().Имя
    без сравнения со строкой (например для логирования) не флагуются.
    """
    out = []
    toks = ctx.model.tokens
    n = len(toks)
    i = 0
    while i < n - 5:
        if (toks[i].kind == "op" and toks[i].value == "."
                and toks[i + 1].kind == "ident" and toks[i + 1].value.upper() == "МЕТАДАННЫЕ"
                and toks[i + 2].kind == "op" and toks[i + 2].value == "("
                and toks[i + 3].kind == "op" and toks[i + 3].value == ")"
                and toks[i + 4].kind == "op" and toks[i + 4].value == "."
                and toks[i + 5].kind == "ident" and toks[i + 5].value.upper() == "ИМЯ"):
            if _followed_by_string_compare(toks, i + 6, n):
                out.append(Finding(
                    code="type-check-via-metadata-name",
                    severity="warning",
                    line=toks[i + 1].line,
                    message=(
                        "Тип определяется сравнением Метаданные().Имя со строкой — "
                        "используйте ТипЗнч(Значение) = Тип(\"…\"): имя метаданного ненадёжно "
                        "(регистр/переименование) и работает медленнее."
                    ),
                ))
            i += 6
            continue
        i += 1
    return out


# ── Копирование строк между таблицами значений ───────────────

_COLUMNS_IN_HEADER = re.compile(r"\.\s*Колонки\b", re.IGNORECASE | re.UNICODE)


@rule(code="column-copy-loop", severity="info",
      title="Копирование строк ТЗ перебором колонок — используйте ЗаполнитьЗначенияСвойств")
def check_column_copy_loop(ctx):
    """Флагует копирование значений строки ТЗ в цикле по `.Колонки`.

    «При копировании строк между различными таблицами значений … со схожим
    составом колонок следует использовать метод глобального контекста
    ЗаполнитьЗначенияСвойств» — он значительно эффективнее перебора колонок.

    Сигнал: цикл `Для Каждого <Колонка> Из <…>.Колонки Цикл`, в теле которого есть
    присваивание по имени колонки `<…>[<Колонка>.Имя] = …`. severity=info.
    """
    out = []
    model = ctx.model
    code_lines = ctx.code.split("\n")
    for loop in model.loops:
        lv = loop.loop_var
        if not lv:
            continue
        header_src = " ".join(code_lines[loop.header_line - 1:loop.header_end_line])
        if not _COLUMNS_IN_HEADER.search(header_src):
            continue
        assign_re = re.compile(
            r"\[\s*" + re.escape(lv) + r"\s*\.\s*Имя\s*\]\s*=",
            re.IGNORECASE | re.UNICODE,
        )
        for ln in range(loop.header_end_line + 1, loop.end_line):
            if assign_re.search(ctx.code_line(ln)):
                out.append(Finding(
                    code="column-copy-loop",
                    severity="info",
                    line=loop.header_line,
                    message=(
                        "Копирование значений по колонкам в цикле по «.Колонки» — "
                        "используйте ЗаполнитьЗначенияСвойств(СтрокаПриёмника, СтрокаИсточника): "
                        "короче и значительно быстрее."
                    ),
                ))
                break
    return out


# ── Общие требования к построению конструкций ────────────────

# Коды управляющих символов, у которых есть эквивалент в системном наборе Символы.
_SYMBOL_CODES = {
    "9": "Таб", "10": "ПС", "11": "ВТаб", "12": "ПФ", "13": "ВК", "160": "НПП",
}


@rule(code="char-code-literal", severity="info",
      title="Символ(код) вместо системного набора Символы.*")
def check_char_code_literal(ctx):
    """Флагует Символ(<код>) для стандартных разделителей — есть набор Символы.

    «Необходимо использовать системные наборы значений везде, где возможно их
    применить, например, вместо Символ(10) следует использовать Символы.ПС».

    Флагуется Символ(N) с числовым литералом N, для которого есть эквивалент в
    наборе Символы (9→Таб, 10→ПС, 11→ВТаб, 12→ПФ, 13→ВК, 160→НПП). Символ(<перем>)
    и прочие коды не затрагиваются.
    """
    out = []
    toks = ctx.model.tokens
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "ident" or t.value.upper() != "СИМВОЛ":
            continue
        if i > 0 and toks[i - 1].kind == "op" and toks[i - 1].value == ".":
            continue
        if not (i + 3 < n and toks[i + 1].kind == "op" and toks[i + 1].value == "("
                and toks[i + 2].kind == "number"
                and toks[i + 3].kind == "op" and toks[i + 3].value == ")"):
            continue
        code = toks[i + 2].value
        name = _SYMBOL_CODES.get(code)
        if name:
            out.append(Finding(
                code="char-code-literal",
                severity="info",
                line=t.line,
                message=(
                    f"Символ({code}) — используйте системный набор: Символы.{name}."
                ),
            ))
    return out


# ── Обработчики событий формы, подключаемые из кода ──────────

_ATTACH_PREFIXES = ("ПОДКЛЮЧАЕМЫЙ_", "ATTACHABLE_")


@rule(code="attachable-handler-prefix", severity="info",
      title="Обработчик из УстановитьДействие без префикса Подключаемый_")
def check_attachable_handler_prefix(ctx):
    """Флагует УстановитьДействие(<Событие>, "<Обработчик>"), где имя обработчика
    не начинается с префикса «Подключаемый_».

    «Обработчикам событий модуля формы, которые устанавливаются из кода с помощью
    метода УстановитьДействие, рекомендуется задавать префикс Подключаемый_»
    (Attachable_) — чтобы отличать их в результатах поиска неиспользуемых методов.

    Проверяется второй строковый аргумент вызова `.УстановитьДействие(...)`.
    Пустая строка (отключение действия) пропускается.
    """
    out = []
    toks = ctx.model.tokens
    n = len(toks)
    k = 0
    while k < n - 2:
        if (toks[k].kind == "op" and toks[k].value == "."
                and toks[k + 1].kind == "ident" and toks[k + 1].value.upper() == "УСТАНОВИТЬДЕЙСТВИЕ"
                and toks[k + 2].kind == "op" and toks[k + 2].value == "("):
            # Собрать строковые аргументы по индексам (depth 1).
            j = k + 3
            depth = 1
            arg_index = 0
            arg_string = {}      # индекс аргумента → строковый литерал (если аргумент — одна строка)
            arg_simple = {}      # индекс аргумента → только один токен
            while j < n and depth > 0:
                tj = toks[j]
                if tj.kind == "op" and tj.value == "(":
                    depth += 1
                elif tj.kind == "op" and tj.value == ")":
                    depth -= 1
                    if depth == 0:
                        break
                elif depth == 1 and tj.kind == "op" and tj.value == ",":
                    arg_index += 1
                elif depth == 1:
                    arg_simple[arg_index] = arg_simple.get(arg_index, 0) + 1
                    if tj.kind == "string":
                        arg_string[arg_index] = tj.value
                j += 1
            handler = arg_string.get(1)
            if handler and arg_simple.get(1) == 1:
                if not handler.upper().startswith(_ATTACH_PREFIXES):
                    out.append(Finding(
                        code="attachable-handler-prefix",
                        severity="info",
                        line=toks[k + 1].line,
                        message=(
                            f"Обработчик «{handler}» из УстановитьДействие — задайте имени префикс "
                            f"«Подключаемый_», чтобы отличать подключаемые обработчики."
                        ),
                    ))
            k = j
            continue
        k += 1
    return out


# ── Программное создание прикладных объектов ─────────────────

# Типы прикладных объектов, для которых есть менеджер с методом СоздатьX,
# поэтому конструктор Новый("…Объект.…") запрещён.
_APPLIED_OBJECT_TYPE = re.compile(
    r"^(?:Справочник|Документ|ПланВидовХарактеристик|ПланСчетов|ПланВидовРасчета|"
    r"БизнесПроцесс|Задача|ПланОбмена)Объект\."
    r"|^Регистр(?:Сведений|Накопления|Бухгалтерии|Расчета)НаборЗаписей\.",
    re.IGNORECASE | re.UNICODE,
)


@rule(code="new-applied-object-via-constructor", severity="warning",
      title="Создание прикладного объекта через Новый(...) вместо менеджера")
def check_new_applied_object_via_constructor(ctx):
    """Флагует `Новый("СправочникОбъект.…")` и подобное создание прикладных объектов.

    «Для программного создания прикладных объектов следует использовать методы
    соответствующих менеджеров (СоздатьЭлемент, СоздатьДокумент, СоздатьНаборЗаписей
    и т.д.). … использование конструктора (оператор Новый) запрещается».

    Детектируется `Новый(<строка>)`, где строка начинается с типа прикладного
    объекта, имеющего менеджер (СправочникОбъект., ДокументОбъект.,
    Регистр…НаборЗаписей. и т.п.).
    """
    out = []
    toks = ctx.model.tokens
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "ident" or t.value.upper() not in ("НОВЫЙ", "NEW"):
            continue
        if not (i + 2 < n and toks[i + 1].kind == "op" and toks[i + 1].value == "("
                and toks[i + 2].kind == "string"):
            continue
        type_name = toks[i + 2].value.strip()
        if _APPLIED_OBJECT_TYPE.match(type_name):
            out.append(Finding(
                code="new-applied-object-via-constructor",
                severity="warning",
                line=t.line,
                message=(
                    f"Создание «{type_name}» через конструктор Новый(...) запрещено — "
                    f"используйте метод менеджера (СоздатьЭлемент/СоздатьДокумент/"
                    f"СоздатьНаборЗаписей и т.п.)."
                ),
            ))
    return out


# ── Многократная запись регистров сведений и накопления ──────

@rule(code="record-set-in-loop", severity="info",
      title="СоздатьНаборЗаписей() в цикле — записывайте один набор")
def check_record_set_in_loop(ctx):
    """Флагует создание набора записей регистра внутри цикла.

    «Не рекомендуется записывать наборы записей регистров сведений и накоплений в
    цикле по одной или нескольким записям — это в несколько раз медленнее записи
    одним набором. Ориентир — порционная запись наборов из 1000 записей». Создание
    набора на каждой итерации — признак такой поэлементной записи: правильно
    создать набор один раз до цикла, наполнить в цикле и записать один раз (с
    подходящим РежимЗамещения).
    """
    out = []
    model = ctx.model
    for t in model.tokens:
        if t.kind == "ident" and t.value.upper() == "СОЗДАТЬНАБОРЗАПИСЕЙ":
            if model.is_in_loop(t.line):
                out.append(Finding(
                    code="record-set-in-loop",
                    severity="info",
                    line=t.line,
                    message=(
                        "СоздатьНаборЗаписей() в цикле: поэлементная запись набора в несколько "
                        "раз медленнее. Создайте набор один раз до цикла, наполните и запишите "
                        "один раз (порциями ~1000, с подходящим РежимЗамещения)."
                    ),
                ))
    return out


# ── Сдвиг границы последовательности документов ──────────────

@rule(code="sequence-boundary-in-posting", severity="info",
      title="Сдвиг границы последовательности при проведении — вынесите в регламент")
def check_sequence_boundary_in_posting(ctx):
    """Флагует вызов УстановитьГраницу в обработчике проведения.

    «Не рекомендуется двигать границу последовательности при проведении документов»
    — граница по одному набору значений измерений является одним ресурсом, при
    параллельном проведении пользователи блокируют друг друга. Операцию следует
    вынести из оперативных операций в регламентные.
    """
    out = []
    model = ctx.model
    posting = [
        m for m in model.methods
        if m.name and m.name.upper() in ("ОБРАБОТКАПРОВЕДЕНИЯ", "ПРИПРОВЕДЕНИИ")
    ]
    if not posting:
        return []
    toks = model.tokens
    n = len(toks)
    for k in range(n - 2):
        if (toks[k].kind == "op" and toks[k].value == "."
                and toks[k + 1].kind == "ident" and toks[k + 1].value.upper() == "УСТАНОВИТЬГРАНИЦУ"
                and toks[k + 2].kind == "op" and toks[k + 2].value == "("):
            line = toks[k + 1].line
            for m in posting:
                if m.header_line <= line <= m.end_line:
                    out.append(Finding(
                        code="sequence-boundary-in-posting",
                        severity="info",
                        line=line,
                        message=(
                            "Сдвиг границы последовательности (УстановитьГраницу) при проведении: "
                            "граница по набору измерений — один ресурс, параллельные проведения "
                            "блокируют друг друга. Вынесите операцию в регламентное задание."
                        ),
                    ))
                    break
    return out


# ── Порядок записи движений документов ───────────────────────

@rule(code="explicit-write-in-posting", severity="warning",
      title="Явная .Записать() в ОбработкаПроведения — запись должна быть неявной")
def check_explicit_write_in_posting(ctx):
    """Флагует явный вызов `.Записать()` в обработчике ОбработкаПроведения.

    «Не рекомендуется использовать явную запись наборов записей регистров (методом
    Записать) в процедурах обработки проведения документов. Запись должна
    производиться неявно системой, при завершении процедуры проведения» — иначе при
    параллельной работе возможны взаимные блокировки. Исключение — когда записанные
    данные нужны последующим алгоритмам до выхода из проведения.
    """
    out = []
    model = ctx.model
    posting = [
        m for m in model.methods
        if m.name and m.name.upper() == "ОБРАБОТКАПРОВЕДЕНИЯ"
    ]
    if not posting:
        return []
    toks = model.tokens
    n = len(toks)
    for k in range(n - 2):
        if (toks[k].kind == "op" and toks[k].value == "."
                and toks[k + 1].kind == "ident" and toks[k + 1].value.upper() == "ЗАПИСАТЬ"
                and toks[k + 2].kind == "op" and toks[k + 2].value == "("):
            line = toks[k + 1].line
            for m in posting:
                if m.header_line <= line <= m.end_line:
                    out.append(Finding(
                        code="explicit-write-in-posting",
                        severity="warning",
                        line=line,
                        message=(
                            "Явная .Записать() в ОбработкаПроведения: запись наборов записей "
                            "должна выполняться системой неявно при завершении проведения "
                            "(иначе риск взаимных блокировок). Оправдано, только если данные "
                            "нужны последующим шагам проведения."
                        ),
                    ))
                    break
    return out


# ── Использование РегистрСведенийМенеджерЗаписи ──────────────

@rule(code="record-manager-in-loop", severity="info",
      title="СоздатьМенеджерЗаписи() в цикле — используйте НаборЗаписей")
def check_record_manager_in_loop(ctx):
    """Флагует вызов СоздатьМенеджерЗаписи() внутри цикла.

    «Объект РегистрСведенийМенеджерЗаписи следует применять только тогда, когда …
    отбор одновременно по всем измерениям. В остальных случаях следует использовать
    РегистрСведенийНаборЗаписей». Создание менеджера записи на каждой итерации цикла
    с последующей записью — типовой анти-паттерн; эффективнее один набор записей.
    """
    out = []
    model = ctx.model
    for t in model.tokens:
        if t.kind == "ident" and t.value.upper() == "СОЗДАТЬМЕНЕДЖЕРЗАПИСИ":
            if model.is_in_loop(t.line):
                out.append(Finding(
                    code="record-manager-in-loop",
                    severity="info",
                    line=t.line,
                    message=(
                        "СоздатьМенеджерЗаписи() в цикле: запись по одной записи на итерацию "
                        "неэффективна — заполните РегистрСведенийНаборЗаписей и запишите один раз."
                    ),
                ))
    return out


# ── Запросы в цикле ──────────────────────────────────────────

# Методы объекта Запрос, обращающиеся к СУБД. Требуем предшествующую «.», поэтому
# глобальный оператор Выполнить("строка кода") сюда не попадает.
_QUERY_EXEC_NAMES = {"ВЫПОЛНИТЬ", "ВЫПОЛНИТЬПАКЕТ", "EXECUTE", "EXECUTEBATCH"}
_NEW_KW = {"НОВЫЙ", "NEW"}
_QUERY_TYPE = {"ЗАПРОС", "QUERY"}
_METHOD_KW = {"ПРОЦЕДУРА", "PROCEDURE", "ФУНКЦИЯ", "FUNCTION"}


def _query_execute_lines(model):
    """Строки с вызовом `<объект>.Выполнить(` / `.ВыполнитьПакет(` (метод Запрос)."""
    lines = []
    toks = model.tokens
    for k in range(len(toks) - 2):
        t0, t1, t2 = toks[k], toks[k + 1], toks[k + 2]
        if (t0.kind == "op" and t0.value == "."
                and t1.kind == "ident" and t1.value.upper() in _QUERY_EXEC_NAMES
                and t2.kind == "op" and t2.value == "("):
            lines.append(t1.line)
    return lines


def _new_query_lines(model):
    """Строки с конструктором `Новый Запрос`."""
    lines = []
    toks = model.tokens
    for k in range(len(toks) - 1):
        t0, t1 = toks[k], toks[k + 1]
        if (t0.kind == "ident" and t0.value.upper() in _NEW_KW
                and t1.kind == "ident" and t1.value.upper() in _QUERY_TYPE):
            lines.append(t1.line)
    return lines


def _methods_covering_lines(model, lines):
    """Множество ИМЁН методов (upper), в чьё тело попадает хотя бы одна строка lines."""
    names = set()
    if not lines:
        return names
    for m in model.methods:
        if not m.name:
            continue
        for ln in lines:
            if m.header_line <= ln <= m.end_line:
                names.add(m.name.upper())
                break
    return names


def _local_call_sites_in_loops(model, method_names):
    """Вызовы локальных методов из method_names в теле циклов.

    Локальный вызов — `Имя(` без предшествующей точки (квалифицированные вызовы
    `Объект.Метод(` и `ОбщийМодуль.Метод(` разрешаются вне модуля — не наш случай,
    глубина 1 работает только в рамках модуля). Заголовок объявления самого метода
    исключается. Возвращает список (строка, имя-как-в-коде)."""
    out = []
    if not method_names:
        return out
    toks = model.tokens
    n = len(toks)
    for k in range(n - 1):
        t = toks[k]
        if t.kind != "ident" or t.value.upper() not in method_names:
            continue
        nxt = toks[k + 1]
        if not (nxt.kind == "op" and nxt.value == "("):
            continue
        prev = toks[k - 1] if k > 0 else None
        if prev is not None and prev.kind == "op" and prev.value == ".":
            continue  # Объект.Метод( — не локальный вызов
        if prev is not None and prev.kind == "ident" and prev.value.upper() in _METHOD_KW:
            continue  # заголовок объявления метода
        if model.is_in_loop(t.line):
            out.append((t.line, t.value))
    return out


@rule(code="query-execute-in-loop", severity="warning",
      title="Запрос.Выполнить() в цикле — вынесите запрос из цикла")
def check_query_execute_in_loop(ctx):
    """Флагует выполнение запроса (`.Выполнить()`/`.ВыполнитьПакет()`) в теле цикла.

    «Следует стремиться к минимизации количества запросов к СУБД». Запрос на каждой
    итерации цикла — типовой анти-паттерн: как правило, его можно вынести из цикла и
    выполнить один раз, выбрав все нужные данные по списку (условие В (&Список)).
    Допустимые исключения (порционная обработка, виртуальные таблицы с датой среза) —
    проверяются вручную (query-review); при обоснованном исключении рядом должен быть
    комментарий.
    """
    out = []
    model = ctx.model
    for ln in _query_execute_lines(model):
        if model.is_in_loop(ln):
            out.append(Finding(
                code="query-execute-in-loop",
                severity="warning",
                line=ln,
                message=(
                    "Выполнение запроса (.Выполнить()) в цикле: запрос к СУБД на каждой "
                    "итерации. Вынесите запрос из цикла — выберите все данные одним запросом "
                    "(условие В (&Список)). Исключения (порционная обработка, ВТ с датой среза) "
                    "обоснуйте комментарием."
                ),
            ))
    return out


@rule(code="query-new-in-loop", severity="warning",
      title="Новый Запрос в цикле — создавайте объект запроса до цикла")
def check_query_new_in_loop(ctx):
    """Флагует создание объекта `Новый Запрос` в теле цикла.

    Пересоздание объекта запроса на каждой итерации — маркёр запроса в цикле. Объект
    Запрос следует создавать один раз до цикла (при необходимости менять только
    параметры через УстановитьПараметр), а лучше — выполнить один запрос по списку.
    """
    out = []
    model = ctx.model
    for ln in _new_query_lines(model):
        if model.is_in_loop(ln):
            out.append(Finding(
                code="query-new-in-loop",
                severity="warning",
                line=ln,
                message=(
                    "Новый Запрос в цикле: объект запроса пересоздаётся на каждой итерации. "
                    "Создайте запрос один раз до цикла (меняйте только параметры), а лучше "
                    "выберите все данные одним запросом по списку."
                ),
            ))
    return out


@rule(code="query-execute-in-loop-via-call", severity="warning",
      title="Вызов в цикле метода, выполняющего запрос (глубина 1)")
def check_query_execute_in_loop_via_call(ctx):
    """Флагует вызов в цикле локального метода модуля, который выполняет запрос.

    Неявный запрос в цикле: в теле цикла вызывается метод того же модуля, внутри
    которого есть `.Выполнить()`. Анализ межпроцедурный, глубина 1 и только в рамках
    модуля (вызовы в общие модули не раскрываются). severity=warning — скрытый запрос в
    цикле бьёт по производительности; если метод осознанно спроектирован для пакетной
    работы, проверьте граф вызовов через code-index и обоснуйте при ревью.
    """
    out = []
    model = ctx.model
    q_methods = _methods_covering_lines(model, _query_execute_lines(model))
    for ln, name in _local_call_sites_in_loops(model, q_methods):
        out.append(Finding(
            code="query-execute-in-loop-via-call",
            severity="warning",
            line=ln,
            message=(
                f"Вызов метода «{name}()» в цикле — внутри него выполняется запрос "
                f"(.Выполнить()): скрытый запрос к СУБД на каждой итерации. Вынесите запрос "
                f"из цикла или выберите данные по списку одним запросом. (глубина 1, в рамках "
                f"модуля; глубже — проверьте граф вызовов через code-index)"
            ),
        ))
    return out


@rule(code="query-new-in-loop-via-call", severity="warning",
      title="Вызов в цикле метода, создающего Новый Запрос (глубина 1)")
def check_query_new_in_loop_via_call(ctx):
    """Флагует вызов в цикле локального метода модуля, который создаёт `Новый Запрос`.

    Неявный запрос в цикле: в теле цикла вызывается метод того же модуля, внутри
    которого есть `Новый Запрос`. Межпроцедурно, глубина 1, только в рамках модуля.
    severity=warning; для большей глубины — анализ графа вызовов через code-index.
    """
    out = []
    model = ctx.model
    q_methods = _methods_covering_lines(model, _new_query_lines(model))
    for ln, name in _local_call_sites_in_loops(model, q_methods):
        out.append(Finding(
            code="query-new-in-loop-via-call",
            severity="warning",
            line=ln,
            message=(
                f"Вызов метода «{name}()» в цикле — внутри него создаётся Новый Запрос: "
                f"вероятен скрытый запрос на каждой итерации. Проверьте, нельзя ли вынести "
                f"запрос из цикла или выбрать данные по списку. (глубина 1, в рамках модуля; "
                f"глубже — проверьте граф вызовов через code-index)"
            ),
        ))
    return out


# ── БСП: сообщение пользователю через конструктор ────────────

_USER_MESSAGE_TYPE = {"СООБЩЕНИЕПОЛЬЗОВАТЕЛЮ", "USERMESSAGE"}


@rule(code="user-message-via-constructor", severity="info",
      title="Новый СообщениеПользователю вместо ОбщегоНазначения.СообщитьПользователю")
def check_user_message_via_constructor(ctx):
    """Флагует создание объекта `Новый СообщениеПользователю` (обычно с
    последующим `.Сообщить()`).

    В БСП для вывода сообщения есть `ОбщегоНазначения.СообщитьПользователю`
    (на клиенте — `ОбщегоНазначенияКлиент.СообщитьПользователю`) — сообщение с
    привязкой к данным/полю формы (КлючДанных, Поле, ПутьКДанным, Отказ). Голый
    `Новый СообщениеПользователю` такой привязки, как правило, лишён. Это находка
    навыка bsp-reuse, надёжно детектируемая по токенам; severity=info (единообразие
    и читаемость, не производительность — см. шкалу bsp-reuse).

    Паттерн: два соседних идентификатора `Новый` + `СообщениеПользователю`
    (конструктор типа) — ложные срабатывания маловероятны.
    """
    out = []
    toks = ctx.model.tokens
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind != "ident" or t.value.upper() not in _NEW_KW:
            continue
        if (i + 1 < n and toks[i + 1].kind == "ident"
                and toks[i + 1].value.upper() in _USER_MESSAGE_TYPE):
            out.append(Finding(
                code="user-message-via-constructor",
                severity="info",
                line=t.line,
                message=(
                    "«Новый СообщениеПользователю» → используйте "
                    "ОбщегоНазначения.СообщитьПользователю(Текст, КлючДанных, Поле, "
                    "ПутьКДанным, Отказ) — сообщение с привязкой к данным/полю формы "
                    "(в клиентском контексте — ОбщегоНазначенияКлиент)."
                ),
            ))
    return out
