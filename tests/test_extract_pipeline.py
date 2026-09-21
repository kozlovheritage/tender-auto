from tendercore.extract.sections import extract_relevant_sections
from tendercore.extract.hints import extract_hints_from_text
from tendercore.extract.pipeline import extract_texts_from_paths


def test_sections_short_passthrough():
    assert extract_relevant_sections("короткий текст", first_chars=100) == "короткий текст"


def test_sections_finds_deep_keyword():
    text = "X" * 100 + "мусор " * 20 + "здесь срок поставки: 30 календарных дней"
    out = extract_relevant_sections(text, first_chars=50, cap=5000)
    assert "срок поставки" in out
    assert out.startswith(text[:50])


def test_hints_term_business():
    h = extract_hints_from_text("Срок поставки: 7 рабочих дней с даты заключения")
    assert "возможный срок поставки: 10" in h and "переведено из 7 рабочих" in h


def test_hints_nmck():
    assert "2798400" in extract_hints_from_text("НМЦК: 2 798 400 руб.")


def test_hints_qty():
    assert "количество позиций = 7" in extract_hints_from_text("Количество позиций: 7")


def test_pipeline_injection(tmp_path):
    (tmp_path / "a.txt").write_text("Поставка насосов Grundfos CR32", encoding="utf-8")
    (tmp_path / "b.txt").write_text("прочий текст без бренда", encoding="utf-8")
    scanner = lambda text, fn: "Grundfos" if "Grundfos" in text else None
    doc, crit, succ, errs, hints = extract_texts_from_paths(
        [str(tmp_path / "a.txt"), str(tmp_path / "b.txt")], brand_scanner=scanner)
    assert hints == ["Grundfos"] and "Grundfos" in doc
    assert set(succ) == {"a.txt", "b.txt"} and crit == []


def test_pipeline_critical_on_bad_docx(tmp_path):
    (tmp_path / "Техническое_задание.docx").write_bytes(b"not a docx")
    doc, crit, succ, errs, hints = extract_texts_from_paths([str(tmp_path / "Техническое_задание.docx")])
    assert not doc.strip()
    assert "Техническое_задание.docx" in crit