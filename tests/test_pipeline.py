from tendercore.models import Decision
from tendercore.pipeline import Deps, process_tender

RESP_OK = """Решение: участвуем
--- Основная информация ---
Заказчик: ООО Тест
Предмет закупки: Компрессор Grundfos
Количество позиций: 2
НМЦК/НМЦД: 3 000 000 руб.
Срок поставки: 45 календарных дней
--- Что нужно поставить ---
| № | Наименование | Артикул | Ед. | Кол-во |
| --- | --- | --- | --- | --- |
| 1 | Компрессор | CR32 | шт | 2 |
--- Производитель / бренд / страна ---
Grundfos
--- Критичные требования ТЗ ---
информация отсутствует в документации
--- Доступность закупки в Китае: Да ---
"""

ROW = {"Реестровый номер": "32616300000", "Дата окончания подачи заявок": "10.09.2026",
       "Название": "Поставка насоса", "Начальная цена": 3000000}


def _deps(tmp_path, llm=RESP_OK, download_ret=([], False, False, False), calls=None):
    calls = calls if calls is not None else {}

    def download(reg, row):
        calls["download"] = True
        return download_ret

    def report(r, d, resp, sup):
        calls["report"] = True
        return str(tmp_path / f"{r}.docx")

    return Deps(download=download, llm=lambda p: llm,
                search=lambda s, b, c: "Поставщик 1 — X", report=report), calls


def test_precheck_shortcut(tmp_path):
    row = dict(ROW, Название="Поставка подшипников")
    deps, calls = _deps(tmp_path)
    res = process_tender(row, deps)
    assert res.decision == Decision.NOT_PARTICIPATE
    assert "download" not in calls


def test_network_error(tmp_path):
    deps, _ = _deps(tmp_path, download_ret=([], False, False, True))
    res = process_tender(ROW, deps)
    assert res.decision == Decision.NETWORK_ERROR


def test_happy_path(tmp_path):
    (tmp_path / "a.txt").write_text("Срок поставки: 45 дней. Компрессор Grundfos CR32.",
                                    encoding="utf-8")
    deps, calls = _deps(tmp_path, download_ret=([str(tmp_path / "a.txt")], False, False, False))
    res = process_tender(ROW, deps)
    assert res.decision == Decision.PARTICIPATE
    assert res.china_flag is True
    assert res.suppliers_found is True
    assert calls.get("report")


def test_term_override(tmp_path):
    bad = RESP_OK.replace("45 календарных дней", "10 календарных дней")
    (tmp_path / "a.txt").write_text("текст", encoding="utf-8")
    deps, _ = _deps(tmp_path, llm=bad,
                    download_ret=([str(tmp_path / "a.txt")], False, False, False))
    res = process_tender(ROW, deps)
    assert res.decision == Decision.NOT_PARTICIPATE