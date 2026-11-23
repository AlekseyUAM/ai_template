# Tests for check_event_handlers.py and the event_handlers.json snapshot.
import importlib.util
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_event_handlers as ceh

INDEX = ceh.EventIndex(ceh.load_data())


def findings(text, key):
    return ceh.analyze_text(text, key, INDEX)


def codes(text, key):
    return [finding.code for finding in findings(text, key)]


# ── canonical declarations ───────────────────────────────────

def test_canonical_document_handlers_pass():
    text = (
        "Процедура ПередЗаписью(Отказ, РежимЗаписи, РежимПроведения)\n"
        "КонецПроцедуры\n"
        "Процедура ПриЗаписи(Отказ)\n"
        "КонецПроцедуры\n"
        "Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
        "КонецПроцедуры\n"
        "Процедура ОбработкаПроверкиЗаполнения(Отказ, ПроверяемыеРеквизиты)\n"
        "КонецПроцедуры\n"
    )
    assert findings(text, "Document.ObjectModule") == []


def test_catalog_before_write_one_param_pass():
    text = "Процедура ПередЗаписью(Отказ)\nКонецПроцедуры\n"
    assert findings(text, "Catalog.ObjectModule") == []


def test_unknown_custom_procedure_ignored():
    text = "Процедура МояСлужебнаяПроцедура(А, Б)\nКонецПроцедуры\n"
    assert findings(text, "Document.ObjectModule") == []


# ── wrong signature: extra / missing / renamed ───────────────

def test_bad_posting_export_and_extra_params():
    text = ("Процедура ОбработкаПроведения(ОтменитьПроведение, Параметр, "
            "ВыполняетсяЛица) Экспорт\nКонецПроцедуры\n")
    result = findings(text, "Document.ObjectModule")
    assert [f.code for f in result] == ["event-handler-exported",
                                        "event-handler-params"]
    params = next(f for f in result if f.code == "event-handler-params")
    assert params.severity == "error"
    assert "Процедура ОбработкаПроведения(Отказ, РежимПроведения)" in params.message
    assert "Procedure Posting(Cancel, PostingMode)" in params.message


def test_required_trailing_param_omitted_is_error():
    # ПередЗаписью документа: (Отказ [необяз.], РежимЗаписи, РежимПроведения)
    text = "Процедура ПередЗаписью(Отказ)\nКонецПроцедуры\n"
    result = findings(text, "Document.ObjectModule")
    assert [f.code for f in result] == ["event-handler-params"]
    assert "Процедура ПередЗаписью(Отказ, РежимЗаписи, РежимПроведения)" in result[0].message


def test_optional_trailing_param_may_be_omitted():
    # ПередНачаломРаботыСистемы: единственный параметр Отказ необязателен.
    text = "Процедура ПередНачаломРаботыСистемы()\nКонецПроцедуры\n"
    assert findings(text, "Configuration.ManagedApplicationModule") == []


def test_renamed_param_is_info_with_signature():
    text = "Процедура ОбработкаПроведения(Отказ, Режим)\nКонецПроцедуры\n"
    result = findings(text, "Document.ObjectModule")
    assert [f.code for f in result] == ["event-handler-param-name"]
    assert result[0].severity == "info"
    assert "РежимПроведения" in result[0].message
    assert "Процедура ОбработкаПроведения(Отказ, РежимПроведения)" in result[0].message


def test_report_compose_result_four_params_allowed():
    text = ("Процедура ПриКомпоновкеРезультата(ДокументРезультат, "
            "ДанныеРасшифровки, СтандартнаяОбработка, АдресХранилища)\n"
            "КонецПроцедуры\n")
    assert findings(text, "Report.ObjectModule") == []


def test_report_compose_result_renamed_details_allowed():
    text = ("Процедура ПриКомпоновкеРезультата(ДокументРезультат, "
            "ДанныеРасшифровкиОбъект, СтандартнаяОбработка, АдресХранилища)\n"
            "КонецПроцедуры\n")
    assert findings(text, "Report.ObjectModule") == []


