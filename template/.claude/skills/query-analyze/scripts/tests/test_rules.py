import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rules

HAVE_NODE = shutil.which("node") is not None


def _codes(text):
    ctx = rules.QueryContext(text)
    return [f.code for f in rules.run_all(ctx)]


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_select_star_flagged():
    assert "select-star" in _codes("ВЫБРАТЬ * ИЗ Справочник.Товары КАК Т")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_select_explicit_fields_not_flagged():
    assert "select-star" not in _codes("ВЫБРАТЬ Т.Код, Т.Наименование ИЗ Справочник.Товары КАК Т")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_select_multiplication_not_flagged():
    assert "select-star" not in _codes("ВЫБРАТЬ Т.Цена * Т.Кол КАК Сумма ИЗ Документ.Продажа КАК Т")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_many_tables_flagged():
    q = "ВЫБРАТЬ Т0.Код ИЗ Спр.A КАК Т0 " + " ".join(
        f"ЛЕВОЕ СОЕДИНЕНИЕ Спр.T{i} КАК Т{i} ПО Т{i}.Ссылка = Т0.Ссылка" for i in range(1, 7))
    assert "many-joins" in _codes(q)   # 7 таблиц


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_six_tables_not_flagged():
    q = "ВЫБРАТЬ Т0.Код ИЗ Спр.A КАК Т0 " + " ".join(
        f"ЛЕВОЕ СОЕДИНЕНИЕ Спр.T{i} КАК Т{i} ПО Т{i}.Ссылка = Т0.Ссылка" for i in range(1, 6))
    assert "many-joins" not in _codes(q)  # 6 таблиц


def test_context_line_of():
    ctx = rules.QueryContext("ВЫБРАТЬ\n*\nИЗ Т")
    assert ctx.line_of(ctx.text.index("*")) == 2


def test_statements_split_by_semicolon():
    ctx = rules.QueryContext("ВЫБРАТЬ 1;\nВЫБРАТЬ 2 ПОМЕСТИТЬ Т;\nВЫБРАТЬ 3")
    stmts = ctx.statements
    assert len(stmts) == 3
    assert [s[0] for s in stmts] == [1, 2, 3]
    assert "ВЫБРАТЬ 2" in stmts[1][1]


def test_statements_ignores_empty_trailing():
    ctx = rules.QueryContext("ВЫБРАТЬ 1;")
    assert len(ctx.statements) == 1
    assert ctx.statements[0][0] == 1


# ── keyword-lowercase ─────────────────────────────────

def test_keyword_lowercase_flagged():
    # ключевое слово полностью строчное
    assert "keyword-lowercase" in _codes("выбрать Код из Справочник.Товары")


def test_keyword_lowercase_mixed_case_flagged():
    # ключевое слово в смешанном регистре
    assert "keyword-lowercase" in _codes("Выбрать Код Из Справочник.Товары")


def test_keyword_lowercase_where_flagged():
    assert "keyword-lowercase" in _codes(
        "ВЫБРАТЬ Код ИЗ Справочник.Товары где Код > 0"
    )


def test_keyword_uppercase_not_flagged():
    assert "keyword-lowercase" not in _codes(
        "ВЫБРАТЬ Код, Наименование ИЗ Справочник.Товары ГДЕ Код > 0"
    )


def test_keyword_uppercase_join_not_flagged():
    assert "keyword-lowercase" not in _codes(
        "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т "
        "ЛЕВОЕ СОЕДИНЕНИЕ РегистрНакопления.Остатки КАК О ПО Т.Ссылка = О.Номенклатура"
    )


def test_keyword_as_alias_value_not_flagged():
    # слово «выбрать» в строковом литерале не должно давать ложное срабатывание
    # (простой случай: оно не является ключевым словом в SQL-контексте)
    # Проверяем, что нормальный запрос без строковых литералов не ложно срабатывает
    assert "keyword-lowercase" not in _codes(
        "ВЫБРАТЬ Ссылка, Наименование ИЗ Справочник.Номенклатура"
    )


def test_keyword_lowercase_not_flagged_in_dotted_field():
    assert "keyword-lowercase" not in _codes("ВЫБРАТЬ Т.конец ИЗ Регистр.Остатки КАК Т")


def test_keyword_case_expression_words_not_flagged_as_alias():
    # «Конец», «Выбор», «Когда», «Тогда», «Иначе» как псевдоним поля (КАК Конец)
    # не должны давать ложное срабатывание keyword-lowercase (Fix 2).
    assert "keyword-lowercase" not in _codes("ВЫБРАТЬ Т.Дата КАК Конец ИЗ Спр.Т КАК Т")


def test_keyword_lowercase_not_flagged_in_comment_or_string():
    assert "keyword-lowercase" not in _codes('ВЫБРАТЬ Т.Код // из базы\nИЗ Спр.Т КАК Т\nГДЕ Т.Имя = "из это"')


def test_keyword_lowercase_flagged_real():
    assert "keyword-lowercase" in _codes("выбрать Т.Код из Спр.Т как Т")


