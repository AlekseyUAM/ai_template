# Тесты проверки имён метаданных на зарезервированные системные имена.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_metadata_names


def test_reserved_metadata_name_flagged(tmp_path):
    path = tmp_path / "Catalog.xml"
    path.write_text(
        "<MetaDataObject><Name>ВидДвиженияНакопления</Name></MetaDataObject>\n",
        encoding="utf-8")
    findings = check_metadata_names.scan([str(tmp_path)])
    assert any(item["name"] == "ВидДвиженияНакопления" for item in findings)


def test_reserved_value_set_metadata_name_flagged(tmp_path):
    path = tmp_path / "Attribute.xml"
    path.write_text(
        "<MetaDataObject><Name>WebЦвета</Name></MetaDataObject>\n",
        encoding="utf-8")
    findings = check_metadata_names.scan([str(tmp_path)])
    assert any(item["name"] == "WebЦвета" for item in findings)


def test_normal_metadata_name_not_flagged(tmp_path):
    path = tmp_path / "Catalog.xml"
    path.write_text(
        "<MetaDataObject><Name>Организации</Name></MetaDataObject>\n",
        encoding="utf-8")
    assert check_metadata_names.scan([str(tmp_path)]) == []
