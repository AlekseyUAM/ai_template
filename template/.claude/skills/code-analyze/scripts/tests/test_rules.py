# Тесты автоматических правил code-analyze.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rules


def codes(text):
    ctx = rules.ModuleContext(text)
    return [f.code for f in rules.run_all(ctx)]


def findings(text):
    ctx = rules.ModuleContext(text)
    return rules.run_all(ctx)


# ── string-concat-in-loop ────────────────────────────────────

def test_concat_in_loop_flagged():
    text = (
        "Для НомерКолонки = 1 По 10 Цикл\n"
        "    ИзвлеченныйТекст = ИзвлеченныйТекст + Символы.ПС + ТекстОбласти;\n"
        "КонецЦикла;\n"
    )
    assert "string-concat-in-loop" in codes(text)


def test_concat_correct_strsoedinit_not_flagged():
    text = (
        "ИзвлеченныеТексты = Новый Массив;\n"
        "Для НомерКолонки = 1 По 10 Цикл\n"
        "    ИзвлеченныеТексты.Добавить(ТекстОбласти);\n"
        "КонецЦикла;\n"
        "ИзвлеченныйТекст = СтрСоединить(ИзвлеченныеТексты, Символы.ПС);\n"
    )
    assert "string-concat-in-loop" not in codes(text)


def test_concat_outside_loop_not_flagged():
    text = "ИтогТекст = ИтогТекст + \"a\";\n"
    assert "string-concat-in-loop" not in codes(text)


def test_concat_reassign_without_self_not_flagged():
    # «Текст = Другая + Ещё» — аккумулятора нет (нет Текст справа)
    text = (
        "Пока Усл Цикл\n"
        "    Текст = Левое + Правое;\n"
        "КонецЦикла;\n"
    )
    assert "string-concat-in-loop" not in codes(text)


# ── tv-find-multiple-columns ──────────────────────────────────

def test_find_multiple_columns_flagged():
    text = 'Результат = ТЗ.Найти("найдется все", "Колонка1, Колонка2");\n'
    assert "tv-find-multiple-columns" in codes(text)


def test_find_single_column_not_flagged():
    text = 'Результат = ТЗ.Найти("значение", "Колонка1");\n'
    assert "tv-find-multiple-columns" not in codes(text)


def test_find_without_columns_not_flagged():
    text = 'Результат = Список.Найти(Значение);\n'
    assert "tv-find-multiple-columns" not in codes(text)


# ── var-name-starts-with-underscore ───────────────────────────

def test_var_underscore_flagged():
    text = "Перем _Служебная;\n"
    assert "var-name-starts-with-underscore" in codes(text)


def test_param_underscore_flagged():
    text = "Процедура П(_Параметр)\nКонецПроцедуры\n"
    assert "var-name-starts-with-underscore" in codes(text)


def test_normal_name_not_flagged():
    text = "Перем КоличествоПачекВКоробке;\n"
    assert "var-name-starts-with-underscore" not in codes(text)
    assert "var-name-single-char" not in codes(text)


# ── var-name-single-char ──────────────────────────────────────

def test_single_char_var_flagged():
    text = "Перем А;\n"
    assert "var-name-single-char" in codes(text)


def test_single_char_loop_counter_not_flagged():
    text = (
        "Процедура П()\n"
        "    Для Сч = 1 По 10 Цикл\n"
        "        А = Сч;\n"
        "    КонецЦикла;\n"
        "КонецПроцедуры\n"
    )
    # Сч — счётчик цикла (не Перем, не параметр) → не флагуется
    assert "var-name-single-char" not in codes(text)


def test_single_char_param_flagged():
    text = "Функция Ф(X)\n Возврат X;\nКонецФункции\n"
    assert "var-name-single-char" in codes(text)


# ── raise-in-cancel-event ─────────────────────────────────────

def test_raise_in_cancel_event_flagged():
    text = (
        "Процедура ПередЗаписью(Отказ)\n"
        "    Если Не Условие Тогда\n"
        "        ВызватьИсключение \"Нельзя\";\n"
        "    КонецЕсли;\n"
        "КонецПроцедуры\n"
    )
    assert "raise-in-cancel-event" in codes(text)


def test_raise_without_cancel_param_not_flagged():
    text = (
        "Процедура Проверить(Значение)\n"
        "    ВызватьИсключение \"Нельзя\";\n"
        "КонецПроцедуры\n"
    )
    assert "raise-in-cancel-event" not in codes(text)


