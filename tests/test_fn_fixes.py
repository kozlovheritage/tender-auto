from tendercore.analysis.postcheck import run_post_validations

_HEADER = """Решение: участвуем
--- Основная информация ---
Заказчик: Тестовый заказчик
Предмет закупки: Тестовый предмет
Количество позиций: 1
НМЦК/НМЦД: 1 000 000 руб.
Адрес поставки: г. Москва, ул. Тестовая, 1
Срок поставки: 45 календарных дней
"""

RESP_PUMP = _HEADER + """--- Что нужно поставить ---
| № | Наименование | Артикул | Ед. изм. | Кол-во |
| --- | --- | --- | --- | --- |
| 1 | Насос центробежный | AB-100 | шт | 1 |
"""

RESP_PUMP_PARTS = _HEADER + """--- Что нужно поставить ---
| № | Наименование | Артикул | Ед. изм. | Кол-во |
| --- | --- | --- | --- | --- |
| 1 | Запчасти для насоса | AB-100 | шт | 1 |
"""

def test_pump_rejected():
    # Самостоятельный насос в спецификации → стоп-фактор #6
    assert run_post_validations(RESP_PUMP, "participate") == "not_participate"

def test_pump_parts_allowed():
    # Запчасти к насосу → НЕ стоп-фактор (фикс Б)
    assert run_post_validations(RESP_PUMP_PARTS, "participate") == "participate"