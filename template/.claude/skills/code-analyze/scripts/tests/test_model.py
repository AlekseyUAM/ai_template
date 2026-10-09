# Тесты структурной модели модуля BSL.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsl_model


def test_tokenize_strings_and_comments():
    text = 'А = "строка // не комментарий"; // хвост\n'
    toks = bsl_model.tokenize(text)
    kinds = [(t.kind, t.value) for t in toks]
    assert ("string", "строка // не комментарий") in kinds
    assert any(k == "comment" for k, _ in kinds)


def test_tokenize_doubled_quote():
    text = 'Б = "он сказал ""да""";'
    toks = bsl_model.tokenize(text)
    strs = [t.value for t in toks if t.kind == "string"]
    assert strs == ['он сказал "да"']


def test_sanitize_preserves_length_and_lines():
    text = 'А = "xx"; // c\nБ = 1;'
    san = bsl_model.sanitize(text)
    assert len(san) == len(text)
    assert san.count("\n") == text.count("\n")
    assert '"' not in san and "//" not in san
    assert "Б = 1;" in san


def test_method_detection_and_export():
    text = (
        "&НаСервере\n"
        "Процедура Тест(Параметр1, Знач Параметр2) Экспорт\n"
        "    Возврат;\n"
        "КонецПроцедуры\n"
    )
    m = bsl_model.Module(text)
    assert len(m.methods) == 1
    meth = m.methods[0]
    assert meth.name == "Тест"
    assert meth.is_export is True
    assert meth.directive == "НаСервере"
    assert meth.params == ["Параметр1", "Параметр2"]
    assert meth.kind == "procedure"


def test_function_detection():
    text = "Функция Ф() \n Возврат 1; \nКонецФункции\n"
    m = bsl_model.Module(text)
    assert m.methods[0].kind == "function"
    assert m.methods[0].is_export is False


def test_loop_body_and_nesting():
    text = (
        "Процедура П()\n"
        "    Для Сч = 1 По 10 Цикл\n"
        "        А = Сч;\n"
        "    КонецЦикла;\n"
        "КонецПроцедуры\n"
    )
    m = bsl_model.Module(text)
    assert len(m.loops) == 1
    loop = m.loops[0]
    assert loop.loop_var == "Сч"
    assert m.is_in_loop(3) is True       # строка «А = Сч;»
    assert m.is_in_loop(5) is False      # КонецПроцедуры


def test_for_each_loop_var():
    text = "Для Каждого Элемент Из Коллекция Цикл\n КонецЦикла;\n"
    m = bsl_model.Module(text)
    assert m.loops[0].loop_var == "Элемент"


def test_var_declarations():
    text = "Перem = 0;\nПерем ПеременнаяА, _Плохая Экспорт;\n"
    # намеренно: первая строка — НЕ объявление (ловушка на «Перem» латиницей)
    m = bsl_model.Module(text)
    names = [n for n, _l, _e in m.var_declarations]
    assert "ПеременнаяА" in names
    assert "_Плохая" in names


def test_method_at_line():
    text = (
        "Процедура Первая()\n КонецПроцедуры\n"
        "Процедура Вторая()\n Б = 1;\n КонецПроцедуры\n"
    )
    m = bsl_model.Module(text)
    assert m.method_at(4).name == "Вторая"
    assert m.method_at(1).name == "Первая"