def test_cancel_event_without_raise_not_flagged():
    text = (
        "Процедура ПередЗаписью(Отказ)\n"
        "    Отказ = Истина;\n"
        "КонецПроцедуры\n"
    )
    assert "raise-in-cancel-event" not in codes(text)


# ── error-description-without-stack ───────────────────────────

def test_error_description_flagged():
    text = "ТекстОшибки = ОписаниеОшибки();\n"
    assert "error-description-without-stack" in codes(text)


def test_detailed_error_presentation_not_flagged():
    text = "Текст = ОбработкаОшибок.ПодробноеПредставлениеОшибки(ИнформацияОбОшибке());\n"
    assert "error-description-without-stack" not in codes(text)


# ── type-check-via-metadata-name ──────────────────────────────

def test_type_check_via_metadata_name_flagged():
    text = 'Если Ссылка.Метаданные().Имя = "ПоступлениеТоваровУслуг" Тогда\nКонецЕсли;\n'
    assert "type-check-via-metadata-name" in codes(text)


def test_type_check_via_metadata_name_neq_flagged():
    text = 'Если Ссылка.Метаданные().Имя <> "Документ" Тогда\nКонецЕсли;\n'
    assert "type-check-via-metadata-name" in codes(text)


def test_metadata_name_without_compare_not_flagged():
    text = "ИмяОбъекта = Ссылка.Метаданные().Имя;\n"
    assert "type-check-via-metadata-name" not in codes(text)


def test_typeof_comparison_not_flagged():
    text = 'Если ТипЗнч(Ссылка) = Тип("ДокументСсылка.ПоступлениеТоваровУслуг") Тогда\nКонецЕсли;\n'
    assert "type-check-via-metadata-name" not in codes(text)


# ── column-copy-loop ──────────────────────────────────────────

def test_column_copy_loop_flagged():
    text = (
        "Для каждого СтрокаИсточника Из ТаблицаИсточник Цикл\n"
        "    СтрокаПриёмника = ТаблицаПриёмник.Добавить();\n"
        "    Для каждого Колонка Из ТаблицаПриёмник.Колонки Цикл\n"
        "        СтрокаПриёмника[Колонка.Имя] = СтрокаИсточника[Колонка.Имя];\n"
        "    КонецЦикла;\n"
        "КонецЦикла;\n"
    )
    assert "column-copy-loop" in codes(text)


def test_fill_property_values_not_flagged():
    text = (
        "Для каждого СтрокаИсточника Из ТаблицаИсточник Цикл\n"
        "    СтрокаПриёмника = ТаблицаПриёмник.Добавить();\n"
        "    ЗаполнитьЗначенияСвойств(СтрокаПриёмника, СтрокаИсточника);\n"
        "КонецЦикла;\n"
    )
    assert "column-copy-loop" not in codes(text)


def test_columns_loop_read_only_not_flagged():
    text = (
        "Для каждого Колонка Из Таблица.Колонки Цикл\n"
        "    Сообщить(Колонка.Имя);\n"
        "КонецЦикла;\n"
    )
    assert "column-copy-loop" not in codes(text)


# ── char-code-literal ─────────────────────────────────────────

def test_char_code_literal_flagged():
    text = "Разделитель = Символ(10);\n"
    assert "char-code-literal" in codes(text)


def test_char_code_tab_flagged():
    text = "Т = Символ(9);\n"
    fs = [f for f in findings(text) if f.code == "char-code-literal"]
    assert fs and "Таб" in fs[0].message


def test_char_code_variable_not_flagged():
    text = "С = Символ(КодСимвола);\n"
    assert "char-code-literal" not in codes(text)


def test_char_code_unknown_code_not_flagged():
    text = "С = Символ(1);\n"
    assert "char-code-literal" not in codes(text)


def test_symbols_set_not_flagged():
    text = "Разделитель = Символы.ПС;\n"
    assert "char-code-literal" not in codes(text)


# ── attachable-handler-prefix ─────────────────────────────────

def test_attachable_handler_without_prefix_flagged():
    text = 'Элемент.УстановитьДействие("ПриИзменении", "ПолеПриИзменении");\n'
    assert "attachable-handler-prefix" in codes(text)


