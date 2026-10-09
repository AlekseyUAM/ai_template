import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_queries import (
    extract_query_strings,
    extract_queries_from_xml,
    unescape_xml_entities,
)


def test_multiline_query_with_pipes():
    src = "\n".join([
        "Процедура Тест()",
        '\tЗапрос.Текст = "ВЫБРАТЬ',
        "\t|\tТаблица.Поле",
        "\t|ИЗ",
        '\t|\tСправочник.Тест КАК Таблица";',
        "КонецПроцедуры",
    ])
    res = extract_query_strings(src)
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ\n\tТаблица.Поле\nИЗ\n\tСправочник.Тест КАК Таблица"
    assert res[0].line_start == 2


def test_two_queries_numbered_in_order():
    src = 'А = "ВЫБРАТЬ Поле1";\nБ = "ВЫБРАТЬ Поле2";'
    res = extract_query_strings(src)
    assert [q.text for q in res] == ["ВЫБРАТЬ Поле1", "ВЫБРАТЬ Поле2"]
    assert [q.line_start for q in res] == [1, 2]


def test_ignores_non_query_literal():
    assert extract_query_strings('Сообщить("Привет");') == []


def test_unescapes_doubled_quotes():
    res = extract_query_strings('Т = "ВЫБРАТЬ ""abc"" КАК Поле";')
    assert len(res) == 1
    assert res[0].text == 'ВЫБРАТЬ "abc" КАК Поле'


def test_ignores_keyword_in_comment():
    src = '// ВЫБРАТЬ это не запрос "ВЫБРАТЬ Поле"\nХ = 1;'
    assert extract_query_strings(src) == []


def test_recognizes_destroy_case_insensitive():
    res = extract_query_strings('Т = "уничтОжить Справочник.Тест";')
    assert len(res) == 1
    assert res[0].text == "уничтОжить Справочник.Тест"


def test_ignores_date_single_quotes():
    res = extract_query_strings("Д = '20240101'; Т = \"ВЫБРАТЬ 1\";")
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ 1"


def test_unescape_basic_entities():
    assert unescape_xml_entities("a &lt; b &gt; c &amp; d") == "a < b > c & d"


def test_unescape_quot_apos():
    assert unescape_xml_entities("&quot;x&quot; &apos;y&apos;") == "\"x\" 'y'"


def test_unescape_left_to_right_priority():
    assert unescape_xml_entities("&amp;lt;") == "&lt;"


def test_unescape_numeric_dec_and_hex():
    assert unescape_xml_entities("&#1041;&#x42E;") == "БЮ"


def test_unescape_bad_codepoint_kept():
    assert unescape_xml_entities("&#x110000;") == "&#x110000;"


def test_xml_single_query_decoded():
    xml = "<dataSet><query>ВЫБРАТЬ Т.Поле\nГДЕ Т.А &lt;&gt; &amp;П</query></dataSet>"
    res = extract_queries_from_xml(xml)
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ Т.Поле\nГДЕ Т.А <> &П"


def test_xml_multiple_queries_line_start():
    xml = "\n".join([
        "<schema>",
        "  <query>ВЫБРАТЬ Поле1</query>",
        "  <other>x</other>",
        "  <query>ВЫБРАТЬ Поле2</query>",
        "</schema>",
    ])
    res = extract_queries_from_xml(xml)
    assert [q.text for q in res] == ["ВЫБРАТЬ Поле1", "ВЫБРАТЬ Поле2"]
    assert [q.line_start for q in res] == [2, 4]


def test_xml_ignores_non_query():
    assert extract_queries_from_xml("<query>не запрос</query>") == []
