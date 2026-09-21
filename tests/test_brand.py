"""Юнит-тесты для brand.py на реальных кейсах из логов."""
from tendercore.analysis.brand import (
    is_brand_trusted,
    is_non_brand,
    extract_brand_b1_from_table,
    extract_brand_b3_from_filenames,
    extract_brand,
)


def test_is_brand_trusted():
    assert is_brand_trusted("Mitsubishi") is True
    assert is_brand_trusted("TP-Link") is True
    assert is_brand_trusted("FakeBrand") is False
    assert is_brand_trusted("") is False


def test_is_non_brand_stoplist():
    """Тест стоп-листа: III, zip, Total, модели без OEM."""
    assert is_non_brand("III") is True
    assert is_non_brand("IV") is True
    assert is_non_brand("zip") is True
    assert is_non_brand("rar") is True
    assert is_non_brand("Total") is True
    assert is_non_brand("Insert") is True
    assert is_non_brand("SR-2500") is True  # модель снегоочистителя
    assert is_non_brand("EAP225") is True  # модель TP-Link
    assert is_non_brand("Mitsubishi") is False  # это бренд


def test_is_non_brand_filenames():
    """Тест: Части документации не должны майниться как бренды."""
    assert is_non_brand("Часть_I") is True
    assert is_non_brand("Часть_II") is True
    assert is_non_brand("Часть_III") is True
    assert is_non_brand("Part_IV") is True
    assert is_non_brand("Section_V") is True


def test_extract_brand_b1_from_table():
    """B1: бренд из таблицы позиций."""
    table = """
    № | Наименование | Производитель | Кол-во
    1 | Кондиционер  | Mitsubishi Electric | 10
    """
    assert extract_brand_b1_from_table(table) == "Mitsubishi Electric"
    
    table2 = "Производитель: Daikin Industries"
    assert extract_brand_b1_from_table(table2) == "Daikin Industries"
    
    # Стоп-лист: Total не должен майниться
    table3 = "Производитель: Total"
    assert extract_brand_b1_from_table(table3) is None


def test_extract_brand_b3_from_filenames():
    """B3: бренд из имён файлов (без расширений и частей)."""
    # Нормальный кейс
    files = ["Техническое_задание_Mitsubishi.docx", "Проект_договора.pdf"]
    assert extract_brand_b3_from_filenames(files) == "Mitsubishi"
    
    # Кейс из лога 31.08: Часть_III не должен майниться
    files2 = [
        "Часть_III_Техническая_часть.docx",
        "Часть_I_Извещение.docx",
        "Часть_II_Проект_договора.docx",
    ]
    assert extract_brand_b3_from_filenames(files2) is None
    
    # Кейс из лога: zip не должен майниться
    files3 = ["2._Документация.zip", "ТЗ.docx"]
    # zip отсекается, но ТЗ не содержит бренд в верхнем регистре
    assert extract_brand_b3_from_filenames(files3) is None
    
    # Нормальный кейс: TP-Link
    files4 = ["Спецификация_TP-Link.docx"]
    assert extract_brand_b3_from_filenames(files4) == "TP-Link"


def test_extract_brand_priority():
    """Приоритет B1→B2→B3→B4."""
    subject = "Поставка оборудования Daikin"
    filenames = ["ТЗ_Mitsubishi.docx"]
    table = "Производитель: Toshiba"
    doc_text = "Производитель: Panasonic"
    
    # B1 (таблица) имеет высший приоритет
    brand, source = extract_brand(subject, filenames, table, doc_text)
    assert brand == "Toshiba"
    assert source == "b1"
    
    # Без таблицы — B2 (тема)
    brand2, source2 = extract_brand(subject, filenames, "", doc_text)
    assert brand2 == "Daikin"
    assert source2 == "b2"
    
    # Без темы — B3 (файлы)
    brand3, source3 = extract_brand("", filenames, "", doc_text)
    assert brand3 == "Mitsubishi"
    assert source3 == "b3"