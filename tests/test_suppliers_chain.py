from tendercore.suppliers.chain import (
    clean_raw_email, clean_subject_for_search, decode_cfemail,
    extract_company_name, format_suppliers_for_docx, get_country_from_url,
    inject_emails_into_suppliers_text, parse_results_to_suppliers,
    select_rfq_emails,
)


def test_clean_subject_noise():
    r = clean_subject_for_search("Поставка насоса для нужд МУП")
    assert "муп" not in r.lower() and "поставка" not in r.lower()


def test_clean_subject_bigram():
    assert clean_subject_for_search("токарный станок") == "lathe machine"


def test_country_from_url():
    assert get_country_from_url("https://example.de/x") == "Германия"
    assert get_country_from_url("https://site.co.uk/") == "Великобритания"
    assert get_country_from_url("https://site.com/") is None


def test_extract_company_name():
    assert extract_company_name("Transcon Electronic Systems | Official Website", "u") \
        == "Transcon Electronic Systems"


def test_decode_cfemail():
    assert decode_cfemail("026360") == "ab"
    assert decode_cfemail("zz") is None


def test_clean_raw_email():
    assert clean_raw_email("u003einfo@site.com") == "info@site.com"
    assert clean_raw_email("%20sales@site.com") == "sales@site.com"
    assert clean_raw_email("not-an-email") is None


def test_select_rfq_emails():
    sel, rej = select_rfq_emails(
        ["sales@x.com", "hr@x.com", "info@x.com", "export@x.com", "boss@x.com"])
    assert set(sel) == {"sales@x.com", "export@x.com"}
    rej_emails = {e for e, _ in rej}
    assert "hr@x.com" in rej_emails and "boss@x.com" in rej_emails


def test_inject_emails():
    text = "Поставщик 1 — Transcon Electronic Systems (Чехия)"
    out = inject_emails_into_suppliers_text(text, {"info@transcon.cz"})
    assert "E-mail для поставщика 1 — info@transcon.cz" in out


def test_parse_results_filters_junk():
    res = [("Пр", [
        {"title": "Transcon Electronic Systems", "link": "https://transcon.cz/",
         "snippet": "Czech maker"},
        {"title": "wikipedia pump", "link": "https://en.wikipedia.org/wiki/Pump",
         "snippet": ""},
    ])]
    sup = parse_results_to_suppliers(res)
    assert len(sup) == 1 and sup[0]["country"] == "Чехия"


def test_format_suppliers():
    out = format_suppliers_for_docx(
        [{"name": "X", "country": "Китай", "host": "x.cn"}], {"a@b.de"})
    assert "1. X — Китай" in out and "a@b.de" in out