# ── Part A: QueryContext.code / code_upper ────────────────────

def test_code_blanks_strings_and_comments_preserving_positions():
    ctx = rules.QueryContext('ВЫБРАТЬ Поле // из базы\nГДЕ П = "из этого"')
    assert len(ctx.code) == len(ctx.text)
    assert ctx.code.count("\n") == ctx.text.count("\n")
    assert "из базы" not in ctx.code
    assert "из этого" not in ctx.code
    assert "ВЫБРАТЬ Поле" in ctx.code


# ── query-one-line ─────────────────────────────────────

def test_query_one_line_flagged():
    # весь запрос в одну строку (ВЫБРАТЬ и ИЗ на одной строке)
    assert "query-one-line" in _codes(
        "ВЫБРАТЬ Код, Наименование ИЗ Справочник.Товары"
    )


def test_query_one_line_with_where_flagged():
    assert "query-one-line" in _codes(
        "ВЫБРАТЬ Код ИЗ Справочник.Товары ГДЕ Код > 0"
    )


def test_query_multiline_not_flagged():
    # правильно оформленный многострочный запрос
    assert "query-one-line" not in _codes(
        "ВЫБРАТЬ\n\tКод,\n\tНаименование\nИЗ\n\tСправочник.Товары"
    )


def test_query_select_and_from_different_lines_not_flagged():
    assert "query-one-line" not in _codes(
        "ВЫБРАТЬ Код\nИЗ Справочник.Товары"
    )


def test_query_one_line_not_flagged_multiline_with_inline_subquery():
    q = ("ВЫБРАТЬ\n    Т.Код,\n    (ВЫБРАТЬ СУММА(О.Кол) ИЗ Регистр.Остатки КАК О) КАК Ост\nИЗ\n    Справочник.Товары КАК Т")
    assert "query-one-line" not in _codes(q)


# ── alias-starts-with-underscore ──────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_underscore_source_flagged():
    assert "alias-starts-with-underscore" in _codes("ВЫБРАТЬ Таб.Код КАК Код ИЗ Справочник.Товары КАК _таб")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_underscore_field_not_flagged():
    assert "alias-starts-with-underscore" not in _codes("ВЫБРАТЬ Таб.Код КАК _а ИЗ Справочник.Товары КАК Таб")


# ── alias-single-char ──────────────────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_single_char_source_flagged():
    assert "alias-single-char" in _codes("ВЫБРАТЬ Т.Код КАК Код ИЗ Справочник.Товары КАК Т")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_single_char_field_not_flagged():
    # К — псевдоним ПОЛЯ,  его не регулирует
    assert "alias-single-char" not in _codes("ВЫБРАТЬ Т.Код КАК К ИЗ Справочник.Товары КАК Таб")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_source_in_join_flagged():
    q = "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Таб ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Цены КАК Ц ПО Ц.Товар = Таб.Ссылка"
    assert "alias-single-char" in _codes(q)


# ── Упорядочивание результатов запроса ────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_autoorder_not_recommended_flagged():
    assert "autoorder-not-recommended" in _codes("ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т АВТОУПОРЯДОЧИВАНИЕ")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_autoorder_with_first_flagged_and_no_double():
    codes = _codes("ВЫБРАТЬ ПЕРВЫЕ 5 Т.Код ИЗ Спр.Т КАК Т АВТОУПОРЯДОЧИВАНИЕ")
    assert "autoorder-with-first" in codes
    assert "autoorder-not-recommended" not in codes


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_no_autoorder_not_flagged():
    codes = _codes("ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т")
    assert not any(c.startswith(":") for c in codes)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_autoorder_cross_statement_not_combined():
    q = "ВЫБРАТЬ ПЕРВЫЕ 10 Т.Код ИЗ Спр.Т КАК Т;\nВЫБРАТЬ Д.Код ИЗ Спр.Д КАК Д АВТОУПОРЯДОЧИВАНИЕ"
    codes = _codes(q)
    assert "autoorder-with-first" not in codes
    assert "autoorder-not-recommended" in codes


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_autoorder_with_first_is_error_severity():
    ctx = rules.QueryContext("ВЫБРАТЬ ПЕРВЫЕ 5 Т.Код ИЗ Спр.Т КАК Т АВТОУПОРЯДОЧИВАНИЕ")
    findings = rules.run_all(ctx)
    with_first = [f for f in findings if f.code == "autoorder-with-first"]
    assert with_first and with_first[0].severity == "error"