def test_catalog_document_style_before_write_is_error():
    # РежимПроведения — параметр документа; для справочника это дефект.
    text = ("Процедура ПередЗаписью(Отказ, РежимЗаписи, РежимПроведения)\n"
            "КонецПроцедуры\n")
    result = findings(text, "Catalog.ObjectModule")
    assert [f.code for f in result] == ["event-handler-params"]
    assert result[0].severity == "error"
    assert "Процедура ПередЗаписью(Отказ)" in result[0].message


def test_english_handler_names_accepted():
    text = "Procedure Posting(Cancel, PostingMode)\nEndProcedure\n"
    assert findings(text, "Document.ObjectModule") == []


# ── view of the module ──────────────────────────────────────

def test_event_of_another_module_is_warning():
    text = ("Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
            "КонецПроцедуры\n")
    result = findings(text, "Catalog.ObjectModule")
    assert [f.code for f in result] == ["event-handler-wrong-module"]
    assert "Модуль объекта (Документ)" in result[0].message
    assert "Процедура ОбработкаПроведения(Отказ, РежимПроведения)" in result[0].message


def test_exported_foreign_event_not_flagged_as_wrong_module():
    text = ("Процедура ОбработкаПроведения(Отказ, РежимПроведения) Экспорт\n"
            "КонецПроцедуры\n")
    assert findings(text, "Catalog.ObjectModule") == []


def test_common_module_does_not_report_wrong_module():
    text = ("Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
            "КонецПроцедуры\n")
    assert findings(text, "CommonModule.Module") == []


def test_application_modules_do_not_cross_report():
    text = ("Процедура ОбработкаПолученияФормыВыбораПользователей"
            "СистемыВзаимодействия(А, Б, В, Г, Д, Е)\nКонецПроцедуры\n")
    assert findings(text, "Configuration.OrdinaryApplicationModule") == []


# ── path inference ──────────────────────────────────────────

def test_infer_document_object_module_windows_path():
    assert ceh.infer_module_key(
        r"D:\p\src\cf\Documents\Заказ\Ext\ObjectModule.bsl"
    )[:2] == ("Document.ObjectModule", "Заказ")


def test_infer_catalog_manager_module():
    assert ceh.infer_module_key(
        "/p/src/cf/Catalogs/Товары/Ext/ManagerModule.bsl"
    )[:2] == ("Catalog.ManagerModule", "Товары")


def test_infer_information_register_record_set():
    assert ceh.infer_module_key(
        "/p/src/cf/InformationRegisters/Курсы/Ext/RecordSetModule.bsl"
    )[:2] == ("InformationRegister.RecordSetModule", "Курсы")


def test_infer_common_module():
    assert ceh.infer_module_key(
        "/p/src/cf/CommonModules/Общий/Ext/Module.bsl"
    )[:2] == ("CommonModule.Module", "Общий")


def test_infer_object_command_module():
    assert ceh.infer_module_key(
        "/p/src/cf/Catalogs/Товары/Commands/Открыть/Ext/CommandModule.bsl"
    )[:2] == ("Command.CommandModule", "Товары")


def test_infer_application_module():
    assert ceh.infer_module_key(
        "/p/src/cf/Ext/ManagedApplicationModule.bsl"
    )[:2] == ("Configuration.ManagedApplicationModule", None)


def test_infer_external_processor_module():
    assert ceh.infer_module_key(
        "/p/src/epf/Обработка/Ext/ObjectModule.bsl"
    )[:2] == ("ExternalDataProcessor.ObjectModule", "Обработка")


def test_form_module_is_skipped():
    key, _obj, reason = ceh.infer_module_key(
        "/p/src/cf/Catalogs/Товары/Forms/Форма/Ext/Form/Module.bsl")
    assert key is None
    assert "формы" in reason


