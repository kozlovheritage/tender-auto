from tendercore.analysis.precheck import check_title


def test_russian_it_brand():
    assert "стоп-фактор #12" in check_title("Поставка компьютеров Байкал-М")
    assert "стоп-фактор #12" in check_title("Серверы Эльбрус-8С")


def test_consumer_goods():
    assert "стоп-фактор #14" in check_title("Поставка сковород и кастрюль")


def test_works_services():
    assert "стоп-фактор #11" in check_title("Выполнение работ по монтажу вентиляции")
    assert "стоп-фактор #11" in check_title("Оказание услуг по охране объекта")


def test_clean_title_passes():
    assert check_title("Поставка токарных станков") is None
    assert check_title("Поставка насосного оборудования Grundfos") is None