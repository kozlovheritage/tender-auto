from tendercore.rfq.queue import is_blank, validate_entry, validate_queue


def test_blank_sentinels():
    assert is_blank("—")
    assert is_blank("-")
    assert is_blank("информация отсутствует")
    assert is_blank("")
    assert is_blank(None)
    assert is_blank("0")
    assert not is_blank("3751680.04")
    assert not is_blank("07.09.2026")


def test_validate_entry_ok():
    entry = {
        "tender_number": "32616335374",
        "tender_subject": "Поставка шнекороторного снегоочистителя",
        "tender_deadline": "07.09.2026",
        "tender_price": "6616666.67",
        "tender_url": "https://zakupki.gov.ru/x",
        "items_table": [{"item": "Снегоочиститель SR-2500", "part_number": "SR-2500"}],
    }
    assert validate_entry(entry) == []


def test_validate_entry_missing():
    entry = {
        "tender_number": "32616335895",
        "tender_subject": "Поставка компьютерного оборудования",
        "tender_deadline": "—",
        "tender_price": "0",
        "tender_url": "",
    }
    problems = validate_entry(entry)
    assert any("tender_deadline" in p for p in problems)
    assert any("tender_price" in p for p in problems)
    assert any("tender_url" in p for p in problems)
    assert any("items_table" in p for p in problems)


def test_validate_queue_split():
    payload = {"tenders": [
        {"tender_number": "1", "tender_subject": "S", "tender_deadline": "01.01.2026",
         "tender_price": "100", "tender_url": "https://x",
         "items_table": [{"item": "Товар", "part_number": "A1"}]},
        {"tender_number": "2", "tender_subject": "—", "tender_deadline": "01.01.2026",
         "tender_price": "100", "tender_url": "https://x",
         "items_table": [{"item": "Товар"}]},
    ]}
    valid, invalid = validate_queue(payload)
    assert len(valid) == 1 and len(invalid) == 1