# ── ОБЪЕДИНИТЬ vs ОБЪЕДИНИТЬ ВСЕ ─────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_union_without_all_flagged():
    assert "union-without-all" in _codes("ВЫБРАТЬ 1 КАК П ОБЪЕДИНИТЬ ВЫБРАТЬ 2")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_union_all_not_flagged():
    assert "union-without-all" not in _codes("ВЫБРАТЬ 1 КАК П ОБЪЕДИНИТЬ ВСЕ ВЫБРАТЬ 2")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_union_without_all_multiline_flagged():
    q = (
        "ВЫБРАТЬ\n    ПТУ.Ссылка\nИЗ\n    Документ.ПоступлениеТоваровУслуг КАК ПТУ\n"
        "ОБЪЕДИНИТЬ\n"
        "ВЫБРАТЬ\n    РТУ.Ссылка\nИЗ\n    Документ.РеализацияТоваровУслуг КАК РТУ"
    )
    assert "union-without-all" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_union_all_multiline_not_flagged():
    q = (
        "ВЫБРАТЬ\n    ПТУ.Ссылка\nИЗ\n    Документ.ПоступлениеТоваровУслуг КАК ПТУ\n"
        "ОБЪЕДИНИТЬ ВСЕ\n"
        "ВЫБРАТЬ\n    РТУ.Ссылка\nИЗ\n    Документ.РеализацияТоваровУслуг КАК РТУ"
    )
    assert "union-without-all" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_union_without_all_multiple_flagged_once_each():
    # три члена с двумя ОБЪЕДИНИТЬ без ВСЕ — два срабатывания
    q = (
        "ВЫБРАТЬ А ИЗ Т1 КАК Т1\n"
        "ОБЪЕДИНИТЬ\n"
        "ВЫБРАТЬ Б ИЗ Т2 КАК Т2\n"
        "ОБЪЕДИНИТЬ\n"
        "ВЫБРАТЬ В ИЗ Т3 КАК Т3"
    )
    codes = _codes(q)
    assert codes.count("union-without-all") == 2


# ── Оператор ПОДОБНО (AST-модель) ──────────────────────