def test_unknown_path_requires_explicit_type():
    key, _obj, reason = ceh.infer_module_key("/p/tmp/документ.txt")
    assert key is None
    assert "не определяется" in reason


# ── snapshot consistency ────────────────────────────────────

def test_snapshot_document_posting_contract():
    event = INDEX.modules["Document.ObjectModule"]["events"]["ОбработкаПроведения"]
    signature = event["signatures"][0]
    assert signature["params_ru"] == ["Отказ", "РежимПроведения"]
    assert signature["params_en"] == ["Cancel", "PostingMode"]
    assert signature["optional"] == [True, False]


def test_snapshot_report_compose_result_has_bsp_overload():
    event = INDEX.modules["Report.ObjectModule"]["events"]["ПриКомпоновкеРезультата"]
    names = [sig["params_ru"] for sig in event["signatures"]]
    assert ["ДокументРезультат", "ДанныеРасшифровки", "СтандартнаяОбработка",
            "АдресХранилища"] in names
    assert ["ДокументРезультат", "ДанныеРасшифровкиОбъект", "СтандартнаяОбработка",
            "АдресХранилища"] in names


def test_snapshot_signatures_have_optional_flags():
    for key, mod in INDEX.modules.items():
        if mod.get("handler_name_arbitrary"):
            continue
        assert mod.get("events"), key
        for name, event in mod["events"].items():
            assert name
            assert event.get("signatures"), (key, name)
            for signature in event["signatures"]:
                total = len(signature.get("params_ru")
                            or signature.get("params_en") or [])
                assert len(signature.get("optional") or []) == total, (key, name)


# ── CLI ─────────────────────────────────────────────────────

def test_cli_module_type_override(tmp_path, capsys):
    module = tmp_path / "документ.txt"
    module.write_text(
        "Процедура ОбработкаПроведения(Отказ, Параметр, Лишний) Экспорт\n"
        "КонецПроцедуры\n", encoding="utf-8")
    rc = ceh.main(["--module-type", "Document.ObjectModule", str(module)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "event-handler-params" in out
    assert "Процедура ОбработкаПроведения(Отказ, РежимПроведения)" in out


def test_cli_infers_type_from_path(tmp_path, capsys):
    ext = tmp_path / "src" / "cf" / "Documents" / "Заказ" / "Ext"
    ext.mkdir(parents=True)
    module = ext / "ObjectModule.bsl"
    module.write_text(
        "Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
        "КонецПроцедуры\n", encoding="utf-8")
    rc = ceh.main(["-Detailed", str(module)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Document.ObjectModule" in out
    assert "Заказ" in out


def test_cli_stdin_requires_module_type(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        "Процедура ОбработкаПроведения(Отказ, РежимПроведения)\n"
        "КонецПроцедуры\n"))
    rc = ceh.main(["--module-type", "Document.ObjectModule", "-"])
    assert rc == 0
    assert "Нарушений не найдено" in capsys.readouterr().out


def test_cli_list_module_types(capsys):
    rc = ceh.main(["--list-module-types"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Document.ObjectModule" in out
    assert "Catalog.ObjectModule" in out


# ── generator helper ────────────────────────────────────────

def _load_generator():
    path = (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "tools", "update_event_handlers.py"))
    spec = importlib.util.spec_from_file_location("update_event_handlers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_marks_optional_parameters():
    gen = _load_generator()
    html_text = (
        '<p class="V8SH_chapter">Параметры:</p>'
        '<div class="V8SH_rubric"> <p>&lt;Отказ&gt;</div>Тип: Булево. '
        'Значение по умолчанию: Ложь.'
        '<div class="V8SH_rubric"> <p>&lt;Режим&gt;</div>Тип: Строка.'
        '<p class="V8SH_chapter">Описание:</p>'
    )
    assert gen.params_info(html_text) == [("Отказ", True), ("Режим", False)]
