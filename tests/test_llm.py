from tendercore.llm import (
    LLMConfig, analyze_response_completeness, call_llm, classify_response,
    clean_response_preamble, extract_china_flag, extract_rejection_reason,
    postprocess_response,
)


def test_classify_participate():
    assert classify_response("Решение: участвуем\n--- Основная информация ---\nЗаказчик: Х") == "participate"


def test_classify_not_participate():
    assert classify_response("Решение: не участвуем. Причина: насосы в спецификации") == "not_participate"


def test_classify_clarify():
    assert classify_response("Решение: требуется уточнение") == "clarify"


def test_classify_self_contradiction_to_clarify():
    resp = "Решение: не участвуем. Причина: ограничение не является стоп-фактором"
    assert classify_response(resp) == "clarify"


def test_classify_participate_overridden_by_stopfactor():
    resp = "Решение: участвуем\n...\nСтоп-фактор #6 срабатывает: насосы"
    assert classify_response(resp) == "not_participate"


def test_china_flag():
    assert extract_china_flag("--- Доступность закупки в Китае: Да ---") is True
    assert extract_china_flag("--- Доступность закупки в Китае: Нет ---") is False


def test_clean_preamble_removes_think():
    resp = "<think>думаю</think>\nРешение: участвуем\n--- Основная информация ---\nЗаказчик: Х"
    clean = clean_response_preamble(resp)
    assert "<think>" not in clean and clean.startswith("Решение:")


def test_clean_preamble_keeps_last_report():
    resp = ("Решение: не участвуем. Причина: черновик\n--- Основная информация ---\nстарое\n"
            "Решение: участвуем\n--- Основная информация ---\nновое")
    clean = clean_response_preamble(resp)
    assert clean.startswith("Решение: участвуем")
    assert "новое" in clean and "старое" not in clean


def test_postprocess_nds_and_term():
    resp = "НДС: включён (22%)\nСрок поставки: информация отсутствует в документации"
    hints = "Подсказка из файлов: возможный срок поставки: 45."
    out = postprocess_response(resp, hints)
    assert "20%" in out and "22%" not in out
    assert "Срок поставки: 45 дней" in out


def test_postprocess_replaces_phrase():
    out = postprocess_response("Производитель: не удалось определить", "")
    assert "информация отсутствует в документации" in out


def test_rejection_reason():
    assert "насосы" in extract_rejection_reason("Решение: не участвуем. Причина: насосы")


def test_completeness_missing_fields():
    resp = "\n--- Основная информация ---\nЗаказчик: Х\nСрок поставки: 30 дней\n"
    missing = analyze_response_completeness(resp)
    assert "Адрес поставки" in missing and "НМЦК/НМЦД" in missing
    assert "Заказчик" not in missing


def test_call_llm_no_keys_returns_none():
    assert call_llm("test", LLMConfig()) is None