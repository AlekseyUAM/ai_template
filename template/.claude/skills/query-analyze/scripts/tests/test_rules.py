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
    assert "many-joins" in _codes(q)   # 7 tables


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_six_tables_not_flagged():
    q = "ВЫБРАТЬ Т0.Код ИЗ Спр.A КАК Т0 " + " ".join(
        f"ЛЕВОЕ СОЕДИНЕНИЕ Спр.T{i} КАК Т{i} ПО Т{i}.Ссылка = Т0.Ссылка" for i in range(1, 6))
    assert "many-joins" not in _codes(q)  # 6 tables


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


# ── query-not-parseable ───────────────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_not_parseable_flagged():
    # Deliberately broken syntax: ВЫБРАТЬ … ИЗ without a source.
    assert "query-not-parseable" in _codes("ВЫБРАТЬ Код ИЗ")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_bom_stripped_before_parse():
    """1C export files often have a BOM - it must not cause query-not-parseable."""
    q = "﻿ВЫБРАТЬ Т.Код КАК Код ИЗ Справочник.Товары КАК Т"
    assert "query-not-parseable" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_parseable_not_flagged():
    assert "query-not-parseable" not in _codes("ВЫБРАТЬ Т.Код КАК Код ИЗ Справочник.Товары КАК Т")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_not_parseable_severity_warning():
    ctx = rules.QueryContext("ВЫБРАТЬ Код ИЗ")
    findings = [f for f in rules.run_all(ctx) if f.code == "query-not-parseable"]
    assert findings and findings[0].severity == "warning"


# ── keyword-lowercase ─────────────────────────────────

def test_keyword_lowercase_flagged():
    # keyword is entirely lowercase
    assert "keyword-lowercase" in _codes("выбрать Код из Справочник.Товары")


def test_keyword_lowercase_mixed_case_flagged():
    # keyword in mixed case
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
    # the word «выбрать» in a string literal must not cause a false hit
    # (simple case: it is not a keyword in SQL context)
    # Check that a normal query without string literals does not trigger falsely
    assert "keyword-lowercase" not in _codes(
        "ВЫБРАТЬ Ссылка, Наименование ИЗ Справочник.Номенклатура"
    )


def test_keyword_lowercase_not_flagged_in_dotted_field():
    assert "keyword-lowercase" not in _codes("ВЫБРАТЬ Т.конец ИЗ Регистр.Остатки КАК Т")


# ── alias-collides-with-field (errors 1 and 3) ─────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_collides_with_field_flagged():
    # The source alias «Номенклатура» matched the name of a tabular section field.
    q = (
        "ВЫБРАТЬ СписокНоменклатуры.Номенклатура КАК Номенклатура "
        "ИЗ Документ.ПриходнаяНакладная.СписокНоменклатуры КАК СписокНоменклатуры "
        "ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Номенклатура КАК Номенклатура "
        "ПО СписокНоменклатуры.Номенклатура = Номенклатура.Ссылка"
    )
    assert "alias-collides-with-field" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_collides_with_field_in_join_key():
    # The alias «Партия» matched a VT field in the join key (error 3).
    q = (
        "ВЫБРАТЬ ВТОстаткиСырые.Партия КАК Партия "
        "ПОМЕСТИТЬ ВТОстатки "
        "ИЗ ВТОстаткиСырые КАК ВТОстаткиСырые "
        "ЛЕВОЕ СОЕДИНЕНИЕ Документ.ПриходнаяНакладная КАК Партия "
        "ПО ВТОстаткиСырые.Партия = Партия.Ссылка"
    )
    assert "alias-collides-with-field" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_no_collision_not_flagged():
    # Non-overlapping alias «СпрНоменклатура» - must not trigger.
    q = (
        "ВЫБРАТЬ СписокНоменклатуры.Номенклатура КАК Номенклатура "
        "ИЗ Документ.ПриходнаяНакладная.СписокНоменклатуры КАК СписокНоменклатуры "
        "ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Номенклатура КАК СпрНоменклатура "
        "ПО СписокНоменклатуры.Номенклатура = СпрНоменклатура.Ссылка"
    )
    assert "alias-collides-with-field" not in _codes(q)


# ── order-after-totals (error 2) ────────────────────