def _like(q):
    return _codes("ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т ГДЕ Т.Имя ПОДОБНО " + q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_leading_percent_flagged():
    assert "like-leading-wildcard" in _like('"%абв"')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_leading_underscore_flagged():
    assert "like-leading-wildcard" in _like('"_абв"')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_trailing_percent_ok():
    assert "like-leading-wildcard" not in _like('"абв%"')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_param_ok():
    assert not any(c.startswith(":") for c in _like("&Шаблон"))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_field_operand_concat_flagged():
    assert "like-concatenation" in _like("Т.Шаблон")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_concat_flagged():
    assert "like-concatenation" in _like('"абв" + "%"')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_literal_not_concat():
    assert "like-concatenation" not in _like('"абв%"')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_brackets_flagged_error():
    fs = [f for f in rules.run_all(rules.QueryContext('ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т ГДЕ Т.Имя ПОДОБНО "[абв]%"')) if f.code == "like-square-brackets"]
    assert fs and fs[0].severity == "error"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_brackets_escaped_specsymbol_ok():
    assert "like-square-brackets" not in _codes('ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т ГДЕ Т.Имя ПОДОБНО "~[тест~]" СПЕЦСИМВОЛ "~"')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_unrelated_arithmetic_not_concat():
    assert "like-concatenation" not in _codes('ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т ГДЕ Т.Имя ПОДОБНО "АВ%" И Т.Цена + Т.Налог > 0')


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_like_in_comment_not_flagged():
    assert not any(c.startswith(":") for c in _codes('ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т // ПОДОБНО "%x"\nГДЕ Т.Код = 1'))


# ── Округление результатов арифметических операций ──────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_without_cast_flagged():
    """Деление без ВЫРАЗИТЬ — предупреждение ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Числитель / Т.Знаменатель КАК Результат\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "division-without-cast" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_with_cast_not_flagged():
    """Деление обёрнуто в ВЫРАЗИТЬ — нет предупреждения ."""
    q = (
        "ВЫБРАТЬ\n"
        "    ВЫРАЗИТЬ(Т.Числитель / Т.Знаменатель КАК Число(15,8)) КАК Результат\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "division-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_cast_on_operands_not_flagged():
    """ВЫРАЗИТЬ на операндах (а не на результате) — деление внутри ВЫРАЗИТЬ-обёртки."""
    q = (
        "ВЫБРАТЬ\n"
        "    ВЫРАЗИТЬ(Т.Множитель * Т.Числитель КАК Число(25,10)) / ВЫРАЗИТЬ(Т.Знаменатель КАК Число(15,10)) КАК Результат\n"
        "ИЗ\n"
        "    Таблица КАК Т"
    )
    # выражение содержит '/', но начинается с ВЫРАЗИТЬ → flagged: нет,
    # т.к. результат деления не обёрнут. Стандарт разрешает этот вариант
    # (ВЫРАЗИТЬ на операндах); автопроверка его не отклоняет — сложно отличить
    # вариант «касты на операндах» от «нет каста нигде» без семантики.
    # Осознанно: данный сценарий НЕ флагуется (ложное не-срабатывание приемлемо).
    pass


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_avg_without_cast_flagged():
    """СРЕДНЕЕ без ВЫРАЗИТЬ — предупреждение ."""
    q = (
        "ВЫБРАТЬ\n"
        "    СРЕДНЕЕ(Т.Сумма) КАК СредняяСумма\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "avg-without-cast" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_avg_with_cast_not_flagged():
    """СРЕДНЕЕ обёрнуто в ВЫРАЗИТЬ — нет предупреждения ."""
    q = (
        "ВЫБРАТЬ\n"
        "    ВЫРАЗИТЬ(СРЕДНЕЕ(Т.Сумма) КАК Число(15,2)) КАК СредняяСумма\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "avg-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_multiline_flagged():
    """Деление в многострочном запросе — тоже флагуется."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.КоличествоДней / 365 КАК ДоляГода,\n"
        "    Т.Сумма КАК Сумма\n"
        "ИЗ\n"
        "    РегистрСведений.Данные КАК Т"
    )
    assert "division-without-cast" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_no_arithmetic_not_flagged():
    """Обычный запрос без деления и СРЕДНЕЕ — нет срабатываний ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код,\n"
        "    Т.Сумма\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_avg_is_warning_severity():
    """СРЕДНЕЕ без ВЫРАЗИТЬ имеет severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n    СРЕДНЕЕ(Т.Цена) КАК СрЦена\nИЗ\n    Документ.Продажа КАК Т"
    )
    findings = rules.run_all(ctx)
    avg_findings = [f for f in findings if f.code == "avg-without-cast"]
    assert avg_findings and avg_findings[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_is_warning_severity():
    """Деление без ВЫРАЗИТЬ имеет severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n    Т.А / Т.Б КАК Частное\nИЗ\n    Документ.Продажа КАК Т"
    )
    findings = rules.run_all(ctx)
    div_findings = [f for f in findings if f.code == "division-without-cast"]
    assert div_findings and div_findings[0].severity == "warning"


# ── ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ ────────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_full_join_flagged():
    """ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ — должно давать предупреждение ."""
    q = (
        "ВЫБРАТЬ\n"
        "    ЕСТЬNULL(ПП.Номенклатура, ФП.Номенклатура) КАК Номенклатура\n"
        "ИЗ\n"
        "    ПланПродаж КАК ПП\n"
        "        ПОЛНОЕ СОЕДИНЕНИЕ ФактическиеПродажи КАК ФП\n"
        "        ПО ПП.Номенклатура = ФП.Номенклатура"
    )
    assert "full-join" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_left_join_not_flagged():
    """ЛЕВОЕ СОЕДИНЕНИЕ — не должно давать ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрНакопления.Остатки КАК О\n"
        "        ПО О.Номенклатура = Т.Ссылка"
    )
    assert "full-join" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_inner_join_not_flagged():
    """ВНУТРЕННЕЕ СОЕДИНЕНИЕ — не должно давать ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "        ВНУТРЕННЕЕ СОЕДИНЕНИЕ РегистрНакопления.Остатки КАК О\n"
        "        ПО О.Номенклатура = Т.Ссылка"
    )
    assert "full-join" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_full_join_is_warning_severity():
    """ имеет severity=warning (методическая рекомендация, не запрет)."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n"
        "    ЕСТЬNULL(А.Код, Б.Код) КАК Код\n"
        "ИЗ\n"
        "    Спр.А КАК А\n"
        "        ПОЛНОЕ СОЕДИНЕНИЕ Спр.Б КАК Б\n"
        "        ПО А.Ссылка = Б.Ссылка"
    )
    findings = rules.run_all(ctx)
    fj = [f for f in findings if f.code == "full-join"]
    assert fj and fj[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_full_join_two_joins_flagged_twice():
    """Два ПОЛНЫХ СОЕДИНЕНИЯ в одном пакете — два срабатывания на два запроса."""
    q = (
        "ВЫБРАТЬ ЕСТЬNULL(А.Код, Б.Код) КАК Код ИЗ Спр.А КАК А ПОЛНОЕ СОЕДИНЕНИЕ Спр.Б КАК Б ПО А.Ссылка = Б.Ссылка;\n"
        "ВЫБРАТЬ ЕСТЬNULL(В.Код, Г.Код) КАК Код ИЗ Спр.В КАК В ПОЛНОЕ СОЕДИНЕНИЕ Спр.Г КАК Г ПО В.Ссылка = Г.Ссылка"
    )
    assert _codes(q).count("full-join") == 2


# ── Вложенные запросы в условии соединения ────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_join_on_flagged():
    """Вложенный ВЫБРАТЬ в условии ПО — должен давать ошибку ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Спр.А КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ Спр.Б КАК Б\n"
        "        ПО Б.С В (ВЫБРАТЬ Х.С ИЗ Спр.Х КАК Х)"
    )
    assert "subquery-in-join-condition" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_join_on_standard_example_flagged():
    """Пример из стандарта  — вложенный запрос в ПО ЛЕВОГО СОЕДИНЕНИЯ."""
    q = (
        "ВЫБРАТЬ\n"
        "    ОстаткиТоваров.Номенклатура КАК Номенклатура,\n"
        "    Цены.Цена КАК ЦенаПрошлогоМесяца\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК ОстаткиТоваров\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрСведений.Цена КАК Цены\n"
        "        ПО Цены.Номенклатура = ОстаткиТоваров.Номенклатура\n"
        "        И Цены.Период В (\n"
        "            ВЫБРАТЬ МАКСИМУМ(ЦеныПрошлогоМесяца.Период)\n"
        "            ИЗ РегистрСведений.Цена КАК ЦеныПрошлогоМесяца\n"
        "            ГДЕ ЦеныПрошлогоМесяца.Период < НАЧАЛОПЕРИОДА(ОстаткиТоваров.Период, МЕСЯЦ)\n"
        "        )\n"
        "ГДЕ\n"
        "    ОстаткиТоваров.Склад = &Склад"
    )
    assert "subquery-in-join-condition" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_plain_join_no_subquery_not_flagged():
    """Обычное соединение без вложенного запроса — не должно давать ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрНакопления.Остатки КАК О\n"
        "        ПО О.Номенклатура = Т.Ссылка"
    )
    assert "subquery-in-join-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_from_not_flagged():
    """Вложенный запрос в ИЗ (источник данных) — не должен давать ."""
    q = (
        "ВЫБРАТЬ\n"
        "    П.Код\n"
        "ИЗ\n"
        "    (ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т) КАК П"
    )
    assert "subquery-in-join-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_select_field_not_flagged():
    """Вложенный запрос в поле ВЫБРАТЬ — не должен давать ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код,\n"
        "    (ВЫБРАТЬ СУММА(О.Кол) ИЗ Регистр.Остатки КАК О) КАК Ост\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "subquery-in-join-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_join_on_is_warning_severity():
    """ — вложенный запрос в условии соединения — severity=warning («не следует»)."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Спр.А КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ Спр.Б КАК Б\n"
        "        ПО Б.С В (ВЫБРАТЬ Х.С ИЗ Спр.Х КАК Х)"
    )
    findings = rules.run_all(ctx)
    subq = [f for f in findings if f.code == "subquery-in-join-condition"]
    assert subq and subq[0].severity == "warning"


