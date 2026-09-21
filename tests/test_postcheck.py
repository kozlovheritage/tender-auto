from tendercore.analysis.postcheck import (
    validate_delivery_term, find_cyrillic_models, find_real_gost,
    check_volume, pp1875_to_clarify, check_generic,
)


def test_term_business_days_converted():
    days, reason = validate_delivery_term("Срок поставки: 15 рабочих дней")
    assert days == 21
    assert "менее 30" in reason


def test_term_calendar_ok():
    days, reason = validate_delivery_term("Срок поставки: 45 календарных дней")
    assert days == 45 and reason is None


def test_term_missing():
    assert validate_delivery_term("Срок поставки: информация отсутствует") == (None, None)
    assert validate_delivery_term("Срок поставки: до 31.08.2026") == (None, None)


def test_cyr_models_from_log():
    found = find_cyrillic_models("оборудование ЖРО-1, ДЭ-226, ООО «Ромашка»")
    assert "ЖРО-1" in found and "ДЭ-226" in found


def test_gost_real_vs_material():
    resp = "- Критичные требования ТЗ -\nсоответствие ГОСТ Р 53987-2010\n- Прочее -"
    assert find_real_gost(resp)
    resp2 = "- Критичные требования ТЗ -\nГОСТ на топливо\n- Прочее -"
    assert find_real_gost(resp2) is None


def test_volume_cap():
    assert check_volume("Количество позиций: 151")
    assert check_volume("Количество позиций: 4") is None


def test_pp1875_matrix():
    assert pp1875_to_clarify("применяется ПП 1875", False, "participate")
    assert not pp1875_to_clarify("применяется ПП 1875", True, "participate")
    assert not pp1875_to_clarify("применяется ПП 1875", False, "not_participate")


def test_generic():
    assert check_generic(False, set(), False)
    assert check_generic(True, set(), False) is None
    assert check_generic(False, {"Grundfos"}, False) is None