def test_order_after_totals_flagged():
    # Text rule - works without node too.
    q = (
        "ВЫБРАТЬ ВТП.Номенклатура КАК Номенклатура "
        "ИЗ ВТПотребности КАК ВТП "
        "ИТОГИ ПО Номенклатура "
        "УПОРЯДОЧИТЬ ПО Номенклатура"
    )
    assert "order-after-totals" in _codes(q)


def test_order_before_totals_not_flagged():
    q = (
        "ВЫБРАТЬ ВТП.Номенклатура КАК Номенклатура "
        "ИЗ ВТПотребности КАК ВТП "
        "УПОРЯДОЧИТЬ ПО Номенклатура "
        "ИТОГИ ПО Номенклатура"
    )
    assert "order-after-totals" not in _codes(q)


def test_totals_without_order_not_flagged():
    q = "ВЫБРАТЬ ВТП.Номенклатура КАК Номенклатура ИЗ ВТ КАК ВТП ИТОГИ ПО Номенклатура"
    assert "order-after-totals" not in _codes(q)


# ── totals-field-not-aggregated (error 4) ───────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_totals_field_not_aggregated_flagged():
    q = (
        "ВЫБРАТЬ Т.Номенклатура КАК Номенклатура, Т.Услуга КАК Услуга "
        "ИЗ РегистрСведений.Цены КАК Т "
        "ИТОГИ ПО Номенклатура"
    )
    assert "totals-field-not-aggregated" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_totals_field_aggregated_not_flagged():
    q = (
        "ВЫБРАТЬ Т.Номенклатура КАК Номенклатура, Т.Услуга КАК Услуга "
        "ИЗ РегистрСведений.Цены КАК Т "
        "ИТОГИ МАКСИМУМ(Услуга) ПО Номенклатура"
    )
    assert "totals-field-not-aggregated" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_totals_grouping_field_not_flagged():
    # The grouping field (Номенклатура) is filled on totals rows - not flagged.
    q = (
        "ВЫБРАТЬ Т.Номенклатура КАК Номенклатура "
        "ИЗ РегистрСведений.Цены КАК Т "
        "ИТОГИ ПО Номенклатура"
    )
    assert "totals-field-not-aggregated" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_no_totals_not_flagged():
    q = "ВЫБРАТЬ Т.Номенклатура КАК Номенклатура, Т.Услуга КАК Услуга ИЗ РегистрСведений.Цены КАК Т"
    assert "totals-field-not-aggregated" not in _codes(q)


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


def test_keyword_case_expression_words_not_flagged_as_alias():
    # «Конец», «Выбор», «Когда», «Тогда», «Иначе» as a field alias (КАК Конец)
    # must not cause a false keyword-lowercase hit (Fix 2).
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
    # the whole query on one line (ВЫБРАТЬ and ИЗ on the same line)
    assert "query-one-line" in _codes(
        "ВЫБРАТЬ Код, Наименование ИЗ Справочник.Товары"
    )


def test_query_one_line_with_where_flagged():
    assert "query-one-line" in _codes(
        "ВЫБРАТЬ Код ИЗ Справочник.Товары ГДЕ Код > 0"
    )


def test_query_multiline_not_flagged():
    # a properly formatted multi-line query
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
    # К is a FIELD alias - the rule does not cover it
    assert "alias-single-char" not in _codes("ВЫБРАТЬ Т.Код КАК К ИЗ Справочник.Товары КАК Таб")


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_alias_source_in_join_flagged():
    q = "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Таб ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Цены КАК Ц ПО Ц.Товар = Таб.Ссылка"
    assert "alias-single-char" in _codes(q)


# ── Ordering of query results ────────────────

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
    # three members with two ОБЪЕДИНИТЬ without ВСЕ - two hits
    q = (
        "ВЫБРАТЬ А ИЗ Т1 КАК Т1\n"
        "ОБЪЕДИНИТЬ\n"
        "ВЫБРАТЬ Б ИЗ Т2 КАК Т2\n"
        "ОБЪЕДИНИТЬ\n"
        "ВЫБРАТЬ В ИЗ Т3 КАК Т3"
    )
    codes = _codes(q)
    assert codes.count("union-without-all") == 2


# ── ПОДОБНО operator (AST model) ──────────────────────


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


