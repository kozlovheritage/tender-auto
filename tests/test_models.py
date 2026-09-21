from tendercore.models import Decision, TenderResult


def test_defaults():
    r = TenderResult(reg_number="32616306952")
    assert r.decision is Decision.ERROR
    assert r.missing_fields == []
    assert r.label == "Ошибка"


def test_label_mapping():
    r = TenderResult(reg_number="1", decision=Decision.PARTICIPATE)
    assert r.label == "Участвуем"