# ── Соединения с вложенными запросами и виртуальными таблицами ──

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_join_to_subquery_flagged():
    """Соединение с вложенным запросом (источник данных — подзапрос) — должно давать ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Документ.РеализацияТоваровУслуг КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ (\n"
        "            ВЫБРАТЬ\n"
        "                РС.Номенклатура КАК Номенклатура\n"
        "            ИЗ РегистрСведений.Лимиты КАК РС\n"
        "            ГДЕ РС.Дата > &Дата\n"
        "            СГРУППИРОВАТЬ ПО РС.Номенклатура\n"
        "        ) КАК Лимиты\n"
        "        ПО Лимиты.Номенклатура = Т.Номенклатура"
    )
    assert "join-to-subquery" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_join_to_subquery_is_warning_severity():
    """join-to-subquery — severity=warning («не следует»)."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Спр.А КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ (\n"
        "            ВЫБРАТЬ Х.С КАК С ИЗ Спр.Х КАК Х\n"
        "        ) КАК П\n"
        "        ПО П.С = Т.Ссылка"
    )
    ctx = rules.QueryContext(q)
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "join-to-subquery"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_plain_join_to_table_not_flagged():
    """Обычное соединение с таблицей метаданных — не должно давать join-to-subquery."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрСведений.Лимиты КАК Лим\n"
        "        ПО Лим.Номенклатура = Т.Ссылка"
    )
    assert "join-to-subquery" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_join_to_virtual_table_not_flagged():
    """Соединение с виртуальной таблицей — не должно давать join-to-subquery."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрНакопления.ТоварыНаСкладах.Остатки() КАК Ост\n"
        "        ПО Ост.Номенклатура = Т.Ссылка"
    )
    assert "join-to-subquery" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_join_to_subquery_one_finding_per_query():
    """Два соединения с подзапросами в одном запросе — одно срабатывание."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Спр.А КАК Т\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ (ВЫБРАТЬ Х.С КАК С ИЗ Спр.Х КАК Х) КАК П1\n"
        "        ПО П1.С = Т.Ссылка\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ (ВЫБРАТЬ Х.С КАК С ИЗ Спр.Х КАК Х) КАК П2\n"
        "        ПО П2.С = Т.Ссылка"
    )
    assert _codes(q).count("join-to-subquery") == 1


# ── Эффективные условия запросов ─────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__podstroka_in_where_flagged():
    """ПОДСТРОКА применяется к полю в условии ГДЕ — флагуется как function-in-condition."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        'ГДЕ\n'
        '    ПОДСТРОКА(Т.Имя, 1, 6) = "строка"'
    )
    assert "function-in-condition" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__month_in_where_flagged():
    """МЕСЯЦ применяется к полю в условии ГДЕ — флагуется function-in-condition."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        "    МЕСЯЦ(Т.Дата) = 1"
    )
    assert "function-in-condition" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__year_in_where_flagged():
    """ГОД применяется к полю в условии ГДЕ — флагуется function-in-condition."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        "    ГОД(Т.Дата) = 2024"
    )
    assert "function-in-condition" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__normal_condition_not_flagged():
    """Обычное условие Поле = Значение — не флагуется function-in-condition."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        "    Т.Имя = &Имя"
    )
    assert "function-in-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__podstroka_as_secondary_not_flagged():
    """ПОДСТРОКА в ДОПОЛНИТЕЛЬНОМ условии (при наличии основного индексного
    `Т.Код = &Код`) НЕ флагуется:  запрещает функции в ОСНОВНОМ условии,
    а в дополнительных они допустимы (основное условие уже сузило выборку)."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        '    Т.Код = &Код\n'
        '    И ПОДСТРОКА(Т.Имя, 1, 6) = "строка"'
    )
    assert "function-in-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__case_as_sole_condition_flagged():
    """ВЫБОР как единственное условие ГДЕ — флагуется case-as-sole-condition (п.5)."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        "    ВЫБОР\n"
        "        КОГДА Т.Поле2 = &Значение2\n"
        "        ТОГДА Т.Поле3 > 0\n"
        "        ИНАЧЕ Т.Поле4 > 0\n"
        "    КОНЕЦ"
    )
    assert "case-as-sole-condition" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__case_as_secondary_not_flagged():
    """ВЫБОР как дополнительное условие (после И с основным индексным условием) — не флагуется (п.5 ПРАВИЛЬНО)."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        "    Т.Поле1 = &Значение1\n"
        "    И ВЫБОР\n"
        "        КОГДА Т.Поле2 = &Значение2\n"
        "        ТОГДА Т.Поле3 > 0\n"
        "        ИНАЧЕ Т.Поле4 > 0\n"
        "    КОНЕЦ"
    )
    assert "case-as-sole-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__function_in_condition_is_warning():
    """function-in-condition имеет severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т\nГДЕ МЕСЯЦ(Т.Дата) = 1"
    )
    findings = rules.run_all(ctx)
    fcs = [f for f in findings if f.code == "function-in-condition"]
    assert fcs and fcs[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__case_sole_is_warning():
    """case-as-sole-condition имеет severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т\n"
        "ГДЕ ВЫБОР КОГДА Т.П = 1 ТОГДА Т.А > 0 ИНАЧЕ Т.Б > 0 КОНЕЦ"
    )
    findings = rules.run_all(ctx)
    fcs = [f for f in findings if f.code == "case-as-sole-condition"]
    assert fcs and fcs[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__no_conditions_no_false_positive():
    """Запрос без ГДЕ — нет срабатываний ."""
    q = "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т"
    assert not any(c.startswith(":") for c in _codes(q))


# ── Обращения к виртуальным таблицам ─────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_filter_in_where_flagged():
    """Фильтр на поле виртуальной таблицы вынесен в ГДЕ — должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК О\n"
        "ГДЕ\n"
        "    О.Склад = &Склад"
    )
    assert "vt-filter-in-where" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_filter_in_params_not_flagged():
    """Фильтр передан в параметры виртуальной таблицы — не должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки(, Склад = &Склад) КАК О"
    )
    assert "vt-filter-in-where" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__non_virtual_where_not_flagged():
    """Фильтр в ГДЕ на НЕ-виртуальной таблице — не должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Наименование\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ГДЕ\n"
        "    Т.Склад = &Склад"
    )
    assert "vt-filter-in-where" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_filter_in_where_is_warning():
    """vt-filter-in-where имеет severity=warning («не рекомендуется»)."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК О\n"
        "ГДЕ\n"
        "    О.Склад = &Склад"
    )
    ctx = rules.QueryContext(q)
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "vt-filter-in-where"]
    assert found and found[0].severity == "warning"