# ── Rounding of arithmetic operation results ──────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_without_cast_flagged():
    """Division without ВЫРАЗИТЬ - warning ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Числитель / Т.Знаменатель КАК Результат\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "division-without-cast" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_with_cast_not_flagged():
    """Division is wrapped in ВЫРАЗИТЬ - no warning ."""
    q = (
        "ВЫБРАТЬ\n"
        "    ВЫРАЗИТЬ(Т.Числитель / Т.Знаменатель КАК Число(15,8)) КАК Результат\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "division-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_cast_on_operands_not_flagged():
    """ВЫРАЗИТЬ on the operands (not on the result) - division inside a ВЫРАЗИТЬ wrapper."""
    q = (
        "ВЫБРАТЬ\n"
        "    ВЫРАЗИТЬ(Т.Множитель * Т.Числитель КАК Число(25,10)) / ВЫРАЗИТЬ(Т.Знаменатель КАК Число(15,10)) КАК Результат\n"
        "ИЗ\n"
        "    Таблица КАК Т"
    )
    # the expression contains '/', but starts with ВЫРАЗИТЬ -> flagged: no,
    # since the division result is not wrapped. The standard allows this variant
    # (ВЫРАЗИТЬ on the operands); the auto-check does not reject it - it is hard to distinguish
    # the "casts on operands" variant from "no cast anywhere" without semantics.
    # Deliberate: this scenario is NOT flagged (a false negative is acceptable).
    pass


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_avg_without_cast_flagged():
    """СРЕДНЕЕ without ВЫРАЗИТЬ - warning ."""
    q = (
        "ВЫБРАТЬ\n"
        "    СРЕДНЕЕ(Т.Сумма) КАК СредняяСумма\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "avg-without-cast" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_avg_with_cast_not_flagged():
    """СРЕДНЕЕ is wrapped in ВЫРАЗИТЬ - no warning ."""
    q = (
        "ВЫБРАТЬ\n"
        "    ВЫРАЗИТЬ(СРЕДНЕЕ(Т.Сумма) КАК Число(15,2)) КАК СредняяСумма\n"
        "ИЗ\n"
        "    Документ.Продажа КАК Т"
    )
    assert "avg-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_multiline_flagged():
    """Division in a multi-line query - also flagged."""
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
    """A normal query without division and СРЕДНЕЕ - no hits ."""
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
    """СРЕДНЕЕ without ВЫРАЗИТЬ has severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n    СРЕДНЕЕ(Т.Цена) КАК СрЦена\nИЗ\n    Документ.Продажа КАК Т"
    )
    findings = rules.run_all(ctx)
    avg_findings = [f for f in findings if f.code == "avg-without-cast"]
    assert avg_findings and avg_findings[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_division_is_warning_severity():
    """Division without ВЫРАЗИТЬ has severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n    Т.А / Т.Б КАК Частное\nИЗ\n    Документ.Продажа КАК Т"
    )
    findings = rules.run_all(ctx)
    div_findings = [f for f in findings if f.code == "division-without-cast"]
    assert div_findings and div_findings[0].severity == "warning"


# ── ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ ────────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_full_join_flagged():
    """ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ - must produce a warning ."""
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
    """ЛЕВОЕ СОЕДИНЕНИЕ - must not produce ."""
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
    """ВНУТРЕННЕЕ СОЕДИНЕНИЕ - must not produce ."""
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
    """ has severity=warning (a methodological recommendation, not a prohibition)."""
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
    """Two full joins in one package - two hits for two queries."""
    q = (
        "ВЫБРАТЬ ЕСТЬNULL(А.Код, Б.Код) КАК Код ИЗ Спр.А КАК А ПОЛНОЕ СОЕДИНЕНИЕ Спр.Б КАК Б ПО А.Ссылка = Б.Ссылка;\n"
        "ВЫБРАТЬ ЕСТЬNULL(В.Код, Г.Код) КАК Код ИЗ Спр.В КАК В ПОЛНОЕ СОЕДИНЕНИЕ Спр.Г КАК Г ПО В.Ссылка = Г.Ссылка"
    )
    assert _codes(q).count("full-join") == 2


# ── Nested queries in a join condition ────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_join_on_flagged():
    """Nested ВЫБРАТЬ in a ПО condition - must produce an error ."""
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
    """Example from the standard  - a nested query in the ПО of a LEFT JOIN."""
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
    """A plain join without a nested query - must not produce ."""
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
    """A nested query in ИЗ (data source) - must not produce ."""
    q = (
        "ВЫБРАТЬ\n"
        "    П.Код\n"
        "ИЗ\n"
        "    (ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т) КАК П"
    )
    assert "subquery-in-join-condition" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_subquery_in_select_field_not_flagged():
    """A nested query in a ВЫБРАТЬ field - must not produce ."""
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
    """ - a nested query in a join condition - severity=warning ("should not")."""
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


# ── Joins with nested queries and virtual tables ──

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_join_to_subquery_flagged():
    """A join with a nested query (data source is a subquery) - must produce ."""
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
    """join-to-subquery - severity=warning ("should not")."""
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
    """A plain join with a metadata table - must not produce join-to-subquery."""
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
    """A join with a virtual table - must not produce join-to-subquery."""
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
    """Two joins with subqueries in one query - one hit."""
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


# ── Efficient query conditions ─────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__podstroka_in_where_flagged():
    """ПОДСТРОКА is applied to a field in a ГДЕ condition - flagged as function-in-condition."""
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
    """МЕСЯЦ is applied to a field in a ГДЕ condition - flagged by function-in-condition."""
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
    """ГОД is applied to a field in a ГДЕ condition - flagged by function-in-condition."""
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
    """A plain Поле = Значение condition - not flagged by function-in-condition."""
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
    """ПОДСТРОКА in an ADDITIONAL condition (when a main index condition
    `Т.Код = &Код` is present) is NOT flagged:  the standard prohibits functions in the MAIN condition,
    while in additional ones they are allowed (the main condition has already narrowed the selection)."""
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
    """ВЫБОР as the sole ГДЕ condition - flagged by case-as-sole-condition (item 5)."""
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
    """ВЫБОР as an additional condition (after И with the main index condition) - not flagged (item 5 RIGHT)."""
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
    """function-in-condition has severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т\nГДЕ МЕСЯЦ(Т.Дата) = 1"
    )
    findings = rules.run_all(ctx)
    fcs = [f for f in findings if f.code == "function-in-condition"]
    assert fcs and fcs[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__case_sole_is_warning():
    """case-as-sole-condition has severity=warning."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ Т.Код ИЗ Спр.Т КАК Т\n"
        "ГДЕ ВЫБОР КОГДА Т.П = 1 ТОГДА Т.А > 0 ИНАЧЕ Т.Б > 0 КОНЕЦ"
    )
    findings = rules.run_all(ctx)
    fcs = [f for f in findings if f.code == "case-as-sole-condition"]
    assert fcs and fcs[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__no_conditions_no_false_positive():
    """A query without ГДЕ - no hits ."""
    q = "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т"
    assert not any(c.startswith(":") for c in _codes(q))


# ── Access to virtual tables ─────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_filter_in_where_flagged():
    """A virtual table field filter is moved to ГДЕ - must be flagged ."""
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
    """The filter is passed to the virtual table parameters - must not be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки(, Склад = &Склад) КАК О"
    )
    assert "vt-filter-in-where" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__non_virtual_where_not_flagged():
    """A filter in ГДЕ on a non-virtual table - must not be flagged ."""
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
    """vt-filter-in-where has severity=warning ("not recommended")."""
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


