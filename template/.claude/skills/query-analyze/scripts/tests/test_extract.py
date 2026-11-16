import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_queries import (
    extract_query_strings,
    extract_queries_from_xml,
    unescape_xml_entities,
)
from extract_queries import main


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


def test_main_fails_on_invalid_utf8(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_bytes(b"\xff\xfe")
    assert main(["-Path", str(path)]) == 2
    err = capsys.readouterr().err
    assert "ВНИМАНИЕ" in err
    assert "не удалось прочитать как UTF-8" in err


def test_main_invalid_utf8_skipped_but_others_extracted(tmp_path, capsys):
    bad = tmp_path / "Bad.bsl"
    bad.write_bytes(b"\xff\xfe")
    good = tmp_path / "Good.bsl"
    good.write_text('\tЗапрос.Текст = "ВЫБРАТЬ 1";\n', encoding="utf-8")
    assert main(["-Path", str(tmp_path)]) == 2
    out = capsys.readouterr()
    assert f"ВНИМАНИЕ: {bad}: не удалось прочитать как UTF-8" in out.err
    assert "ВЫБРАТЬ 1" in out.out
    assert main(["-Path", str(tmp_path), "-NoFail"]) == 0


def test_main_no_fail_suppresses_loud_exit(tmp_path, capsys):
    path = tmp_path / "Module.bsl"
    path.write_text(
        'Процедура Тест()\n\tЗапрос.Текст = "не запрос";\nКонецПроцедуры\n',
        encoding="utf-8",
    )
    assert main(["-Path", str(path), "-NoFail"]) == 0
    assert "извлечено 0 запросов" in capsys.readouterr().err
