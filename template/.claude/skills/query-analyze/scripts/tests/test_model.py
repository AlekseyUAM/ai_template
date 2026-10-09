import sys, shutil
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rules

HAVE_NODE = shutil.which("node") is not None


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node для разбора через бандл")
def test_model_parses_real_query():
    ctx = rules.QueryContext("ВЫБРАТЬ Т.Код ИЗ Справочник.Товары КАК Т")
    m = ctx.model
    assert m is not None and ctx.model_error is None
    tables = m["members"][0]["members"][0]["model"]["tables"]
    assert tables[0]["fullName"] == "Справочник.Товары"
    assert tables[0]["alias"] == "Т"


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_iter_query_models_yields_leaf():
    ctx = rules.QueryContext("ВЫБРАТЬ 1 КАК П ОБЪЕДИНИТЬ ВЫБРАТЬ 2")
    rows = list(rules.iter_query_models(ctx))
    assert len(rows) == 2
    # второй участник добавлен через ОБЪЕДИНИТЬ (без ВСЕ) -> distinct True
    assert rows[1][1] is True


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node")
def test_model_parse_error_is_graceful():
    ctx = rules.QueryContext("ВЫБРАТЬ ИЗ ГДЕ ПОДОБНО")  # заведомо битый
    m = ctx.model
    # не бросает исключение — результат либо None, либо dict
    assert m is None or isinstance(m, dict)
    # если модель не распарсилась, должна быть зафиксирована причина
    if m is None:
        assert ctx.model_error is not None


def test_model_none_when_bundle_missing(monkeypatch):
    monkeypatch.setattr(rules, "_PARSER_BUNDLE", "/nonexistent/sdbl_parse.js")
    ctx = rules.QueryContext("ВЫБРАТЬ 1")
    assert ctx.model is None
    assert ctx.model_error is not None


def test_iter_query_models_empty_when_no_model(monkeypatch):
    monkeypatch.setattr(rules, "_PARSER_BUNDLE", "/nonexistent/sdbl_parse.js")
    ctx = rules.QueryContext("ВЫБРАТЬ 1")
    assert list(rules.iter_query_models(ctx)) == []


def test_model_error_set_when_bundle_missing(monkeypatch):
    """ctx.model_error не None, когда бандл парсера отсутствует (Fix 1 — Critical)."""
    monkeypatch.setattr(rules, "_PARSER_BUNDLE", "/nonexistent/sdbl_parse.js")
    ctx = rules.QueryContext("ВЫБРАТЬ * ИЗ Спр.Т КАК Т")
    _ = ctx.model
    assert ctx.model_error is not None


def test_ast_rules_produce_no_findings_when_bundle_missing(monkeypatch):
    """AST-правила не дают находок без бандла — документируем тихий пропуск (Fix 1 — Critical).

    Запрос «ВЫБРАТЬ * ИЗ Спр.Т КАК Т» нарушает select-star,
    но без парсера находок не будет — правило молча пропускается.
    """
    monkeypatch.setattr(rules, "_PARSER_BUNDLE", "/nonexistent/sdbl_parse.js")
    ctx = rules.QueryContext("ВЫБРАТЬ * ИЗ Спр.Т КАК Т")
    findings = rules.run_all(ctx)
    _TEXT_ONLY = frozenset({"keyword-lowercase", "query-one-line"})
    ast_findings = [f for f in findings if f.code not in _TEXT_ONLY]
    assert ast_findings == [], (
        "AST-правила должны возвращать пустой список при недоступном парсере"
    )