# ── Efficient access to the Остатки VT ───────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_with_period_flagged():
    """Остатки VT with an explicit date (period) - must be flagged ."""
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
    """Остатки VT without a date (empty first parameter) - must not be flagged ."""
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
    """Остатки() VT with empty parentheses - must not be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ОстаткиТоваров.Остатки() КАК О"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_oboroty_not_flagged():
    """ОстаткиИОбороты VT - must not be flagged  (a different table)."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.ОстаткиТоваров.ОстаткиИОбороты(&Нач, &Кон, , , Склад = &Склад) КАК О"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__non_virtual_not_flagged():
    """A regular table (not the Остатки VT) - must not be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "ostatok-with-period" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__ostatok_with_period_is_info():
    """ostatok-with-period has severity=info (balances as of a date are legitimate,
    the intent cannot be determined from the text; the rule only asks to check)."""
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
    """Остатки VT of an accounting register with a date - must be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Счет\n"
        "ИЗ\n"
        "    РегистрБухгалтерии.Хозрасчетный.Остатки(&Дата) КАК О"
    )
    assert "ostatok-with-period" in _codes(q)


# ── Number of virtual table parameters ─────────────────

# VT signatures are fixed: РН.Остатки has (Период, Условие), РН.Обороты has 4,
# РН.ОстаткиИОбороты has 5, РС.СрезПоследних/СрезПервых has 2. Omitted trailing
# parameters are allowed (default values), extra ones are a platform error.

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_ostatki_too_many_params_flagged():
    """РН.Остатки: a dimension filter is passed as the THIRD argument, but the signature is
    (Период, Условие). The platform will not compile such a query."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура КАК Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.Товары.Остатки(\n"
        "        ДОБАВИТЬКДАТЕ(КОНЕЦПЕРИОДА(&Дата, ДЕНЬ), СЕКУНДА, 1),\n"
        "        ,\n"
        "        Организация = &Организация) КАК О"
    )
    findings = rules.run_all(rules.QueryContext(q))
    found = [f for f in findings if f.code == "vt-too-many-params"]
    assert found and found[0].severity == "error"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_ostatki_condition_in_second_param_not_flagged():
    """Correct form: the dimension filter is in the SECOND parameter (Условие)."""
    q = (
        "ВЫБРАТЬ\n"
        "    О.Номенклатура КАК Номенклатура\n"
        "ИЗ\n"
        "    РегистрНакопления.Товары.Остатки(&Дата, Организация = &Организация) КАК О"
    )
    assert "vt-too-many-params" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_ostatki_fewer_params_not_flagged():
    """Omitted trailing VT parameters are allowed (default values are used)."""
    q = "ВЫБРАТЬ О.Номенклатура ИЗ РегистрНакопления.Товары.Остатки(&Дата) КАК О"
    assert "vt-too-many-params" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_oboroty_four_params_not_flagged():
    q = (
        "ВЫБРАТЬ О.Номенклатура ИЗ "
        "РегистрНакопления.Товары.Обороты(&Нач, &Кон, , Склад = &Склад) КАК О"
    )
    assert "vt-too-many-params" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_oboroty_five_params_flagged():
    q = (
        "ВЫБРАТЬ О.Номенклатура ИЗ "
        "РегистрНакопления.Товары.Обороты(&Нач, &Кон, , Склад = &Склад, Лишний = 1) КАК О"
    )
    assert "vt-too-many-params" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_ostatki_oboroty_six_params_flagged():
    q = (
        "ВЫБРАТЬ О.Номенклатура ИЗ "
        "РегистрНакопления.Товары.ОстаткиИОбороты(&Нач, &Кон, , , Склад = &Склад, Лишний = 1) КАК О"
    )
    assert "vt-too-many-params" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_srez_poslednih_three_params_flagged():
    q = (
        "ВЫБРАТЬ К.Курс ИЗ "
        "РегистрСведений.Курсы.СрезПоследних(&Дата, Валюта = &Валюта, Лишний = 1) КАК К"
    )
    assert "vt-too-many-params" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_buh_ostatki_too_many_params_flagged():
    """РБ.Остатки: maximum is 4 parameters (period, account condition, subconto types,
    condition). The 5th argument is an error regardless of the metadata composition."""
    q = (
        "ВЫБРАТЬ О.Счет ИЗ "
        "РегистрБухгалтерии.Хозрасчетный.Остатки(&Дата, УсловиеСчета, , , Лишний = 1) КАК О"
    )
    assert "vt-too-many-params" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__vt_no_parens_not_flagged():
    q = "ВЫБРАТЬ К.Курс ИЗ РегистрСведений.Курсы.СрезПоследних КАК К"
    assert "vt-too-many-params" not in _codes(q)


# ── Use of temporary tables ──────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__join_no_index_flagged():
    """A VT without ИНДЕКСИРОВАТЬ ПО participates in a JOIN - must be flagged by temp-table-join-no-index."""
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
    """A VT with ИНДЕКСИРОВАТЬ ПО participates in a JOIN - must not be flagged by temp-table-join-no-index."""
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
    """A VT without ИНДЕКСИРОВАТЬ ПО but NOT used in a JOIN - must not be flagged."""
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
    """temp-table-join-no-index has severity=warning ("should be indexed")."""
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
    """A VT without ИНДЕКСИРОВАТЬ ПО is used in В (...) - must be flagged by temp-table-in-no-index."""
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
    """A VT with ИНДЕКСИРОВАТЬ ПО in В (...) - must not be flagged by temp-table-in-no-index."""
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
    """temp-table-in-no-index has severity=warning ("should be indexed")."""
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
    """A single query without ПОМЕСТИТЬ - no hits ."""
    q = "ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т"
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__drop_temp_not_flagged():
    """УНИЧТОЖИТЬ is not ПОМЕСТИТЬ, there must be no hit."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Т ИЗ Справочник.Товары КАК Т\n"
        "ИНДЕКСИРОВАТЬ ПО Т.Код;\n"
        "УНИЧТОЖИТЬ ВТ_Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