def test_attachable_handler_with_prefix_not_flagged():
    text = 'Элемент.УстановитьДействие("ПриИзменении", "Подключаемый_ПолеПриИзменении");\n'
    assert "attachable-handler-prefix" not in codes(text)


def test_attachable_handler_empty_not_flagged():
    text = 'Элемент.УстановитьДействие("ПриИзменении", "");\n'
    assert "attachable-handler-prefix" not in codes(text)


# ── record-manager-in-loop ────────────────────────────────────

def test_record_manager_in_loop_flagged():
    text = (
        "Для каждого Строка Из Таблица Цикл\n"
        "    Менеджер = РегистрыСведений.Права.СоздатьМенеджерЗаписи();\n"
        "    Менеджер.Записать();\n"
        "КонецЦикла;\n"
    )
    assert "record-manager-in-loop" in codes(text)


def test_record_manager_outside_loop_not_flagged():
    text = "Менеджер = РегистрыСведений.Права.СоздатьМенеджерЗаписи();\n"
    assert "record-manager-in-loop" not in codes(text)


# ── new-applied-object-via-constructor ────────────────────────

def test_new_document_object_flagged():
    text = 'Док = Новый("ДокументОбъект.ПоступлениеТоваровУслуг");\n'
    assert "new-applied-object-via-constructor" in codes(text)


def test_new_record_set_flagged():
    text = 'Набор = Новый("РегистрСведенийНаборЗаписей.Цены");\n'
    assert "new-applied-object-via-constructor" in codes(text)


def test_create_document_via_manager_not_flagged():
    text = "Док = Документы.ПоступлениеТоваровУслуг.СоздатьДокумент();\n"
    assert "new-applied-object-via-constructor" not in codes(text)


def test_new_structure_not_flagged():
    text = 'С = Новый Структура("а", 1);\n'
    assert "new-applied-object-via-constructor" not in codes(text)


def test_new_array_not_flagged():
    text = 'М = Новый("Массив");\n'
    assert "new-applied-object-via-constructor" not in codes(text)


# ── explicit-write-in-posting ─────────────────────────────────

def test_explicit_write_in_posting_flagged():
    text = (
        "Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
        "    Движения.Остатки.Записать();\n"
        "КонецПроцедуры\n"
    )
    assert "explicit-write-in-posting" in codes(text)


def test_write_outside_posting_not_flagged():
    text = (
        "Процедура ЗаписатьДанные()\n"
        "    Набор.Записать();\n"
        "КонецПроцедуры\n"
    )
    assert "explicit-write-in-posting" not in codes(text)


# ── record-set-in-loop ────────────────────────────────────────

def test_record_set_in_loop_flagged():
    text = (
        "Для каждого Значение Из Настройки Цикл\n"
        "    Набор = РегистрыСведений.Настройки.СоздатьНаборЗаписей();\n"
        "    Набор.Записать();\n"
        "КонецЦикла;\n"
    )
    assert "record-set-in-loop" in codes(text)


def test_record_set_outside_loop_not_flagged():
    text = (
        "Набор = РегистрыСведений.Настройки.СоздатьНаборЗаписей();\n"
        "Для каждого Значение Из Настройки Цикл\n"
        "    НоваяЗапись = Набор.Добавить();\n"
        "КонецЦикла;\n"
        "Набор.Записать();\n"
    )
    assert "record-set-in-loop" not in codes(text)


# ── sequence-boundary-in-posting ──────────────────────────────

def test_sequence_boundary_in_posting_flagged():
    text = (
        "Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
        "    Последовательности.ПартионныйУчет.УстановитьГраницу(МоментВремени());\n"
        "КонецПроцедуры\n"
    )
    assert "sequence-boundary-in-posting" in codes(text)


def test_sequence_boundary_outside_posting_not_flagged():
    text = (
        "Процедура Регламент()\n"
        "    Последовательности.ПартионныйУчет.УстановитьГраницу(МоментВремени());\n"
        "КонецПроцедуры\n"
    )
    assert "sequence-boundary-in-posting" not in codes(text)


# ── общая проверка серьёзности и позиции ──────────────────────

def test_finding_has_line():
    text = (
        "Строка1\n"
        "Перем _Плохая;\n"
    )
    fs = [f for f in findings(text) if f.code == "var-name-starts-with-underscore"]
    assert fs and fs[0].line == 2