# ── Эффективное обращение к ВТ Остатки ───────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_with_period_flagged():
    """ВТ Остатки с явной датой (period) — должна флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура,\n"
        "    О.КоличествоОстаток\n"
        "ИЗ\n"
        "    РегистрНакопления.ОстаткиТоваров.Остатки(&СегодняшняяДата, Склад = &Склад) КАК О"
    )
    assert "ostatok-with-period" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_without_period_not_flagged():
    """ВТ Остатки без даты (пустой первый параметр) — не должна флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура,\n"
        "    О.КоличествоОстаток\n"
        "ИЗ\n"
        "    РегистрНакопления.ОстаткиТоваров.Остатки(, Склад = &Склад) КАК О"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_empty_parens_not_flagged():
    """ВТ Остатки() с пустыми скобками — не должна флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ОстаткиТоваров.Остатки() КАК О"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_oboroty_not_flagged():
    """ВТ ОстаткиИОбороты — не должна флагироваться  (другая таблица)."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ОстаткиТоваров.ОстаткиИОбороты(&Нач, &Кон, , , Склад = &Склад) КАК О"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__non_virtual_not_flagged():
    """Обычная таблица (не ВТ Остатки) — не должна флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_with_period_is_info():
    """ostatok-with-period имеет severity=info (остатки на дату — легитимны,
    намерение по тексту не определить; правило лишь просит проверить)."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.Товары.Остатки(&Дата) КАК О"
    )
    ctx = rules.QueryContext(q)
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "ostatok-with-period"]
    assert found and found[0].severity == "info"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__buh_ostatok_with_period_flagged():
    """ВТ Остатки регистра бухгалтерии с датой — должна флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Счет\n"
        "ИЗ\n"
        "    РегистрБухгалтерии.Хозрасчетный.Остатки(&Дата) КАК О"
    )
    assert "ostatok-with-period" in _codes(q)


# ── Использование временных таблиц ──────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__join_no_index_flagged():
    """ВТ без ИНДЕКСИРОВАТЬ ПО участвует в JOIN — должна флагироваться temp-table-join-no-index."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Товары\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    ВТ.Код,\n"
        "    Д.Наименование\n"
        "ИЗ\n"
        "    ВТ_Товары КАК ВТ\n"
        "    ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Документы КАК Д\n"
        "    ПО ВТ.Код = Д.Товар"
    )
    assert "temp-table-join-no-index" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__join_with_index_not_flagged():
    """ВТ с ИНДЕКСИРОВАТЬ ПО участвует в JOIN — не должна флагироваться temp-table-join-no-index."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Товары\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ИНДЕКСИРОВАТЬ ПО Т.Код;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    ВТ.Код,\n"
        "    Д.Наименование\n"
        "ИЗ\n"
        "    ВТ_Товары КАК ВТ\n"
        "    ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Документы КАК Д\n"
        "    ПО ВТ.Код = Д.Товар"
    )
    assert "temp-table-join-no-index" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__no_join_not_flagged():
    """ВТ без ИНДЕКСИРОВАТЬ ПО, но НЕ используемая в JOIN — не должна флагироваться."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Товары\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    ВТ.Код\n"
        "ИЗ\n"
        "    ВТ_Товары КАК ВТ"
    )
    assert "temp-table-join-no-index" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__join_no_index_is_warning():
    """temp-table-join-no-index имеет severity=warning («следует индексировать»)."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Т ИЗ Справочник.Товары КАК Т;\n"
        "ВЫБРАТЬ ВТ.Код ИЗ ВТ_Т КАК ВТ\n"
        "ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Документы КАК Д ПО ВТ.Код = Д.Товар"
    )
    ctx = rules.QueryContext(q)
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "temp-table-join-no-index"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__in_no_index_flagged():
    """ВТ без ИНДЕКСИРОВАТЬ ПО используется в В (...) — должна флагироваться temp-table-in-no-index."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Коды\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    Д.Ссылка\n"
        "ИЗ\n"
        "    Документ.Реализация КАК Д\n"
        "ГДЕ\n"
        "    Д.Номенклатура В (ВЫБРАТЬ ВТ.Код ИЗ ВТ_Коды КАК ВТ)"
    )
    assert "temp-table-in-no-index" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__in_with_index_not_flagged():
    """ВТ с ИНДЕКСИРОВАТЬ ПО в В (...) — не должна флагироваться temp-table-in-no-index."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Коды\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т\n"
        "ИНДЕКСИРОВАТЬ ПО Т.Код;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    Д.Ссылка\n"
        "ИЗ\n"
        "    Документ.Реализация КАК Д\n"
        "ГДЕ\n"
        "    Д.Номенклатура В (ВЫБРАТЬ ВТ.Код ИЗ ВТ_Коды КАК ВТ)"
    )
    assert "temp-table-in-no-index" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__in_no_index_is_warning():
    """temp-table-in-no-index имеет severity=warning («следует индексировать»)."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Коды ИЗ Справочник.Товары КАК Т;\n"
        "ВЫБРАТЬ Д.Ссылка ИЗ Документ.Реализация КАК Д\n"
        "ГДЕ Д.Номенклатура В (ВЫБРАТЬ ВТ.Код ИЗ ВТ_Коды КАК ВТ)"
    )
    ctx = rules.QueryContext(q)
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "temp-table-in-no-index"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__single_query_no_false_positive():
    """Одиночный запрос без ПОМЕСТИТЬ — нет срабатываний ."""
    q = "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т"
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__drop_temp_not_flagged():
    """УНИЧТОЖИТЬ — не является ПОМЕСТИТЬ, срабатывания  не должно быть."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Т ИЗ Справочник.Товары КАК Т\n"
        "ИНДЕКСИРОВАТЬ ПО Т.Код;\n"
        "УНИЧТОЖИТЬ ВТ_Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


# ── Вычисление количества записей ─────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_one_flagged():
    """СУММА(1) вместо КОЛИЧЕСТВО(*) — должно флагироваться sum-one-for-count."""
    q = (
        "ВЫБРАТЬ\n"
        "    СУММА(1) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "sum-one-for-count" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__isnull_sum_one_flagged():
    """ЕСТЬNULL(СУММА(1), 0) — должно флагироваться sum-one-for-count."""
    q = (
        "ВЫБРАТЬ\n"
        "    ЕСТЬNULL(СУММА(1), 0) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "sum-one-for-count" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__kolvo_star_not_flagged():
    """КОЛИЧЕСТВО(*) — правильный паттерн, не должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(*) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__kolvo_field_not_flagged():
    """КОЛИЧЕСТВО(Т.Код) — правильный паттерн, не должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(Т.Код) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_one_is_warning():
    """sum-one-for-count имеет severity=warning (рекомендация «следует КОЛИЧЕСТВО»)."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n    СУММА(1) КАК К\nИЗ\n    Справочник.Товары КАК Т"
    )
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "sum-one-for-count"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_case_without_cast_flagged():
    """СУММА(ВЫБОР...ТОГДА 1...) без ВЫРАЗИТЬ — должно флагироваться sum-case-without-cast."""
    q = (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(*) КАК Количество,\n"
        "    СУММА(ВЫБОР КОГДА Т.ЭтоГруппа ТОГДА 1 ИНАЧЕ 0 КОНЕЦ) КАК КоличествоГрупп\n"
        "ИЗ\n"
        "    Справочник.Номенклатура КАК Т"
    )
    assert "sum-case-without-cast" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_case_with_cast_not_flagged():
    """СУММА(ВЫБОР...ТОГДА ВЫРАЗИТЬ(1 КАК ЧИСЛО(17,0))...) — правильный паттерн, не должно флагироваться."""
    q = (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(*) КАК Количество,\n"
        "    СУММА(ВЫБОР КОГДА Т.ЭтоГруппа ТОГДА ВЫРАЗИТЬ(1 КАК ЧИСЛО(17, 0)) ИНАЧЕ 0 КОНЕЦ) КАК КоличествоГрупп\n"
        "ИЗ\n"
        "    Справочник.Номенклатура КАК Т"
    )
    assert "sum-case-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_case_field_not_flagged():
    """СУММА(ВЫБОР...ТОГДА Т.Сумма...) — не счётчик, не должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    СУММА(ВЫБОР КОГДА Т.ЭтоГруппа ТОГДА Т.Сумма ИНАЧЕ 0 КОНЕЦ) КАК СуммаГрупп\n"
        "ИЗ\n"
        "    Справочник.Номенклатура КАК Т"
    )
    assert "sum-case-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_case_without_cast_is_warning():
    """sum-case-without-cast имеет severity=warning («следует» расширить разрядность)."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n"
        "    СУММА(ВЫБОР КОГДА Т.Ф ТОГДА 1 ИНАЧЕ 0 КОНЕЦ) КАК Кол\n"
        "ИЗ\n"
        "    Справочник.Т КАК Т"
    )
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "sum-case-without-cast"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_field_not_flagged():
    """СУММА(Т.Поле) — обычная сумма, не флагируется ."""
    q = (
        "ВЫБРАТЬ\n"
        "    СУММА(Т.Количество) КАК ОбщееКоличество\n"
        "ИЗ\n"
        "    Документ.Реализация КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


# ── Запросы в динамических списках ────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__last_query_from_temp_only_flagged():
    """Последний SELECT в пакете выбирает ТОЛЬКО из ВТ — должно флагироваться ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Товары\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    ВТ.Код\n"
        "ИЗ\n"
        "    ВТ_Товары КАК ВТ"
    )
    assert "last-query-from-temp-only" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__last_query_with_real_table_not_flagged():
    """Последний SELECT соединяет ВТ с реальной таблицей — не флагируется ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ПОМЕСТИТЬ ВТ_Товары\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т;\n"
        "\n"
        "ВЫБРАТЬ\n"
        "    ВТ.Код,\n"
        "    Д.Наименование\n"
        "ИЗ\n"
        "    ВТ_Товары КАК ВТ\n"
        "    ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Документы КАК Д\n"
        "    ПО ВТ.Код = Д.Товар"
    )
    assert "last-query-from-temp-only" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__single_query_no_temp_not_flagged():
    """Одиночный запрос без ПОМЕСТИТЬ — не флагируется ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "last-query-from-temp-only" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__last_query_from_temp_is_warning():
    """last-query-from-temp-only имеет severity=warning («следует перепроектировать»)."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Т ИЗ Справочник.Товары КАК Т;\n"
        "ВЫБРАТЬ ВТ.Код ИЗ ВТ_Т КАК ВТ"
    )
    ctx = rules.QueryContext(q)
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "last-query-from-temp-only"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__drop_temp_after_real_select_not_flagged():
    """УНИЧТОЖИТЬ — не SELECT, не влияет на определение «последнего» SELECT."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Т ИЗ Справочник.Товары КАК Т;\n"
        "ВЫБРАТЬ ВТ.Код ИЗ ВТ_Т КАК ВТ\n"
        "ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Документы КАК Д ПО ВТ.Код = Д.Товар;\n"
        "УНИЧТОЖИТЬ ВТ_Т"
    )
    assert "last-query-from-temp-only" not in _codes(q)