# ── Counting records ─────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_one_flagged():
    """СУММА(1) instead of КОЛИЧЕСТВО(*) - must be flagged by sum-one-for-count."""
    q = (
        "ВЫБРАТЬ\n"
        "    СУММА(1) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "sum-one-for-count" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__isnull_sum_one_flagged():
    """ЕСТЬNULL(СУММА(1), 0) - must be flagged by sum-one-for-count."""
    q = (
        "ВЫБРАТЬ\n"
        "    ЕСТЬNULL(СУММА(1), 0) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "sum-one-for-count" in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__kolvo_star_not_flagged():
    """КОЛИЧЕСТВО(*) - the correct pattern, must not be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(*) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__kolvo_field_not_flagged():
    """КОЛИЧЕСТВО(Т.Код) - the correct pattern, must not be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(Т.Код) КАК Количество\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_one_is_warning():
    """sum-one-for-count has severity=warning (the "one should use КОЛИЧЕСТВО" recommendation)."""
    ctx = rules.QueryContext(
        "ВЫБРАТЬ\n    СУММА(1) КАК К\nИЗ\n    Справочник.Товары КАК Т"
    )
    findings = rules.run_all(ctx)
    found = [f for f in findings if f.code == "sum-one-for-count"]
    assert found and found[0].severity == "warning"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_case_without_cast_flagged():
    """СУММА(ВЫБОР...ТОГДА 1...) without ВЫРАЗИТЬ - must be flagged by sum-case-without-cast."""
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
    """СУММА(ВЫБОР...ТОГДА ВЫРАЗИТЬ(1 КАК ЧИСЛО(17,0))...) - the correct pattern, must not be flagged."""
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
    """СУММА(ВЫБОР...ТОГДА Т.Сумма...) - not a counter, must not be flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    СУММА(ВЫБОР КОГДА Т.ЭтоГруппа ТОГДА Т.Сумма ИНАЧЕ 0 КОНЕЦ) КАК СуммаГрупп\n"
        "ИЗ\n"
        "    Справочник.Номенклатура КАК Т"
    )
    assert "sum-case-without-cast" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__sum_case_without_cast_is_warning():
    """sum-case-without-cast has severity=warning (one "should" extend the precision)."""
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
    """СУММА(Т.Поле) - a regular sum, not flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    СУММА(Т.Количество) КАК ОбщееКоличество\n"
        "ИЗ\n"
        "    Документ.Реализация КАК Т"
    )
    assert not any(c.startswith(":") for c in _codes(q))


# ── Queries in dynamic lists ────────────────────

@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__last_query_from_temp_only_flagged():
    """The last SELECT in the package selects ONLY from VTs - must be flagged ."""
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
    """The last SELECT joins a VT with a real table - not flagged ."""
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
    """A single query without ПОМЕСТИТЬ - not flagged ."""
    q = (
        "ВЫБРАТЬ\n"
        "    Т.Код\n"
        "ИЗ\n"
        "    Справочник.Товары КАК Т"
    )
    assert "last-query-from-temp-only" not in _codes(q)


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test__last_query_from_temp_is_warning():
    """last-query-from-temp-only has severity=warning ("should be redesigned")."""
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
    """УНИЧТОЖИТЬ is not SELECT and does not affect the determination of the "last" SELECT."""
    q = (
        "ВЫБРАТЬ Т.Код ПОМЕСТИТЬ ВТ_Т ИЗ Справочник.Товары КАК Т;\n"
        "ВЫБРАТЬ ВТ.Код ИЗ ВТ_Т КАК ВТ\n"
        "ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Документы КАК Д ПО ВТ.Код = Д.Товар;\n"
        "УНИЧТОЖИТЬ ВТ_Т"
    )
    assert "last-query-from-temp-only" not in _codes(q)
